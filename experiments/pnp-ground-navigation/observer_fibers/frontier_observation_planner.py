"""OFG-003: discover PNG-001 frontiers and plan exact conditional observer fibers.

Uses original PNG-001 min_fill_order, OFG-002 source replay and symbolic
inclusion-exclusion. Costs are explicit *declared work units*, not physical time.
No external observation or authentication is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from json import dumps

from pathlib import Path
import sys

# The original PNG-001 module is a sibling of the observer_fibers directory.
_PNG = str(Path(__file__).resolve().parent.parent)
if _PNG not in sys.path:
    sys.path.insert(0, _PNG)
from frontier_ground import min_fill_order  # noqa: E402

from separator_fiber_ground import (GroundRefusal, SeparatorSource, _digest,
    _rectangles, _union_count, _hidden_domains, _rank, _unrank,
    _witness_for_new, compile_ground, verify_ground,
    new_coordinates, old_coordinates, source_accepts)


@dataclass(frozen=True)
class Intention:
    n: int
    clauses: tuple[tuple[int, ...], ...]
    requested_vars: tuple[int, ...]
    # An observation offer charges a fixed integral cost for one separator bit.
    offers: tuple[tuple[int, int], ...] = ()


def _validate(q: Intention, max_separator: int, max_bag: int, max_states: int) -> None:
    if (type(q.n) is not int or not (2 <= q.n <= 4096)
        or any(type(x) is not int or x < 1 or x > q.n for x in q.requested_vars)
        or tuple(sorted(set(q.requested_vars))) != q.requested_vars
        or any(type(k) is not int or k < 1 or k > q.n or type(c) is not int or c < 0
               for k, c in q.offers)
        or len({v for v, _ in q.offers}) != len(q.offers)
        or any(not isinstance(cl, tuple) or any(type(x) is not int or not 1 <= abs(x) <= q.n
            for x in cl) for cl in q.clauses)
        or type(max_separator) is not int or not 1 <= max_separator <= 3
        or type(max_bag) is not int or max_bag < 2
        or type(max_states) is not int or max_states < 1):
        raise GroundRefusal('invalid intention, literal, offer, or finite budget')


def _primal(q):
    graph = {v:set() for v in range(1,q.n+1)}
    for cl in q.clauses:
        vs={abs(x) for x in cl}
        for v in vs:
            graph[v].update(vs-{v})
    return graph


def _components(graph, separator):
    sep=set(separator)
    pending=set(graph)-sep
    bags=[]
    while pending:
        first=min(pending); pending.remove(first)
        comp={first}; stack=[first]
        while stack:
            v=stack.pop()
            for u in sorted(graph[v]-sep):
                if u in pending:
                    pending.remove(u); comp.add(u); stack.append(u)
        bags.append(tuple(sorted(comp)))
    return tuple(sorted(bags))


def _frontier_candidates(q, graph, limit):
    """Use PNG-001 elimination order and replay its induced frontal separators."""
    order=min_fill_order(q.clauses, q.n)
    filled={v:set(neighbors) for v,neighbors in graph.items()}
    # Degenerate edgeless/contradictory sources still have a valid separator anchor.
    candidates={(min(graph),)}
    for pivot in order:
        neighbors=tuple(sorted(filled[pivot]))
        if 0 < len(neighbors) <= limit:
            candidates.add(neighbors)
        # Single-vertex cuts are useful even when their elimination frontier is wider.
        if graph[pivot]:
            candidates.add((pivot,))
        for a,b in combinations(neighbors,2):
            filled[a].add(b); filled[b].add(a)
        for a in neighbors:
            filled[a].discard(pivot)
        del filled[pivot]
    # Bounded unions allow cuts whose components are separated by two frontiers.
    small=sorted(candidates)
    if limit >= 2 and len(small) <= 128:
        for a,b in combinations(small,2):
            s=tuple(sorted(set(a)|set(b)))
            if len(s) <= limit:
                candidates.add(s)
    return tuple(sorted(candidates)), tuple(order)


def discover(q: Intention, *, max_separator=2, max_bag=8, max_local_states=200_000):
    """Choose a bounded cut from *derived* PNG-001 frontiers; refuse if none fits.

    This is an explicitly bounded heuristic, not optimal tree decomposition.
    Clause-graph connected components independently ensure factorization.
    """
    _validate(q,max_separator,max_bag,max_local_states)
    graph=_primal(q)
    candidates,order=_frontier_candidates(q,graph,max_separator)
    feasible=[]
    for s in candidates:
        bags=_components(graph,s)
        if not bags or any(len(b)+len(s)>max_bag for b in bags):
            continue
        states=(1 << len(s))*sum(1 << len(b) for b in bags)
        if states > max_local_states:
            continue
        # Worst bag width first, then local evaluation budget, then cut size.
        score=(max(len(b)+len(s) for b in bags),states,len(s),s)
        feasible.append((score,s,bags))
    if not feasible:
        raise GroundRefusal('no PNG frontier cut fits separator/bag/local-state budgets')
    _,separator,bags=min(feasible)
    return {'separator':separator,'bags':bags,
            'estimated_local_states':(1<<len(separator))*sum(1<<len(b) for b in bags),
            'min_fill_order':order,'candidate_count':len(candidates),
            'feasible_count':len(feasible)}


def _source(q, geometry):
    sep=tuple(geometry['separator']); bags=tuple(tuple(b) for b in geometry['bags'])
    target=set(q.requested_vars)
    old=[]; new=[]
    for j,bag in enumerate(bags):
        local_target=tuple(v for v in ((sep if j==0 else ()) + bag) if v in target)
        values=[]
        for mask in range(1 << (len(sep)+len(bag))):
            positions={v:i for i,v in enumerate(bag)}
            positions.update({v:len(bag)+i for i,v in enumerate(sep)})
            value=sum(bool(mask & (1<<positions[v])) << k for k,v in enumerate(local_target))
            values.append(value)
        old.append((0,)*len(values));new.append(tuple(values))
    # OFG-002 hidden source: conditional filters are applied to the verified rows.
    return SeparatorSource(q.n,sep,bags,q.clauses,tuple(old),tuple(new),False)


def _rows(ground, sep, observed, outcome):
    selected=[(sep.index(v), i) for i,v in enumerate(observed)]
    return [row for row in ground['rows'] if all(bool(row['separator']&(1<<pos))==
                  bool(outcome & (1<<i)) for pos,i in selected)]


def _condition(ground, sep, observed, outcome):
    rows=_rows(ground,sep,observed,outcome)
    rectangles=_rectangles(rows)
    return rows,rectangles,_union_count(rectangles)


def _nav_bound(rectangles, bags):
    """Conservative rank/unrank intersection-work upper estimate, not wall time."""
    if not rectangles:
        return 0
    # Every prefix query costs at most one pass over (2**R-1) subsets.
    domain_size=sum(len(d) for d in _hidden_domains(rectangles))
    # Rank and unrank together make at most 2*sum(domain sizes)+1
    # symbolic union calls; each visits at most (2**R-1)*bags cells.
    return (2**len(rectangles)-1)*len(bags)*(2*domain_size+1) + len(rectangles)*len(bags)


def _policy(ground, geometry, offers, navigation_unit, preparation_units):
    sep=geometry['separator']; bags=geometry['bags']
    costs={v:c for v,c in offers if v in sep}
    policies=[]
    offer_vars=tuple(sorted(costs))
    for r in range(len(offer_vars)+1):
        for observed in combinations(offer_vars,r):
            sizes=[]; works=[]
            for outcome in range(1 << len(observed)):
                _,rectangles,size=_condition(ground,sep,observed,outcome)
                sizes.append(size)
                works.append(_nav_bound(rectangles,bags))
            width=(max(sizes)-1).bit_length() if any(sizes) else 0
            observation_cost=sum(costs[v] for v in observed)
            bound=max(works,default=0)
            policies.append({'observe':observed,'observation_cost':observation_cost,
                'shared_preparation_units':preparation_units,
                'worst_navigation_work_upper':bound,'minimum_aux_bits_worst':width,
                'total_declared_cost':preparation_units+observation_cost+navigation_unit*bound,
                'outcome_fiber_sizes':tuple(sizes)})
    # We minimize declared aggregate cost; ties prefer fewer observations and bits.
    return min(policies,key=lambda p:(p['total_declared_cost'],len(p['observe']),
                                     p['minimum_aux_bits_worst'],p['observe'])), tuple(policies)


def _preparation_units(q, geometry, ground):
    # An explicit abstract upper count of local source clause checks in both
    # construction and independent verifier. Includes an enumeration charge
    # and one candidate inspection unit per sampled separator.
    sep=set(geometry['separator']); bags=geometry['bags']
    members={v:i for i,bag in enumerate(bags) for v in bag}
    bag_clauses=[0]*len(bags); global_clauses=0
    for clause in q.clauses:
        support={members[abs(l)] for l in clause if abs(l) not in sep}
        if len(support)>1:
            raise GroundRefusal('candidate separator crosses source clauses')
        if support:
            bag_clauses[next(iter(support))]+=1
        else:
            global_clauses+=1
    t=1<<len(sep)
    clause_checks=t*(global_clauses+sum((1<<len(b))*m for b,m in zip(bags,bag_clauses)))
    local=ground['local_states_checked']
    # Two traversals (producer and independent source checker) are charged.
    return {'local_enumeration_per_pass':local,
            'source_clause_checks_upper_per_pass':clause_checks,
            'discovery_candidates':geometry['candidate_count'],
            'total_preparation_units':2*(local+clause_checks)+geometry['candidate_count']}


def _wire(value):
    if isinstance(value, dict):
        return {k:_wire(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)):
        return [_wire(v) for v in value]
    return value


def compile_plan(q: Intention, *, max_separator=2,max_bag=8,max_local_states=200_000,
                 navigation_unit=1):
    if type(navigation_unit) is not int or navigation_unit < 0:
        raise GroundRefusal('navigation cost must be nonnegative integer')
    geometry=discover(q,max_separator=max_separator,max_bag=max_bag,
                      max_local_states=max_local_states)
    source=_source(q,geometry)
    ground=compile_ground(source,max_bag_width=max_bag,
                          max_separator_width=max_separator,max_local_states=max_local_states)
    verify_ground(source,ground)
    preparation=_preparation_units(q,geometry,ground)
    chosen,alternatives=_policy(ground,geometry,q.offers,navigation_unit,
                                preparation['total_preparation_units'])
    return _wire({'schema':'ifs.ofg.frontier-observation-plan.v3',
        'limits':(max_separator,max_bag,max_local_states,navigation_unit),
        'geometry':geometry,'source_identity':_digest(source),
        'preparation_ledger':preparation,
        'ground':ground,'selected_policy':chosen,'alternatives':alternatives})


def verify_plan(q: Intention, plan):
    """Independently reconstruct topology, original clauses, fibers and policy."""
    if type(plan) is not dict or plan.get('schema')!='ifs.ofg.frontier-observation-plan.v3':
        raise GroundRefusal('invalid plan schema')
    try:
        a,b,c,u=plan['limits']
        if type(u) is not int or u < 0:
            raise GroundRefusal('negative or invalid navigation price')
        geometry=discover(q,max_separator=a,max_bag=b,max_local_states=c)
        source=_source(q,geometry)
        verify_ground(source,plan['ground'])
        preparation=_preparation_units(q,geometry,plan['ground'])
        chosen,alternatives=_policy(plan['ground'],geometry,q.offers,u,
                                    preparation['total_preparation_units'])
        expected={'schema':'ifs.ofg.frontier-observation-plan.v3',
            'limits':(a,b,c,u),'geometry':geometry,'source_identity':_digest(source),
            'preparation_ledger':preparation,
            'ground':plan['ground'],'selected_policy':chosen,'alternatives':alternatives}
    except (KeyError,TypeError,ValueError,IndexError,OverflowError) as error:
        raise GroundRefusal('plan cannot be verified') from error
    try:
        identical=dumps(plan,sort_keys=True,separators=(',',':'),allow_nan=False)==dumps(
            _wire(expected),sort_keys=True,separators=(',',':'),allow_nan=False)
    except (ValueError,TypeError):
        identical=False
    if not identical:
        raise GroundRefusal('plan conflicts with source-reconstructed geometry or cost policy')
    return True


def _admitted(q,plan,observed,outcome, *, verify=False):
    if verify:
        verify_plan(q,plan)
    geom=plan['geometry']; source=_source(q,geom)
    if plan.get('source_identity')!=_digest(source):
        raise GroundRefusal('source identity changed')
    if observed != tuple(plan['selected_policy']['observe']):
        raise GroundRefusal('observation set differs from admitted plan')
    if type(outcome) is not int or not 0 <= outcome < (1<<len(observed)):
        raise GroundRefusal('unknown or malformed observation outcome')
    rows,rectangles,total=_condition(plan['ground'],geom['separator'],observed,outcome)
    return source,rows,rectangles,total


def observe_source_state(q,plan,assignment):
    """Test-only observation oracle: requires an externally supplied source state."""
    source=_source(q,plan['geometry'])
    if not source_accepts(source,assignment):
        raise GroundRefusal('oracle source state violates original clauses')
    return sum(bool(assignment & (1<<(v-1)))<<i
               for i,v in enumerate(plan['selected_policy']['observe']))


def encode(q,plan,assignment,outcome):
    observed=tuple(plan['selected_policy']['observe'])
    source,rows,rectangles,total=_admitted(q,plan,observed,outcome)
    if not source_accepts(source,assignment):
        raise GroundRefusal('invalid original source assignment')
    measured=sum(bool(assignment & (1<<(v-1)))<<i for i,v in enumerate(observed))
    if measured!=outcome:
        raise GroundRefusal('actual source state conflicts with observed separator values')
    coordinate=new_coordinates(source,assignment)
    code=_rank(rectangles,coordinate)
    if code>=total:
        raise GroundRefusal('invalid rank')
    return code


def decode(q,plan,outcome,code):
    observed=tuple(plan['selected_policy']['observe'])
    source,rows,rectangles,total=_admitted(q,plan,observed,outcome)
    if type(code) is not int or not 0<=code<total:
        raise GroundRefusal('supplement outside observed source fiber')
    coordinate=_unrank(rectangles,code)
    old=(0,)*len(source.bags)
    assignment=_witness_for_new(source,rows,old,coordinate)
    if (not source_accepts(source,assignment)
        or new_coordinates(source,assignment)!=coordinate
        or sum(bool(assignment & (1<<(v-1)))<<i for i,v in enumerate(observed))!=outcome):
        raise GroundRefusal('witness inconsistent with source or received observation')
    return assignment


def requested_projection(q,assignment):
    return tuple(int(bool(assignment&(1<<(v-1)))) for v in q.requested_vars)
