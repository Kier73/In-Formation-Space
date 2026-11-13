"""RE-005: finite causal identification, independent witness authentication scope."""
import copy
import hashlib
import unittest

from independent_event_causation import (
    EPISODES, TRUTHS, EvidenceError, demonstration, enroll, fixture_stamp_factory,
    infer, make_receiver, make_source, make_witness, plant_value,
    sha, verify_source, verify_witness_bundle,
)


class RE005EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.registration = enroll()
        self.key = self.registration["key_hex"]
        self.key_id = self.registration["key_id"]
        self.a = make_source(fixture_stamp_factory("A"))
        self.c = make_witness(fixture_stamp_factory("C"), self.key, self.key_id)
        self.b = make_receiver("common_cause_marker", fixture_stamp_factory("B"), self.a, self.c)

    def infer(self, *, a=None, c=None, b=None, admitted=False, key=None, key_id=None):
        return infer(a or self.a, c or self.c, b or self.b,
                     self.key if key is None else key,
                     self.key_id if key_id is None else key_id,
                     controlled_exclusion_assured=admitted)

    def test_perfect_passive_association_has_two_causes(self):
        self.assertEqual([plant_value("event_causal", e[0]) for e in EPISODES[:2]], [2, 1])
        self.assertEqual([plant_value("common_cause_marker", e[0]) for e in EPISODES[:2]], [2, 1])

    def test_witnessed_control_without_exclusion_still_underdetermined(self):
        result = self.infer()
        self.assertEqual(result["survivors"], sorted(TRUTHS))
        self.assertEqual(result["episodes"][2]["observation_scope"], "not_identifiable")

    def test_controlled_exclusion_changes_which_causes_fit(self):
        result = self.infer(admitted=True)
        self.assertEqual(result["survivors"], ["common_cause_alias", "common_cause_marker"])
        self.assertEqual(result["episodes"][2]["observation_scope"], "controlled_assumption")
        self.assertFalse(result["physical_causation_proved"])

    def test_true_causal_law_is_recoverable_under_control_assumption(self):
        b = make_receiver("event_causal", fixture_stamp_factory("B"), self.a, self.c)
        result = self.infer(b=b, admitted=True)
        self.assertEqual(result["survivors"], ["event_causal"])
        self.assertFalse(result["physical_causation_proved"])

    def test_source_and_witness_can_have_incompatible_local_ticks(self):
        self.assertLess(self.c["records"][0]["local_tick"], self.a["records"][0]["local_tick"])
        self.assertIsNone(self.infer()["external_clock_alignment"])

    def test_enrollment_secret_random_per_registration(self):
        second = enroll()
        self.assertNotEqual(self.key_id, second["key_id"])
        self.assertEqual(hashlib.sha256(bytes.fromhex(self.key)).hexdigest(), self.key_id)

    def test_witness_mac_checks_enrolled_key_not_published_claim(self):
        other = enroll()
        with self.assertRaisesRegex(EvidenceError, "not enrolled|fingerprint|authentication"):
            self.infer(key=other["key_hex"], key_id=other["key_id"])

    def test_changed_witness_event_rejected_without_digest_rewrite(self):
        bad = copy.deepcopy(self.c)
        bad["records"][0]["event"] = 0
        with self.assertRaisesRegex(EvidenceError, "digest"):
            self.infer(c=bad)

    def test_changed_witness_event_rejected_even_after_digest_rewrite(self):
        bad = copy.deepcopy(self.c)
        bad["records"][0]["event"] = 0
        bad["records"][0]["digest"] = sha({k:v for k,v in bad["records"][0].items() if k != "digest"})
        # Recomputing an unkeyed hash cannot forge the enrolled witness MAC.
        with self.assertRaisesRegex(EvidenceError, "authentication"):
            self.infer(c=bad)

    def test_role_change_and_rehashed_record_do_not_forge_witness(self):
        bad = copy.deepcopy(self.c)
        bad["records"][0]["role"] = "A"
        bad["records"][0]["digest"] = sha({k:v for k,v in bad["records"][0].items() if k != "digest"})
        with self.assertRaisesRegex(EvidenceError, "identity"):
            self.infer(c=bad)

    def test_replay_witness_from_other_episode_fails(self):
        bad = copy.deepcopy(self.c)
        bad["records"][0], bad["records"][1] = bad["records"][1], bad["records"][0]
        with self.assertRaisesRegex(EvidenceError, "schedule"):
            self.infer(c=bad)

    def test_b_speaks_to_exact_witness_digest_not_alternative(self):
        bad = copy.deepcopy(self.b)
        bad["records"][0]["witness_digest"] = "f" * 64
        bad["records"][0]["digest"] = sha({k:v for k,v in bad["records"][0].items() if k != "digest"})
        with self.assertRaisesRegex(EvidenceError, "different evidence"):
            self.infer(b=bad)

    def test_dropped_witness_episode_rejected(self):
        bad = copy.deepcopy(self.c)
        bad["records"].pop()
        with self.assertRaisesRegex(EvidenceError, "schedule"):
            self.infer(c=bad)

    def test_untrusted_control_flag_cannot_be_derived_from_mac(self):
        self.assertTrue(all(r["status"] == "observed" for r in self.c["records"]))
        self.assertEqual(self.infer()["survivors"], sorted(TRUTHS))
        self.assertEqual(self.infer(admitted=True)["survivors"], ["common_cause_alias", "common_cause_marker"])

    def test_refusal_never_read_as_zero_event(self):
        c = make_witness(fixture_stamp_factory("C"), self.key, self.key_id, permitted=False)
        b = make_receiver("common_cause_marker", fixture_stamp_factory("B"), self.a, c)
        result = self.infer(c=c, b=b, admitted=True)
        self.assertEqual(result["survivors"], sorted(TRUTHS))
        self.assertTrue(all(r["event"] is None and r["status"] == "refused" for r in c["records"]))

    def test_refusal_with_forged_event_fails_closed(self):
        c = make_witness(fixture_stamp_factory("C"), self.key, self.key_id, permitted=False)
        c["records"][2]["event"] = 0
        c["records"][2]["digest"] = sha({k:v for k,v in c["records"][2].items() if k != "digest"})
        with self.assertRaisesRegex(EvidenceError, "authentication|refusal"):
            verify_witness_bundle(c, self.key, self.key_id)

    def test_missing_receiver_event_fails(self):
        bad = copy.deepcopy(self.b)
        bad["records"] = bad["records"][:-1]
        with self.assertRaisesRegex(EvidenceError, "schedule"):
            self.infer(b=bad)

    def test_wrong_source_protocol_rejected_even_rehashed(self):
        bad = copy.deepcopy(self.a)
        bad["records"][2]["protocol"] = "passive"
        bad["records"][2]["digest"] = sha({k:v for k,v in bad["records"][2].items() if k != "digest"})
        with self.assertRaisesRegex(EvidenceError, "source schedule mismatch"):
            verify_source(bad)

    def test_authenticated_event_not_physical_cause_proof(self):
        r = self.infer(admitted=True)
        self.assertEqual(r["event_source_authentication"], "HMAC-valid relative to enrolled shared secret")
        self.assertFalse(r["physical_event_authentication"])
        self.assertFalse(r["physical_causation_proved"])

    def test_deterministic_report(self):
        r = demonstration()
        self.assertEqual(r["without_control_assurance"]["survivors"], sorted(TRUTHS))
        self.assertEqual(r["with_control_assurance"]["survivors"], ["common_cause_alias", "common_cause_marker"])


if __name__ == "__main__":
    unittest.main()
