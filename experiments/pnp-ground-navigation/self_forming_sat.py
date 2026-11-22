"""SFI-001: construct an exact finite Boolean interpreter from CNF evidence.

The generator specializes its registers, affine decoder, original-source clause
observer, partition topology, and result reducer for the given intention.
It never treats the precomputed PNG-003 answer as the executed result.  The
PNG-003 producer does perform work (including solving) during construction;
that cost must be charged separately. Standard library only.
"""
from __future__ import annotations

from hashlib import sha256
import json
from time import perf_counter

from algebraic_ground import eliminate, decode
from derived_verifier import verify_receipt

SCHEMA='sfi.sat.problem-formed-interpreter.v1'
MAX_SOURCE=4_000_000
MAX_PARTS=128


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()


def digest(value):
    return sha256(canonical(value)).hexdigest()


def _require(value,why):
    if not value: raise ValueError(why)


def form(receipt, *, intention='SAT', maximum_free=16,
         partition_size=1024, verifier_free=16):
    """Independently verify a supplied source-ground proof before forming.

    If no feasible complete search under bounds: outcome=UNDETERMINED, not UNSAT.
    """
    start=perf_counter()
    _require(intention in ('SAT','#SAT'),'Unknown observer intention')
    _require(type(maximum_free) is int and 0 <= maximum_free <= 20 and
             type(partition_size) is int and 1 <= partition_size <= 65_536,
             'Invalid finite execution budgets')
    _require(len(canonical(receipt)) <= MAX_SOURCE,'Source-ground proof exceeds bounded envelope')
    audit=verify_receipt(receipt,max_enumerated_free=verifier_free)
    _require(audit['source_rewrite_verified'] and audit['resolution_verified'] and
             audit['exact_source_equivalence_verified'], 'Not an exact proven source-ground')
    n=receipt['n']
    equations=receipt['ground']['equations']
    system=eliminate(equations,n)
    contradiction=system['contradiction'] is not None or bool(receipt['resolution_empty'])
    free=system['free'] if not contradiction else None
    d=len(free) if free is not None else None
    if contradiction:
        mode='refutation'
        partitions=[]
    elif d>maximum_free or (1 << d)+partition_size-1>partition_size*MAX_PARTS:
        mode='undetermined'
        partitions=[]
    else:
        mode='constructed-search'
        partitions=[{'index':i,'start':s,'stop':min(1<<d,s+partition_size)}
                    for i,s in enumerate(range(0,1<<d,partition_size))]
    program={
        'schema':SCHEMA,'intention':intention,
        'budgets':{'maximum_free':maximum_free,'partition_size':partition_size,'maximum_partitions':MAX_PARTS},
        'source_sha256':receipt['source_sha256'],
        'ground_sha256':receipt['ground_sha256'],
        'source_variables':n,
        'source_clauses':receipt['original_clauses'],
        'source_relation':{'equations':equations, 'decoder':system['decoder']},
        'free_dimension':d,
        'mode':mode,'partitions':partitions,
        'operator_graph':([{'op':'xor-parity', 'register':i+1,
                            'constant':const, 'mask':mask}
                           for i,(const,mask) in enumerate(system['decoder'])]
                          +[{'op':'or-literals','index':i,'literals':clause}
                            for i,clause in enumerate(receipt['original_clauses'])]
                          +[{'op':'and-all'},
                            {'op':'stop-on-witness' if intention=='SAT' else 'accumulate-count'}])
                          if mode=='constructed-search' else [],
        'proof_verified':True,
        'evidence_scope':'exact synthetic source CNF; proof independently replayed; no authority',
    }
    program['digest']=digest(program)
    stats={'proof_steps':len(receipt['resolution_steps'])+len(receipt['contract_steps']),
           'construction_elapsed_ms':round((perf_counter()-start)*1000,3),
           'source_ground_compilation_elapsed_ms':receipt['compilation_ledger']['elapsed_ms'],
           'original_vars':n,'generated_registers':d,
           'generated_gates':len(program['operator_graph']),
           'generated_hosts':len(partitions),
           'total_coordinate_capacity':None if d is None else 1<<d}
    return program,stats


def verify_program(program, receipt):
    """Reconstruct exactly from the source proof rather than trusting checksum.

    Ignore timing and original resource settings, which are not part of the
    identity of the constructed microarchitecture.
    """
    _require(program.get('schema')==SCHEMA and
             program.get('digest')==digest({k:v for k,v in program.items() if k!='digest'}),
             'Malformed or modified interpreter')
    limits=program['budgets']
    _require(type(limits) is dict and limits.get('maximum_partitions')==MAX_PARTS,
             'Invalid architecture limits')
    built,_=form(receipt,intention=program['intention'],
                 maximum_free=limits['maximum_free'],
                 partition_size=limits['partition_size'])
    _require(built==program,'Interpreter does not reconstruct from source proof')
    return True


def _satisfies(clauses,assignment):
    return all(any(assignment[abs(l)-1]==(l>0) for l in clause) for clause in clauses)


def execute_partition(program, part_index):
    """Direct exact SAT evaluation on source CNF, not on precomputed result.

    All source bits are realized from the induced free-coordinate register.
    The clause predicate is independently applied to *original* CNF clauses.
    """
    _require(program['mode']=='constructed-search','No admitted executable search')
    _require(type(part_index) is int and 0<=part_index<len(program['partitions']),
             'Invalid partition index')
    part=program['partitions'][part_index]
    decoder=program['source_relation']['decoder']
    checked=0;models=0;witness=None;first_z=None
    for z in range(part['start'],part['stop']):
        assignment=[const ^ ((mask&z).bit_count()&1) for const,mask in decoder]
        checked+=1
        if _satisfies(program['source_clauses'],assignment):
            models+=1
            if witness is None:
                witness=assignment;first_z=z
            if program['intention']=='SAT':break
    body={'schema':'sfi.sat.segment-result.v1','interpreter':program['digest'],
          'part_index':part_index,'start':part['start'],'stop':part['stop'],
          'evaluated':checked,'models':models,'witness':witness,
          'first_coordinate':first_z}
    body['sha256']=digest(body)
    return body


def check_segment(program,result):
    """Independently reexecute source-observation semantics and check receipt."""
    _require(type(result) is dict and set(result)==
             {'schema','interpreter','part_index','start','stop','evaluated','models',
              'witness','first_coordinate','sha256'},'Malformed partition result')
    _require(result['sha256']==digest({k:v for k,v in result.items() if k!='sha256'}),
             'Partition result changed')
    _require(result==execute_partition(program,result['part_index']),
             'Partition result disagrees with original CNF')
    return True


def aggregate(program,results, *, source_receipt=None):
    """Decision/count only after full partition coverage, or proved refutation."""
    if program['mode']=='refutation':
        _require(source_receipt is not None,'Refutation requires source proof')
        _require(program['source_sha256']==source_receipt['source_sha256'],
                 'Refutation source identity changed')
        verify_program(program,source_receipt)
        return {'status':'UNSAT','count':0 if program['intention']=='#SAT' else None,
                'witness':None,'evaluated':0,'interpreter':program['digest'],
                'proof':'independently replayed PNG-003 algebraic/resolution refutation'}
    if program['mode']=='undetermined':
        _require(not results,'Undetermined state cannot fabricate a result')
        return {'status':'UNDETERMINED','count':None,'witness':None,
                'evaluated':0,'interpreter':program['digest']}
    _require(len(results)==len(program['partitions']),'Missing partitions')
    indexed={v['part_index']:v for v in results}
    _require(len(indexed)==len(results) and
             set(indexed)==set(range(len(program['partitions']))),
             'Duplicated or missing partition')
    for v in results:check_segment(program,v)
    found=next((v['witness'] for v in results if v['witness'] is not None),None)
    count=sum(v['models'] for v in results) if program['intention']=='#SAT' else None
    return {'status':'SAT' if found else 'UNSAT', 'count':count,
            'witness':found,'evaluated':sum(v['evaluated'] for v in results),
            'interpreter':program['digest']}
