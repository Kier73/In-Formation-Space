"""CIG-004 — source-derived multi-step nonlinear observer Ground.

The original CNF defines fixed points of a simultaneously updated Boolean law.
A declared observer (last generated output) induces the least exact GF(2)-linear
pullback-invariant ANF feature span, under explicit bounded construction work.
No pre-labelled gates are passed to compile_ground; orientation is selected by
canonical monotone variable order, not asserted to be intrinsic to CNF.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from itertools import product
import json
from time import perf_counter_ns

from cut_intention import analyze, digest, make_source, GroundRefusal
from coupled_ground import SCHEMA as COUPLED_SCHEMA, _cut
from nonlinear_observer_ground import source_reduce

SCHEMA='ifs.cig004.chain-observer-ground.v1'
MAX_FEATURES=20
MAX_TERMS=1024
MAX_PRODUCT=16384
MAX_STAGES=12


def _cnf_true(clauses, bits):
    return all(any(((bits >> (abs(x)-1)) & 1)==int(x>0) for x in c) for c in clauses)


def _xor(p, q):
    return tuple(sorted(set(p)^set(q)))


def _mul(p,q):
    if len(p)*len(q)>MAX_PRODUCT:raise GroundRefusal('ANF multiplication cost budget')
    values=set()
    for a in p:
        for b in q:
            m=a|b    # Boolean ring: x_i * x_i = x_i
            if m in values: values.remove(m)
            else:values.add(m)
    if len(values)>MAX_TERMS:raise GroundRefusal('ANF term budget')
    return tuple(sorted(values))


def _pullback(poly, rows):
    ans=()
    for monomial in poly:
        product=(0,)
        while monomial:
            low=monomial & -monomial
            product=_mul(product,rows[low.bit_length()-1])
            monomial ^= low
        ans=_xor(ans,product)
        if len(ans)>MAX_TERMS:raise GroundRefusal('pullback term budget')
    return ans


def _eval(poly,state):
    return sum((state&monomial)==monomial for monomial in poly)&1


def _discover(clauses,n):
    """Every original clause must be explained by a certified local function.

    Max-index local output is a deterministic *chosen orientation*, not an
    orientation uniquely implied by SAT for symmetric operations such as XOR.
    """
    scopes=defaultdict(list)
    for clause in clauses:
        scope=tuple(sorted({abs(x)-1 for x in clause}))
        if len(scope)!=3:raise GroundRefusal('non-functional or unsupported source clause')
        scopes[scope].append(tuple(clause))
    gates=[];explained=[]
    for scope,proof in sorted(scopes.items(),key=lambda item:max(item[0])):
        out=max(scope);ins=scope[:2]
        table=[]
        for z in range(4):
            possible=[]
            for v in (0,1):
                bits=sum(((z>>j)&1)<<a for j,a in enumerate(ins))|(v<<out)
                if _cnf_true(proof,bits): possible.append(v)
            if len(possible)!=1:raise GroundRefusal('clauses do not prove total functional output')
            table.append(possible[0])
        coefficients=table.copy()
        for j in (0,1):
            for mask in range(4):
                if (mask>>j)&1:coefficients[mask]^=coefficients[mask ^ (1<<j)]
        poly=tuple(sorted(sum(1<<ins[j] for j in range(2) if (mask>>j)&1)
                         for mask,c in enumerate(coefficients) if c))
        gates.append({'output':out,'inputs':list(ins),'table':table,
                      'anf_masks':list(poly),'source_clauses':[list(c) for c in sorted(proof)]})
        explained.extend(proof)
    if len(gates)>MAX_STAGES:raise GroundRefusal('chain stage budget')
    if not gates:raise GroundRefusal('no source-derived gates')
    if len({g['output'] for g in gates})!=len(gates):raise GroundRefusal('multiple laws for one output')
    if sorted(explained)!=sorted(clauses):raise GroundRefusal('source clauses not fully explained')
    outputs={g['output'] for g in gates}
    if any(any(v>=g['output'] for v in g['inputs']) for g in gates):
        raise GroundRefusal('not a monotone directed source DAG')
    if not any(any(v in outputs for v in g['inputs']) for g in gates):
        raise GroundRefusal('no multi-stage dependency')
    return gates


def _operator(gates,n):
    rows=[(1<<i,) for i in range(n)]
    for g in gates:rows[g['output']]=tuple(g['anf_masks'])
    return tuple(rows)


def _reduce(poly,pivots):
    rest=set(poly);code=0
    for pivot in sorted(pivots,reverse=True):
        if pivot in rest:
            index,row=pivots[pivot]
            rest.symmetric_difference_update(row)
            code ^= 1<<index
    return tuple(sorted(rest)),code


def _closure(rows,target,max_features=MAX_FEATURES):
    if type(max_features) is not int or not 1<=max_features<=MAX_FEATURES:
        raise GroundRefusal('feature budget invalid')
    basis=[];pivots={};frontier=[];pullbacks=0
    def insert(poly):
        rest,_=_reduce(poly,pivots)
        if rest:
            if len(basis)>=max_features:raise GroundRefusal('pullback feature budget exceeded')
            idx=len(basis);pivots[max(rest)]=(idx,rest)
            basis.append(rest);frontier.append(rest)
    insert((1<<target,))
    while frontier:
        items=tuple(frontier);frontier.clear()
        for poly in items:
            image=_pullback(poly,rows);pullbacks+=1
            insert(image)
    matrix=[]
    for poly in basis:
        rest,mask=_reduce(_pullback(poly,rows),pivots)
        if rest:raise AssertionError('basis not closed')
        matrix.append(mask)
    rest,read=_reduce((1<<target,),pivots)
    if rest:raise AssertionError('observer lost')
    return {'basis':[list(x) for x in basis],'matrix_rows':matrix,
            'read_mask':read,'dimension':len(basis),'closure_pullbacks':pullbacks}


def _apply_matrix(matrix,state):
    return sum(((r&state).bit_count()&1)<<i for i,r in enumerate(matrix))


def _compose(after,before):
    composed=[]
    for row in after:
        acc=0
        while row:
            bit=row & -row
            acc ^= before[bit.bit_length()-1]
            row ^= bit
        composed.append(acc)
    return tuple(composed)


def _navigate(matrix,features,steps):
    if type(steps) is not int or steps<0 or steps.bit_length()>4096:
        raise GroundRefusal('logical time budget')
    result=tuple(1<<i for i in range(len(matrix)));power=tuple(matrix)
    products=0;remain=steps
    while remain:
        if remain&1:
            result=_compose(power,result);products+=1
        remain>>=1
        if remain:
            power=_compose(power,power);products+=1
    return _apply_matrix(result,features),products


def make_chain_source(*,depth=4,k=10):
    """Public ordinary CNF only: four source bits and a depth-stage repair DAG."""
    if type(depth) is not int or not 2<=depth<=8:raise ValueError('depth outside fixture')
    base=make_source(k,1);pairs=analyze(base)['pairs']
    if len(pairs)<depth+4:raise ValueError('insufficient independent source labels')
    free=(0,1,2,3);outputs=tuple(4+i for i in range(depth))
    operations=[]
    for i in range(depth):
        if i==0: a,b,kind=free[0],free[1],'and'
        elif i==1:a,b,kind=outputs[0],free[2],'xor'
        elif i==2:a,b,kind=outputs[1],free[0],'and'
        elif i==3:a,b,kind=outputs[2],free[3],'xor'
        else:a,b,kind=outputs[i-1],free[(i-3)%4],('and' if i%2==0 else 'xor')
        operations.append((a,b,outputs[i],kind))
    coupling=[]
    for a,b,out,kind in operations:
        x,y,z=(pairs[j][0] for j in (a,b,out))
        for va,vb,vz in product((0,1),repeat=3):
            actual=(va&vb) if kind=='and' else (va^vb)
            if vz!=actual:
                coupling.append([((-1 if bit else 1)*v) for bit,v in ((va,x),(vb,y),(vz,z))])
    return {'schema':COUPLED_SCHEMA,'base':base,'coupling':coupling},tuple(range(k//2))


def compile_ground(source,cut,*,max_features=MAX_FEATURES,initial=3,steps=10**30+17):
    start=perf_counter_ns()
    proof,active,clauses=source_reduce(source)
    _cut(proof,cut)  # original node-observer contract independently audited by receiver
    n=len(active)
    if n>24:raise GroundRefusal('active bit budget')
    gates=_discover(clauses,n)
    outputs={g['output'] for g in gates}
    registers=[i for i in range(n) if i not in outputs]
    # Check total functional source implies a free-register bijection, rather
    # than treating its source-only fixed point as a precomputed SAT answer.
    rows=_operator(gates,n)
    target=max(outputs)
    info=_closure(rows,target,max_features=max_features)
    if type(initial) is not int or not 0<=initial<1<<n:
        raise GroundRefusal('initial state out of active domain')
    feature_state=sum(_eval(tuple(row),initial)<<j for j,row in enumerate(info['basis']))
    final,products=_navigate(info['matrix_rows'],feature_state,steps)
    observation=((final&info['read_mask']).bit_count()&1)
    future_poly=(1<<target,)
    stabilization=None;alignment_pullbacks=0
    for h in range(len(gates)+2):
        next_poly=_pullback(future_poly,rows);alignment_pullbacks+=1
        if next_poly==future_poly:
            stabilization=h;break
        future_poly=next_poly
    if stabilization is None:
        raise GroundRefusal('future-aligned observer exceeds finite closure horizon')
    eventual_value=_eval(future_poly,initial)
    if steps>=stabilization and eventual_value!=observation:
        raise AssertionError('future-aligned readout disagrees with feature navigation')
    # Zeroing all free registers yields the unique sourced zero-coordinate model
    zero_state=0
    for g in gates:
        zero_state=(zero_state & ~(1<<g['output']))|(_eval(tuple(g['anf_masks']),zero_state)<<g['output'])
    if not _cnf_true(clauses,zero_state):raise GroundRefusal('witness failed source')
    original=[0]*source['base']['n']
    label_values={v:(zero_state>>i)&1 for i,v in enumerate(active)}
    for i,(a,b) in enumerate(proof['pairs']):
        original[a-1]=original[b-1]=label_values.get(i,0)
    if not all(any(original[abs(l)-1]==int(l>0) for l in clause)
               for clause in source['base']['clauses']+source['coupling']):
        raise GroundRefusal('original CNF witness rejected')
    models=1<<(len(registers)+len(proof['pairs'])-n)
    doc={'schema':SCHEMA,'source_digest':digest(source),'cut':list(cut),
         'active_labels':list(active),'clauses':[list(c) for c in clauses],
         'orientation':'maximum-variable local output; proof-checked chosen rewrite',
         'gates':gates,'registers':registers,'operator_rows':[list(row) for row in rows],
         'observer':target,'features':info,
         'future_alignment':{'stabilization_steps':stabilization,
              'anf_masks':list(future_poly),'exact_for_steps_at_least':stabilization,
              'observed':eventual_value,'dimension':1 if future_poly else 0,
              'symbolic_pullbacks':alignment_pullbacks},
         'source_result':{'status':'SAT','count':str(models),'witness':original},
         'navigation':{'initial':str(initial),'steps':str(steps),'initial_features':str(feature_state),
                       'result_features':str(final),'observed':observation,'matrix_products':products},
         'ledger':{'source_clause_count':len(source['base']['clauses'])+len(source['coupling']),
                   'active_variables':n,'original_endpoint_variables':source['base']['n'],
                   'original_sat_models':str(models),'source_cube_size':str(1<<n),
                   'nonlinear_operator_row_count':len(rows),
                   'closure_pullbacks':info['closure_pullbacks'],
                   'matrix_products':products,
                   'future_alignment_pullbacks':alignment_pullbacks}}
    return doc,{'producer_ns':perf_counter_ns()-start}
