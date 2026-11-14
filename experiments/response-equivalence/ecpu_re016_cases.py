"""RE-016 real-E-CPU integration cases (CI checkout required)."""
import copy
import unittest

from credential_continuity import ContinuityError
from public_migration import hosted_material,MigrationError
from ecpu_re016_hosts import ceremony_host,signer_host,assemble,public_verifier_host,independent_replay
from detection_calibration import sha


class ECPUMigrationCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.material=hosted_material(deterministic=True)
        cls.ceremony=ceremony_host(cls.material['ceremony'])
        cls.signers={r:signer_host(r,cls.ceremony,cls.material['signer_keys'][r])
                     for r in ('R1','W1','W2')}
        cls.bundle=assemble(cls.ceremony,cls.signers)

    def test_true_real_ecpu_causal_job_handoff(self):
        got=public_verifier_host(self.ceremony,self.signers,self.bundle['retained_pin'])
        self.assertEqual(got['result']['status'],'revoked')
        self.assertEqual(got['result']['historical_validation_mode'],'attested_prior_legacy_replay')
        self.assertEqual(got['causal_relation'],'C_before_each_signer; signers_pairwise_concurrent')

    def test_independent_public_replay(self):
        received=public_verifier_host(self.ceremony,self.signers,self.bundle['retained_pin'])
        self.assertFalse(independent_replay(self.ceremony,self.signers,self.bundle['retained_pin'],received)['historic_hmac_reverified'])

    def test_wrong_credential_signature_rejected(self):
        bad=copy.deepcopy(self.signers)
        bad['W1']['migration_signature']=bad['W2']['migration_signature']
        bad['W1']['digest']=sha({k:v for k,v in bad['W1'].items() if k!='digest'})
        with self.assertRaises(ContinuityError):assemble(self.ceremony,bad)

    def test_stolen_or_swapped_frame_rejected_after_rehash(self):
        bad=copy.deepcopy(self.signers)
        bad['W1']['frame']=copy.deepcopy(bad['W2']['frame'])
        bad['W1']['digest']=sha({k:v for k,v in bad['W1'].items() if k!='digest'})
        with self.assertRaises(MigrationError):assemble(self.ceremony,bad)

    def test_counterfeit_frame_with_wrong_causal_stamp_rejected(self):
        bad=copy.deepcopy(self.signers)
        bad['R1']['frame']=copy.deepcopy(self.ceremony['frame'])
        bad['R1']['frame']['actor_id']='R1'
        bad['R1']['frame']['causal']['actor_id']='R1'
        bad['R1']['digest']=sha({k:v for k,v in bad['R1'].items() if k!='digest'})
        with self.assertRaises((MigrationError,ValueError)):assemble(self.ceremony,bad)

    def test_migrated_public_evidence_is_not_a_secret_carrier(self):
        self.assertNotIn('keys',self.ceremony['public_history']['registration'])
        self.assertNotIn('baseline',self.ceremony)
        self.assertFalse(public_verifier_host(self.ceremony,self.signers,
                           self.bundle['retained_pin'])['legacy_key_material_used'])

    def test_missing_signer_host_rejected(self):
        bad=copy.deepcopy(self.signers);del bad['W2']
        with self.assertRaises(MigrationError):assemble(self.ceremony,bad)

    def test_wrong_latest_pin_rejected(self):
        old=copy.deepcopy(self.bundle['retained_pin'])
        old['migration_digest']='a'*64
        with self.assertRaises(MigrationError):public_verifier_host(self.ceremony,self.signers,old)

    def test_no_historical_verification_claim_in_replay(self):
        result=public_verifier_host(self.ceremony,self.signers,self.bundle['retained_pin'])
        self.assertFalse(result['result']['historical_hmac_reexecuted'])


if __name__=='__main__':unittest.main()