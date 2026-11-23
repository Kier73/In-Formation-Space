"""Native reuse: require IFS PNG/SFI/OFG and pinned NCR-007 via PYTHONPATH.

Run only in a complete In-Formation-Space checkout with Navigable-Compute
available, e.g. under CIG-003 GitHub Actions. Never silently substitute stubs.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

THIS=Path(__file__).resolve().parent
PNG=THIS.parent
OFG=PNG/'observer_fibers'
for path in (PNG,OFG):
    if str(path) not in sys.path:sys.path.insert(0,str(path))

from nonlinear_observer_ground import make_gated_source,compile_ground,source_reduce
from verify_nonlinear_observer import verify
from frontier_ground import solve,brute_count, min_fill_order
from morphic_sat import compile_ground as sfi_compile
from morphic_verifier import verify as sfi_verify,independent_count
from frontier_observation_planner import Intention,compile_plan,verify_plan,discover
from navigable_compute.nonlinear_koopman import BooleanOperator,pullback


def run():
    source,cut=make_gated_source(groups=2)
    c,_=compile_ground(source,cut)
    assert verify(source,c)
    _,active,clauses=source_reduce(source)
    n=len(active)
    assert n==6
    cnf=[tuple(clause) for clause in clauses]
    count,w,ledger=solve(cnf,n)
    assert count==brute_count(cnf,n)==7
    assert w is not None
    sfi,sfi_cost=sfi_compile(cnf,n)
    assert sfi_verify(sfi)['proven']
    assert independent_count(sfi,max_free=12)==7
    observed=tuple(sorted(g['output_index']+1 for g in c['gates']))
    q=Intention(n,tuple(cnf),observed,tuple((v,0) for v in observed))
    topology=discover(q,max_separator=2,max_bag=8,max_local_states=200000)
    plan=compile_plan(q,max_separator=2,max_bag=8,max_local_states=200000)
    assert verify_plan(q,plan)
    assert tuple(topology['min_fill_order'])==tuple(min_fill_order(cnf,n))
    rows=[(1<<i,) for i in range(n)]
    for g in c['gates']:rows[g['output_index']]=tuple(int(mask) for mask in g['anf_masks'])
    operator=BooleanOperator(tuple(rows))
    for g in c['gates']:
        original=(1<<g['output_index'],)
        nonlinear=tuple(int(mask) for mask in g['anf_masks'])
        assert pullback(original,operator)==nonlinear
        assert pullback(nonlinear,operator)==nonlinear
    # Full projected source operator is an idempotent nonlinear rewrite.
    for state in range(1<<n):
        first=operator.apply(state)
        assert operator.apply(first)==first
        if all(any(((state>>(abs(l)-1))&1)==int(l>0) for l in cl) for cl in clauses):
            assert first==state
    return {'native_ifs_png_model_count':count,
            'native_ifs_png_factor_lookups':ledger['factor_lookups'],
            'native_ifs_sfi_registers':len(sfi['registers']),
            'native_ifs_sfi_gate_instructions':len(sfi['instructions']),
            'native_ofg_selected_separator':list(topology['separator']),
            'native_ofg_selected_probe':plan['selected_policy']['observe'],
            'native_ncr_pullbacks_checked':len(c['gates'])*2,
            'exhaustive_nonlinear_operator_source_states':1<<n,
            'source_count_exact':True,'independent_cig_verification':True}


if __name__=='__main__':print(json.dumps(run(),indent=2,default=list))
