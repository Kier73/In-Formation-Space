"""TCN-009: intention-first synthesis of finite-field computational systems.

Constrained complete model search, not an inference of unknown physical dynamics.
Inputs are required transition examples, an invariant subset, typed polynomial
observables, declared hosts and a desired observable conjunction. All work and
admission scope are explicit; hosts are not authenticated.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from heapq import heappop, heappush
from itertools import product
import json
import math
from typing import Mapping


class SpecificationError(ValueError):
    pass


def _prime(p):
    return type(p) is int and 5 <= p <= 257 and all(p % d for d in range(2, math.isqrt(p)+1))


def _poly_trim(c):
    c = list(c)
    while len(c) > 1 and c[-1] == 0:
        c.pop()
    return tuple(c)


def _eval(c, x, p):
    z = 0
    for a in reversed(c):
        z = (z*x+a) % p
    return z


def _mul(a,b,p):
    out=[0]*(len(a)+len(b)-1)
    for i,x in enumerate(a):
        for j,y in enumerate(b):
            out[i+j]=(out[i+j]+x*y)%p
    return _poly_trim(out)


def _add(a,b,p):
    return _poly_trim([( (a[i] if i<len(a) else 0)+(b[i] if i<len(b) else 0) )%p for i in range(max(len(a),len(b)))])


def _interp(samples,p):
    """Exact Lagrange interpolation through distinct finite-field points."""
    f=(0,)
    for i,(x,y) in enumerate(samples):
        top=(1,)
        denominator=1
        for j,(z,_) in enumerate(samples):
            if i!=j:
                top=_mul(top,((-z)%p,1),p)
                denominator=denominator*(x-z)%p
        factor=y*pow(denominator,-1,p)%p
        f=_add(f,tuple(v*factor%p for v in top),p)
    return f


def _canonical(data):
    return json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def _digest(data):
    return sha256(_canonical(data).encode()).hexdigest()


@dataclass(frozen=True)
class Operation:
    name: str
    samples: tuple[tuple[int,int],...]
    max_degree: int = 3


@dataclass(frozen=True)
class Observable:
    name: str
    coefficients: tuple[int,...]


@dataclass(frozen=True)
class Host:
    name: str
    max_degree: int
    allowed_ops: tuple[str,...]
    execution_cost: int


@dataclass(frozen=True)
class Intent:
    p: int
    frame: str
    safe_states: tuple[int,...]
    start: int
    operations: tuple[Operation,...]
    observables: tuple[Observable,...]
    goals: tuple[tuple[str,int],...]
    hosts: tuple[Host,...]
    total_execution_budget: int=30
    candidate_budget: int=20000

    def __post_init__(self):
        if not _prime(self.p):
            raise SpecificationError('prime p must be in [5,257]')
        p=self.p
        if type(self.frame) is not str or not self.frame or len(self.frame)>80:
            raise SpecificationError('named finite-field frame required')
        if not self.safe_states or len(set(self.safe_states))!=len(self.safe_states) or any(type(x) is not int or x<0 or x>=p for x in self.safe_states):
            raise SpecificationError('nonempty unique invariant states in F_p required')
        if type(self.start) is not int or self.start not in self.safe_states:
            raise SpecificationError('start must satisfy invariant')
        if not self.operations or len(self.operations)>3 or len({o.name for o in self.operations})!=len(self.operations):
            raise SpecificationError('one to three distinctly named operations required')
        if not self.observables or len({o.name for o in self.observables})!=len(self.observables):
            raise SpecificationError('distinct observables required')
        if not self.goals or any(name not in {o.name for o in self.observables} or type(value) is not int or not 0<=value<p for name,value in self.goals):
            raise SpecificationError('goals must refer to typed observables')
        if not self.hosts or len({h.name for h in self.hosts})!=len(self.hosts):
            raise SpecificationError('distinct declared hosts required')
        if type(self.total_execution_budget) is not int or self.total_execution_budget<0 or type(self.candidate_budget) is not int or self.candidate_budget<1:
            raise SpecificationError('finite nonnegative execution and positive search budgets required')
        for op in self.operations:
            if not op.name or type(op.max_degree) is not int or not 0<=op.max_degree<=min(5,p-1) or not op.samples:
                raise SpecificationError('operation name, samples and degree 0..5 required')
            if any(len(pair)!=2 or any(type(v) is not int or not 0<=v<p for v in pair) for pair in op.samples):
                raise SpecificationError('transition examples must be F_p pairs')
        for obs in self.observables:
            if not obs.name or not obs.coefficients or len(obs.coefficients)>6 or any(type(v) is not int for v in obs.coefficients):
                raise SpecificationError('observable polynomial degree <=5 required')
        for host in self.hosts:
            if not host.name or type(host.max_degree) is not int or not 0<=host.max_degree<=5 or type(host.execution_cost) is not int or host.execution_cost<1 or len(set(host.allowed_ops))!=len(host.allowed_ops):
                raise SpecificationError('invalid host capabilities or cost')

    def record(self):
        return json.loads(_canonical(asdict(self)))


def _enumerate_operation(intent,op,limit):
    """All maps consistent with samples in degree<=D; truncation is explicit.

    Any polynomial matching m distinct samples can be written I(x)+V(x)Q(x),
    deg(V)=m.  This is a COMPLETE parameterization within the declared degree.
    """
    p=intent.p
    examples={}
    for x,y in op.samples:
        if x in examples and examples[x]!=y:
            return [],0,True,{'reason':'conflicting_transition_example','input':x,'required':[examples[x],y]}
        examples[x]=y
    samples=tuple(sorted(examples.items()))
    maxd=op.max_degree
    base=_interp(samples[:min(len(samples),maxd+1)],p)
    if any(_eval(base,x,p)!=y for x,y in samples):
        return [],0,True,{'reason':'interpolation_obstruction','examples':list(map(list,samples[:maxd+2])), 'max_degree':maxd}
    vanishing=(1,)
    for x,_ in samples:
        vanishing=_mul(vanishing,((-x)%p,1),p)
    safe=tuple(sorted(intent.safe_states))
    accepted=[]
    examined=0
    first_rejected=None
    def consider(poly):
        nonlocal examined,first_rejected
        examined+=1
        for x in safe:
            value=_eval(poly,x,p)
            if value not in safe:
                if first_rejected is None:
                    first_rejected={'reason':'invariant_violation','operation':op.name,'input':x,'output':value,'polynomial':list(poly)}
                return
        accepted.append(poly)
    consider(base)
    if examined>=limit:
        # If there can be additional polynomial completions, do not claim completeness.
        return accepted,examined,maxd<len(samples),first_rejected
    if maxd >= len(samples):
        # Polynomial solutions: base + V * Q; enumerate by increasing degree of Q.
        for k in range(maxd-len(samples)+1):
            for prefix in product(range(p),repeat=k):
                for last in range(1,p):
                    q=tuple(prefix)+(last,)
                    poly=_add(base,_mul(vanishing,q,p),p)
                    consider(poly)
                    if examined>=limit:
                        return accepted,examined,False,first_rejected
    return accepted,examined,True,first_rejected


def _shortest_path(intent, candidates, host_assignments):
    p=intent.p
    allowed=set(intent.safe_states)
    goals={name:value for name,value in intent.goals}
    if any(len({v for n,v in intent.goals if n==name})>1 for name in goals):
        return None
    obs={o.name:tuple(c%p for c in o.coefficients) for o in intent.observables}
    def satisfied(x):
        return all(_eval(obs[n],x,p)==v for n,v in intent.goals)
    # Weighted directed graph with positive costs; deterministic ties by op names.
    start=intent.start
    queue=[(0,0,(),start)]
    best={start:(0,0,())}
    while queue:
        cost,steps,path,x=heappop(queue)
        if best.get(x)!=(cost,steps,path):
            continue
        if satisfied(x):
            trace=[start]
            state=start
            for name in path:
                idx=next(i for i,op in enumerate(intent.operations) if op.name==name)
                state=_eval(candidates[idx],state,p)
                trace.append(state)
            return {'operation_path':list(path),'state_path':trace,'execution_cost':cost}
        for i,op in enumerate(intent.operations):
            if host_assignments[i] is None:continue
            nxt=_eval(candidates[i],x,p)
            if nxt not in allowed:
                raise AssertionError('qualified map violated invariant')
            new=(cost+host_assignments[i].execution_cost,steps+1,path+(op.name,))
            if nxt not in best or new<best[nxt]:
                best[nxt]=new
                heappush(queue,(*new,nxt))
    return None


def _fit_host(intent, op,poly):
    eligible=[h for h in intent.hosts if op.name in h.allowed_ops and h.max_degree>=len(poly)-1]
    return min(eligible,key=lambda h:(h.execution_cost,h.name)) if eligible else None


def compile_system(intent: Intent):
    """Exhaustively select a finite model family, then verify every safe edge.

    If the stated candidate budget truncates exploration, refuse any claim of
    optimality or unreachability, even if a plausible candidate was found.
    """
    if not isinstance(intent,Intent):
        raise SpecificationError('typed Intent required')
    p=intent.p
    counterexamples=[]
    pools=[]
    checked=0
    for op in intent.operations:
        pool,used,complete,cex=_enumerate_operation(intent,op,intent.candidate_budget-checked)
        checked+=used
        if cex is not None:counterexamples.append(cex)
        if not complete:
            return {'status':'refused_search_budget','candidates_examined':checked,'witness':{'reason':'incomplete_polynomial_enumeration','operation':op.name},'scope':'no mathematical impossibility or global optimality assertion'}
        if not pool:
            return {'status':'unreachable_declared_polynomial_family','candidates_examined':checked,'witness':cex,'scope':'only within the declared maximum degrees and invariant'}
        pools.append(pool)
    combination_count=math.prod(len(pool) for pool in pools)
    if combination_count>intent.candidate_budget-checked:
        return {'status':'refused_search_budget','candidates_examined':checked,'witness':{'reason':'incomplete_architecture_enumeration','combinations':combination_count},'scope':'no mathematical impossibility or global optimality assertion'}
    candidate_results=[]
    witnessed_reachable=False
    host_missing=False
    hosted_count=0
    # Full candidate product is finite and charged against the search budget.
    for polynomials in product(*pools):
        checked+=1
        hosts=tuple(_fit_host(intent,op,poly) for op,poly in zip(intent.operations,polynomials))
        if any(h is None for h in hosts):
            host_missing=True
            continue
        hosted_count+=1
        path=_shortest_path(intent,polynomials,hosts)
        if path is None:continue
        witnessed_reachable=True
        if path['execution_cost']>intent.total_execution_budget:continue
        architecture=[{'name':op.name,'coefficients':list(poly),'degree':len(poly)-1,
                       'host':h.name,'per_step_cost':h.execution_cost}
                      for op,poly,h in zip(intent.operations,polynomials,hosts)]
        key=(sum(len(poly)-1 for poly in polynomials),path['execution_cost'],
             len(path['operation_path']),
             tuple(tuple(poly) for poly in polynomials),
             tuple(h.name for h in hosts),tuple(path['operation_path']))
        candidate_results.append((key,architecture,path))
    if candidate_results:
        key,architecture,path=min(candidate_results,key=lambda z:z[0])
        # Redundant verification of all invariant edges and all examples.
        for op,entry in zip(intent.operations,architecture):
            poly=entry['coefficients']
            assert all(_eval(poly,x,p)==y for x,y in op.samples)
            assert all(_eval(poly,x,p) in intent.safe_states for x in intent.safe_states)
        obs={o.name:tuple(v%p for v in o.coefficients) for o in intent.observables}
        assert all(_eval(obs[name],path['state_path'][-1],p)==target for name,target in intent.goals)
        return {'status':'realizable','frame':intent.frame,'field_modulus':p,
                'architecture':architecture,'realization':path,
                'selected_structural_degree_sum':key[0],
                'candidates_examined':checked,
                'invariant_verified_on':len(intent.safe_states),
                'witness':counterexamples[:3],
                'scope':'finite complete declared polynomial family, untrusted hosts; mathematical construction only'}
    if witnessed_reachable:
        status='refused_execution_budget'
        witness={'reason':'reachable_but_over_budget','budget':intent.total_execution_budget}
    elif host_missing and hosted_count==0:
        status='unreachable_with_declared_hosts'
        witness={'reason':'some invariant-preserving constructions lack declared capable hosts'}
    else:
        status='unreachable_in_selected_hosted_family'
        witness={'reason':'exhaustive finite reachability and candidate enumeration found no goal state','first_counterexamples':counterexamples[:3]}
    return {'status':status,'candidates_examined':checked,'witness':witness,
            'scope':'complete only in enumerated polynomial+declared host family'}


def replay_receipt(intent: Intent,record: Mapping):
    """Recompute compiler result; unkeyed digest is integrity, not authentication."""
    if not isinstance(record,Mapping) or set(record)!={'schema','intent','result','sha256'}:
        return False
    try:
        raw={k:record[k] for k in ('schema','intent','result')}
        return (raw['schema']=='ifs.constructive-system-ground.v1' and
                _digest(raw)==record['sha256'] and
                raw['intent']==intent.record() and
                raw['result']==compile_system(intent))
    except (TypeError,ValueError,SpecificationError):
        return False


def receipt(intent: Intent):
    raw={'schema':'ifs.constructive-system-ground.v1','intent':intent.record(),
         'result':compile_system(intent)}
    return {**raw,'sha256':_digest(raw)}


def navigate_repeated(intent: Intent, selected: Mapping, operation_name: str, index: int, *, source=None):
    """Exact large-step navigation for a synthesized deterministic finite operation.

    Builds a full finite orbit first (O(|safe|) time/space); query is O(1) plus
    arithmetic on the decimal coordinate. This is not cheap model discovery.
    """
    if selected.get('status')!='realizable':
        raise SpecificationError('no admitted mathematical system')
    if type(index) is not int or index<0:
        raise SpecificationError('nonnegative integer coordinate required')
    x=intent.start if source is None else source
    if type(x) is not int or x not in intent.safe_states:
        raise SpecificationError('source violates invariant')
    matches=[entry for entry in selected['architecture'] if entry['name']==operation_name]
    if len(matches)!=1:
        raise SpecificationError('unknown operation')
    poly=matches[0]['coefficients']
    seen={}
    orbit=[]
    while x not in seen:
        seen[x]=len(orbit)
        orbit.append(x)
        x=_eval(poly,x,intent.p)
        if x not in intent.safe_states:
            raise AssertionError('invariant was not preserved')
    transient=seen[x]
    period=len(orbit)-transient
    reduced=index if index<len(orbit) else transient+(index-transient)%period
    return {'state':orbit[reduced],'transient':transient,'period':period,
            'precomputation_transitions':len(orbit),'reduced_coordinate':reduced,
            'scope':'finite orbit of a declared synthesized operator, not an external observation'}


def synthesize_terminal_phase(intent: Intent, result: Mapping,
                              phase_hosts, *, higher_coefficients=(1,), max_cost=100):
    """TCN-008 bridge: explicit observer renders terminal state as phase slope.

    Observer convention f(y)=terminal_state*y+sum higher_coefficients[j]*y^(j+3)
    is *requested*, not inferred from dynamics. Returns the existing TCN-008
    receipt, with its independent verifier and unauthenticated-host scope.
    Full p-point intention construction is charged O(p), not O(1).
    """
    if result.get('status') != 'realizable':
        raise SpecificationError('phase readout requires a realized mathematical Ground')
    if intent.p < 7 or not 1 <= len(higher_coefficients) <= 3 or any(type(c) is not int for c in higher_coefficients):
        raise SpecificationError('TCN-008 phase readout requires p>=7 and 1..3 higher coefficients')
    from intention_ground import make_intent, make_receipt, synthesize, verify_receipt
    terminal = result['realization']['state_path'][-1]
    coefficients=(0,terminal,0)+tuple(c%intent.p for c in higher_coefficients)
    phases=tuple(_eval(coefficients,y,intent.p) for y in range(intent.p))
    phase_intent=make_intent(intent.p,phases,max_cost=max_cost)
    artifact=make_receipt(phase_intent,tuple(phase_hosts))
    if not verify_receipt(artifact):
        raise ArithmeticError('TCN-008 phase receipt reconstruction failed')
    plan=synthesize(phase_intent,tuple(phase_hosts))
    return {'rendered_from_terminal_state':terminal,
            'observer_phase_coefficients':list(coefficients),
            'phase_intent_points':intent.p,
            'status':plan['status'],
            'phase_ground':plan['ground'],
            'phase_host':plan['selected_host'],
            'phase_receipt':artifact,
            'scope':'observer-declared readout; TCN-008 synthetic phase construction, not external execution'}
