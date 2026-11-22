"""Independent SFI-002 exact Boolean function interpreter checker.

This module does not import the producer, its clause normalizer, truth-table
learner, selection strategy, decoder, or partition evaluator. It checks every
extracted gate as an exact Boolean relation, the source clause partition and
acyclic dependency, then reproduces segment claims from original clauses.
"""
from __future__ import annotations
import hashlib
import json


def _hash(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',', ':'),
           ensure_ascii=True,allow_nan=False).encode('ascii')).hexdigest()


def _normal(clauses,n):
    if type(n) is not int or not 1<=n<=256 or type(clauses) is not list or len(clauses)>30000:
        raise ValueError('invalid bounded source')
    seen=set()
    for row in clauses:
        if type(row) is not list or len(row)>256 or any(type(x) is not int or x==0 or abs(x)>n for x in row):
            raise ValueError('invalid original source clause')
        if any(-x in row for x in row):
            raise ValueError('source is not normalized')
        c=tuple(sorted(set(row),key=lambda x:(abs(x),x<0)))
        if c!=tuple(row) or c in seen:
            raise ValueError('noncanonical source clause')
        seen.add(c)
    result=sorted(seen,key=lambda c:(len(c),c))
    if [list(r) for r in result]!=clauses: raise ValueError('nonnormalized clause order')
    return seen


def _literal(c,assignment):
    for lit in c:
        observed=(assignment >> (abs(lit)-1))&1
        if bool(observed)==(lit>0):return True
    return False


def verify(ground, *, max_free=20):
    if type(ground) is not dict or set(ground)!={'schema','n','source_clauses','instructions',
         'residual','registers','scope','digest'}:
        raise ValueError('invalid interpreter certificate')
    if ground['schema']!='sfi.problem-formed-boolean-interpreter.v2' or ground['digest']!=_hash({
          k:v for k,v in ground.items() if k!='digest'}):
        raise ValueError('source interpreter identity changed')
    n=ground['n'];source=_normal(ground['source_clauses'],n)
    if type(ground['instructions']) is not list or len(ground['instructions'])>n or \
       type(ground['registers']) is not list:
        raise ValueError('invalid generated computer layout')
    used=set();outputs=set();verified=[]
    for instruction in ground['instructions']:
        if type(instruction) is not dict or set(instruction)!={'output','inputs','table','clauses'}:
            raise ValueError('malformed generated gate')
        out=instruction['output'];inputs=instruction['inputs'];table=instruction['table']
        if type(out) is not int or not 1<=out<=n or out in outputs or \
           type(inputs) is not list or len(inputs)>3 or \
           any(type(v) is not int or not 1<=v<=n for v in inputs) or \
           inputs!=sorted(set(inputs)) or out in inputs or \
           type(table) is not list or len(table)!=(1<<len(inputs)) or \
           any(type(x) is not int or x not in (0,1) for x in table):
            raise ValueError('invalid finite function signature')
        # Declared order must already be executable: no forward dependency.
        if any(v in set(x['output'] for x in ground['instructions'])-outputs for v in inputs):
            raise ValueError('dependency cycle or non-topological order')
        if type(instruction['clauses']) is not list or not instruction['clauses']:
            raise ValueError('missing evidence clauses')
        block=set()
        for row in instruction['clauses']:
            if type(row) is not list or tuple(row) not in source or \
               tuple(row) in used or out not in (abs(z) for z in row) or \
               any(abs(z) not in (out,*inputs) for z in row):
                raise ValueError('unqualified claimed gate evidence')
            block.add(tuple(row))
        if len(block)!=len(instruction['clauses']):raise ValueError('duplicate evidence clause')
        # Exhaustive local truth-table reconstruction, with a *different*
        # truth-condition evaluator from the producer.
        for v in range(1<<len(inputs)):
            possible=[]
            for b in (0,1):
                state=sum(((v>>j)&1)<<(p-1) for j,p in enumerate(inputs))|(b<<(out-1))
                if all(_literal(row,state) for row in block): possible.append(b)
            if possible!=[table[v]]:
                raise ValueError('gate truth-table or source equivalence forged')
        used.update(block);outputs.add(out);verified.append(out)
    if ground['registers']!=[v for v in range(1,n+1) if v not in outputs]:
        raise ValueError('missing or fabricated interpreter state coordinates')
    rest=_normal(ground['residual'],n)
    if rest != source-used or rest&used:
        raise ValueError('source rewrite lost, duplicated, or invented clauses')
    if len(ground['registers'])>max_free:
        return {'proven':True,'complete_search_admitted':False,
                'source_variables':n,'generated_registers':len(ground['registers']),
                'verified_gates':len(verified)}
    return {'proven':True,'complete_search_admitted':True,
            'source_variables':n,'generated_registers':len(ground['registers']),
            'verified_gates':len(verified)}


def _independent_decode(ground,z):
    state=sum(((z>>j)&1)<<(v-1) for j,v in enumerate(ground['registers']))
    for instruction in ground['instructions']:
        k=0
        for j,v in enumerate(instruction['inputs']):
            if state & (1<<(v-1)):k+=1<<j
        state|=instruction['table'][k]<<(instruction['output']-1)
    return state


def check_partition(ground,report,*,maximum=1<<16,partition_size=1024):
    if not verify(ground)['proven']:
        raise ValueError('unverified interpreter')
    if type(report) is not dict or set(report)!={'schema','ground','intent','index',
         'start','stop','checked','models','witness_decimal','digest'} or \
       report['digest']!=_hash({k:v for k,v in report.items() if k!='digest'}):
        raise ValueError('malformed computation receipt')
    if report['schema']!='sfi.nonaffine-partition-result.v1' or report['ground']!=ground['digest'] or \
       report['intent'] not in ('SAT','COUNT') or type(report['index']) is not int:
        raise ValueError('wrong semantic computation')
    total=1<<len(ground['registers'])
    if total>maximum or partition_size<1 or ((total+partition_size-1)//partition_size)>128:
        raise ValueError('coordinate budget does not admit proof replay')
    start=report['index']*partition_size;stop=min(total,start+partition_size)
    if report['index']<0 or start>=total or (report['start'],report['stop'])!=(start,stop):
        raise ValueError('partition epoch or coordinates changed')
    found=None;count=0;checked=0
    for z in range(start,stop):
        assignment=_independent_decode(ground,z)
        checked+=1
        if all(_literal(clause,assignment) for clause in ground['source_clauses']):
            count+=1
            if found is None:found=str(assignment)
            if report['intent']=='SAT':break
    if (report['checked'],report['models'],report['witness_decimal'])!=(checked,count,found):
        raise ValueError('partition observation disagrees with source CNF')
    return True


def independent_count(ground,*,max_free=16):
    verify(ground,max_free=max_free)
    if len(ground['registers'])>max_free:raise ValueError('independent count exceeds budget')
    return sum(all(_literal(clause,_independent_decode(ground,z))
                   for clause in ground['source_clauses'])
               for z in range(1<<len(ground['registers'])))
