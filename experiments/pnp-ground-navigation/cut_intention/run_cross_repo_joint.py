"""CIG-005 native integration: real CIG-004, PNG, SFI, OFG and pinned NCR-007.

CI must checkout Kier73/Navigable-Compute at a pinned SHA and set PYTHONPATH.
No mocks or local fallback for a missing native dependency are permitted.
"""
from __future__ import annotations
import json,sys
from pathlib import Path
from time import perf_counter_ns

HERE=Path(__file__).resolve().parent
PNP=HERE.parent
OFG=PNP/'observer_fibers'
for path in (PNP,OFG):
    if str(path) not in sys.path:sys.path.insert(0,str(path))

from joint_intention_ground import make_branching_source,compile_ground
from verify_joint_intention import verify
from nonlinear_observer_ground import source_reduce
from chain_observer_ground import compile_ground as chain_compile
from verify_chain_observer import verify as verify_chain
from frontier_ground import solve,brute_count
from morphic_sat import compile_ground as sfi_compile
from morphic_verifier import verify as sfi_verify, independent_count
from frontier_observation_planner import Intention,discover,compile_plan,verify_plan
from navigable_compute.nonlinear_koopman import BooleanOperator,pullback


def _xor_selected(polys,mask):
    result=set()
    for i,row in enumerate(polys):
        if mask&(1<<i):result.symmetric_difference_update(row)
    return tuple(sorted(result))


def run():
    source=make_branching_source();cut=[0,1,2,3,4]
    cert,_=compile_ground(source,cut)
    assert verify(source,cert)
    # The original CIG-004 single-observer constructor still qualifies this
    # branching CNF and its max-index output, preserving predecessor semantics.
    precursor,_=chain_compile(source,cut)
    assert verify_chain(source,precursor)
    _,active,clauses=source_reduce(source)
    n=len(active)
    assert n==7
    st=perf_counter_ns()
    models,witness,png_ledger=solve(clauses,n)
    elapsed=(perf_counter_ns()-st)/1e6
    assert models==brute_count(clauses,n)==8
    assert witness is not None
    sfi,discovery=sfi_compile([tuple(c) for c in clauses],n)
    assert sfi_verify(sfi)['proven']
    assert independent_count(sfi,max_free=12)==8
    # OFG's native discovery/planner has a distinct static CNF objective;
    # inclusion is an independent source-ground cross-check, not a replacement
    # for the nonlinear time-dependent CIG policy.
    objective=Intention(n,tuple(tuple(c) for c in clauses),(5,6,7),((5,3),(6,2),(7,6)))
    geom=discover(objective,max_separator=2,max_bag=8,max_local_states=100000)
    ofg=compile_plan(objective,max_separator=2,max_bag=8,max_local_states=100000)
    assert verify_plan(objective,ofg)
    native=BooleanOperator(tuple(tuple(row) for row in cert['operator_rows']))
    for state in range(1<<n):
        assert native.apply(state)==sum(
            ((sum((state&mask)==mask for mask in row)&1)<<i)
            for i,row in enumerate(cert['operator_rows']))
    base=[tuple(p) for p in cert['whole_future']['basis']]
    for feature,coefficient in zip(base,cert['whole_future']['matrix_rows']):
        assert pullback(feature,native)==_xor_selected(base,coefficient)
    for poly in cert['eventual']['stable_anf_masks']:
        assert pullback(tuple(poly),native)==tuple(poly)
    for name,poly in cert['policy']['offer_eventual_anf'].items():
        assert pullback(tuple(poly),native)==tuple(poly)
    return {'schema':'ifs.cig005.native-cross-repo.v1',
            'original_source_verified':True,
            'native_png_fixed_point_models':models,
            'native_png_factor_lookups':png_ledger['factor_lookups'],
            'native_png_elapsed_ms':round(elapsed,4),
            'native_sfi_fixed_point_models':8,
            'native_sfi_extracted_gates':len(sfi['instructions']),
            'native_ofg_separator':list(geom['separator']),
            'native_ofg_selected':list(ofg['selected_policy']['observe']),
            'native_ncr_pullbacks_verified':len(base)+
                len(cert['eventual']['stable_anf_masks'])+
                len(cert['policy']['offer_eventual_anf']),
            'native_ncr_operator_source_states_checked':1<<n,
            'native_cig004_original_source_verified':True}


if __name__=='__main__':print(json.dumps(run(),indent=2))
