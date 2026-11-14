"""RE-014: durable policy decisions, adverse records and independent reconstruction."""
import copy
import hashlib
import hmac
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from authority_reconstruction import (
    AuthorityError, POLICY, SCHEMA, append, claim_scope, create_store, demo,
    evidence, evidence_id, export, registration, replay, sign_event,
)
from detection_calibration import canonical, sha


class DurableAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'authority.sqlite3'
        create_store(self.db)
        self.reg = registration(deterministic=True)
        self.doc = evidence(self.reg)

    def add(self, role, kind, *, reason=None):
        return append(self.db, sign_event(self.reg, role, kind, self.doc, reason=reason),
                      self.reg, self.doc)

    def issue(self):
        self.add('M','endorse')
        self.add('P','endorse')
        return self.add('V','issue')

    def test_empty_journal_has_no_assumption_authority(self):
        r = replay(export(self.db), self.reg, self.doc)
        self.assertEqual(r['status'], 'pending_authority')
        self.assertEqual(r['approvals'], [])
        self.assertIsNone(r['certificate_digest'])
        self.assertFalse(r['physical_source_truth_established'])

    def test_single_assumption_approval_does_not_issue(self):
        self.add('M','endorse')
        r = replay(export(self.db), self.reg, self.doc)
        self.assertEqual(r['status'], 'pending_authority')
        self.assertEqual(r['approvals'], ['M'])

    def test_two_role_approval_without_issue_still_pending(self):
        self.add('M','endorse'); self.add('P','endorse')
        r = replay(export(self.db),self.reg,self.doc)
        self.assertEqual(r['status'],'pending_authority')
        self.assertEqual(r['approvals'],['M','P'])

    def test_issue_only_after_two_distinct_approved_claims(self):
        anchor = self.issue()
        r = replay(export(self.db),self.reg,self.doc,independently_anchored=anchor)
        self.assertEqual(r['status'],'conditionally_admitted')
        self.assertEqual(r['scope'],'fixture-passive-stratified-detection')
        self.assertIsNotNone(r['certificate_digest'])
        self.assertFalse(r['iid_assumption_proved'])
        self.assertFalse(r['physical_sensor_identity_established'])

    def test_insufficient_approval_rejected_atomically(self):
        with self.assertRaisesRegex(AuthorityError,'prerequisite'):
            self.add('V','issue')
        self.assertEqual(export(self.db)['anchor']['count'],0)
        self.add('M','endorse')
        with self.assertRaisesRegex(AuthorityError,'prerequisite'):
            self.add('V','issue')
        self.assertEqual(export(self.db)['anchor']['count'],1)

    def test_duplicate_endorsement_rejected_atomically(self):
        self.add('M','endorse')
        with self.assertRaisesRegex(AuthorityError,'duplicated'):
            self.add('M','endorse')
        self.assertEqual(export(self.db)['anchor']['count'],1)

    def test_second_issuance_is_not_an_upgrade(self):
        self.issue()
        with self.assertRaisesRegex(AuthorityError,'prerequisite'):
            self.add('V','issue')
        self.assertEqual(export(self.db)['anchor']['count'],3)

    def test_signed_revocation_is_irreversible_in_same_revision(self):
        anchor = self.issue()
        self.add('R','revoke',reason='instrument_replaced')
        state = replay(export(self.db),self.reg,self.doc)
        self.assertEqual(state['status'],'revoked')
        self.assertEqual(state['history'][-1],'revoke:R')
        with self.assertRaises(AuthorityError): self.add('V','issue')
        with self.assertRaises(AuthorityError): self.add('M','endorse')
        with self.assertRaises(AuthorityError): self.add('R','revoke',reason='population_shift')
        self.assertEqual(export(self.db)['anchor']['count'],4)
        self.assertEqual(anchor['count'],3)

    def test_revocation_before_issue_is_rejected(self):
        with self.assertRaisesRegex(AuthorityError,'revocation needs'):
            self.add('R','revoke',reason='instrument_replaced')
        self.assertEqual(export(self.db)['anchor']['count'],0)

    def test_unrecognized_policy_transition_fails_at_signer(self):
        for actor,kind in [('M','issue'),('P','revoke'),('R','endorse'),('V','endorse')]:
            with self.subTest(actor=actor,kind=kind):
                with self.assertRaisesRegex(AuthorityError,'unauthorized'):
                    sign_event(self.reg,actor,kind,self.doc)

    def test_unrecognized_revocation_reason_fails(self):
        with self.assertRaisesRegex(AuthorityError,'unauthorized'):
            self.add('R','revoke',reason='looks_fine')

    def test_document_replay_under_other_scope_is_rejected(self):
        self.issue()
        other = evidence(self.reg,protocol='stimulated')
        with self.assertRaisesRegex(AuthorityError,'scope mismatch'):
            replay(export(self.db),self.reg,other)

    def test_mutated_evidence_invalidates_authority_claims(self):
        self.issue()
        other=copy.deepcopy(self.doc)
        other['A']['records'][0]['body']['sensor']='substituted-device'
        with self.assertRaises(Exception):
            replay(export(self.db),self.reg,other)

    def test_rehashed_hmac_receipt_mutation_is_rejected(self):
        self.issue()
        transcript=export(self.db)
        rec=transcript['entries'][0]['receipt']
        rec['body']['assumption_claim']='physical_source_truth_proved'
        rec['digest']=sha({k:v for k,v in rec.items() if k!='digest'})
        transcript['entries'][0]['chain_digest']=sha({'ordinal':0,'previous':None,'receipt':rec})
        with self.assertRaises(AuthorityError):
            replay(transcript,self.reg,self.doc)

    def test_correctly_signed_unrecognized_assertion_rejected(self):
        rec=sign_event(self.reg,'M','endorse',self.doc)
        rec['body']['assumption_claim']='universal_iid_physical_proof'
        unsigned={k:v for k,v in rec.items() if k not in ('mac','digest')}
        key=bytes.fromhex(self.reg['keys']['M'])
        rec['mac']=hmac.new(key,canonical(unsigned),hashlib.sha256).hexdigest()
        rec['digest']=sha({**unsigned,'mac':rec['mac']})
        with self.assertRaisesRegex(AuthorityError,'policy event'):
            append(self.db,rec,self.reg,self.doc)

    def test_enrollment_substitution_not_accepted(self):
        self.add('M','endorse')
        newreg=copy.deepcopy(self.reg)
        newreg['keys']['M']='ff'*32
        with self.assertRaisesRegex(AuthorityError,'enrollment'):
            replay(export(self.db),newreg,self.doc)

    def test_foreign_challenge_replay_rejected(self):
        self.add('M','endorse')
        other=copy.deepcopy(self.reg)
        other['challenge']='new-scope-challenge'
        with self.assertRaisesRegex(Exception,'identity'):
            replay(export(self.db),other,self.doc)

    def test_ledger_row_reordering_detected(self):
        self.issue()
        t=export(self.db)
        t['entries'][0],t['entries'][1]=t['entries'][1],t['entries'][0]
        with self.assertRaisesRegex(AuthorityError,'chain'):
            replay(t,self.reg,self.doc)

    def test_ledger_row_loss_detected(self):
        self.issue()
        t=export(self.db)
        t['entries'].pop(1)
        with self.assertRaisesRegex(AuthorityError,'chain'):
            replay(t,self.reg,self.doc)

    def test_ledger_chain_hash_mutation_rejected(self):
        self.issue()
        t=export(self.db)
        t['entries'][1]['chain_digest']='a'*64
        with self.assertRaisesRegex(AuthorityError,'chain'):
            replay(t,self.reg,self.doc)

    def test_self_declared_anchor_tampering_rejected(self):
        self.issue()
        t=export(self.db)
        t['anchor']['head']='d'*64
        with self.assertRaisesRegex(AuthorityError,'anchor'):
            replay(t,self.reg,self.doc)

    def test_rollback_detected_only_with_independent_head(self):
        self.issue()
        before=export(self.db)
        self.add('R','revoke',reason='population_shift')
        after=export(self.db)
        self.assertEqual(replay(before,self.reg,self.doc)['status'], 'conditionally_admitted')
        with self.assertRaisesRegex(AuthorityError,'independent journal anchor'):
            replay(before,self.reg,self.doc,independently_anchored=after['anchor'])

    def test_forged_attestation_does_not_prove_physical_sensing(self):
        self.issue()
        r=replay(export(self.db),self.reg,self.doc)
        self.assertFalse(r['physical_source_truth_established'])
        self.assertFalse(r['physical_sensor_identity_established'])
        self.assertIsNone(r['adversarial_guarantee'])
        self.assertFalse(r['external_attestation_present'])

    def test_authority_roles_have_distinct_enrollment_keys(self):
        self.assertEqual(len({self.reg['key_ids'][role] for role in ('M','P','R','V')}),4)

    def test_sqlite_prevents_accidental_record_rewrite(self):
        self.add('M','endorse')
        with sqlite3.connect(self.db) as c:
            with self.assertRaisesRegex(sqlite3.IntegrityError,'append-only'):
                c.execute("DELETE FROM decisions WHERE ordinal=0")
            with self.assertRaisesRegex(sqlite3.IntegrityError,'append-only'):
                c.execute("UPDATE decisions SET chain_digest='x' WHERE ordinal=0")

    def test_store_can_reopen_for_appends_and_verify(self):
        self.add('M','endorse')
        self.add('P','endorse')
        self.add('V','issue')
        self.assertEqual(replay(export(self.db),self.reg,self.doc)['journal_anchor']['count'],3)

    def test_independent_process_reconstructs_without_sqlite(self):
        self.issue()
        payload = {'transcript':export(self.db),'enrollment':self.reg,'evidence':self.doc}
        script = ("import json,sys;from authority_reconstruction import replay;"
                  "a=json.load(sys.stdin);r=replay(a['transcript'],a['enrollment'],a['evidence']);"
                  "print(r['status'])")
        result=subprocess.run([sys.executable,'-c',script],input=json.dumps(payload),
            text=True,capture_output=True,cwd=Path(__file__).parent,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'conditionally_admitted')

    def test_deterministic_demo_has_revocation(self):
        d=demo()
        self.assertEqual(d['before'],'pending_authority')
        self.assertEqual(d['after_approvals'],'conditionally_admitted')
        self.assertEqual(d['after_revocation'],'revoked')
        self.assertEqual(d['approval_roles'],['M','P'])


if __name__=='__main__':
    unittest.main()
