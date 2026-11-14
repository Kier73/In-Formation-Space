"""RE-011 regression: controlled faults, calibration assumptions, and forgeries."""
import copy
import math
import unittest

from detection_calibration import (
    CalibrationError, POSITIVE, SHAM, TOTAL, _base, _key, _sign,
    enrollment, fixture, produce_source, produce_observer, reconstruct, sha,
    upper_binomial_miss, verify_log, event_id,
)

class DetectionCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.reg = enrollment(deterministic=True)
        self.source = produce_source(self.reg)
        self.a = produce_observer(self.source, self.reg, 'A', 'complementary_dropouts')
        self.b = produce_observer(self.source, self.reg, 'B', 'complementary_dropouts')

    def test_source_declares_exact_sham_and_positive_scope(self):
        records = verify_log(self.source, self.reg, 'S')
        self.assertEqual(len(records), TOTAL)
        self.assertEqual(sum(x['injected'] for x in records), POSITIVE)
        self.assertEqual(sum(not x['injected'] for x in records), SHAM)

    def test_complementary_pattern_yields_no_joint_miss(self):
        result = reconstruct(self.source, self.a, self.b, self.reg)
        c = result['counts']
        self.assertEqual((c['A_non_detection'],c['B_non_detection'],c['joint_non_detection']), (12,12,0))
        self.assertIsNone(result['conditional_95pct_one_sided_upper_miss'])
        self.assertFalse(result['physical_injections_verified'])

    def test_common_mode_same_marginals_but_joint_miss_twelve(self):
        a = produce_observer(self.source, self.reg, 'A','common_mode_dropouts')
        b = produce_observer(self.source, self.reg, 'B','common_mode_dropouts')
        counts = reconstruct(self.source,a,b,self.reg)['counts']
        self.assertEqual((counts['A_non_detection'], counts['B_non_detection']), (12,12))
        self.assertEqual(counts['joint_non_detection'], 12)
        self.assertEqual(reconstruct(self.source,a,b,self.reg)['joint_non_detection_trials'],list(range(0,60,5)))

    def test_colluding_reports_are_valid_signed_non_detections(self):
        a = produce_observer(self.source,self.reg,'A','colluding_silence')
        b = produce_observer(self.source,self.reg,'B','colluding_silence')
        r = reconstruct(self.source,a,b,self.reg)
        self.assertEqual(r['counts']['joint_non_detection'],60)
        self.assertIsNone(r['adversarial_miss_bound'])

    def test_iid_bounds_never_enabled_implicitly(self):
        self.assertIsNone(fixture()[2]['conditional_95pct_one_sided_upper_miss'])
        with self.assertRaisesRegex(CalibrationError,'Boolean'):
            reconstruct(self.source,self.a,self.b,self.reg,iid_assumed='yes')

    def test_iid_bound_is_conditional_and_joint_not_product(self):
        complementary=fixture('complementary_dropouts',iid_assumed=True)[2]
        common=fixture('common_mode_dropouts',iid_assumed=True)[2]
        a=complementary['conditional_95pct_one_sided_upper_miss']
        b=common['conditional_95pct_one_sided_upper_miss']
        self.assertEqual(a['A'],b['A'])
        self.assertEqual(a['B'],b['B'])
        self.assertLess(a['joint'], b['joint'])
        self.assertNotEqual(b['joint'], b['A']*b['B'])
        self.assertFalse(common['independence_between_observers_verified'])

    def test_binomial_zero_misses_matches_exact_closed_form(self):
        upper=upper_binomial_miss(0,60)
        exact=1-0.05**(1/60)
        self.assertAlmostEqual(upper,exact,places=12)

    def test_binomial_all_misses_is_one(self):
        self.assertEqual(upper_binomial_miss(60,60),1.0)

    def test_binomial_one_sided_monotone_in_count(self):
        self.assertLess(upper_binomial_miss(0,60),upper_binomial_miss(12,60))

    def test_binomial_rejects_wrong_shape(self):
        for args in [(-1,60), (61,60), (0,0), (False,60), (0,True)]:
            with self.assertRaises(ValueError):upper_binomial_miss(*args)

    def test_sham_false_positive_is_separate_from_missed_injection(self):
        a=produce_observer(self.source,self.reg,'A','complementary_dropouts',false_positives=frozenset({65}))
        r=reconstruct(self.source,a,self.b,self.reg)
        self.assertEqual(r['counts']['A_sham_false_positive'],1)
        self.assertEqual(r['counts']['A_non_detection'],12)

    def test_unavailable_is_not_a_negative_reading(self):
        a=produce_observer(self.source,self.reg,'A','complementary_dropouts',unavailable=frozenset({3,70}))
        r=reconstruct(self.source,a,self.b,self.reg)
        self.assertEqual(r['counts']['A_unavailable'],2)
        self.assertEqual(r['counts']['A_non_detection'],13)
        self.assertEqual(a['records'][3]['status'],'unavailable')
        self.assertIsNone(a['records'][3]['event_id'])

    def test_missing_middle_signed_record_fail_closed(self):
        damaged=copy.deepcopy(self.a)
        damaged['records'].pop(11)
        with self.assertRaisesRegex(CalibrationError,'incomplete'):
            reconstruct(self.source,damaged,self.b,self.reg)

    def test_removed_seal_rejected(self):
        damaged=copy.deepcopy(self.a)
        damaged['seal']=None
        with self.assertRaises(CalibrationError): reconstruct(self.source,damaged,self.b,self.reg)

    def test_reorder_signed_record_rejected(self):
        damaged=copy.deepcopy(self.a)
        damaged['records'][1],damaged['records'][2]=damaged['records'][2],damaged['records'][1]
        with self.assertRaisesRegex(CalibrationError,'index/parent'):
            reconstruct(self.source,damaged,self.b,self.reg)

    def test_signed_data_alteration_rehashed_without_key_rejected(self):
        damaged=copy.deepcopy(self.b)
        damaged['records'][2]['status']='not_detected'
        doc=damaged['records'][2]
        doc['digest']=sha({k:v for k,v in doc.items() if k!='digest'})
        with self.assertRaisesRegex(CalibrationError,'HMAC'):
            reconstruct(self.source,self.a,damaged,self.reg)

    def test_swapped_observer_role_fails(self):
        with self.assertRaisesRegex(CalibrationError,'role/session'):
            reconstruct(self.source,self.b,self.a,self.reg)

    def test_cross_session_replay_fails(self):
        altered=copy.deepcopy(self.reg)
        altered['challenge']='foreign'
        with self.assertRaisesRegex(CalibrationError,'role/session'):
            reconstruct(self.source,self.a,self.b,altered)

    def test_key_substitution_fails(self):
        altered=copy.deepcopy(self.reg)
        altered['keys']['A']='aa'*32
        with self.assertRaisesRegex(CalibrationError,'enrollment'):
            reconstruct(self.source,self.a,self.b,altered)

    def test_repeated_trial_without_valid_chain_fails(self):
        altered=copy.deepcopy(self.b)
        altered['records'][5]=altered['records'][4]
        with self.assertRaises(CalibrationError):
            reconstruct(self.source,self.a,altered,self.reg)

    def test_signed_wrong_event_identity_rejected(self):
        altered=copy.deepcopy(self.b)
        item=altered['records'][3]
        base={k:v for k,v in item.items() if k not in ('mac','digest')}
        base['event_id']='b'*64
        altered['records'][3]=_sign(base,_key(self.reg,'B'))
        # Valid role HMAC but breaks later chain AND response correspondence.
        with self.assertRaises(CalibrationError):
            reconstruct(self.source,self.a,altered,self.reg)

    def test_authenticated_lie_does_not_prove_physical_sensing(self):
        a=produce_observer(self.source,self.reg,'A','colluding_silence')
        b=produce_observer(self.source,self.reg,'B','colluding_silence')
        r=reconstruct(self.source,a,b,self.reg)
        self.assertFalse(r['physical_instrument_identity_verified'])
        self.assertFalse(r['source_truthfulness_verified'])

    def test_public_evidence_identical_when_source_claim_is_false(self):
        # Both worlds emit *identical public bytes*: in W1 S actually injected and
        # both sensors missed; in W2 S merely CLAIMED injection, no event occurred.
        # No verification over signed records can distinguish them without a
        # separately justified source-truthfulness premise.
        w1={'physical_event_happened':True,'evidence':(self.source,self.a,self.b)}
        w2={'physical_event_happened':False,'evidence':(self.source,self.a,self.b)}
        self.assertNotEqual(w1['physical_event_happened'],w2['physical_event_happened'])
        self.assertEqual(w1['evidence'],w2['evidence'])

    def test_positive_and_sham_totals_are_fixture_conditions(self):
        distorted=copy.deepcopy(self.source)
        distorted['records'][1]['injected']=False
        with self.assertRaises(CalibrationError):
            reconstruct(distorted,self.a,self.b,self.reg)

if __name__=='__main__':
    unittest.main()