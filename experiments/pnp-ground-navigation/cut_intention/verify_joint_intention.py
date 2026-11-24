"""Independent CIG-005 receiver: original-CNF replay, joint ANF closure,
minimality, nonlinear quotient/decoder and priced observation-policy audit.

Does not import the CIG-005 producer, constructor or optimization routines.
Reuses the established *independent* CIG-003/CIG-004 source and ANF verifiers.
"""
from __future__ import annotations
from itertools import combinations
from math import prod

from verify_nonlinear_observer import _source as qualified_source
from verify_chain_observer import (_truth_anf, _substitute, _value, _true,
    _linear_expression, _matrix_navigate, _hash)

SCHEMA='ifs.cig005.joint-intention-ground.v1'
TARGETS=(5,4,6)
OFFERS=('y','j','z','y_xor_j','y_and_j')
DEFAULT_PRICES={'y':3,'j':2,'z':6,'y_xor_j':1,'y_and_j':2}


class Reject(ValueError):
    pass


def _independent_joint_orbit(targets,operator,max_features=24):
    basis=[]
    frontier=[(1<<target,) for target in targets]
    while frontier:
        p=frontier.pop(0)
        if basis and _linear_expression(basis,p) is not None:continue
        if len(basis)>=max_features:raise Reject('independent joint orbit budget exceeded')
        basis.append(p)
        frontier.append(_substitute(p,operator))
    return tuple(basis)


def _independent_eventual(operator,targets):
    histories=[];horizons=[];fixed=[]
    for target in targets:
        p=(1<<target,)
        seq=[list(p)]
        for h in range(13):
            nxt=_substitute(p,operator)
            if nxt==p:
                horizons.append(h);histories.append(seq);fixed.append(p)
                break
            seq.append(list(nxt));p=nxt
        else:raise Reject('non-stabilizing source observer')
    return {'observer_stabilization':horizons,'horizon':max(horizons),
        'orbit_anf_masks':histories,'stable_anf_masks':[list(v) for v in fixed],
        'stable_linear_dimension':len(_independent_basis(fixed))}


def _independent_basis(polys):
    kept=[]
    for p in polys:
        if _linear_expression(kept,p) is None:kept.append(p)
    return kept


def _supports(polys):
    union=0
    for p in polys:
        for m in p:union|=m
    return tuple(i for i in range(union.bit_length()) if union & (1<<i))


def _states(support):
    for bits in range(1<<len(support)):
        yield sum(((bits>>i)&1)<<v for i,v in enumerate(support))


def _raw_offer_polys():
    y,j,z=1<<5,1<<4,1<<6
    return {'y':(y,),'j':(j,),'z':(z,),
            'y_xor_j':(j,y), 'y_and_j':(y|j,)}


def _offer_profile(operator,horizon):
    offers={}
    for name,p in _raw_offer_polys().items():
        for _ in range(horizon):p=_substitute(p,operator)
        if _substitute(p,operator)!=p:raise Reject('offered observation not stable')
        offers[name]=p
    return offers


def _evaluate_subset(targets,offers,subset,support):
    table={};checks=0
    for state in _states(support):
        coordinate=sum(_value(offers[name],state)<<i for i,name in enumerate(subset))
        target=sum(_value(p,state)<<i for i,p in enumerate(targets))
        checks+=1
        if coordinate in table and table[coordinate]!=target:
            return None,checks
        table[coordinate]=target
    return table,checks


def _policy_replay(operator,eventual,received):
    prices=received['prices']
    if type(prices) is not dict or set(prices)!=set(OFFERS) or any(
            type(v)is not int or v<0 for v in prices.values()):
        raise Reject('invalid measurement price schedule')
    target=tuple(tuple(row) for row in eventual['stable_anf_masks'])
    offers=_offer_profile(operator,eventual['horizon'])
    scope=_supports([*target,*offers.values()])
    if len(scope)>12:raise Reject('independent policy support budget')
    accepted=[];work=0
    for size in range(1,len(OFFERS)+1):
        for selection in combinations(OFFERS,size):
            table,used=_evaluate_subset(target,offers,selection,scope)
            work+=used
            if table is not None:
                accepted.append((sum(prices[k] for k in selection),size,selection,table))
    if not accepted:raise Reject('no valid preserving measurement set')
    cost,_,names,decoder=min(accepted,key=lambda item:item[:3])
    expected={'selected':list(names),'declared_cost':cost,
          'decoder':[decoder.get(i) for i in range(1<<len(names))],
          'source_support':list(scope),'admissible_policies':len(accepted),
          'policy_subsets_considered':31,'source_local_evaluations':work,
          'offer_eventual_anf':{name:list(offers[name]) for name in OFFERS},
          'prices':prices}
    if received!=expected:raise Reject('wrong optimal offered observer policy')
    # Explicit nonlinear polynomial decoder proof, using the verified ANFs:
    # construct truth-table ANFs of each target bit on the observed coordinates,
    # substitute the selected source-polynomials; insist on exact equality.
    chosen=[offers[name] for name in names]
    for output,required in enumerate(target):
        decoded=()
        for mask in range(1<<len(names)):
            parity=0
            for subset in range(1<<len(names)):
                if subset&~mask==0:
                    entry=expected['decoder'][subset]
                    parity ^= (entry or 0)>>output & 1
            if parity:
                term=(0,)
                for i,p in enumerate(chosen):
                    if mask & (1<<i):
                        # Separate Boolean-ring multiplication by exact union.
                        counts={}
                        for a in term:
                            for b in p:
                                mon=a|b
                                counts[mon]=counts.get(mon,0)^1
                        term=tuple(sorted(x for x,bit in counts.items() if bit))
                decoded=tuple(sorted(set(decoded)^set(term)))
        if decoded!=required:
            raise Reject('nonlinear observer decoder not identically source-correct')
    return expected


def verify(source,certificate,*,expected_prices=None):
    try:
        if type(certificate)is not dict or certificate.get('schema')!=SCHEMA:
            raise Reject('unrecognized CIG-005 source certificate')
        if certificate['source_digest']!=_hash(source):
            raise Reject('source bytes/digest mismatch')
        pairs,active,clauses,_=qualified_source(source,certificate['cut'])
        n=len(active)
        if n!=7 or len(clauses)!=16 or certificate['active_labels']!=active:
            raise Reject('source labels or finite admission contract changed')
        if certificate['clauses']!=[list(c) for c in clauses]:
            raise Reject('source clause equivalence altered')
        if certificate['orientation']!='maximum-variable local output; proof-checked chosen rewrite':
            raise Reject('unsupported interpretation orientation')
        if certificate['observers']!=list(TARGETS) or certificate['observer_names']!=['y','j','z']:
            raise Reject('observer intention switched')
        grouped={}
        for clause in clauses:
            support=tuple(sorted({abs(x)-1 for x in clause}))
            if len(support)!=3:raise Reject('clause has no supported function scope')
            grouped.setdefault(support,[]).append(tuple(clause))
        gates=[]
        for support,proof in sorted(grouped.items(),key=lambda g:max(g[0])):
            target=max(support);inputs=list(support[:2]);truth=[]
            for bits in range(4):
                accepted=[]
                for output in (0,1):
                    x=sum(((bits>>j)&1)<<v for j,v in enumerate(inputs))|(output<<target)
                    if _true(proof,x):accepted.append(output)
                if len(accepted)!=1:raise Reject('original clauses not a total Boolean gate')
                truth.append(accepted[0])
            gates.append({'output':target,'inputs':inputs,'table':truth,
              'anf_masks':list(_truth_anf(inputs,truth)),
              'source_clauses':[list(c) for c in sorted(proof)]})
        if len(gates)!=4 or certificate['gates']!=gates:
            raise Reject('gate evidence or local nonlinear truth table forged')
        for gate in gates:
            if any(x>=gate['output'] for x in gate['inputs']):
                raise Reject('not a chosen forward DAG')
        outputs={g['output'] for g in gates}
        if outputs!={3,4,5,6}:raise Reject('source no longer the admitted branching family')
        rows=[(1<<i,) for i in range(n)]
        for gate in gates:rows[gate['output']]=tuple(gate['anf_masks'])
        if certificate['operator_rows']!=[list(p) for p in rows]:
            raise Reject('source transition operator is not exact')
        raw=tuple((1<<v,) for v in TARGETS)
        minimum=_independent_joint_orbit(TARGETS,rows)
        feature=certificate['whole_future']
        basis=tuple(tuple(p) for p in feature['basis'])
        if not basis or len(basis)>24 or feature['dimension']!=len(basis):
            raise Reject('feature dimension invalid')
        if len(_independent_basis(basis))!=len(basis) or len(basis)!=len(minimum):
            raise Reject('claimed minimal joint invariant span incorrect')
        for poly in basis:
            if _linear_expression(minimum,poly) is None:raise Reject('extra feature not in joint span')
        for poly in minimum:
            if _linear_expression(basis,poly) is None:raise Reject('missing joint temporal feature')
        matrix=[]
        for p in basis:
            row=_linear_expression(basis,_substitute(p,rows))
            if row is None:raise Reject('feature transition leaves span')
            matrix.append(row)
        masks=[_linear_expression(basis,p) for p in raw]
        if any(v is None for v in masks):raise Reject('observer missing from joint space')
        if (feature['matrix_rows']!=matrix or feature['read_masks']!=masks
                or feature['closure_pullbacks']!=len(basis)):
            raise Reject('feature dynamics, observables or ledger wrong')
        individual=[len(_independent_joint_orbit((v,),rows)) for v in TARGETS]
        if certificate['individual_dimensions']!=individual:
            raise Reject('independently constructed dimensions incorrect')
        eventual=_independent_eventual(rows,TARGETS)
        if eventual!=certificate['eventual']:
            raise Reject('incorrect nonlinear eventual-time polynomials or first horizon')
        stable=tuple(tuple(p) for p in eventual['stable_anf_masks'])
        support=_supports(stable)
        if len(support)>12:raise Reject('exact quotient support budget exceeded')
        hist={};reps={}
        for state in _states(support):
            output=sum(_value(poly,state)<<i for i,poly in enumerate(stable))
            hist[output]=hist.get(output,0)+1
            reps.setdefault(output,state)
        expected={'source_support':list(support),'image_size':len(hist),
             'minimum_binary_bits':(len(hist)-1).bit_length(),
             'histogram_active_support':{str(k):v for k,v in sorted(hist.items())},
             'representatives':{str(k):v for k,v in sorted(reps.items())}}
        if certificate['quotient']!=expected:
            raise Reject('quotient cardinality or witnesses wrong')
        bound_prices = DEFAULT_PRICES if expected_prices is None else expected_prices
        if certificate['policy']['prices'] != bound_prices:
            raise Reject('observation-price schedule not authorized by receiver intention')
        policy=_policy_replay(rows,eventual,certificate['policy'])
        nav=certificate['navigation'];initial=int(nav['initial']);steps=int(nav['steps'])
        if (type(nav['initial'])is not str or type(nav['steps'])is not str or
            initial<0 or initial>=1<<n or steps<0 or steps.bit_length()>4096):
            raise Reject('invalid source time or coordinates')
        initial_features=sum(_value(p,initial)<<i for i,p in enumerate(basis))
        future,products=_matrix_navigate(matrix,initial_features,steps)
        result=sum(((future&mask).bit_count()&1)<<i for i,mask in enumerate(masks))
        stable_result=sum(_value(p,initial)<<i for i,p in enumerate(stable))
        if (nav['initial_features']!=str(initial_features) or
            nav['result_features']!=str(future) or nav['observed']!=result or
            nav['eventual_observed']!=stable_result or nav['matrix_products']!=products or
            (steps>=eventual['horizon'] and result!=stable_result)):
            raise Reject('long-time navigation or readout falsified')
        source_models=1<<(len(pairs)-n+(n-len(outputs)))
        claim=certificate['source_result']
        witness=claim['witness']
        if (claim['status']!='SAT' or claim['count']!=str(source_models) or
            type(witness)is not list or len(witness)!=source['base']['n'] or
            any(type(bit)is not int or bit not in (0,1) for bit in witness) or
            not _true(source['base']['clauses']+source['coupling'],
                      sum(bit<<i for i,bit in enumerate(witness)))):
            raise Reject('original endpoint source SAT/count/witness incorrect')
        if n<=12:
            models=0
            for state in range(1<<n):
                T=sum(_value(row,state)<<v for v,row in enumerate(rows))
                hit=_true(clauses,state)
                if hit !=(T==state):
                    raise Reject('source CNF not exactly chosen T fixed points')
                models+=int(hit)
                # Distinct direct finite-step check catches matrix orientation.
                for t in range(7):
                    direct=state
                    for _ in range(t):
                        direct=sum(_value(row,direct)<<v for v,row in enumerate(rows))
                    projected=sum(_value(p,state)<<i for i,p in enumerate(basis))
                    nav_state,_=_matrix_navigate(matrix,projected,t)
                    observed=sum(((nav_state&mask).bit_count()&1)<<i for i,mask in enumerate(masks))
                    direct_obs=sum(((direct>>v)&1)<<i for i,v in enumerate(TARGETS))
                    if observed!=direct_obs:raise Reject('finite-time nonlinear observer mismatch')
                if hit:
                    projected=sum(_value(p,state)<<i for i,p in enumerate(stable))
                    observed=sum(((state>>v)&1)<<i for i,v in enumerate(TARGETS))
                    if projected!=observed:
                        raise Reject('fixed point disagrees with stable observation')
            if models!=(1<<(n-len(outputs))):
                raise Reject('original fixed-point count invalid')
        led=certificate['ledger']
        expected_ledger={'original_cnf_clauses':len(source['base']['clauses'])+len(source['coupling']),
                 'original_endpoint_variables':source['base']['n'],
                 'active_variables':n,'local_gate_truth_rows':len(gates)*4,
                 'closure_pullbacks':len(basis),
                 'individual_closure_dimensions':individual,
                 'eventual_symbolic_pullbacks':sum(x+1 for x in eventual['observer_stabilization']),
                 'quotient_local_state_visits':1<<len(support),
                 'policy_local_evaluations':policy['source_local_evaluations'],
                 'matrix_products':products}
        if led!=expected_ledger:raise Reject('inaccurate cost accounting')
        return True
    except Reject:
        raise
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,IndexError,RecursionError) as error:
        raise Reject('cannot independently admit source observer certificate') from error
