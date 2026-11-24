"""CIG-006 actual native-integration check; no stubs or fallback paths.

Requires same-repo PNG-001/SFI-002/OFG-003 modules and GitHub-CI pinned
NCR-007 implementation. Their semantics are independently cross-compared on
the same source; report is not a physical host/transport attestation.
"""
from __future__ import annotations
import json,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
PNP=HERE.parent
OFG=PNP/'observer_fibers'
for d in (PNP,OFG):
    if str(d) not in sys.path:sys.path.insert(0,str(d))

from joint_intention_ground import make_branching_source
from nonlinear_observer_ground import source_reduce
from language_selector import compile_language
from verify_language_selector import verify as verify_language
from heavy_campaign import xor_chain,gates_80
from heavy_ground import compile_ground as exact_heavy
from verify_heavy_ground import verify as verify_heavy
from frontier_ground import solve as png_solve
from morphic_sat import compile_ground as sfi_compile
from morphic_verifier import verify as sfi_verify,independent_count
from frontier_observation_planner import Intention,compile_plan,verify_plan
from navigable_compute.nonlinear_koopman import BooleanOperator,pullback


def _span_xor(basis,coeff):
    terms=set()
    for i,row in enumerate(basis):
        if coeff&(1<<i):terms.symmetric_difference_update(row)
    return tuple(sorted(terms))


def run():
    source=make_branching_source();cut=[0,1,2,3,4]
    cert,_=compile_language(source,cut)
    assert verify_language(source,cert,intention=cert['intent'])
    proof,active,clauses=source_reduce(source)
    n=len(active)
    assert n==7
    models,witness,ledger=png_solve(clauses,n)
    assert models==8 and witness is not None
    gate,discovery=sfi_compile([tuple(row) for row in clauses],n)
    assert sfi_verify(gate)['proven']
    assert independent_count(gate,max_free=12)==8
    # OFG's native source-driven observation plan has a static-observation
    # objective; this is a cross-check, not the CIG temporal policy.
    intention=Intention(n,tuple(tuple(c) for c in clauses),(5,6,7),((5,3),(6,2),(7,6)))
    plan=compile_plan(intention,max_separator=2,max_bag=8,max_local_states=100_000)
    assert verify_plan(intention,plan)
    native_checks=0
    for cand in cert['candidates']:
        if cand['status']!='ADMITTED':continue
        operator=BooleanOperator(tuple(tuple(row) for row in cand['operator_rows']))
        for state in range(1<<n):
            true=sum((sum((state&mask)==mask for mask in row)&1)<<j
                     for j,row in enumerate(cand['operator_rows']))
            assert operator.apply(state)==true
        basis=tuple(tuple(row) for row in cand['feature_basis'])
        for poly,coefficient in zip(basis,cand['feature_matrix_rows']):
            assert pullback(poly,operator)==_span_xor(basis,coefficient)
            native_checks+=1
        # Verify all selected huge-time readouts with exact native symbolic
        # pullback closure, not huge-time physical iteration.
        for j,observer in enumerate(cert['intent']['targets']):
            assert (1<<observer,) in [tuple(x) for x in basis] or _span_xor(basis,cand['feature_read_masks'][j])==(1<<observer,)
    cross=[]
    for label,example in [('parity_sat',xor_chain(192)),('parity_unsat',xor_chain(192,True)),
                          ('nonlinear_count',gates_80())]:
        n,source_clauses,goal=example
        cmp,_=exact_heavy(source_clauses,n,intent=goal)
        assert verify_heavy(source_clauses,n,cmp,expected_intention=goal)
        count,model,info=png_solve(source_clauses,n)
        if goal=='#SAT':assert int(cmp['result']['count'])==count
        else:assert (cmp['result']['status']=='SAT')==(count>0)
        cross.append({'case':label,'native_png_models':str(count),
                      'native_png_factor_lookups':info['factor_lookups'],
                      'verified_source_ground':True})
    return {'schema':'ifs.cig006.native-cross-repo.v1',
      'native_png_fixedpoint_models':models,
      'native_sfi_fixedpoint_models':8,
      'native_sfi_verified_gates':len(gate['instructions']),
      'native_ofg_source_policy_verified':True,
      'native_ncr_source_pullbacks_checked':native_checks,
      'native_ncr_full_states_per_candidate':1<<len(active),
      'large_native_png_cross_checks':cross,
      'status':'source-verified; no actual distributed execution/physical measurement'}

if __name__=='__main__':print(json.dumps(run(),indent=2))
