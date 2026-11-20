"""TCN-009 deterministic research report (no timing claims)."""
import json
from system_ground import (Intent,Operation,Observable,Host,compile_system,
                           navigate_repeated,receipt,replay_receipt,synthesize_terminal_phase)
from intention_ground import Host as PhaseHost, verify_receipt as phase_verify


def report():
    p=7
    basis=Intent(p,'safe.ternary',(1,2,4),4,
        (Operation('control',((1,1),(2,4)),2),),
        (Observable('identity',(0,1)),Observable('square',(0,0,1))),
        (('identity',1),('square',1)),
        (Host('polynomial',2,('control',),1),))
    exact=compile_system(basis)
    witness=receipt(basis)
    linear=Intent(p,basis.frame,basis.safe_states,basis.start,
        (Operation('control',((1,1),(2,4)),1),),basis.observables,basis.goals,basis.hosts)
    linear_status=compile_system(linear)
    scarce=Intent(p,basis.frame,basis.safe_states,basis.start,basis.operations,
        basis.observables,basis.goals,basis.hosts,candidate_budget=3)
    q=11
    cubic=Intent(q,'nonzero.element',tuple(range(1,q)),2,
        (Operation('scale',((0,0),(1,2),(2,4)),1),
         Operation('cube',((0,0),(1,1),(2,8),(3,5)),3)),
        (Observable('identity',(0,1)),Observable('square',(0,0,1))),
        (('identity',6),('square',3)),
        (Host('scalar',1,('scale',),1),Host('higher',3,('cube',),1)),
        total_execution_budget=40)
    compiled=compile_system(cubic)
    huge=navigate_repeated(cubic,compiled,'cube',10**100+123)
    readout=synthesize_terminal_phase(cubic,compiled,(PhaseHost('phase-cubic',3,(6,)),),higher_coefficients=(4,))
    impossible=Intent(11,'field',tuple(range(11)),1,
        (Operation('quartic',tuple((x,pow(x,4,11)) for x in range(5)),3),),
        (Observable('identity',(0,1)),),(('identity',2),),
        (Host('degree-three',3,('quartic',),1),))
    return {'experiment':'TCN-009','scope':'bounded enumerated finite-field computational-system intentions',
       'invariant_completion':{'status':exact['status'],
           'selected_polynomial':exact['architecture'][0]['coefficients'],
           'state_path':exact['realization']['state_path'],
           'first_rejected_map':exact['witness'][0],
           'mathematical_receipt_reconstructed':replay_receipt(basis,witness),
           'linear_only':linear_status['status'],
           'search_budget_guard':compile_system(scarce)['status']},
       'composite_system':{'status':compiled['status'],
           'architecture':compiled['architecture'],'path':compiled['realization'],
           'invariant_states_checked':compiled['invariant_verified_on'],
           'hundred_digit_nonlinear_orbit':huge},
       'terminal_phase_adapter':{
           'tcn008_status':readout['status'],'phase_coefficients':readout['phase_ground']['coefficients'],
           'tcn008_mathematical_receipt_reconstructed':phase_verify(readout['phase_receipt']),
           'host_authenticated':False},
       'unreachable_degree_three_family':compile_system(impossible),
       'cost_accounting':'search counts full candidate polynomial programs; reachability enumerates finite safe states; long repeat precomputes finite orbit; full p-point phase output materializes p residues',
       'external_realization_witnessed':False,'authenticated_hosts':False}


if __name__=='__main__':
    print(json.dumps(report(),indent=2,sort_keys=True))
