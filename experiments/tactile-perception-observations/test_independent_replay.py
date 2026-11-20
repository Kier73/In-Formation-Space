"""Independent reconstruction tests: replay source bytes, not summary claims."""
import base64
import json
import unittest

from independent_replay import verify
from noaa_bridge import compare_expressions
from test_noaa_bridge import packet, read

def report():
    m,e=read("metric"),read("english")
    return {"experiment":"TPP-003","observations":[m,e],
            "cross_unit_relation":compare_expressions(m,e)}

class IndependentReplayTests(unittest.TestCase):
    def test_replay_exact_original_bytes(self):
        result=verify(report())
        self.assertEqual(result["status"],"unit-expression-consistent")
        self.assertEqual(result["checked_observations"],2)
        self.assertTrue(result["verified_raw_bytes"])

    def test_tamper_normalized_value_refused(self):
        r=report()
        r["observations"][0]["observations"][0]["value"]="9.999"
        with self.assertRaisesRegex(ValueError,"normalized observation"):
            verify(r)

    def test_tamper_content_hash_refused(self):
        r=report()
        r["observations"][0]["raw_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"digest"):
            verify(r)

    def test_tamper_original_bytes_with_old_hash_refused(self):
        r=report()
        doc=r["observations"][0]
        raw=base64.b64decode(doc["raw_body_base64"])
        doc["raw_body_base64"]=base64.b64encode(raw.replace(b"1.524",b"9.524")).decode("ascii")
        with self.assertRaisesRegex(ValueError,"digest"):
            verify(r)

    def test_forged_claimed_equivalence_refused(self):
        r=report()
        r["cross_unit_relation"]["max_absolute_deviation_m"]="0"
        with self.assertRaisesRegex(ValueError,"claimed translation"):
            verify(r)

    def test_provider_quality_tamper_refused(self):
        r=report()
        r["observations"][0]["observations"][0]["provider_quality"]="v"
        with self.assertRaisesRegex(ValueError,"normalized observation"):
            verify(r)

    def test_unavailable_source_undetermined(self):
        r=report()
        r["observations"][0]={"status":"unavailable","observations":[]}
        r["cross_unit_relation"]={"status":"undetermined","matches":0}
        self.assertEqual(verify(r)["status"],"undetermined")

if __name__=="__main__":
    unittest.main()
