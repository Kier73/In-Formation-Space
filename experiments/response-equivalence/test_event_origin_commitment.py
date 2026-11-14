"""RE-010 tests: scoped third-source evidence, tamper and malicious origin."""
import copy
import unittest

from event_origin_commitment import (
    DEFAULT_CLAIMS, OBSERVED_CLAIMS, OriginError, detect_origin_fork,
    fixture, make_origin, registration, triangulate, verify_origin, sha,
)
from common_mode_counter import produce_source, acknowledge
from coverage_reconstruction import ACTORS, produce_log


class IndependentOriginTests(unittest.TestCase):
    def setUp(self):
        self.s, self.l, self.a, self.o, self.r, self.d = fixture()

    def result(self, origin=None, **kw):
        return triangulate(self.s, self.l, self.a,
                           self.o if origin is None else origin, self.r, self.d, **kw)

    def test_source_origin_claims_four_observers_only_three(self):
        q = self.result()
        self.assertEqual(q['status'], 'origin_corrob_source_claim_not_observer_readout')
        self.assertEqual((q['source_reported_total'],q['origin_reported_total'],q['observer_reported_total']), (4,4,3))
        self.assertEqual(q['origin_only_epochs'], [3])
        self.assertEqual(q['conditional_on_origin_truthfulness_and_completeness'], 'candidate observer omission')

    def test_origin_claims_three_agrees_with_observers_not_counter(self):
        o = make_origin(self.r, OBSERVED_CLAIMS)
        q = self.result(o)
        self.assertEqual(q['status'], 'origin_corrob_observer_claim_not_source_count')
        self.assertEqual(q['conditional_on_origin_truthfulness_and_completeness'], 'candidate source overcount')
        self.assertEqual(q['origin_only_epochs'], [])

    def test_lower_source_count_three_all_claims_agree(self):
        s,l,a,o,r,d=fixture(claimed_origin=OBSERVED_CLAIMS,source_counts=(0,1,3))
        q=triangulate(s,l,a,o,r,d)
        self.assertEqual(q['status'],'all_declared_claims_agree')
        self.assertFalse(q['global_event_completeness_proved'])

    def test_false_origin_claim_and_real_event_have_identical_records(self):
        # Physical-world descriptor is not an input to the origin signer.
        physical_worlds = ('epoch-3-was-real', 'epoch-3-was-fabricated-by-origin')
        by_world = {w:make_origin(self.r, DEFAULT_CLAIMS) for w in physical_worlds}
        self.assertEqual(*by_world.values())
        self.assertFalse(self.result()['physical_occurrence_verified'])

    def test_zero_reliable_origin_physical_authentication(self):
        q=self.result()
        for k in ('physical_occurrence_verified','origin_sensor_independence_verified',
                  'origin_completeness_verified','physical_common_mode_loss_proved',
                  'global_event_completeness_proved'):
            self.assertIs(q[k],False)

    def test_invalid_origin_key_id_rejected(self):
        bad=copy.deepcopy(self.r)
        bad['keys']['O']='aa'*32
        with self.assertRaisesRegex(OriginError,'enrollment'):
            self.result() if False else verify_origin(self.o,bad)

    def test_origin_does_not_share_signer_key_with_source_or_observers(self):
        self.assertEqual(len({self.r['key_ids'][x] for x in ('A','B','S','O')}),4)

    def test_missing_origin_is_unavailable_not_negative_reading(self):
        q=triangulate(self.s,self.l,self.a,None,self.r,self.d)
        self.assertEqual(q['status'],'origin_evidence_unavailable')
        self.assertIsNone(q['origin_vs_observers'])

    def test_rehashed_origin_event_claim_rejected_by_hmac(self):
        changed=copy.deepcopy(self.o)
        changed['receipts'][1]['mark']='fabricated-after-signing'
        x=changed['receipts'][1]
        x['digest']=sha({k:v for k,v in x.items() if k!='digest'})
        with self.assertRaisesRegex(OriginError,'HMAC'):
            self.result(changed)

    def test_rehashing_seal_head_cannot_masquerade_as_signature(self):
        changed=copy.deepcopy(self.o)
        changed['seal']['head']='f'*64
        x=changed['seal']
        x['digest']=sha({k:v for k,v in x.items() if k!='digest'})
        with self.assertRaisesRegex(OriginError,'HMAC'):
            self.result(changed)

    def test_origin_duplicate_epoch_rejected_at_creation(self):
        with self.assertRaisesRegex(OriginError,'duplicated'):
            make_origin(self.r,[(1,'a'),(1,'b')])

    def test_unsorted_origin_epoch_rejected_at_creation(self):
        with self.assertRaisesRegex(OriginError,'unordered'):
            make_origin(self.r,[(4,'q'),(1,'p')])

    def test_session_replay_rejected(self):
        bad=copy.deepcopy(self.r)
        bad['challenge']='another-session'
        with self.assertRaisesRegex(Exception,'challenge|identity|session'):
            verify_origin(self.o,bad)

    def test_controller_digest_binding_rejects_wrong_session(self):
        from event_origin_commitment import make_origin
        ctr='a'*64
        orig=make_origin(self.r,controller_digest=ctr)
        self.assertEqual(len(verify_origin(orig,self.r,controller_digest=ctr)),4)
        with self.assertRaisesRegex(OriginError,'controller'):
            verify_origin(orig,self.r,controller_digest='b'*64)

    def test_signed_event_fingerprint_alteration_fails(self):
        bad=copy.deepcopy(self.o)
        bad['receipts'][0]['fingerprint']='0'*64
        with self.assertRaisesRegex(OriginError,'HMAC'):
            verify_origin(bad,self.r)

    def test_same_key_can_sign_lie_undetectable_without_independent_ground(self):
        # Honest signing behavior is not guaranteed by holding the enrolled key.
        fake=make_origin(self.r,DEFAULT_CLAIMS)
        self.assertEqual(len(verify_origin(fake,self.r)),4)
        self.assertFalse(self.result(fake)['physical_occurrence_verified'])

    def test_observed_event_id_conflict_not_cast_as_missing_count(self):
        wrong=make_origin(self.r,((1,'different'),(3,'hidden-event'),(4,'q'),(6,'r')))
        q=self.result(wrong)
        self.assertEqual(q['status'],'origin_observer_event_identity_conflict')
        self.assertEqual(q['identity_conflict_epochs'],[1])

    def test_source_origin_count_windows_match(self):
        q=self.result()
        self.assertEqual([w['source_minus_origin'] for w in q['source_origin_windows']],[0,0])
        self.assertEqual([w['observer_reported'] for w in q['source_origin_windows']],[1,2])

    def test_fork_detected_only_if_both_signed_histories_present(self):
        alternative=make_origin(self.r,OBSERVED_CLAIMS)
        self.assertTrue(detect_origin_fork([self.o,alternative],self.r)['equivocation_proved'])
        self.assertFalse(detect_origin_fork([self.o],self.r)['equivocation_proved'])
        self.assertFalse(detect_origin_fork([self.o,copy.deepcopy(self.o)],self.r)['equivocation_proved'])

    def test_false_origin_in_same_window_does_not_infer_event_epoch_from_counter(self):
        other=make_origin(self.r,((1,'p'),(2,'other'),(4,'q'),(6,'r')))
        q=self.result(other)
        self.assertEqual(q['origin_only_epochs'],[2])
        self.assertEqual(q['status'],'origin_corrob_source_claim_not_observer_readout')
        self.assertNotEqual(other['seal']['digest'],self.o['seal']['digest'])

    def test_observer_record_missing_suspends_origin_comparison(self):
        damaged=copy.deepcopy(self.l)
        damaged['B']['records']=[x for x in damaged['B']['records'] if x['epoch']!=3]
        q=triangulate(self.s,damaged,self.a,self.o,self.r,self.d)
        self.assertEqual(q['status'],'unresolved_observer_evidence')

    def test_observer_contradiction_suspends_origin_comparison(self):
        from coverage_reconstruction import produce_log
        # B says absent where A says present (epoch 1); B normally dropout there.
        source=self.s
        logs=copy.deepcopy(self.l)
        logs['A']=produce_log('A',self.r)
        logs['B']=produce_log('B',self.r,{1:'absent'})
        ack={a:acknowledge(a,logs[a],source,self.r) for a in ACTORS}
        q=triangulate(source,logs,ack,self.o,self.r)
        self.assertEqual(q['status'],'unresolved_observer_evidence')

    def test_origin_key_not_implicitly_authorized_by_source_key(self):
        from event_origin_commitment import verify_origin
        bad=copy.deepcopy(self.r)
        bad['keys']['O']=bad['keys']['S']
        with self.assertRaisesRegex(OriginError,'enrollment'):
            verify_origin(self.o,bad)

    def test_source_overcount_could_be_origin_undercount(self):
        q=self.result(make_origin(self.r,OBSERVED_CLAIMS))
        self.assertEqual(q['status'],'origin_corrob_observer_claim_not_source_count')
        self.assertFalse(q['origin_completeness_verified'])

if __name__=='__main__':
    unittest.main()