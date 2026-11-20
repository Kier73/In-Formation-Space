"""TCN-009 full-family tests, independent exhaustive oracle controls."""
import hashlib
import json
import unittest

from system_ground import (Intent, Operation, Observable, Host, SpecificationError,
                           _eval, compile_system, receipt, replay_receipt,
                           navigate_repeated, synthesize_terminal_phase)


def crafted(*, degree=2, hosts=None, budget=20, search_budget=2000, goals=(('identity',1),)):
    # Required observations alone imply f=3x+5; it maps safe state 4 -> 3
    # and violates the invariant. A quadratic completion repairs it.
    return Intent(7,'safe.ternary', (1,2,4),4,
                  (Operation('control',((1,1),(2,4)),degree),),
                  (Observable('identity',(0,1)),Observable('square',(0,0,1))),
                  goals,
                  hosts or (Host('quadratic',2,('control',),1),),
                  budget, search_budget)


def cube_system(*, hosts=None, budget=20):
    p=11
    return Intent(p,'nonzero.element',tuple(range(1,p)),2,
                  (Operation('scale',((0,0),(1,2),(2,4)),1),
                   Operation('cube',((0,0),(1,1),(2,8),(3,5)),3)),
                  (Observable('identity',(0,1)),Observable('square',(0,0,1))),
                  (('identity',6),('square',3)),
                  hosts or (Host('scalar',1,('scale',),1),Host('higher',3,('cube',),1)),
                  budget,2000)


class ConstructiveSystemTests(unittest.TestCase):
    def test_invariant_constructs_quadratic_ground(self):
        spec=crafted()
        result=compile_system(spec)
        self.assertEqual(result['status'],'realizable')
        self.assertEqual(result['architecture'][0]['degree'],2)
        self.assertEqual(result['architecture'][0]['coefficients'],[2,4,2])
        self.assertEqual(result['realization']['state_path'],[4,1])
        self.assertEqual(result['invariant_verified_on'],3)
        self.assertTrue(result['witness'])
        self.assertEqual(result['witness'][0]['reason'],'invariant_violation')

    def test_lower_degree_refusal_and_richer_host_rescue(self):
        r=compile_system(crafted(degree=1))
        self.assertEqual(r['status'],'unreachable_declared_polynomial_family')
        self.assertEqual(r['witness']['input'],4)
        base=crafted(hosts=(Host('linear',1,('control',),1),))
        self.assertEqual(compile_system(base)['status'],'unreachable_with_declared_hosts')
        self.assertEqual(compile_system(crafted())['status'],'realizable')

    def test_observables_are_goal_semantics(self):
        r=compile_system(crafted(goals=(('identity',1),('square',1))))
        self.assertEqual(r['status'],'realizable')
        fail=compile_system(crafted(goals=(('identity',1),('square',2))))
        self.assertEqual(fail['status'],'unreachable_in_selected_hosted_family')

    def test_multiple_operations_hosts_and_full_trace(self):
        spec=cube_system()
        r=compile_system(spec)
        self.assertEqual(r['status'],'realizable')
        arch={e['name']:e for e in r['architecture']}
        self.assertEqual(arch['cube']['coefficients'],[0,0,0,1])
        self.assertEqual(arch['scale']['coefficients'],[0,2])
        self.assertEqual(arch['cube']['host'],'higher')
        self.assertEqual(arch['scale']['host'],'scalar')
        states=r['realization']['state_path']
        self.assertEqual(states[0],2)
        self.assertEqual(states[-1],6)
        self.assertTrue(all(state in spec.safe_states for state in states))
        for index,name in enumerate(r['realization']['operation_path']):
            self.assertEqual(states[index+1],_eval(arch[name]['coefficients'],states[index],spec.p))

    def test_host_changes_actuation_cost_not_semantics(self):
        spec=cube_system(hosts=(Host('slow-cube',3,('cube',),20),Host('cheap-scale',1,('scale',),1)))
        r=compile_system(spec)
        self.assertEqual(r['status'],'realizable')
        self.assertEqual(r['realization']['operation_path'],['scale']*8)
        self.assertEqual(r['realization']['execution_cost'],8)

    def test_budget_refuses_not_unreachable(self):
        r=compile_system(crafted(budget=0))
        self.assertEqual(r['status'],'refused_execution_budget')
        self.assertIn('reachable',r['witness']['reason'])

    def test_search_budget_refuses_even_if_earlier_candidate_succeeds(self):
        r=compile_system(crafted(search_budget=3))
        self.assertEqual(r['status'],'refused_search_budget')
        self.assertNotIn('architecture',r)

    def test_no_solution_in_polynomial_family_yields_exact_counterexample(self):
        # x^4 on 5 distinct points is impossible for degree <=3.
        spec=Intent(11,'field',tuple(range(11)),1,
                    (Operation('quartic',tuple((x,pow(x,4,11)) for x in range(5)),3),),
                    (Observable('identity',(0,1)),),(('identity',2),),
                    (Host('cubic',3,('quartic',),1),))
        r=compile_system(spec)
        self.assertEqual(r['status'],'unreachable_declared_polynomial_family')
        self.assertEqual(r['witness']['reason'],'interpolation_obstruction')
        self.assertEqual(len(r['witness']['examples']),5)

    def test_conflicting_observation_samples(self):
        spec=Intent(7,'field',tuple(range(7)),1,
                    (Operation('bad',((1,2),(1,3)),2),),
                    (Observable('id',(0,1)),),(('id',2),),(Host('host',2,('bad',),1),))
        r=compile_system(spec)
        self.assertEqual(r['status'],'unreachable_declared_polynomial_family')
        self.assertEqual(r['witness']['reason'],'conflicting_transition_example')

    def test_contradictory_observable_goals(self):
        spec=crafted(goals=(('identity',1),('identity',2)))
        self.assertEqual(compile_system(spec)['status'],'unreachable_in_selected_hosted_family')

    def test_full_independent_polynomial_brute(self):
        # Enumerate EVERY degree<=2 map on F7: coefficient tuple a,b,c.
        # Accept all that satisfy examples, preserve invariant and reach 1 from 4.
        valid=[]
        safe={1,2,4}
        for a in range(7):
            for b in range(7):
                for c in range(7):
                    co=(a,b,c)
                    if _eval(co,1,7)!=1 or _eval(co,2,7)!=4:continue
                    if any(_eval(co,x,7) not in safe for x in safe):continue
                    x=4
                    can=False
                    for _ in range(4):
                        if x==1:can=True;break
                        x=_eval(co,x,7)
                    if can:valid.append(co)
        self.assertEqual(valid,[(2,4,2)])
        self.assertEqual(compile_system(crafted())['architecture'][0]['coefficients'],list(valid[0]))

    def test_hundred_digit_nonlinear_orbit_navigation(self):
        spec=cube_system()
        r=compile_system(spec)
        self.assertEqual(r['status'],'realizable')
        orbit=navigate_repeated(spec,r,'cube',10**100+123)
        self.assertLessEqual(orbit['precomputation_transitions'],len(spec.safe_states))
        self.assertLess(orbit['reduced_coordinate'],len(spec.safe_states))
        self.assertEqual(orbit['state'],navigate_repeated(spec,r,'cube',orbit['reduced_coordinate'])['state'])
        self.assertEqual(orbit['period'],4)
        self.assertEqual(orbit['transient'],0)

    def test_replay_and_recomputed_hash_tamper(self):
        spec=crafted()
        r=receipt(spec)
        self.assertTrue(replay_receipt(spec,r))
        bad=json.loads(json.dumps(r))
        bad['result']['architecture'][0]['coefficients']=[1,0,0]
        without={k:bad[k] for k in ('schema','intent','result')}
        bad['sha256']=hashlib.sha256(json.dumps(without,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        self.assertFalse(replay_receipt(spec,bad))

    def test_cross_intent_replay_refused(self):
        self.assertFalse(replay_receipt(crafted(budget=0),receipt(crafted())))

    def test_receipt_survives_json_roundtrip(self):
        spec=crafted()
        serialized=json.loads(json.dumps(receipt(spec)))
        self.assertTrue(replay_receipt(spec,serialized))

    def test_phase_readout_reuses_tcn008_realizer(self):
        from intention_ground import Host as PhaseHost, verify_receipt as verify_phase_receipt, SynthesizedGround
        import numpy as np
        spec=cube_system()
        plan=compile_system(spec)
        host=PhaseHost('cubic-renderer',3,(6,),capacity=100)
        phase=synthesize_terminal_phase(spec,plan,(host,),higher_coefficients=(4,),max_cost=100)
        self.assertEqual(phase['status'],'realizable')
        self.assertEqual(phase['rendered_from_terminal_state'],6)
        self.assertEqual(phase['phase_ground']['coefficients'],[0,6,0,4])
        self.assertTrue(verify_phase_receipt(phase['phase_receipt']))
        g=SynthesizedGround(spec.p,tuple(phase['phase_ground']['coefficients']),6)
        self.assertLess(float(np.max(abs(g.full_vector()-g.dense_independent()))),1e-12)

    def test_phase_readout_refuses_unsupported_host(self):
        from intention_ground import Host as PhaseHost
        spec=cube_system()
        plan=compile_system(spec)
        host=PhaseHost('quadratic-only',2,(6,),capacity=100)
        phase=synthesize_terminal_phase(spec,plan,(host,),higher_coefficients=(4,))
        self.assertEqual(phase['status'],'unreachable_with_declared_hosts')

    def test_invalid_specs(self):
        base=crafted()
        with self.assertRaises(SpecificationError):
            Intent(9,base.frame,base.safe_states,base.start,base.operations,base.observables,base.goals,base.hosts)
        with self.assertRaises(SpecificationError):
            Intent(7,base.frame,base.safe_states,3,base.operations,base.observables,base.goals,base.hosts)
        with self.assertRaises(SpecificationError):
            navigate_repeated(base,compile_system(base),'control',-1)
        with self.assertRaises(SpecificationError):
            navigate_repeated(base,compile_system(base),'unknown',100)


if __name__=='__main__':
    unittest.main()
