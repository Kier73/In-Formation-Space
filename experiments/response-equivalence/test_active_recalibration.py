"""RE-013 source integrity, action scope, independent renewal and counterexamples."""
import copy
import unittest

from active_recalibration import (
    ACTIONS, RenewalError, MAX_JOINT_NONDETECTION, bound, choose_plan,
    evaluate, old_fixture, observer_report, registration, sha, signed_plan,
    verify_prior, verify_revision, sign, _verify_verifier_signed,
)
from applicability_monitor import (ApplicabilityError, plan as monitor_plan, observer as monitor_observer, assess)


class RE013Tests(unittest.TestCase):
    def setUp(self):
        self.reg = registration(deterministic=True)
        self.prior = old_fixture(self.reg)
        self.p = signed_plan(self.reg, self.prior['old_certificate']['digest'],
                             sha(self.prior['suspension']))
        self.a = observer_report(self.reg, self.p, 'A')
        self.b = observer_report(self.reg, self.p, 'B')

    def run_eval(self, *, reg=None, prior=None, plan=None, a=None, b=None, accept=True):
        return evaluate(reg or self.reg, prior or self.prior, plan or self.p,
                        a or self.a, b or self.b, assumptions_accepted=accept)

    def test_old_certificate_is_independently_suspended(self):
        rec = verify_prior(self.reg, self.prior)
        self.assertIn('event_population_shift', rec['reasons'])
        self.assertEqual(rec['status'], 'suspended')

    def test_plan_is_unexecuted_until_new_signed_reports(self):
        p = choose_plan()
        self.assertEqual(p['status'], 'planned_only')
        self.assertEqual(p['protocol'], 'passive')
        self.assertEqual(p['observation_cost'], 68)
        self.assertEqual(p['intervention_cost'], 0)
        self.assertEqual(p['predicted_positive_counts'], {'ordinary':24,'edge':24})
        self.assertEqual(p['predicted_sham_count'], 20)
        self.assertLess(p['predicted_zero_miss_upper'], MAX_JOINT_NONDETECTION)

    def test_stimulated_cheaper_observation_but_different_scope(self):
        passive, stimulated = choose_plan(), choose_plan('stimulated')
        self.assertLess(stimulated['observation_cost'], passive['observation_cost'])
        self.assertGreater(stimulated['intervention_cost'],passive['intervention_cost'])
        self.assertNotEqual(stimulated['claim_scope'],passive['claim_scope'])
        self.assertTrue(all(ACTIONS[a][1]=='stimulated' for a in stimulated['actions'] if a!='sham'))

    def test_search_budget_blocks_miraculous_calibration(self):
        with self.assertRaisesRegex(RenewalError,'no valid'):
            choose_plan(max_batches=2)

    def test_rejects_invalid_target_protocol(self):
        with self.assertRaises(RenewalError):choose_plan('unknown')

    def test_initial_evidence_fails_without_explicit_assumptions(self):
        result=self.run_eval(accept=False)
        self.assertEqual(result['status'],'renewal_not_admitted')
        self.assertIsNone(result['new_certificate'])
        self.assertEqual(len(result['history']),1)
        self.assertFalse(result['original_certificate_restored'])

    def test_verified_new_revision_preserves_predecessor(self):
        result=self.run_eval()
        self.assertEqual(result['status'],'conditional_revision_issued')
        self.assertEqual(result['counts']['ordinary']['n'],24)
        self.assertEqual(result['counts']['edge']['n'],24)
        self.assertEqual(result['counts']['sham'],{'n':20,'false_positive':0})
        self.assertEqual([x['revision'] for x in result['history']],[1,2])
        self.assertEqual(result['history'][0]['status'],'suspended')
        self.assertNotEqual(result['new_certificate']['digest'],self.prior['old_certificate']['digest'])
        self.assertEqual(verify_revision(self.reg,self.prior,self.p,self.a,self.b,result,
                          expected_protocol='passive')['revision'],2)
        self.assertIsNone(result['physical_detection_guarantee'])
        self.assertIsNone(result['adversarial_detection_guarantee'])
        self.assertFalse(result['hardware_identity_established'])

    def test_verifier_is_distinct_from_source_and_observers(self):
        result=self.run_eval()
        self.assertEqual(result['new_certificate']['role'],'V')
        self.assertNotEqual(self.reg['key_ids']['V'],self.reg['key_ids']['S'])

    def test_one_observer_miss_is_covered_by_other(self):
        a=observer_report(self.reg,self.p,'A',missing=((0,0),))
        result=self.run_eval(a=a)
        self.assertEqual(result['counts']['ordinary']['joint_misses'],0)
        self.assertEqual(result['status'],'conditional_revision_issued')

    def test_joint_miss_revokes_renewal(self):
        a=observer_report(self.reg,self.p,'A',missing=((0,0),))
        b=observer_report(self.reg,self.p,'B',missing=((0,0),))
        result=self.run_eval(a=a,b=b)
        self.assertEqual(result['counts']['ordinary']['joint_misses'],1)
        self.assertEqual(result['status'],'renewal_not_admitted')
        self.assertIsNone(result['new_certificate'])

    def test_unavailable_is_not_negative_measurement(self):
        a=observer_report(self.reg,self.p,'A',unavailable=((0,0),))
        b=observer_report(self.reg,self.p,'B',unavailable=((0,0),))
        self.assertEqual(a['records'][0]['body']['observations'][0]['status'],'unavailable')
        self.assertIsNone(a['records'][0]['body']['observations'][0]['event_id'])
        self.assertEqual(self.run_eval(a=a,b=b)['status'],'renewal_not_admitted')

    def test_sham_false_positive_blocks_revision(self):
        a=observer_report(self.reg,self.p,'A',false_positive=((6,1),))
        result=self.run_eval(a=a)
        self.assertEqual(result['counts']['sham']['false_positive'],1)
        self.assertIsNone(result['new_certificate'])

    def test_sensor_replacement_cannot_inherit_old_claim(self):
        changed=observer_report(self.reg,self.p,'A',sensor='replacement-A@2')
        with self.assertRaisesRegex(RenewalError,'scope'):
            self.run_eval(a=changed)

    def test_stimulated_measurements_cannot_certify_passive_detection(self):
        sp=signed_plan(self.reg,self.prior['old_certificate']['digest'],
                       sha(self.prior['suspension']), protocol='stimulated')
        a=observer_report(self.reg,sp,'A')
        b=observer_report(self.reg,sp,'B')
        self.assertGreater(a['records'][-1]['body']['state_after'],0)
        result=evaluate(self.reg,self.prior,sp,a,b,assumptions_accepted=True)
        self.assertEqual(result['protocol'],'stimulated')
        with self.assertRaisesRegex(RenewalError,'protocol scope'):
            verify_revision(self.reg,self.prior,sp,a,b,result,expected_protocol='passive')
        self.assertEqual(verify_revision(self.reg,self.prior,sp,a,b,result,
                         expected_protocol='stimulated')['protocol'],'stimulated')

    def test_mutated_invalidation_commitment_rejected_even_if_resigned(self):
        body=copy.deepcopy(self.p['body']);body['invalidation_digest']='f'*64
        p=sign(self.reg,'S','renewal_plan',body)
        with self.assertRaisesRegex(RenewalError,'binding'):
            self.run_eval(plan=p)

    def test_attacker_cannot_replace_optimizer_policy_with_valid_source_signature(self):
        body=copy.deepcopy(self.p['body']);body['proposal']['observation_cost']=1
        p=sign(self.reg,'S','renewal_plan',body)
        with self.assertRaisesRegex(RenewalError,'policy'):
            self.run_eval(plan=p)

    def test_prior_certificate_tamper_rejected(self):
        p=copy.deepcopy(self.prior)
        p['old_certificate']['body']['max_conditional_miss']=0.99
        with self.assertRaises(ApplicabilityError):
            self.run_eval(prior=p)

    def test_suspension_evidence_cannot_be_rewritten(self):
        p=copy.deepcopy(self.prior)
        p['suspension']['status']='conditionally_applicable'
        with self.assertRaisesRegex(RenewalError,'suspension'):
            self.run_eval(prior=p)

    def test_not_suspended_certificate_cannot_be_renewed_as_suspended(self):
        p=copy.deepcopy(self.prior)
        healthy = monitor_plan(self.reg,mode='baseline')
        p['monitor_plan']=healthy
        p['monitor_A']=monitor_observer(self.reg,healthy,'A')
        p['monitor_B']=monitor_observer(self.reg,healthy,'B')
        p['suspension']=assess(p['old_certificate'],self.reg,
           p['baseline']['S'],p['baseline']['A'],p['baseline']['B'],healthy,
           p['monitor_A'],p['monitor_B'],assumptions_accepted=True)
        self.assertEqual(p['suspension']['status'],'conditionally_applicable')
        with self.assertRaisesRegex(RenewalError,'suspension'):
            self.run_eval(prior=p)

    def test_missing_signed_batch_is_fatal(self):
        a=copy.deepcopy(self.a);a['records'].pop(2)
        with self.assertRaisesRegex(RenewalError,'incomplete'):
            self.run_eval(a=a)

    def test_missing_signed_seal_is_fatal(self):
        a=copy.deepcopy(self.a);a['seal']=None
        with self.assertRaises(ApplicabilityError):self.run_eval(a=a)

    def test_reordered_batches_fail_closed(self):
        a=copy.deepcopy(self.a);a['records'][1],a['records'][2]=a['records'][2],a['records'][1]
        with self.assertRaisesRegex(RenewalError,'provenance'):
            self.run_eval(a=a)

    def test_signed_history_fork_is_rejected(self):
        a=copy.deepcopy(self.a)
        body=copy.deepcopy(a['records'][1]['body']);body['parent']='f'*64
        a['records'][1]=sign(self.reg,'A','renewal_batch',body)
        with self.assertRaisesRegex(RenewalError,'provenance'):
            self.run_eval(a=a)

    def test_rehash_cannot_replace_hmac(self):
        a=copy.deepcopy(self.a)
        a['records'][0]['body']['observations'][0]['status']='not_detected'
        a['records'][0]['body']['observations'][0]['event_id']=None
        a['records'][0]['digest']=sha({k:v for k,v in a['records'][0].items() if k!='digest'})
        with self.assertRaisesRegex(ApplicabilityError,'HMAC'):
            self.run_eval(a=a)

    def test_signed_event_identity_mismatch_is_rejected(self):
        a=copy.deepcopy(self.a)
        body=copy.deepcopy(a['records'][0]['body']);body['observations'][0]['event_id']='0'*64
        a['records'][0]=sign(self.reg,'A','renewal_batch',body)
        with self.assertRaisesRegex(RenewalError,'correspondence'):
            self.run_eval(a=a)

    def test_forged_control_outcome_is_rejected_after_incorrect_evidence(self):
        a=copy.deepcopy(self.a)
        body=copy.deepcopy(a['records'][6]['body']);body['observations'][0]['event_id']='f'*64
        body['observations'][0]['status']='detected'
        a['records'][6]=sign(self.reg,'A','renewal_batch',body)
        with self.assertRaisesRegex(RenewalError,'correspondence'):
            self.run_eval(a=a)

    def test_stimulated_state_forgery_rejected(self):
        sp=signed_plan(self.reg,self.prior['old_certificate']['digest'],sha(self.prior['suspension']),protocol='stimulated')
        a=observer_report(self.reg,sp,'A');b=observer_report(self.reg,sp,'B')
        record=copy.deepcopy(a['records'][0]['body']);record['state_after']=0
        a['records'][0]=sign(self.reg,'A','renewal_batch',record)
        with self.assertRaisesRegex(RenewalError,'intervention state'):
            evaluate(self.reg,self.prior,sp,a,b,assumptions_accepted=True)

    def test_tampered_verifier_revision_rejected(self):
        result=self.run_eval()
        bad=copy.deepcopy(result)
        bad['new_certificate']['body']['conditional_simultaneous_upper']=0.0
        with self.assertRaisesRegex(RenewalError,'altered'):
            verify_revision(self.reg,self.prior,self.p,self.a,self.b,bad)

    def test_malicious_verifier_key_substitution_fails(self):
        result=self.run_eval()
        reg=copy.deepcopy(self.reg)
        reg['keys']['V']='00'*32
        with self.assertRaises(RenewalError):
            _verify_verifier_signed(result['new_certificate'],reg)

    def test_conditional_bound_restricts_low_sample_counts(self):
        self.assertGreater(bound(8,8), MAX_JOINT_NONDETECTION)
        self.assertLess(bound(24,24), MAX_JOINT_NONDETECTION)


if __name__ == '__main__':
    unittest.main()
