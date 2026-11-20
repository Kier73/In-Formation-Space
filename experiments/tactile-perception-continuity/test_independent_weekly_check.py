"""Independent TPP-007 source-replay and mathematical-checker adversarial tests."""
from __future__ import annotations

import base64
from hashlib import sha256
import json
import unittest

from independent_weekly_check import verify
from test_seven_day_residual import fixture

class IndependentWeeklyChecks(unittest.TestCase):
    def test_independent_decimal_reconstruction_of_complete_week(self):
        report=fixture()
        audit=verify(report)
        self.assertTrue(audit["checked_complete"])
        self.assertEqual(audit["verified_days"],7)
        self.assertEqual(audit["heldout_observations"],720)

    def test_rewritten_claim_fails_even_with_intact_source_bytes(self):
        report=fixture()
        report["assessment"]["frozen_day_one_correction_m"]="999/1"
        with self.assertRaisesRegex(ValueError,"independent Decimal"):
            verify(report)

    def test_source_checksum_and_context_checked_separately(self):
        report=fixture()
        report["documents"][1]["raw_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"checksum"):
            verify(report)
        report=fixture()
        report["documents"][0]["source"]="https://example.invalid"
        with self.assertRaisesRegex(ValueError,"origin"):
            verify(report)

    def test_modified_physical_sample_with_resealed_bytes_changes_result(self):
        report=fixture()
        doc=report["documents"][0]
        payload=json.loads(base64.b64decode(doc["raw_body_base64"]))
        payload["data"][121]["v"]="7.000"
        data=json.dumps(payload).encode()
        doc["raw_body_base64"]=base64.b64encode(data).decode()
        doc["raw_bytes"]=len(data)
        doc["raw_sha256"]=sha256(data).hexdigest()
        with self.assertRaisesRegex(ValueError,"independent Decimal"):
            verify(report)

    def test_unavailable_source_never_declares_complete_week(self):
        report=fixture()
        original=report["documents"][0]
        report["documents"][0]={k:original[k] for k in (
            "source","product","start_utc_day","end_utc_day")}
        report["documents"][0]["status"]="unavailable"
        with self.assertRaisesRegex(ValueError,"missing source"):
            verify(report)
        report["assessment"]={"status":"undetermined"}
        self.assertFalse(verify(report)["checked_complete"])

if __name__=="__main__":
    unittest.main()
