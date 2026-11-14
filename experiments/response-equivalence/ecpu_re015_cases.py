"""RE-015 real pinned E-CPU causal/rotation integration tests."""
import copy
import tempfile
import unittest
from pathlib import Path

from credential_continuity import ContinuityError, enrollment, issue_baseline
from detection_calibration import sha
from ecpu_re015_hosts import rotate_host,revoke_host,witness_host,verify_host

class HostedContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=enrollment(deterministic=True)
        cls.baseline=issue_baseline()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        d=Path(self.tmp.name);self.path=d/'governance.sqlite3'
        self.rotated=rotate_host(self.baseline,self.data['trust'],self.data['private'],self.path)
        self.revoked=revoke_host(self.rotated,self.baseline,self.data['trust'],self.data['private'],self.path)
        self.witnesses={role:witness_host(role,self.rotated,self.revoked,
            self.baseline,self.data['trust'],self.data['private'][role],d/(role+'.sqlite3'))
            for role in ('W1','W2')}

    def valid(self,**kw):
        return verify_host(kw.get('rotated',self.rotated),kw.get('revoked',self.revoked),
            kw.get('witnesses',self.witnesses), self.baseline,self.data['trust'],
            journal_path=kw.get('journal',self.path))

    def test_recovery_after_issuer_exit_real_causal_handoff(self):
        out=self.valid()
        self.assertEqual(out['reconstructed']['status'],'revoked')
        self.assertEqual(out['causal_relations']['W1_concurrent_W2'],'concurrent')
        self.assertFalse(out['root_private_keys_required_for_verifier'])
        self.assertTrue(out['legacy_re014_hmac_keys_required'])

    def test_revocation_receipt_requires_original_rotation_parent(self):
        bad=copy.deepcopy(self.revoked);bad['parent']='f'*64
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaises(ContinuityError):self.valid(revoked=bad,journal=None)

    def test_changed_q_stamp_after_rehash_cannot_pass_signature(self):
        bad=copy.deepcopy(self.rotated)
        bad['frame']['causal']['vector']['Q']=0
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaises(ContinuityError):self.valid(rotated=bad,journal=None)

    def test_witness_checkpoint_swap_rejected(self):
        bad=copy.deepcopy(self.witnesses)
        bad['W1']['heads'][-1]=bad['W1']['heads'][-2]
        bad['W1']['digest']=sha({k:v for k,v in bad['W1'].items() if k!='digest'})
        with self.assertRaises(ContinuityError):self.valid(witnesses=bad)

    def test_witness_concurrent_without_shared_wall_clock(self):
        out=self.valid()
        self.assertIsNone(out['physical_clock_elapsed'])
        self.assertEqual(out['causal_relations']['R_before_W1'],'before')

    def test_rolledback_sqlite_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            old=Path(d)/'old.sqlite3'
            rotate_host(self.baseline,self.data['trust'],self.data['private'],old)
            with self.assertRaisesRegex(ContinuityError,'SQLite governance journal'):
                self.valid(journal=old)

    def test_external_witness_without_sender_handoff_rejected(self):
        bad=copy.deepcopy(self.witnesses)
        bad['W2']['frame']['causal']['vector']['R']=0
        bad['W2']['digest']=sha({k:v for k,v in bad['W2'].items() if k!='digest'})
        with self.assertRaises(ContinuityError):self.valid(witnesses=bad)

    def test_missing_witness_bundle_rejected(self):
        with self.assertRaises(ContinuityError):self.valid(witnesses={'W1':self.witnesses['W1']})

if __name__=='__main__':unittest.main()