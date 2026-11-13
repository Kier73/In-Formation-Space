"""COE-004: independent E-CPU identity binding and adversarial source-policy checks."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from coe_fixtures import fixtures
from certificate_producer import produce, canonical_bytes
from ground_binding_producer import (
    construct_binding, require_pinned_ecpu,
)
from ground_binding_verifier import (
    GroundLinkRejected, verify_one, strict_json,
    canonical, verify_bundle,
)


class GroundBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = Path(__file__).parent
        cls.policy = json.loads((directory / "expected_ground_sources.json").read_text())
        cls.profile = json.loads((directory / "ground_profile.json").read_text())

    def claim(self, name):
        cert = produce(fixtures()[name])
        raw = canonical_bytes(cert) + b"\n"
        link = construct_binding(name, raw, policy=self.policy, profile=self.profile)
        return raw, link

    def check(self, name, raw, link):
        return verify_one(name, raw, canonical(link) + b"\n",
                          policy=self.policy, profile=self.profile)

    def test_all_five_candidate_ground_links_with_real_ecpu_types(self):
        results = {name: self.check(name, *self.claim(name))
                   for name in sorted(self.policy["expected_network_sha256"])}
        self.assertEqual(len(results), 5)
        self.assertEqual(results["identity"]["semantic_ref"],
                         results["relu_identity"]["semantic_ref"])
        self.assertEqual(results["triangular_bump"]["semantic_ref"],
                         results["rescaled_bump"]["semantic_ref"])
        self.assertNotEqual(results["triangular_bump"]["semantic_ref"],
                            results["zero"]["semantic_ref"])
        self.assertEqual(len({r["computational_ground_ref"]["content_digest"]
                              for r in results.values()}), 1)
        self.assertEqual({r["status"] for r in results.values()},
                         {"verified-link-not-admitted"})

    def test_wrong_expected_source_is_rejected(self):
        raw, claim = self.claim("identity")
        other = self.policy | {"expected_network_sha256":
                                  self.policy["expected_network_sha256"] |
                                  {"identity": self.policy["expected_network_sha256"]["zero"]}}
        with self.assertRaisesRegex(ValueError, "identity"):
            verify_one("identity", raw, canonical(claim)+b"\n",
                       policy=other, profile=self.profile)

    def test_untrusted_self_consistent_ground_revision_is_not_authority(self):
        raw, claim = self.claim("identity")
        changed = copy.deepcopy(claim)
        changed["candidate_ground"]["content_digest"] = "0" * 64
        with self.assertRaisesRegex(GroundLinkRejected, "candidate Ground"):
            self.check("identity", raw, changed)
        changed = copy.deepcopy(claim)
        changed["ground_admission"] = "admitted"
        with self.assertRaisesRegex(GroundLinkRejected, "admission"):
            self.check("identity", raw, changed)

    def test_observer_projection_and_translation_are_pinned(self):
        raw, claim = self.claim("identity")
        changed = copy.deepcopy(claim)
        changed["observation_contract"]["projection_digest"] = "0" * 64
        with self.assertRaisesRegex(GroundLinkRejected, "observer definition"):
            self.check("identity", raw, changed)
        changed = copy.deepcopy(claim)
        changed["translation_contract"]["context_digest"] = "0" * 64
        with self.assertRaisesRegex(GroundLinkRejected, "translation contract"):
            self.check("identity", raw, changed)
        changed = copy.deepcopy(claim)
        changed["translation_digest"] = "0" * 64
        with self.assertRaisesRegex(GroundLinkRejected, "translation digest"):
            self.check("identity", raw, changed)

    def test_no_certificate_swap_even_if_semantic_function_matches(self):
        raw, claim = self.claim("identity")
        other_raw, _ = self.claim("relu_identity")
        with self.assertRaises(ValueError):
            self.check("identity", other_raw, claim)
        changed = copy.deepcopy(claim)
        changed["certificate_file_sha256"] = hashlib.sha256(other_raw).hexdigest()
        with self.assertRaisesRegex(GroundLinkRejected, "certificate bytes"):
            self.check("identity", raw, changed)

    def test_no_source_substitution_and_no_output_proof_mutation(self):
        raw, claim = self.claim("identity")
        edited = json.loads(raw)
        edited["network"]["layers"][0]["bias"][0] = "1"
        with self.assertRaises(ValueError):
            self.check("identity", canonical(edited)+b"\n", claim)
        edited = json.loads(raw)
        edited["semantic_atlas"][0]["affines"][0][1] = "1"
        with self.assertRaises(ValueError):
            self.check("identity", canonical(edited)+b"\n", claim)

    def test_no_schema_downgrade_or_untrusted_model_labels(self):
        raw, claim = self.claim("identity")
        changed = copy.deepcopy(claim)
        changed["schema"] = "future"
        with self.assertRaisesRegex(GroundLinkRejected, "schema"):
            self.check("identity", raw, changed)
        changed = copy.deepcopy(claim)
        changed["model_id"] = "zero"
        with self.assertRaisesRegex(GroundLinkRejected, "label"):
            self.check("identity", raw, changed)
        changed = copy.deepcopy(claim)
        changed["ecpu_revision"] = "0"*40
        with self.assertRaisesRegex(GroundLinkRejected, "revision"):
            self.check("identity", raw, changed)

    def test_noncanonical_binding_bytes_rejected(self):
        raw, claim = self.claim("identity")
        legal = canonical(claim)+b"\n"
        self.assertEqual(strict_json(legal), claim)
        for attack in (legal[:-1], b" "+legal, legal+b"\n",
                       legal.replace(b'"model_id":', b'"model_id":"wrong","model_id":', 1)):
            with self.assertRaises(GroundLinkRejected):
                strict_json(attack)

    def test_ground_profile_is_declared_not_auto_admitted(self):
        raw, claim = self.claim("zero")
        tampered = self.profile | {"admission": "admitted"}
        with self.assertRaisesRegex(GroundLinkRejected, "unadmitted Ground profile"):
            verify_one("zero", raw, canonical(claim)+b"\n", policy=self.policy, profile=tampered)
        tampered = self.profile | {"output_schema": {"ordered": ["y0", "y1"], "value_kind": "exact-real"}}
        with self.assertRaisesRegex(GroundLinkRejected, "language or arity"):
            verify_one("zero", raw, canonical(claim)+b"\n", policy=self.policy, profile=tampered)

    def test_pinned_ecpu_revision_checked_against_actual_git_head(self):
        with mock.patch("ground_binding_producer.subprocess.check_output", return_value=self.policy["ecpu_revision"]+"\n"):
            self.assertEqual(require_pinned_ecpu(self.policy, Path("unused")), self.policy["ecpu_revision"])
        with mock.patch("ground_binding_producer.subprocess.check_output", return_value="0"*40+"\n"):
            with self.assertRaisesRegex(ValueError, "checkout differs"):
                require_pinned_ecpu(self.policy, Path("unused"))


if __name__ == "__main__":
    unittest.main()
