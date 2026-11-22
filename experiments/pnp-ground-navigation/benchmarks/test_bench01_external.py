"""Adversarial tests for external source pinning and CDCL publication evidence."""
from __future__ import annotations
import hashlib
import unittest
from unittest.mock import patch
from subprocess import TimeoutExpired, CompletedProcess
from bench01_3sat import as_dimacs
from bench01_external import (
    CORPUS_COMMIT, OFFICIAL_2026_COMMIT, git_blob_sha1, manifest,
    model_to_bitset, parent_accept_cdcl, raw_url, run_cdcl, verify_source,
)

class ExternalSourceTests(unittest.TestCase):
    def sample(self):
        raw = as_dimacs(50, [[1, 2, 3] for _ in range(218)])
        return dict(id='test', path=manifest()[0]['path'],
                    github_blob_sha1=git_blob_sha1(raw),
                    publisher_label='UNSAT'), raw

    def test_fixed_corpus_and_full_commit_pins(self):
        m = manifest()
        self.assertEqual(len(m), 6)
        self.assertEqual(len(set(x['path'] for x in m)), 6)
        self.assertEqual(len(CORPUS_COMMIT), 40)
        self.assertEqual(len(OFFICIAL_2026_COMMIT), 40)
        self.assertIn(CORPUS_COMMIT, raw_url(m[0]))

    def test_source_bytes_checked_before_parsing(self):
        entry, raw = self.sample()
        result = verify_source(raw, entry)
        self.assertEqual(result['n'], 50)
        self.assertEqual(len(result['clauses']), 218)
        self.assertEqual(result['bytes_sha256'], hashlib.sha256(raw).hexdigest())
        with self.assertRaisesRegex(ValueError, 'pinned blob'):
            verify_source(raw + b'c forged\n', entry)
        with self.assertRaises(ValueError):
            verify_source(raw * 200, entry)

    def test_not_an_arbitrary_url_downloader(self):
        with self.assertRaises(ValueError):
            raw_url(dict(path='../../secret.cnf'))

    def test_labels_never_prove_truth(self):
        entry, raw = self.sample()
        self.assertEqual(entry['publisher_label'], 'UNSAT')
        self.assertEqual(verify_source(raw, entry)['n'], 50)
        self.assertEqual(parent_accept_cdcl(
            {'claim': 'SAT', 'model': '1'}, 50, [[1, 2, 3]]),
            ('SAT', 'original-source-witness'))

    def test_renamed_dimensions_with_matching_blob_fail(self):
        raw = as_dimacs(51, [[1,2,3] for _ in range(218)])
        entry = self.sample()[0]
        entry['github_blob_sha1'] = git_blob_sha1(raw)
        with self.assertRaisesRegex(ValueError, 'cohort shape'):
            verify_source(raw, entry)

class CDBLBoundaryTests(unittest.TestCase):
    def test_source_checked_model(self):
        self.assertEqual(parent_accept_cdcl(
            {'claim': 'SAT', 'model': '2'}, 2, [[1,2],[-1,2]]),
            ('SAT', 'original-source-witness'))

    def test_false_witness_refused(self):
        with self.assertRaisesRegex(ValueError, 'unsupported SAT'):
            parent_accept_cdcl({'claim': 'SAT', 'model': '0',
                                'worker_source_checked': True}, 2, [[1]])

    def test_unsat_not_proven_by_worker_only(self):
        claim = {'claim': 'UNSAT', 'model': None}
        self.assertEqual(parent_accept_cdcl(claim, 50, [[1]]),
                         ('UNVERIFIED_UNSAT', 'no-independent-CDCL-UNSAT-proof'))
        self.assertEqual(parent_accept_cdcl(claim, 50, [[1]], True),
                         ('UNSAT', 'independent-source-proof'))

    def test_unsat_with_model_refused(self):
        with self.assertRaisesRegex(ValueError, 'spurious model'):
            parent_accept_cdcl({'claim': 'UNSAT', 'model':'0'}, 2, [[1]])

    def test_bad_model_literals_refused(self):
        for m in ([1,-1],[3],[0],[True]):
            with self.assertRaises(ValueError):
                model_to_bitset(m,2)
        self.assertEqual(model_to_bitset([-1,2], 2),2)

    def test_timeout_yields_unknown(self):
        with patch('bench01_external.subprocess.run',
                   side_effect=TimeoutExpired('python',0.1)):
            r = run_cdcl(2, [[1]], timeout=0.1)
        self.assertEqual((r['accepted'],r['reason']),
                         ('UNKNOWN','subprocess-deadline'))

    def test_missing_backend_is_error(self):
        with patch('bench01_external.subprocess.run',
                   return_value=CompletedProcess(['python'],1,'','missing solver')):
            r=run_cdcl(2,[[1]],timeout=1)
        self.assertEqual(r['accepted'],'ERROR')

    def test_invalid_worker_output_is_error(self):
        with patch('bench01_external.subprocess.run',
                   return_value=CompletedProcess(['python'],0,'not-json','')):
            r=run_cdcl(2,[[1]],timeout=1)
        self.assertEqual(r['accepted'],'ERROR')

if __name__ == '__main__':
    unittest.main()
