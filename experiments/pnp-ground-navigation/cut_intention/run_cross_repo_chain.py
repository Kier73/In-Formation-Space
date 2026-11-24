"""CIG-004 native cross-repository comparison, no substituted implementation.

Run on CI after checking out pinned Navigable-Compute into the PYTHONPATH.
The real PNG/SFI/OFG/NCR modules must import successfully or this exits nonzero.
"""
from __future__ import annotations
import json,sys
from pathlib import Path
from time import perf_counter_ns

THIS=Path(__file__).resolve().parent
PNP=THIS.parent
OFG=PNP/'observer_fibers'
for p in (PNP,OFG):
    if str(p) not in sys.path:sys.path.insert(0,str(p))

from chain_observer_ground import make_chain_source,compile_ground,source_reduce
from verify_chain_observer import verify
from frontier_ground import solve,brute_count
from morphic_sat import compile_ground as native_sfi
from morphic_verifier import verify as native_sfi_verify, independent_count
from frontier_observation_planner import Intention,discover,compile_plan,verify_plan
from navigable_compute.nonlinear_koopman import BooleanOperator,pullback


def run():
    source,cut=make_chain_source(depth=4)
    cert,_=compile_ground(source,cut)
    assert verify(source,cert)
    _,active,source_clauses=source_reduce(source)
    n=len(active)
    assert n==8
    start=perf_counter_ns()
    total,witness,ledger=solve(source_clauses,n)
    png_elapsed=perf_counter_ns()-start
    assert total==brute_count(source_clauses,n)==16
    assert witness is not None
    sfi,stats=native_sfi([tuple(x) for x in source_clauses],n)
    assert native_sfi_verify(sfi)['proven']
    assert independent_count(sfi,max_free=12)==16
    observer=cert['observer']+1
    offer=Intention(n,tuple(tuple(c) for c in source_clauses),(observer,),((observer,0),))
    topology=discover(offer,max_separator=2,max_bag=8,max_local_states=100000)
    plan=compile_plan(offer,max_separator=2,max_bag=8,max_local_states=100000)
    assert verify_plan(offer,plan)
    # Native NCR-007 Boolean-ring pullback: its OR-mask multiplication enforces
    # idempotence across overlapping variables in the four-stage chain.
    T=BooleanOperator(tuple(tuple(x) for x in cert['operator_rows']))
    native_pullbacks=0
    for p,coefficient in zip(cert['features']['basis'],cert['features']['matrix_rows']):
        lifted=pullback(tuple(p),T)
        expected=set()
        for i,feature in enumerate(cert['features']['basis']):
            if coefficient&(1<<i):expected.symmetric_difference_update(feature)
        assert lifted==tuple(sorted(expected))
        native_pullbacks+=1
    eventual=tuple(cert['future_alignment']['anf_masks'])
    assert pullback(eventual,T)==eventual
    for state in range(1<<n):
        nxt=T.apply(state)
        assert (nxt==state)==all(any(((state>>(abs(l)-1))&1)==int(l>0) for l in clause)
                                  for clause in source_clauses)
    return {'schema':'ifs.cig004.native-cross-repo.v1',
       'native_png_count':total,'native_png_source_factor_lookups':ledger['factor_lookups'],
       'native_png_wall_ms':round(png_elapsed/1e6,4),
       'native_sfi_registers':len(sfi['registers']),
       'native_sfi_gates':len(sfi['instructions']),
       'native_sfi_count':16,
       'native_ofg_separator':list(topology['separator']),
       'native_ofg_selected_probes':list(plan['selected_policy']['observe']),
       'native_ncr_symbolic_pullbacks_verified':native_pullbacks+1,
       'ncr_operator_exact_on_256_source_states':True,
       'cig_independent_original_source_verified':True}


if __name__=='__main__':print(json.dumps(run(),indent=2))
