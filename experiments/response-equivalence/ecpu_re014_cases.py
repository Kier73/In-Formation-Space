"""RE-014 hosted causal + journal integration tests (requires pinned E-CPU)."""
import copy
import tempfile
import unittest
from pathlib import Path

from authority_reconstruction import AuthorityError, evidence, registration, sign_event
from detection_calibration import sha
from ecpu_re014_hosts import issue_host, revoke_host, verify_host


class HostedAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'authority.sqlite3'
        self.reg=registration(deterministic=True)
        self.doc=evidence(self.reg)
        m=sign_event(self.reg,'M','endorse',self.doc)
        p=sign_event(self.reg,'P','endorse',self.doc)
        self.issued=issue_host(self.reg,self.doc,m,p,self.db)

    def test_actual_ecpu_causal_handoff_and_durable_sqlite(self):
        out=verify_host(self.issued,self.reg,self.doc,sqlite_path=self.db,
                        expected_anchor=self.issued['anchor'])
        self.assertEqual(out['authority']['status'],'conditionally_admitted')
        self.assertEqual(out['causal_relation'],'Q_before_W')
        self.assertIsNone(out['cross_host_elapsed'])

    def test_revocation_causally_follows_issue_and_replays(self):
        r=revoke_host(self.issued,self.reg,self.doc,self.db)
        out=verify_host(r,self.reg,self.doc,sqlite_path=self.db,
                        expected_anchor=r['anchor'],parent_issued=self.issued)
        self.assertEqual(out['authority']['status'],'revoked')
        self.assertEqual(out['causal_relation'],'R_before_W')

    def test_revocation_without_issuance_parent_fails(self):
        r=revoke_host(self.issued,self.reg,self.doc,self.db)
        with self.assertRaisesRegex(AuthorityError,'without preserved'):
            verify_host(r,self.reg,self.doc,expected_anchor=r['anchor'])

    def test_stale_anchor_detects_append_only_revocation(self):
        r=revoke_host(self.issued,self.reg,self.doc,self.db)
        with self.assertRaisesRegex(AuthorityError,'independent journal anchor'):
            verify_host(self.issued,self.reg,self.doc,expected_anchor=r['anchor'])

    def test_replayed_old_sqlite_view_not_current(self):
        revoke_host(self.issued,self.reg,self.doc,self.db)
        with self.assertRaisesRegex(AuthorityError,'SQLite reconstruction differs'):
            verify_host(self.issued,self.reg,self.doc,sqlite_path=self.db)

    def test_swapped_stamp_fails_signed_binding(self):
        bad=copy.deepcopy(self.issued)
        bad['frame']['causal']['vector']['Q']=0
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(AuthorityError,'signed stamp'):
            verify_host(bad,self.reg,self.doc)

    def test_tampered_record_with_rehashed_envelope_fails_binding(self):
        bad=copy.deepcopy(self.issued)
        bad['transcript']['entries'][0]['receipt']['body']['assumption_claim']='physical_truth'
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(AuthorityError,'binding'):
            verify_host(bad,self.reg,self.doc)

    def test_cross_scope_doc_rejected(self):
        from authority_reconstruction import evidence as make_evidence
        other=make_evidence(self.reg,protocol='stimulated')
        with self.assertRaisesRegex(AuthorityError,'binding'):
            verify_host(self.issued,self.reg,other)

    def test_missing_signed_anchor_rejected(self):
        bad=copy.deepcopy(self.issued)
        bad['anchor']['head']='1'*64
        with self.assertRaisesRegex(AuthorityError,'binding'):
            verify_host(bad,self.reg,self.doc)

    def test_revoke_replay_requires_proper_parent(self):
        r=revoke_host(self.issued,self.reg,self.doc,self.db)
        wrong=copy.deepcopy(self.issued)
        wrong['digest']='x'*64
        with self.assertRaises(AuthorityError):
            verify_host(r,self.reg,self.doc,parent_issued=wrong)


if __name__=='__main__':unittest.main()
