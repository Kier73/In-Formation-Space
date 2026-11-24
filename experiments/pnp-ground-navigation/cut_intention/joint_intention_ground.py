"""CIG-005: intention-generated shared nonlinear observer language from source CNF.

Uses existing CIG-001/003/004 source-ground and exact GF(2) ANF primitives.
The source is a fixed-point CNF; its temporal orientation is a chosen,
source-proved repair map, NOT an inferred unique physical dynamic.
"""
from __future__ import annotations
from itertools import combinations, product
from time import perf_counter_ns
from math import ceil, log2

from cut_intention import GroundRefusal, analyze, digest, make_source
from coupled_ground import SCHEMA as COUPLED_SCHEMA, _cut
from nonlinear_observer_ground import source_reduce
from chain_observer_ground import (_discover, _operator, _pullback, _eval,
                                   _reduce, _navigate, _xor, _mul)

SCHEMA = 'ifs.cig005.joint-intention-ground.v1'
OBSERVERS = (5, 4, 6)  # named: y, j, z; intentionally not sorted
OBSERVER_NAMES = ('y', 'j', 'z')
OFFER_ORDER = ('y', 'j', 'z', 'y_xor_j', 'y_and_j')
DEFAULT_PRICES = {'y':3,'j':2,'z':6,'y_xor_j':1,'y_and_j':2}
MAX_FEATURES = 24
MAX_HORIZON = 12
MAX_SUPPORT = 12
MAX_STATES = 4096


def make_branching_source(k=10):
    """Plain endpoint-copy + 4 local CNF Boolean-function blocks, no gate tags.

    The chosen vertex-order orientation yields h'=a&b, j'=h^c,
    y'=j^c, z'=h&j. The source itself specifies only fixed points.
    """
    base = make_source(k, 1)
    pairs = analyze(base)['pairs']
    if len(pairs) < 7:
        raise ValueError('require at least 7 independently observed edge labels')
    clauses=[]
    # Generator metadata is used only to create the test source, never passed to
    # the compiler or its independent verifier.
    for a,b,out,mode in ((0,1,3,'and'),(2,3,4,'xor'),
                         (2,4,5,'xor'),(3,4,6,'and')):
        x,y,z=(pairs[t][0] for t in (a,b,out))
        for vx,vy,vz in product((0,1), repeat=3):
            expected = vx & vy if mode=='and' else vx ^ vy
            if vz!=expected:
                clauses.append([(-v if bit else v)
                                for v,bit in ((x,vx),(y,vy),(z,vz))])
    return {'schema':COUPLED_SCHEMA,'base':base,'coupling':clauses}


def _span_reduce(poly, pivots):
    return _reduce(poly,pivots)


def _closure(rows, targets):
    basis=[];pivots={};frontier=[];pullbacks=0
    def insert(poly):
        remainder,_=_span_reduce(poly,pivots)
        if not remainder:return
        if len(basis)>=MAX_FEATURES:raise GroundRefusal('shared feature budget exceeded')
        i=len(basis);pivots[max(remainder)]=(i,remainder)
        basis.append(remainder);frontier.append(remainder)
    for target in targets:insert((1<<target,))
    while frontier:
        previous=tuple(frontier);frontier.clear()
        for feature in previous:
            pullbacks+=1
            insert(_pullback(feature,rows))
    matrix=[]
    for f in basis:
        leftover,code=_span_reduce(_pullback(f,rows),pivots)
        if leftover:raise AssertionError('unclosed observer span')
        matrix.append(code)
    read=[]
    for target in targets:
        leftover,code=_span_reduce((1<<target,),pivots)
        if leftover:raise AssertionError('observer escaped closed span')
        read.append(code)
    return {'basis':[list(p) for p in basis], 'matrix_rows':matrix,
            'read_masks':read,'dimension':len(basis),
            'closure_pullbacks':pullbacks}


def _rank(polys):
    pivots={};size=0
    for p in polys:
        remaining,_=_span_reduce(p,pivots)
        if remaining:
            pivots[max(remaining)]=(size,remaining);size+=1
    return size


def _eventual(rows,targets):
    histories=[];steps=[];stable=[]
    for target in targets:
        poly=(1<<target,)
        orbit=[list(poly)]
        for h in range(MAX_HORIZON+1):
            next_poly=_pullback(poly,rows)
            if next_poly==poly:
                histories.append(orbit);steps.append(h);stable.append(poly)
                break
            poly=next_poly;orbit.append(list(poly))
        else:raise GroundRefusal('observer pullback does not stabilize within limit')
    horizon=max(steps)
    for poly in stable:
        assert _pullback(poly,rows)==poly
    return {'observer_stabilization':steps,'horizon':horizon,
            'orbit_anf_masks':histories,'stable_anf_masks':[list(p) for p in stable],
            'stable_linear_dimension':_rank(stable)}


def _offer_polynomials():
    y,j,z=(1<<v for v in OBSERVERS)
    return {'y':(y,), 'j':(j,), 'z':(z,),
            'y_xor_j':tuple(sorted((y,j))), 'y_and_j':(y|j,)}


def _push_to_eventual(poly, rows, h):
    for _ in range(h):poly=_pullback(poly,rows)
    assert _pullback(poly,rows)==poly
    return poly


def _support(polys):
    mask=0
    for p in polys:
        for m in p:mask|=m
    return tuple(v for v in range(mask.bit_length()) if mask & (1<<v))


def _profile(polys):
    support=_support(polys)
    if len(support)>MAX_SUPPORT or (1<<len(support))>MAX_STATES:
        raise GroundRefusal('quotient-image source support exceeds verification budget')
    counts={};representatives={}
    for code in range(1<<len(support)):
        state=sum(((code>>i)&1)<<v for i,v in enumerate(support))
        out=sum(_eval(p,state)<<i for i,p in enumerate(polys))
        counts[out]=counts.get(out,0)+1
        representatives.setdefault(out,state)
    return support,counts,representatives


def _decode_for_subset(targets,offers,names,support):
    """Exact small-support function test, not a claim about arbitrary observations."""
    witness={};evaluations=0
    for code in range(1<<len(support)):
        state=sum(((code>>i)&1)<<v for i,v in enumerate(support))
        measured=sum(_eval(offers[n],state)<<i for i,n in enumerate(names))
        wanted=sum(_eval(poly,state)<<i for i,poly in enumerate(targets))
        evaluations+=1
        if measured in witness and witness[measured]!=wanted:
            return None,evaluations
        witness[measured]=wanted
    return witness,evaluations


def _policy(rows,eventual,prices):
    if set(prices)!=set(OFFER_ORDER) or any(type(v)is not int or v<0
                                           for v in prices.values()):
        raise GroundRefusal('invalid declared measurement prices')
    targets=tuple(tuple(x) for x in eventual['stable_anf_masks'])
    raw_offers=_offer_polynomials()
    offers={name:_push_to_eventual(raw_offers[name],rows,eventual['horizon'])
            for name in OFFER_ORDER}
    support=_support([*targets,*offers.values()])
    if len(support)>MAX_SUPPORT:raise GroundRefusal('offer support budget exceeded')
    candidates=[];evaluations=0
    for size in range(1,len(OFFER_ORDER)+1):
        for names in combinations(OFFER_ORDER,size):
            decode,work=_decode_for_subset(targets,offers,names,support)
            evaluations+=work
            if decode is None:continue
            if len(decode)!=(1<<size):
                # Still an exact policy; missing observation combinations have
                # no reachable source assignment and are represented as null.
                pass
            candidates.append((sum(prices[name] for name in names),size,names,decode))
    if not candidates:raise GroundRefusal('no offered observer set preserves all intentions')
    cost,size,names,decoder=min(candidates,key=lambda v:(v[0],v[1],v[2]))
    return {'selected':list(names),'declared_cost':cost,
            'decoder':[decoder.get(i) for i in range(1<<len(names))],
            'source_support':list(support),
            'admissible_policies':len(candidates),
            'policy_subsets_considered':(1<<len(OFFER_ORDER))-1,
            'source_local_evaluations':evaluations,
            'offer_eventual_anf':{name:list(offers[name]) for name in OFFER_ORDER},
            'prices':dict(prices)}


def compile_ground(source,cut,*,prices=None,initial=3,steps=10**100+173):
    start=perf_counter_ns()
    proof,active,clauses=source_reduce(source)
    _cut(proof,cut)
    if len(active)>12:raise GroundRefusal('bounded active-label family only')
    gates=_discover(clauses,len(active))
    outputs={g['output'] for g in gates}
    rows=_operator(gates,len(active))
    if len(active)!=7 or len(gates)!=4 or not all(t in outputs for t in OBSERVERS):
        raise GroundRefusal('CIG-005 currently admits the bounded four-gate branching family')
    joint=_closure(rows,OBSERVERS)
    independent=[_closure(rows,(t,))['dimension'] for t in OBSERVERS]
    eventual=_eventual(rows,OBSERVERS)
    policy=_policy(rows,eventual,dict(DEFAULT_PRICES if prices is None else prices))
    support,distribution,examples=_profile(tuple(tuple(x) for x in eventual['stable_anf_masks']))
    if type(initial)is not int or not 0<=initial<(1<<len(active)):
        raise GroundRefusal('initial active state invalid')
    if type(steps)is not int or steps<0 or steps.bit_length()>4096:
        raise GroundRefusal('requested logical time exceeds exact navigation budget')
    initial_features=sum(_eval(tuple(p),initial)<<i for i,p in enumerate(joint['basis']))
    result,products=_navigate(joint['matrix_rows'],initial_features,steps)
    observed=sum(((result&m).bit_count()&1)<<i for i,m in enumerate(joint['read_masks']))
    eventual_observed=sum(_eval(tuple(p),initial)<<i for i,p in enumerate(eventual['stable_anf_masks']))
    if steps>=eventual['horizon'] and observed!=eventual_observed:
        raise AssertionError('long-time feature navigation inconsistent with stable intention')
    original_source_models=1<<(len(proof['pairs'])-len(active)+len(active)-len(outputs))
    # A zero witness, independently checked against the original 106+ clauses.
    zero=[0]*source['base']['n']
    if not all(any(zero[abs(l)-1]==int(l>0) for l in c)
               for c in source['base']['clauses']+source['coupling']):
        raise GroundRefusal('original CNF zero witness invalid')
    certificate={'schema':SCHEMA,'source_digest':digest(source),'cut':list(cut),
      'active_labels':list(active),'clauses':[list(c) for c in clauses],
      'orientation':'maximum-variable local output; proof-checked chosen rewrite',
      'gates':gates,'operator_rows':[list(p) for p in rows],
      'observers':list(OBSERVERS),'observer_names':list(OBSERVER_NAMES),
      'whole_future':joint,'individual_dimensions':independent,
      'eventual':eventual,'policy':policy,
      'quotient':{'source_support':list(support),'image_size':len(distribution),
                  'minimum_binary_bits':(len(distribution)-1).bit_length(),
                  'histogram_active_support':{str(k):v for k,v in sorted(distribution.items())},
                  'representatives':{str(k):v for k,v in sorted(examples.items())}},
      'navigation':{'initial':str(initial),'steps':str(steps),
                    'initial_features':str(initial_features),
                    'result_features':str(result),'observed':observed,
                    'eventual_observed':eventual_observed,'matrix_products':products},
      'source_result':{'status':'SAT','count':str(original_source_models),'witness':zero},
      'ledger':{'original_cnf_clauses':len(source['base']['clauses'])+len(source['coupling']),
                'original_endpoint_variables':source['base']['n'],
                'active_variables':len(active),'local_gate_truth_rows':len(gates)*4,
                'closure_pullbacks':joint['closure_pullbacks'],
                'individual_closure_dimensions':independent,
                'eventual_symbolic_pullbacks':sum(x+1 for x in eventual['observer_stabilization']),
                'quotient_local_state_visits':1<<len(support),
                'policy_local_evaluations':policy['source_local_evaluations'],
                'matrix_products':products}}
    return certificate,{'producer_ns':perf_counter_ns()-start}
