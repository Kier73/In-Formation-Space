"""SFI-002: infer an executable non-affine Boolean interpreter from CNF alone.

Every extracted instruction is an *observed local Boolean function*, not a
predeclared AND/OR/MUX opcode. An independently checked exact clause partition
and a cycle-free dependency graph preserve ALL source assignments.

The construction searches finite local supports (<=4 variables). It does not
claim optimal synthesis, efficient general SAT, or independently authenticated
host execution. Failure of a finite budget is UNKNOWN, never UNSAT.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from time import perf_counter

SCHEMA = 'sfi.problem-formed-boolean-interpreter.v2'
SEGMENT = 'sfi.nonaffine-partition-result.v1'
MAX_VARIABLES = 256
MAX_CLAUSES = 30000
MAX_SUPPORT = 4
MAX_PARTITIONS = 128


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def digest(data):
    return sha256(canonical(data)).hexdigest()


def normalize(clauses, n):
    if type(n) is not int or not 1 <= n <= MAX_VARIABLES or not isinstance(clauses, (list, tuple)) or len(clauses)>MAX_CLAUSES:
        raise ValueError('source exceeds finite input contract')
    normalized=set()
    for raw in clauses:
        if not isinstance(raw,(list,tuple)) or len(raw)>MAX_VARIABLES:
            raise ValueError('invalid source clause')
        if any(type(l) is not int or l==0 or abs(l)>n for l in raw):
            raise ValueError('invalid source literal')
        unique=set(raw)
        if not any(-l in unique for l in unique):
            normalized.add(tuple(sorted(unique,key=lambda x:(abs(x),x<0))))
    return sorted(normalized,key=lambda c:(len(c),c))


def _sat_clause(clause, bits):
    return any(bool((bits >> (abs(l)-1)) & 1)==(l>0) for l in clause)


def _local_table(target, inputs, clauses, ledger):
    """Learn a truth table iff every input admits exactly one target value."""
    table=[]
    for values in range(1 << len(inputs)):
        allowed=[]
        for bit in (0,1):
            assignment=(bit << (target-1))
            for j,variable in enumerate(inputs):
                assignment |= ((values>>j)&1) << (variable-1)
            ledger['local_literal_scans'] += sum(len(c) for c in clauses)
            if all(_sat_clause(c,assignment) for c in clauses):
                allowed.append(bit)
        if len(allowed)!=1:
            return None
        table.append(allowed[0])
    return table


def discover(clauses, n, *, max_candidates=4000):
    """Find exact local functional clause blocks; no declared gate library."""
    supports={frozenset(abs(l) for l in clause) for clause in clauses
              if 1 <= len(clause) <= MAX_SUPPORT}
    # Every anchor's support is proposed independently, and no function is
    # inferred unless *all* local input coordinates have a unique output.
    # Minimal CNF encodings of arbitrary functions (such as a 3-input
    # multiplexer) need not contain a full-support clause. The union of two
    # overlapping clause supports can reveal the actual four-variable scope.
    # Keep this bounded and charge candidate discovery to the ledger.
    family=[frozenset(abs(l) for l in clause) for clause in clauses
            if 1<=len(clause)<=MAX_SUPPORT]
    pair_attempts=0
    for i,left in enumerate(family):
        for right in family[i+1:]:
            if not left.isdisjoint(right):
                pair_attempts+=1
                joined=left|right
                if len(joined)<=MAX_SUPPORT:supports.add(joined)
    ledger={'support_attempts':0,'paired_supports_scanned':pair_attempts,'local_literal_scans':0,'candidates':0,'cutoff':False}
    candidates=[]
    for support in sorted(supports,key=lambda x:(-len(x),tuple(sorted(x)))):
        if not support or len(support)>MAX_SUPPORT: continue
        for output in sorted(support,reverse=True):
            if ledger['support_attempts']>=max_candidates:
                ledger['cutoff']=True
                break
            ledger['support_attempts']+=1
            selected=[c for c in clauses if output in map(abs,c) and
                      {abs(l) for l in c}.issubset(support)]
            if not selected: continue
            inputs=tuple(sorted(support-{output}))
            # Gate must actually depend on the whole proposed support; otherwise
            # the same subgate would be counted repeatedly in larger contexts.
            table=_local_table(output,inputs,selected,ledger)
            if table is None:continue
            essential=all(any(table[v] != table[v ^ (1 << j)]
                              for v in range(1 << len(inputs)))
                          for j in range(len(inputs)))
            if not essential:continue
            candidates.append({'output':output,'inputs':list(inputs),'table':table,
                               'clauses':[list(c) for c in selected]})
        if ledger['cutoff']: break
    ledger['candidates']=len(candidates)
    return candidates,ledger


def _topological(instructions):
    pending={x['output']:x for x in instructions}
    ordered=[];resolved=set()
    while pending:
        possible=[v for v,g in pending.items() if all(u not in pending for u in g['inputs'])]
        if not possible:return None
        for variable in sorted(possible):
            ordered.append(pending.pop(variable))
            resolved.add(variable)
    return ordered


def compile_ground(clauses, n, *, max_candidates=4000):
    t0=perf_counter()
    source=normalize(clauses,n)
    candidates,ledger=discover(source,n,max_candidates=max_candidates)
    used=set();outputs=set();chosen=[]
    # Broadest supported relations first; a tie is resolved by the exact
    # source variable IDs. Not asserted globally optimal or canonical across
    # renamings. A candidate must consume as-yet-unused clauses.
    candidates.sort(key=lambda g:(-len(g['clauses']),-len(g['inputs']),-g['output'],g['inputs']))
    for gate in candidates:
        block={tuple(c) for c in gate['clauses']}
        if gate['output'] in outputs or not block.isdisjoint(used):continue
        if _topological(chosen+[gate]) is None:continue
        chosen.append(gate)
        used.update(block)
        outputs.add(gate['output'])
    ordered=_topological(chosen)
    assert ordered is not None
    free=[v for v in range(1,n+1) if v not in outputs]
    ground={'schema':SCHEMA,'n':n,'source_clauses':[list(c) for c in source],
            'instructions':ordered,'residual':[list(c) for c in source if c not in used],
            'registers':free,
            'scope':'exact finite local functional rewrite; no source-independent execution claim'}
    ground['digest']=digest(ground)
    ledger.update({'source_clauses':len(source),'instructions':len(ordered),
                   'covered_clauses':len(used),'residual_clauses':len(ground['residual']),
                   'original_bits':n,'register_bits':len(free),
                   'construction_ms':round((perf_counter()-t0)*1000,3)})
    return ground,ledger


def decode(ground,z):
    registers=ground['registers']
    if type(z) is not int or z<0 or z >= 1 << len(registers):
        raise ValueError('invalid generated interpreter coordinate')
    bits=0
    for j,v in enumerate(registers):bits |= ((z>>j)&1) << (v-1)
    for gate in ground['instructions']:
        index=sum(((bits>>(v-1))&1)<<j for j,v in enumerate(gate['inputs']))
        bits |= gate['table'][index] << (gate['output']-1)
    return bits


def execute_partition(ground, index, *, intent='COUNT', budget=1<<16,
                      partition_size=1024):
    """Execute actual generated instructions + original CNF observation."""
    if intent not in ('SAT','COUNT') or type(budget) is not int or budget<0 or \
       type(index) is not int or index<0 or type(partition_size) is not int or partition_size<=0:
        raise ValueError('invalid execution intention or resource bound')
    d=len(ground['registers']);total=1 << d
    partitions=(total+partition_size-1)//partition_size
    if partitions>MAX_PARTITIONS or total>budget:
        raise ValueError('exact search not admitted under finite budget')
    if index>=partitions:raise ValueError('invalid partition coordinate')
    start=index*partition_size;stop=min(start+partition_size,total)
    checked=0;count=0;witness=None
    for z in range(start,stop):
        bits=decode(ground,z)
        checked+=1
        if all(_sat_clause(c,bits) for c in ground['source_clauses']):
            count+=1
            if witness is None:witness=bits
            if intent=='SAT':break
    output={'schema':SEGMENT,'ground':ground['digest'],'intent':intent,
            'index':index,'start':start,'stop':stop,'checked':checked,
            'models':count,'witness_decimal':str(witness) if witness is not None else None}
    output['digest']=digest(output)
    return output


def execute(ground, *, intent='COUNT', max_coordinates=1<<16,
            partition_size=1024):
    """Result is UNKNOWN if the complete coordinate search is not admitted.

    An early SAT witness is valid; UNSAT/COUNT require every coordinate checked.
    """
    if ground.get('digest')!=digest({k:v for k,v in ground.items() if k!='digest'}):
        raise ValueError('ground digest changed')
    d=len(ground['registers']);total=1<<d
    if total>max_coordinates or (total+partition_size-1)//partition_size>MAX_PARTITIONS:
        return {'status':'UNKNOWN','models':None,'witness_decimal':None,
                'checked':0,'free_bits':d,'reason':'finite coordinate budget'}
    count=0;checked=0;results=[];witness=None
    for p in range((total+partition_size-1)//partition_size):
        receipt=execute_partition(ground,p,intent=intent,budget=max_coordinates,
                                  partition_size=partition_size)
        results.append(receipt)
        checked+=receipt['checked'];count+=receipt['models']
        if receipt['witness_decimal'] is not None and witness is None:
            witness=receipt['witness_decimal']
        if intent=='SAT' and witness is not None:break
    return {'status':'SAT' if witness is not None else 'UNSAT',
            'models':count if intent=='COUNT' else None,'witness_decimal':witness,
            'checked':checked,'free_bits':d,'partitions_executed':len(results),
            'partition_receipts':results}


def clause_forbidden(variables,values):
    return tuple((-v if (values>>i)&1 else v) for i,v in enumerate(variables))


def encode_function(output,inputs,table,*,compact=False):
    """A generator for experiments only: source compiler never sees this table."""
    if output in inputs or len(set((output,*inputs)))!=1+len(inputs) or \
       len(table)!=(1<<len(inputs)):
        raise ValueError('invalid fixture function')
    if not compact:
        return [clause_forbidden((output,*inputs),((1-b)&1)|(i<<1))
                for i,b in enumerate(table)]
    # Exact truth-table CNF can be shortened by local consensus until fixed.
    clauses=set(encode_function(output,inputs,table,compact=False))
    changed=True
    while changed:
        changed=False
        for clause in sorted(clauses,key=lambda c:(len(c),c)):
            for lit in clause:
                opposite=tuple(x if x!=lit else -x for x in clause)
                if opposite in clauses:
                    shortened=tuple(x for x in clause if x!=lit)
                    clauses.discard(clause);clauses.discard(opposite);clauses.add(shortened)
                    changed=True;break
            if changed:break
    return sorted(clauses,key=lambda c:(len(c),c))


def seeded_circuit(seed=17,*,source_bits=8,gates=48,mixed=True):
    """Deterministic non-affine DAG fixture; only CNF is supplied to compiler."""
    import random
    rng=random.Random(seed)
    clauses=[];truth=[]
    # Every gate is a non-affine function, with arbitrary 2/3-input truth
    # tables, including mixed input-size and dependency graph topology.
    for j in range(gates):
        target=source_bits+j+1
        k=3 if j%5==0 else 2
        # Ensure each gate has at least one independent/previously defined
        # input, with diverse paths that do not depend on unique op names.
        universe=list(range(1,target))
        inputs=tuple(sorted(rng.sample(universe,k)))
        if k==2:
            func=rng.choice(['and','or','nand','neq'])
            table=[{'and':lambda a,b:a&b,'or':lambda a,b:a|b,
                    'nand':lambda a,b:1-(a&b),'neq':lambda a,b:a^b}[func]
                    (i&1,(i>>1)&1) for i in range(4)]
        else:
            func=rng.choice(['majority','mux'])
            table=[int(sum((i>>q)&1 for q in range(3))>=2) if func=='majority'
                    else ((i>>1)&1 if (i&1) else (i>>2)&1) for i in range(8)]
        clauses.extend(encode_function(target,inputs,table,compact=True))
        truth.append((target,inputs,table))
    if mixed:
        # Residual CNF on independent inputs; at least one solution is retained
        # only for some seeds, never asserted without source checking.
        for _ in range(3):
            picks=sorted(rng.sample(range(1,source_bits+1),3))
            clauses.append(tuple(v if rng.randrange(2) else -v for v in picks))
    return clauses,source_bits+gates,truth
