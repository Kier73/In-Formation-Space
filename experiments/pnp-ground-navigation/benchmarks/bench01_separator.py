"""BENCH-01G: source-qualified separator conditioning for direct 3-SAT.

A small set of observed Boolean variables is removed from the clause incidence
hypergraph. Every assignment to that cut is checked, and each residual source
is split into disjoint components solved using the original SFI-002 *verified*
heterogeneous interpreter. The independent verifier reconstructs the source
restriction and reruns SFI, including its proof and partition verifiers.

This is bounded exact cutset conditioning, an established SAT technique. It is
NOT a general polynomial-time algorithm, a physical E-CPU fabric, nor proof
that structural compression always wins over source DPLL/CDCL.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns
import json
import sys

# Same cross-directory import convention as BENCH-01; no duplicated compiler.
SOURCE_DIR=Path(__file__).resolve().parent.parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0,str(SOURCE_DIR))

from morphic_sat import normalize
from self_selecting_sat import choose_composite

SCHEMA = 'ifs.bench01.source-qualified-separator.v1'
MAX_VARS = 256


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _digest(obj):
    return sha256(_canonical(obj)).hexdigest()


def _source(clauses, n):
    if type(n) is not int or not 1 <= n <= MAX_VARS:
        raise ValueError('source variable bound exceeded')
    source = normalize(clauses, n)
    if any(len(c) > 3 for c in source):
        raise ValueError('BENCH-01G accepts only literal 3-CNF')
    return [list(c) for c in source]


def _parts(clauses, n, removed=()):
    """Hypergraph connectivity after removing the declared observed variables.

    This is a *structural proposal*, not a SAT outcome or a proof of count.
    """
    removed = set(removed)
    parent = list(range(n+1))
    def find(x):
        while x != parent[x]:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for c in clauses:
        ids = [abs(x) for x in c if abs(x) not in removed]
        for x in ids[1:]:
            a,b = find(ids[0]), find(x)
            if a != b:
                parent[max(a,b)] = min(a,b)
    groups={}
    for i in range(1,n+1):
        if i not in removed:
            groups.setdefault(find(i),[]).append(i)
    return sorted((tuple(v) for v in groups.values()),key=lambda g:g[0])


def select_separator(clauses,n, *, max_cut=1):
    """Choose a cut by original-source connectivity, without consulting SAT.

    Current practical admission deliberately covers one variable. Larger cuts
    require a separate fully cost-accounted search; silent exponential search
    is not an acceptable replacement for failed solver construction.
    """
    if type(max_cut) is not int or max_cut not in (0,1):
        raise ValueError('cut size budget must be zero or one')
    source=_source(clauses,n)
    if not max_cut or len(_parts(source,n))>1 or n<4 or [] in source:
        return []
    baseline=len(_parts(source,n))
    assert baseline==1
    eligible=[]
    for i in range(1,n+1):
        parts=_parts(source,n,(i,))
        if len(parts)>1:
            largest=max(map(len,parts))
            eligible.append((largest, -len(parts), i))
    return [min(eligible)[2]] if eligible else []


def _restrict(source,n,cut,bits):
    """Exact CNF restriction; returns one empty-clause contradiction or remapped CNF."""
    partial={v:(bits>>i)&1 for i,v in enumerate(cut)}
    variables=[v for v in range(1,n+1) if v not in partial]
    rename={v:j+1 for j,v in enumerate(variables)}
    reduced=[]
    for clause in source:
        if any(abs(l) in partial and partial[abs(l)]==int(l>0) for l in clause):
            continue
        remainder=[l for l in clause if abs(l) not in partial]
        if not remainder:
            return variables, [[]]
        reduced.append([rename[abs(l)] if l>0 else -rename[abs(l)] for l in remainder])
    return variables, _source(reduced,len(variables))


def _source_satisfied(source,witness):
    return all(any(witness[abs(l)-1]==int(l>0) for l in clause) for clause in source)


def _witness_from_components(components, variables, n, cut, bits):
    result=[None]*n
    for i,v in enumerate(cut):result[v-1]=(bits>>i)&1
    for component in components:
        local_vars=component['source_variables']
        outcome=component['local_result']
        w=outcome.get('witness')
        if type(w) is list:
            if len(w)!=len(local_vars) or any(type(x) is not int or x not in (0,1) for x in w):
                raise ValueError('malformed affine witness')
            vector=w
        elif type(w) is str and w.isascii() and w.isdecimal() and w==str(int(w)):
            value=int(w)
            if value>>len(local_vars):raise ValueError('witness exceeds component width')
            vector=[(value>>j)&1 for j in range(len(local_vars))]
        else:raise ValueError('SAT component omitted its source witness')
        for pos,val in zip(local_vars,vector):
            original=variables[pos-1]
            if result[original-1] is not None:raise ValueError('duplicate witness coordinate')
            result[original-1]=val
    if any(v is None for v in result):raise ValueError('incomplete source witness')
    return result


def _branch(source,n,cut,bits, *, maximum_coordinates,maximum_free,partition_size):
    variables,restricted=_restrict(source,n,cut,bits)
    if [] in restricted:
        return {'bits':bits,'status':'UNSAT','count':0,'witness':None,
                'reason':'source-verified empty clause', 'component_count':0,
                'components':[]}
    composite=choose_composite(restricted,len(variables),intention='#SAT',
        maximum_coordinates=maximum_coordinates,maximum_free=maximum_free,
        partition_size=partition_size)
    status=composite['status']
    count=composite['count'] if status!='UNKNOWN' else None
    witness=None
    if status=='SAT':
        witness=_witness_from_components(composite['components'],variables,n,cut,bits)
        if not _source_satisfied(source,witness):
            raise ValueError('composite witness does not satisfy original source')
    if status=='UNSAT' and count!=0:
        raise ValueError('incorrect zero model count')
    if status=='SAT' and (type(count) is not int or count<=0):
        raise ValueError('SAT component cannot have zero complete count')
    return {'bits':bits,'status':status,'count':count,'witness':witness,
        'component_count':composite['component_count'],
        'components':[{'source_variables':[variables[v-1] for v in p['source_variables']],
            'selected':p['selected'],'status':p['local_result']['status'],
            'registers':p['registers']} for p in composite['components']]}


def _aggregate(branches):
    if any(r['status']=='SAT' for r in branches):
        status='SAT';witness=next(r['witness'] for r in branches if r['status']=='SAT')
    elif all(r['status']=='UNSAT' for r in branches):
        status='UNSAT';witness=None
    else: status='UNKNOWN';witness=None
    count=sum(r['count'] for r in branches) if all(r['count'] is not None for r in branches) else None
    return status,count,witness


def run(clauses,n,*,max_cut=1,maximum_coordinates=65536,maximum_free=16,
        partition_size=1024):
    """Produce a complete or explicitly UNKNOWN, replayable bounded claim."""
    start=perf_counter_ns()
    if type(maximum_coordinates) is not int or not 1<=maximum_coordinates<=1<<20:
        raise ValueError('invalid source-coordinate budget')
    if type(maximum_free) is not int or not 0<=maximum_free<=20:
        raise ValueError('invalid free register budget')
    if type(partition_size) is not int or not 1<=partition_size<=65536:
        raise ValueError('invalid partition budget')
    source=_source(clauses,n)
    cut=select_separator(source,n,max_cut=max_cut)
    if not cut and len(_parts(source,n))==1:
        # For connected sources without a useful separator, do not perform
        # expensive self-formed construction under a false savings promise.
        result={'schema':SCHEMA,'source_sha256':_digest({'n':n,'clauses':source}),
            'n':n,'separator':[],'branches':[],'status':'UNKNOWN','count':None,
            'witness':None,'reason':'no qualified variable separator',
            'budget':{'max_cut':max_cut,'maximum_coordinates':maximum_coordinates,
                       'maximum_free':maximum_free,'partition_size':partition_size}}
    else:
        branches=[_branch(source,n,cut,bits,maximum_coordinates=maximum_coordinates,
                maximum_free=maximum_free,partition_size=partition_size)
                for bits in range(1<<len(cut))]
        status,count,witness=_aggregate(branches)
        result={'schema':SCHEMA,'source_sha256':_digest({'n':n,'clauses':source}),
            'n':n,'separator':cut,'branches':branches,'status':status,
            'count':count,'witness':witness,'reason':None,
            'budget':{'max_cut':max_cut,'maximum_coordinates':maximum_coordinates,
                       'maximum_free':maximum_free,'partition_size':partition_size}}
    result['elapsed_ms']=(perf_counter_ns()-start)/1e6
    result['digest']=_digest({k:v for k,v in result.items() if k!='digest'})
    return result


def _independent_restriction(source, n, cut, bits):
    """Verifier-only clause projection with a different literal/value encoding.

    Compare this source reconstruction with the producer's output before any
    SFI result is accepted. Original clauses are traversed as sets of signed
    integers, not using the producer's remapping implementation.
    """
    observed = {v: (bits >> i) & 1 for i, v in enumerate(cut)}
    surviving = [v for v in range(1, n+1) if v not in observed]
    lookup = {v: i+1 for i, v in enumerate(surviving)}
    rows = set()
    for row in source:
        remaining = []
        decided = False
        for lit in row:
            v = abs(lit)
            if v in observed:
                if (lit > 0) == bool(observed[v]):
                    decided = True
                    break
            else:
                remaining.append((1 if lit > 0 else -1) * lookup[v])
        if decided:
            continue
        if not remaining:
            return surviving, [[]]
        rows.add(tuple(sorted(remaining, key=lambda x: (abs(x), x < 0))))
    return surviving, [list(row) for row in sorted(rows, key=lambda c:(len(c),c))]


def _independent_component_scopes(clauses, n):
    """Verifier-only connectivity using graph exploration instead of DSU."""
    graph = {v: set() for v in range(1, n+1)}
    for row in clauses:
        vertices = set(abs(x) for x in row)
        for a in vertices:
            graph[a].update(vertices-{a})
    unseen = set(graph)
    found = []
    while unseen:
        start = min(unseen)
        seen = {start}
        todo = [start]
        unseen.remove(start)
        while todo:
            for other in graph[todo.pop()] & unseen:
                unseen.remove(other)
                seen.add(other)
                todo.append(other)
        found.append(tuple(sorted(seen)))
    return sorted(found, key=lambda group: group[0])


def verify_receipt(clauses,n,receipt):
    """Independently replay original CNF, every cut branch, and SFI proof path.

    Producer timing is informational only. This bounded checker reexecutes
    branch interpreters: it is intentionally expensive and *must be charged*.
    """
    source=_source(clauses,n)
    if type(receipt) is not dict or receipt.get('schema')!=SCHEMA:
        raise ValueError('invalid receipt')
    if receipt.get('source_sha256')!=_digest({'n':n,'clauses':source}) or receipt.get('n')!=n:
        raise ValueError('source binding changed')
    if receipt.get('digest')!=_digest({k:v for k,v in receipt.items() if k!='digest'}):
        raise ValueError('receipt digest incorrect')
    budget=receipt.get('budget')
    if type(budget) is not dict or set(budget)!={'max_cut','maximum_coordinates','maximum_free','partition_size'}:
        raise ValueError('malformed source budget')
    cut=select_separator(source,n,max_cut=budget['max_cut'])
    if receipt.get('separator')!=cut:
        raise ValueError('source separator was changed')
    # Independently reconstruct the mathematical split; never accept a
    # producer-supplied branch count or factorization flag by itself.
    branches = receipt.get('branches')
    if not cut and len(_parts(source,n))==1:
        if branches != []:
            raise ValueError('undetermined source has no admitted branches')
    elif not isinstance(branches,list) or len(branches)!=(1<<len(cut)):
        raise ValueError('missing or repeated separator assignment')
    else:
        for bits, branch in enumerate(branches):
            if not isinstance(branch,dict) or branch.get('bits') != bits:
                raise ValueError('separator branch assignment not complete')
            independent_vars,independent_clauses=_independent_restriction(source,n,cut,bits)
            producer_vars,producer_clauses=_restrict(source,n,cut,bits)
            if (independent_vars, independent_clauses)!=(producer_vars,producer_clauses):
                raise ValueError('source clause restriction disagrees with independent verifier')
            if [] not in independent_clauses:
                scopes=_independent_component_scopes(independent_clauses,len(independent_vars))
                verified_scopes=sorted(tuple(sorted(component['source_variables']))
                    for component in branch['components'])
                expected_scopes=sorted(tuple(independent_vars[v-1] for v in group)
                    for group in scopes)
                if verified_scopes!=expected_scopes or branch['component_count']!=len(scopes):
                    raise ValueError('source factorization disagrees with independent verifier')
            elif branch.get('status')!='UNSAT' or branch.get('count')!=0:
                raise ValueError('falsified source clause must refute branch')
    expected=run(source,n,**budget)
    # Time is an untrusted observation; it is not used as mathematical evidence.
    for field in ('schema','source_sha256','n','separator','branches',
                  'status','count','witness','reason','budget'):
        if receipt.get(field)!=expected.get(field):
            raise ValueError('unverified separator or component claim: '+field)
    if receipt['status']=='SAT' and not _source_satisfied(source,receipt['witness']):
        raise ValueError('original-source witness rejected')
    return receipt['status']
