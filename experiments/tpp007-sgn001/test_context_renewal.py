"""Adversarial offline and archived-evidence checks for contextual Ground renewal."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from context_renewal import (
    POLICY, _milli, build_receipt, digest, prepare, read_sources,
    score, twice_median, verify_receipt,
)

ARCHIVE = os.environ.get('TPP007_ARCHIVE')
SGN = os.environ.get('TPP007_SGN_REPORT')


def sequence(offsets):
    return [value for offset in offsets for value in [offset] * 240]


class OfflinePolicyTests(unittest.TestCase):
    def test_fractional_integer_median_and_no_decimal_rounding(self):
        self.assertEqual(twice_median([1000,1001]),2001)
        self.assertEqual(twice_median([-1,-3,2,4]),1)
        self.assertEqual(_milli('0.051'),51)
        self.assertEqual(_milli('-0.001'),-1)
        for text in ('NaN','0.0001'):
            with self.assertRaises(ValueError):
                _milli(text)

    def test_future_changes_cannot_change_prepared_proposal(self):
        series = sequence([500,460,420,400,390,460,490])
        expected = prepare(series)
        altered = series.copy()
        altered[-240:] = [100000] * 240
        self.assertEqual(prepare(altered),expected)
        self.assertNotEqual(score(series,expected),score(altered,expected))

    def test_missing_observation_and_changed_policy_refused(self):
        with self.assertRaisesRegex(ValueError,'incomplete'):
            prepare(sequence([1,2,3]))
        with self.assertRaisesRegex(ValueError,'policy'):
            prepare(sequence([1]*7),dict(POLICY,min_improvement_percent=0))

    def test_no_shift_no_renewal(self):
        series = sequence([500]*7)
        self.assertFalse(prepare(series)['renewal_triggered'])
        self.assertEqual(score(series,prepare(series))['status'],'renewal_not_triggered')

    def test_large_shift_without_future_skill_refused(self):
        series = sequence([100,100,100,100,100,300,10000])
        self.assertTrue(prepare(series)['renewal_triggered'])
        self.assertEqual(score(series,prepare(series))['status'],
                         'refused_after_target_observation')

    def test_tampered_earlier_only_proposal_rejected(self):
        series = sequence([100,100,100,100,100,300,330])
        proposal = prepare(series)
        proposal['candidate_offset_twice_millimetres']=-222
        with self.assertRaisesRegex(ValueError,'earlier-only'):
            score(series,proposal)

    def test_calibration_uses_completed_five_days(self):
        series = sequence([553,455,412,401,386,451,492])
        proposal = prepare(series)
        self.assertEqual(proposal['calibration_adjacent_shifts_twice_millimetres'],
                         [196,86,22,30])
        self.assertEqual(proposal['calibrated_threshold_twice_millimetres'],116)
        self.assertTrue(proposal['renewal_triggered'])


@unittest.skipUnless(ARCHIVE and SGN,'original archive and SGN report supplied in CI')
class OriginalEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = json.loads(Path(ARCHIVE).read_text(encoding='utf8'))
        cls.spectral = json.loads(Path(SGN).read_text(encoding='utf8'))
        cls.receipt = build_receipt(cls.archive,cls.spectral)

    def test_original_qualifies_only_completed_historical_target(self):
        self.assertTrue(verify_receipt(self.receipt,self.archive,self.spectral))
        before=self.receipt['payload']['pretarget']
        after=self.receipt['payload']['posttarget']
        self.assertEqual(before['calibration_adjacent_shifts_twice_millimetres'],
                         [195,87,22,30])
        self.assertEqual(before['calibrated_threshold_twice_millimetres'],117)
        self.assertEqual(before['measured_shift_twice_millimetres'],129)
        self.assertEqual(before['candidate_offset_twice_millimetres'],901)
        self.assertEqual(after['status'],'historically_corrob_for_target_only')
        self.assertEqual(after['renewed_candidate_error'],24100)
        self.assertFalse(self.receipt['payload']['authority']['executable_next_unobserved_day'])

    def test_rehash_of_forged_receipt_still_refused(self):
        forged=copy.deepcopy(self.receipt)
        forged['payload']['authority']['executable_next_unobserved_day']=True
        forged['sha256']=digest(forged['payload'])
        with self.assertRaisesRegex(ValueError,'source reconstruction'):
            verify_receipt(forged,self.archive,self.spectral)

    def test_rehashed_provider_body_still_refused(self):
        forged=copy.deepcopy(self.archive)
        forged['documents'][0]['raw_body_base64']='e30='
        forged['documents'][0]['raw_sha256']=__import__('hashlib').sha256(b'{}').hexdigest()
        forged['documents'][0]['raw_bytes']=2
        with self.assertRaisesRegex(ValueError,'source bytes'):
            read_sources(forged)

    def test_rehashed_sgn_qualification_cannot_upgrade_predecessor(self):
        forged=copy.deepcopy(self.spectral)
        forged['lanes']['noaa_residual']['held_out_test']['test_rmse']=0
        with self.assertRaisesRegex(ValueError,'SGN predecessor'):
            build_receipt(self.archive,forged)

    @unittest.skipUnless(shutil.which('node'),'independent Node receiver not installed')
    def test_independent_node_receiver_and_rehashed_adversary(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'receipt.json'
            command=['node',str(Path(__file__).with_name('verify_renewal.mjs')),
                     ARCHIVE,SGN,str(path)]
            path.write_text(json.dumps(self.receipt),encoding='utf8')
            completed=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)
            parsed=json.loads(completed.stdout)
            self.assertEqual(parsed['status'],'verified_retrospective_only')
            self.assertEqual(parsed['receipt_sha256'],self.receipt['sha256'])
            forged=copy.deepcopy(self.receipt)
            forged['payload']['posttarget']['renewed_candidate_error']=0
            forged['sha256']=digest(forged['payload'])
            path.write_text(json.dumps(forged),encoding='utf8')
            refused=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(refused.returncode,0)
            self.assertIn('REFUSED',refused.stderr)


if __name__ == '__main__':
    unittest.main()
