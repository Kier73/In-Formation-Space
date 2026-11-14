"""RE-015 regression: key continuity, two external checkpoints, failure modes."""
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Existing RE workflows use only the standard library. RE-015's dedicated CI
# installs cryptography and MUST exercise these tests. Optional discoverers
# without the dependency skip this module instead of failing unrelated suites.
try:
    import cryptography  # noqa: F401
except ImportError:
    raise unittest.SkipTest('RE-015 Ed25519 tests require cryptography; run the dedicated RE-015 workflow')

from credential_continuity import (
    ContinuityError, _base_context, _event_body, append_journal, append_replica,
    checkpoint_body, demo, empty_ledger, enrollment, export_journal, fixture,
    initialize_journal, initialize_replica, issue_baseline, latest_replica,
    replay_ledger, sign_by_role, sign_checkpoint, sign_governance,
    assemble_event, verify_checkpoint, verify_recovery,
)
from detection_calibration import sha

class ContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example=fixture(deterministic=True)
        cls.enrolled=enrollment(deterministic=True)

    def setUp(self):
        self.data=self.example
        self.trust=self.data['trust']; self.baseline=self.data['baseline']
        self.keys=self.enrolled['private']; self.last=self.data['final']

    def test_recovery_after_issuer_host_lost(self):
        out=verify_recovery(self.last,self.baseline,self.trust,self.data['checkpoints'])
        self.assertEqual(out['status'],'revoked')
        self.assertFalse(out['issuer_process_required_for_recovery'])
        self.assertTrue(out['legacy_re014_hmac_verification_key_required'])

    def test_genesis_is_an_issued_and_unchanged_re014_journal(self):
        old=self.data['initial']
        self.assertEqual(old['rows'],[])
        self.assertEqual(replay_ledger(old,self.trust,self.baseline)['status'],'conditionally_admitted')
        self.assertEqual(self.baseline['issued']['anchor']['count'],3)

    def test_rotation_keeps_certificate_admitted(self):
        state=replay_ledger(self.data['rotated'],self.trust,self.baseline)
        self.assertTrue(state['rotated'])
        self.assertEqual(state['status'],'conditionally_admitted')
        self.assertNotEqual(state['current_key_id'],sha({'public':self.trust['public']['R0']}))

    def test_new_revocation_is_reconstructed_after_rotation(self):
        report=replay_ledger(self.last,self.trust,self.baseline)
        self.assertEqual(report['status'],'revoked')
        self.assertEqual([r['event']['body']['kind'] for r in self.last['rows']],['rotate','revoke'])

    def test_credentials_are_public_verifiable_in_new_overlay(self):
        public=copy.deepcopy(self.trust)
        self.assertEqual(set(public['public']),{'R0','W1','W2'})
        self.assertEqual(replay_ledger(self.last,public,self.baseline)['status'],'revoked')

    def test_base_hmac_is_still_a_trust_dependency(self):
        bad=copy.deepcopy(self.baseline)
        del bad['registration']['keys']['V']
        with self.assertRaises(ContinuityError):
            verify_recovery(self.last,bad,self.trust,self.data['checkpoints'])

    def test_modified_baseline_certificate_rejected(self):
        bad=copy.deepcopy(self.baseline)
        bad['evidence']['plan']['body']['revision']=15
        with self.assertRaises(ContinuityError):
            verify_recovery(self.last,bad,self.trust,self.data['checkpoints'])

    def test_absent_external_checkpoint_rejected(self):
        with self.assertRaisesRegex(ContinuityError,'two separately'):
            verify_recovery(self.last,self.baseline,self.trust,{'W1':self.data['checkpoints']['W1']})

    def test_reusing_one_witness_for_both_fails(self):
        duplicated={'W1':self.data['checkpoints']['W1'], 'W2':self.data['checkpoints']['W1']}
        with self.assertRaisesRegex(ContinuityError,'envelope'):
            verify_recovery(self.last,self.baseline,self.trust,duplicated)

    def test_rollback_rejected_if_newer_checkpoint_retained(self):
        with self.assertRaisesRegex(ContinuityError,'rollback'):
            verify_recovery(self.data['rotated'],self.baseline,self.trust,self.data['checkpoints'])

    def test_global_replay_of_both_witnesses_not_provably_detectable(self):
        body=checkpoint_body(self.data['rotated'],self.trust,self.baseline)
        old={w:sign_checkpoint(w,body,self.keys[w]) for w in ('W1','W2')}
        result=verify_recovery(self.data['rotated'],self.baseline,self.trust,old)
        self.assertEqual(result['status'],'conditionally_admitted')
        self.assertFalse(result['global_rollback_precluded'])

    def test_mismatched_external_checkpoints_detect_fork(self):
        bad=copy.deepcopy(self.data['checkpoints'])
        body=checkpoint_body(self.data['rotated'],self.trust,self.baseline)
        bad['W2']=sign_checkpoint('W2',body,self.keys['W2'])
        with self.assertRaisesRegex(ContinuityError,'rollback'):
            verify_recovery(self.last,self.baseline,self.trust,bad)

    def test_tampered_event_even_with_rehashed_chain_fails(self):
        bad=copy.deepcopy(self.last)
        bad['rows'][1]['event']['body']['reason']='new_conflicting_evidence'
        event=bad['rows'][1]['event']
        event['digest']=sha({k:v for k,v in event.items() if k!='digest'})
        row=bad['rows'][1]
        row['entry_digest']=sha({'sequence':1,'parent':row['parent'],'event':event})
        bad['anchor']['head']=row['entry_digest']
        with self.assertRaisesRegex(ContinuityError,'signature'):
            replay_ledger(bad,self.trust,self.baseline)

    def test_stolen_retired_key_cannot_revoke(self):
        bad=copy.deepcopy(self.last)
        event=bad['rows'][1]['event']
        event['signatures']['R']=sign_by_role(event['body'],self.keys['R0'])
        event['digest']=sha({k:v for k,v in event.items() if k!='digest'})
        bad['rows'][1]['entry_digest']=sha({'sequence':1,'parent':bad['rows'][1]['parent'],'event':event})
        bad['anchor']['head']=bad['rows'][1]['entry_digest']
        with self.assertRaisesRegex(ContinuityError,'signature'):
            replay_ledger(bad,self.trust,self.baseline)

    def test_one_root_cannot_approve_revocation(self):
        bad=copy.deepcopy(self.last)
        event=bad['rows'][1]['event']
        event['signatures']['W2']=event['signatures']['W1']
        event['digest']=sha({k:v for k,v in event.items() if k!='digest'})
        bad['rows'][1]['entry_digest']=sha({'sequence':1,'parent':bad['rows'][1]['parent'],'event':event})
        bad['anchor']['head']=bad['rows'][1]['entry_digest']
        with self.assertRaisesRegex(ContinuityError,'signature'):
            replay_ledger(bad,self.trust,self.baseline)

    def test_two_valid_forked_revocations_need_independent_latest_anchor(self):
        fork=copy.deepcopy(self.data['rotated'])
        body=_event_body('revoke',self.trust,_base_context(self.baseline),
            {'count':1,'head':fork['anchor']['head'],
             'current_public':self.enrolled['replacement_public']},
            reason='new_conflicting_evidence')
        alt=sign_governance(body,{'R':self.keys['R1'],'W1':self.keys['W1'],'W2':self.keys['W2']})
        head=sha({'sequence':1,'parent':fork['anchor']['head'],'event':alt})
        fork['rows'].append({'sequence':1,'parent':fork['anchor']['head'],
                             'event':alt,'entry_digest':head})
        fork['anchor']={'count':2,'head':head}
        self.assertEqual(replay_ledger(fork,self.trust,self.baseline)['status'],'revoked')
        with self.assertRaisesRegex(ContinuityError,'fork'):
            verify_recovery(fork,self.baseline,self.trust,self.data['checkpoints'])

    def test_new_public_key_must_be_distinct(self):
        with self.assertRaisesRegex(ContinuityError,'distinct'):
            _event_body('rotate',self.trust,_base_context(self.baseline),
                 {'count':0,'head':None,'current_public':self.trust['public']['R0']},
                  new_public=self.trust['public']['R0'])

    def test_rotation_requires_old_key_and_both_root_signatures(self):
        body=_event_body('rotate',self.trust,_base_context(self.baseline),
            {'count':0,'head':None,'current_public':self.trust['public']['R0']},
            new_public=self.enrolled['replacement_public'])
        good=sign_governance(body,{'R':self.keys['R0'],'W1':self.keys['W1'],'W2':self.keys['W2']})
        self.assertEqual(good,self.data['rotated']['rows'][0]['event'])
        bad=assemble_event(body,{'R':sign_by_role(body,self.keys['R1']),
            'W1':sign_by_role(body,self.keys['W1']), 'W2':sign_by_role(body,self.keys['W2'])})
        altered={'schema':self.last['schema'],'rows':[{'sequence':0,'parent':None,
                 'event':bad,'entry_digest':sha({'sequence':0,'parent':None,'event':bad})}],
                 'anchor':{'count':1,'head':sha({'sequence':0,'parent':None,'event':bad})}}
        with self.assertRaisesRegex(ContinuityError,'signature'):
            replay_ledger(altered,self.trust,self.baseline)

    def test_revocation_before_rotation_not_admitted(self):
        body=_event_body('revoke',self.trust,_base_context(self.baseline),
            {'count':0,'head':None,'current_public':self.trust['public']['R0']},
            reason='instrument_replaced')
        event=sign_governance(body,{'R':self.keys['R0'],'W1':self.keys['W1'],'W2':self.keys['W2']})
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'g.sqlite3';initialize_journal(db)
            with self.assertRaisesRegex(ContinuityError,'not authorized'):
                append_journal(db,event,self.trust,self.baseline)
            self.assertEqual(export_journal(db),empty_ledger())

    def test_cannot_second_rotate_after_first_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'g.sqlite3';initialize_journal(db)
            first=self.data['rotated']['rows'][0]['event']
            append_journal(db,first,self.trust,self.baseline)
            body=_event_body('rotate',self.trust,_base_context(self.baseline),
                {'count':1,'head':self.data['rotated']['anchor']['head'],
                 'current_public':self.enrolled['replacement_public']},
                new_public=self.trust['public']['R0'])
            event=sign_governance(body,{'R':self.keys['R1'],'W1':self.keys['W1'],'W2':self.keys['W2']})
            with self.assertRaisesRegex(ContinuityError,'not authorized'):
                append_journal(db,event,self.trust,self.baseline)

    def test_witness_replica_requires_consecutive_sealed_heads(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'w.sqlite3';initialize_replica(db)
            final=sign_checkpoint('W1',checkpoint_body(self.last,self.trust,self.baseline),self.keys['W1'])
            with self.assertRaisesRegex(ContinuityError,'not consecutive'):
                append_replica(db,final,'W1',self.trust)
            initial=sign_checkpoint('W1',checkpoint_body(self.data['initial'],self.trust,self.baseline),self.keys['W1'])
            append_replica(db,initial,'W1',self.trust)
            self.assertEqual(latest_replica(db),initial)

    def test_witness_sqlite_records_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'w.sqlite3';initialize_replica(db)
            initial=sign_checkpoint('W1',checkpoint_body(self.data['initial'],self.trust,self.baseline),self.keys['W1'])
            append_replica(db,initial,'W1',self.trust)
            with sqlite3.connect(db) as con:
                with self.assertRaises(sqlite3.DatabaseError):
                    con.execute('DELETE FROM heads')

    def test_governance_sqlite_records_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'g.sqlite3';initialize_journal(db)
            append_journal(db,self.data['rotated']['rows'][0]['event'],self.trust,self.baseline)
            with sqlite3.connect(db) as con:
                with self.assertRaises(sqlite3.DatabaseError):
                    con.execute('UPDATE journal SET parent=NULL')

    def test_foreign_trust_genesis_cannot_replay(self):
        bad=copy.deepcopy(self.trust)
        other=enrollment()['trust']
        bad['public']['W1']=other['public']['W1']
        with self.assertRaisesRegex(ContinuityError,'signature'):
            replay_ledger(self.last,bad,self.baseline)

    def test_cross_scope_baseline_cannot_replay(self):
        bad=copy.deepcopy(self.baseline)
        bad['evidence']['plan']['body']['proposal']['claim_scope']='fixture-stimulated-stratified-detection'
        with self.assertRaises(ContinuityError):
            replay_ledger(self.last,self.trust,bad)

    def test_witness_receipt_integrity(self):
        item=copy.deepcopy(self.data['checkpoints']['W1'])
        item['body']['governance_anchor']['count']=7
        item['digest']=sha({k:v for k,v in item.items() if k!='digest'})
        with self.assertRaisesRegex(ContinuityError,'signature'):
            verify_checkpoint(item,'W1',self.trust)

    def test_issuer_and_sensors_are_not_physically_attested(self):
        result=self.data['recovered']
        self.assertFalse(result['physical_assumptions_proved'])
        self.assertFalse(result['physical_signer_identity_proved'])
        self.assertFalse(result['root_collusion_excluded'])

    def test_demo_reconstructs_after_revocation(self):
        report=demo()
        self.assertEqual(report['history_length'],2)
        self.assertTrue(report['legacy_re014_hmac_key_still_required'])

if __name__=='__main__': unittest.main()