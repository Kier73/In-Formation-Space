"""RE-016: public migration, untrusted historical replay, and future authority receipts."""
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Older RE workflows are standard-library-only; the dedicated RE-016 workflow
# installs cryptography and MUST run every test in this module. Preserve those
# older suites' independence of a new optional Ed25519 dependency.
try:
    import cryptography  # noqa: F401
except ImportError:
    raise unittest.SkipTest('RE-016 public-key tests require cryptography; use the dedicated RE-016 workflow')

from public_migration import (
    MigrationError, attest_migration, append_future_archive, create_future_archive,
    export_future_archive, fixture, future_body, future_pin, hosted_material, pin,
    prepare_migration, public_history, public_verify, replay_future, sign_future,
    verify_future_pin,
)
from credential_continuity import ContinuityError, _sign
from detection_calibration import sha


class PublicMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample=fixture()

    def verify(self, *, migration=None, history=None, ledger=None,trust=None, checkpoints=None,retained=None):
        s=self.sample
        return public_verify(migration if migration is not None else s['migration'],
            history if history is not None else s['public'],
            ledger if ledger is not None else s['ledger'],
            trust if trust is not None else s['trust'],
            checkpoints if checkpoints is not None else s['checkpoints'],
            retained if retained is not None else s['pin'])

    def test_full_public_reconstruction_requires_no_legacy_keys(self):
        r=self.verify()
        self.assertEqual(r['status'],'revoked')
        self.assertEqual(r['historical_validation_mode'],'attested_prior_legacy_replay')
        self.assertFalse(r['historical_hmac_reexecuted'])
        self.assertFalse(r['legacy_secret_required_for_public_verifier'])
        self.assertNotIn('keys',self.sample['public']['registration'])

    def test_original_history_is_not_rewritten_during_export(self):
        before=sha(self.sample['legacy_reference'])
        out=public_history(self.sample['legacy_reference'])
        self.assertEqual(before,sha(self.sample['legacy_reference']))
        self.assertEqual(out['issued'],self.sample['legacy_reference']['issued'])
        self.assertEqual(out['evidence'],self.sample['legacy_reference']['evidence'])
        self.assertNotIn('keys',out['registration'])

    def test_legacy_material_digest_records_unpublished_archive_bytes(self):
        self.assertEqual(self.sample['migration']['body']['original_archive_digest'],
                         sha(self.sample['legacy_reference']))

    def test_rechecking_bad_hmac_during_ceremony_is_mandatory(self):
        altered=copy.deepcopy(self.sample['legacy_reference'])
        altered['issued']['entries'][0]['receipt']['mac']='00'*32
        with self.assertRaises((MigrationError,ContinuityError,ValueError)):
            prepare_migration(altered,self.sample['ledger'],self.sample['trust'],self.sample['checkpoints'])

    def test_bad_historical_evidence_is_rejected_at_ceremony(self):
        altered=copy.deepcopy(self.sample['legacy_reference'])
        altered['evidence']['plan']['body']['revision']=23
        with self.assertRaises((MigrationError,ContinuityError,ValueError)):
            prepare_migration(altered,self.sample['ledger'],self.sample['trust'],self.sample['checkpoints'])

    def test_public_view_mutation_detected(self):
        pub=copy.deepcopy(self.sample['public'])
        pub['issued']['entries'][0]['receipt']['body']['assumption_claim']='different'
        with self.assertRaisesRegex(MigrationError,'commitment'):
            self.verify(history=pub)

    def test_public_view_rejects_secret_distribution(self):
        pub=copy.deepcopy(self.sample['public'])
        pub['registration']['keys']={'V':'aa'*32}
        with self.assertRaises(MigrationError):self.verify(history=pub)

    def test_public_legacy_anchor_cannot_be_swapped(self):
        pub=copy.deepcopy(self.sample['public'])
        pub['issued']['anchor']['count']-=1
        with self.assertRaises(MigrationError):self.verify(history=pub)

    def test_tampered_migration_rehash_without_resigning_rejected(self):
        migration=copy.deepcopy(self.sample['migration'])
        migration['body']['governance_status']='conditionally_admitted'
        migration['digest']=sha({k:v for k,v in migration.items() if k!='digest'})
        with self.assertRaises(MigrationError):self.verify(migration=migration)

    def test_one_attestor_missing_fails(self):
        migration=copy.deepcopy(self.sample['migration'])
        del migration['signatures']['W2']
        migration['digest']=sha({k:v for k,v in migration.items() if k!='digest'})
        with self.assertRaises(MigrationError):self.verify(migration=migration)

    def test_forged_witness_signature_rejected(self):
        migration=copy.deepcopy(self.sample['migration'])
        migration['signatures']['W1']=migration['signatures']['W2']
        migration['digest']=sha({k:v for k,v in migration.items() if k!='digest'})
        with self.assertRaisesRegex(ContinuityError,'signature'):
            self.verify(migration=migration,retained=pin(self.sample['trust'],migration,self.sample['ledger']))

    def test_witness_altered_checkpoint_rejected(self):
        cp=copy.deepcopy(self.sample['checkpoints'])
        cp['W1']['body']['governance_anchor']['count']=1
        cp['W1']['digest']=sha({k:v for k,v in cp['W1'].items() if k!='digest'})
        with self.assertRaises((MigrationError,ContinuityError)):self.verify(checkpoints=cp)

    def test_stale_governance_database_detected_by_external_pin(self):
        ledger=copy.deepcopy(self.sample['ledger'])
        ledger['rows'].pop()
        ledger['anchor']={'count':1,'head':ledger['rows'][-1]['entry_digest']}
        with self.assertRaises(MigrationError):self.verify(ledger=ledger)

    def test_old_or_replaced_retained_pin_detected(self):
        old=copy.deepcopy(self.sample['pin'])
        old['governance_anchor']['count']=1
        with self.assertRaisesRegex(MigrationError,'pin'):
            self.verify(retained=old)

    def test_genesis_substitution_invalid(self):
        trust=copy.deepcopy(self.sample['trust'])
        trust['public']['R0']=trust['public']['W1']
        with self.assertRaises(MigrationError):self.verify(trust=trust)

    def test_signing_key_is_not_hmac_key(self):
        self.assertNotIn('R1',self.sample['public']['registration'].get('keys',{}))
        self.assertNotIn('keys',self.sample['public']['registration'])

    def test_two_signing_roots_can_still_collude_to_false_attestation(self):
        # Public policy authenticates endorsed claims, not the honest ceremony.
        self.assertFalse(self.verify()['physical_assumptions_verified'])
        self.assertFalse(self.verify()['trust_genesis_externally_proved'])

    def test_history_prior_replay_not_upgraded_to_independent_verification(self):
        self.assertEqual(self.verify()['historical_validation_mode'],'attested_prior_legacy_replay')
        self.assertFalse(self.verify()['historical_hmac_reexecuted'])

    def test_public_view_wrong_shape_rejected(self):
        with self.assertRaises(MigrationError):self.verify(history={'issued':{}})

    def test_random_role_scoped_genesis_ceremony(self):
        m=hosted_material(deterministic=False)
        c=m['ceremony']
        body,pub=prepare_migration(c['baseline'],c['ledger'],c['trust'],c['checkpoints'])
        mig=attest_migration(body,m['signer_keys'])
        r=public_verify(mig,pub,c['ledger'],c['trust'],c['checkpoints'],pin(c['trust'],mig,c['ledger']))
        self.assertEqual(r['status'],'revoked')


class FutureReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample=fixture()

    def setUp(self):
        self.m=self.sample['migration'];self.trust=self.sample['trust'];self.private=self.sample['private']
        self.retired=sign_future(future_body(self.m,[],'legacy_keys_retired','original keys retired by custodian'),self.private)
        self.ack=sign_future(future_body(self.m,[self.retired],'custody_confirmed','public mirror alive'),self.private)

    def test_public_future_receipts_after_legacy_erasure(self):
        result=replay_future([self.retired,self.ack],self.m,self.trust)
        self.assertEqual(result['receipt_count'],2)
        self.assertTrue(result['retirement_attested'])
        self.assertTrue(result['no_renewal_admitted_by_receipts'])
        self.assertFalse(result['historical_hmac_reexecuted'])

    def test_future_receipt_archive_sqlite_independent_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'future.sqlite3';create_future_archive(path)
            append_future_archive(path,self.retired,self.m,self.trust)
            append_future_archive(path,self.ack,self.m,self.trust)
            self.assertEqual(export_future_archive(path),[self.retired,self.ack])
            self.assertEqual(verify_future_pin(export_future_archive(path),self.m,self.trust,
                                              future_pin(self.m,[self.retired,self.ack],self.trust))['status'],'revoked')

    def test_legacy_retirement_does_not_establish_secret_destruction(self):
        self.assertTrue(replay_future([self.retired],self.m,self.trust)['retirement_attested'])
        self.assertNotIn('secret_erasure_proved',replay_future([self.retired],self.m,self.trust))

    def test_future_notice_does_not_activate_revoked_certificate(self):
        warning=sign_future(future_body(self.m,[self.retired,self.ack], 'audit_warning','recheck required'),self.private)
        self.assertEqual(replay_future([self.retired,self.ack,warning],self.m,self.trust)['status'],'revoked')

    def test_duplicate_receipt_replay_rejected(self):
        with self.assertRaises(MigrationError):replay_future([self.retired,self.retired],self.m,self.trust)

    def test_second_retirement_rejected(self):
        again=sign_future(future_body(self.m,[self.retired], 'legacy_keys_retired','again'),self.private)
        with self.assertRaises(MigrationError):replay_future([self.retired,again],self.m,self.trust)

    def test_future_receipt_signer_swap_rejected(self):
        forged=copy.deepcopy(self.ack)
        forged['signatures']['W1']=forged['signatures']['W2']
        forged['digest']=sha({k:v for k,v in forged.items() if k!='digest'})
        with self.assertRaises(ContinuityError):replay_future([self.retired,forged],self.m,self.trust)

    def test_future_scope_substitution_rejected_even_with_correct_signatures(self):
        changed=copy.deepcopy(self.ack['body']);changed['claim_scope']='fixture-stimulated-stratified-detection'
        forged=sign_future(changed,self.private)
        with self.assertRaises(MigrationError):replay_future([self.retired,forged],self.m,self.trust)

    def test_future_migration_digest_substitution_rejected(self):
        changed=copy.deepcopy(self.ack['body']);changed['migration_digest']='f'*64
        forged=sign_future(changed,self.private)
        with self.assertRaises(MigrationError):replay_future([self.retired,forged],self.m,self.trust)

    def test_new_certificate_issuance_forbidden_by_future_notice_policy(self):
        with self.assertRaises(MigrationError):future_body(self.m,[],'issue_new_certificate','not allowed')

    def test_future_pin_prevents_rollback_of_receipts(self):
        latest=future_pin(self.m,[self.retired,self.ack],self.trust)
        with self.assertRaisesRegex(MigrationError,'rollback'):
            verify_future_pin([self.retired],self.m,self.trust,latest)

    def test_rollback_of_archive_and_latest_external_pin_together_not_detected(self):
        stale=future_pin(self.m,[self.retired],self.trust)
        self.assertEqual(verify_future_pin([self.retired],self.m,self.trust,stale)['receipt_count'],1)

    def test_missing_latest_witness_file_is_not_auto_recoverable(self):
        with self.assertRaises(MigrationError):verify_future_pin([self.retired],self.m,self.trust,{})

    def test_forged_signed_receipt_type_rejected(self):
        bad=copy.deepcopy(self.retired['body']);bad['kind']='approve_new_revision'
        with self.assertRaises(MigrationError):replay_future([sign_future(bad,self.private)],self.m,self.trust)

    def test_sqlite_delete_update_blocked_normally(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'future.sqlite3';create_future_archive(path)
            append_future_archive(path,self.retired,self.m,self.trust)
            with sqlite3.connect(path) as db:
                with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM future_receipts')
                with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE future_receipts SET seq=5")

    def test_external_database_overwrite_outside_sqlite_not_precluded(self):
        self.assertFalse(public_verify(self.m,self.sample['public'],self.sample['ledger'],self.trust,
                                      self.sample['checkpoints'],self.sample['pin'])['global_rollback_precluded'])


if __name__=='__main__':unittest.main()
