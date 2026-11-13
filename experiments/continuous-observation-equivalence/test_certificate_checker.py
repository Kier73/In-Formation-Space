"""Independent-certificate acceptance and adversarial rejection tests."""
from __future__ import annotations

import copy
from fractions import Fraction
import random
import unittest

from certificate_producer import produce, canonical_bytes
from continuous_equivalence import layer
from independent_certificate_checker import (
    CertificateError, hash_bytes, verify_certificate, verify_json_bytes,
)
from coe_fixtures import fixtures


class IndependentCertificateCheckerTests(unittest.TestCase):
    def setUp(self):
        self.networks = fixtures()

    def accepted(self, source):
        proof = produce(source)
        checked = verify_certificate(proof, expected_network_sha256=proof["network_sha256"])
        self.assertEqual(checked["status"], "verified")
        self.assertEqual(checked["semantic_sha256"], proof["semantic_sha256"])
        return proof

    def rejected(self, proof, reason: str = ""):
        with self.assertRaisesRegex(CertificateError, reason):
            verify_certificate(proof)

    def test_independent_checker_accepts_exact_semantically_equal_distinct_networks(self):
        a, b = self.accepted(self.networks["identity"]), self.accepted(self.networks["relu_identity"])
        self.assertNotEqual(a["network_sha256"], b["network_sha256"])
        self.assertEqual(a["semantic_sha256"], b["semantic_sha256"])
        self.assertEqual(len(a["atomic_cells"]), 1)
        self.assertEqual(len(b["atomic_cells"]), 2)
        self.assertEqual(len(a["semantic_atlas"]), 1)
        self.assertEqual(len(b["semantic_atlas"]), 1)

    def test_rescaled_bump_verifies_and_zero_differs(self):
        a = self.accepted(self.networks["triangular_bump"])
        b = self.accepted(self.networks["rescaled_bump"])
        z = self.accepted(self.networks["zero"])
        self.assertEqual(a["semantic_sha256"], b["semantic_sha256"])
        self.assertNotEqual(a["semantic_sha256"], z["semantic_sha256"])
        self.assertEqual([r["right"] for r in a["atomic_cells"]], ["0", "1/2", "1", "+inf"])

    def test_wrong_output_law_even_with_recomputed_semantic_hash_rejected(self):
        claim = produce(self.networks["triangular_bump"])
        claim["atomic_cells"][1]["affines"][0][0] = "2"
        self.rejected(claim, "incorrect affine law")

    def test_hidden_relu_transition_must_be_exposed_even_when_outputs_cancel(self):
        # The true output atlas is one linear region, but internal ReLUs change at x=0.
        claim = produce(self.networks["relu_identity"])
        claim["atomic_cells"] = copy.deepcopy(claim["semantic_atlas"])
        self.rejected(claim, "undisclosed ReLU sign transition")

    def test_cover_must_be_complete_ordered_nonoverlapping(self):
        claim = produce(self.networks["triangular_bump"])
        claim["atomic_cells"][0]["right"] = "-1"
        self.rejected(claim, "missing, overlapping")
        claim = produce(self.networks["triangular_bump"])
        claim["atomic_cells"][1]["left"] = "-1/2"
        self.rejected(claim, "missing, overlapping")
        claim = produce(self.networks["triangular_bump"])
        claim["atomic_cells"][0]["left"] = "-1"
        self.rejected(claim, "full real line")
        claim = produce(self.networks["triangular_bump"])
        claim["atomic_cells"].pop()
        self.rejected(claim, "full real line")
        claim = produce(self.networks["triangular_bump"])
        claim["atomic_cells"][1]["right"] = "0"
        self.rejected(claim, "empty or inverted")

    def test_network_source_binding_and_hidden_parameter_intervention(self):
        claim = produce(self.networks["triangular_bump"])
        expected = claim["network_sha256"]
        claim["network"]["layers"][0]["bias"][1] = "-1/4"
        self.rejected(claim, "network digest mismatch")
        claim["network_sha256"] = hash_bytes(claim["network"])
        with self.assertRaisesRegex(CertificateError, "independent expected network identity mismatch"):
            verify_certificate(claim, expected_network_sha256=expected)
        self.rejected(claim, "undisclosed ReLU sign transition")

    def test_bad_semantic_atlas_or_digest_fails_closed(self):
        claim = produce(self.networks["triangular_bump"])
        claim["semantic_atlas"] = claim["semantic_atlas"][:2]
        self.rejected(claim, "incorrect or noncanonical semantic atlas")
        claim = produce(self.networks["triangular_bump"])
        claim["semantic_sha256"] = "0" * 64
        self.rejected(claim, "semantic atlas digest mismatch")
        claim = produce(self.networks["triangular_bump"])
        claim["semantic_atlas"][1]["affines"][0][1] = "1"
        claim["semantic_sha256"] = hash_bytes(claim["semantic_atlas"])
        self.rejected(claim, "incorrect or noncanonical semantic atlas")

    def test_noncanonical_fraction_tokens_are_rejected(self):
        for bad in ("00", "+1", "-0", "1/1", "2/4", "-0/2", "0/0", "1e3", "1.0"):
            claim = produce(self.networks["identity"])
            claim["atomic_cells"][0]["affines"][0][0] = bad
            self.rejected(claim, "rational")
        claim = produce(self.networks["triangular_bump"])
        claim["atomic_cells"][0]["right"] = "0/1"
        self.rejected(claim, "rational")

    def test_duplicate_json_keys_noncanonical_encoding_and_trailing_bytes_rejected(self):
        claim = produce(self.networks["identity"])
        valid = canonical_bytes(claim) + b"\n"
        self.assertEqual(verify_json_bytes(valid)["status"], "verified")
        for bad in (canonical_bytes(claim), valid + b"\n", b" " + valid,
                    valid.replace(b'"schema":', b'"schema":0,"schema":', 1)):
            with self.assertRaises(CertificateError):
                verify_json_bytes(bad)

    def test_input_arity_strict_schema_and_resource_budgets(self):
        claim = produce(self.networks["triangular_bump"])
        with self.assertRaisesRegex(CertificateError, "cell budget"):
            verify_certificate(claim, max_cells=2)
        with self.assertRaisesRegex(CertificateError, "work budget"):
            verify_certificate(claim, max_scalar_ops=3)
        claim = produce(self.networks["identity"])
        claim["junk"] = True
        self.rejected(claim, "invalid certificate fields")
        claim = produce(self.networks["identity"])
        claim["schema"] = "unknown"
        self.rejected(claim, "unsupported certificate schema")
        claim = produce(self.networks["identity"])
        claim["network"]["layers"][0]["weights"][0].append("1")
        claim["network_sha256"] = hash_bytes(claim["network"])
        self.rejected(claim, "nonrectangular")

    def test_120_generated_networks_pass_standalone_checker(self):
        rng = random.Random(20261113)
        for case in range(120):
            layers = []
            width = 1
            depth = rng.randint(1, 4)
            for index in range(depth):
                height = rng.randint(1, 3)
                weights = [[rng.randint(-2, 2) for _ in range(width)] for _ in range(height)]
                bias = [Fraction(rng.randint(-3, 3), 2) for _ in range(height)]
                layers.append(layer(weights, bias, "linear" if index == depth - 1 else "relu"))
                width = height
            proof = produce(tuple(layers))
            status = verify_certificate(proof)
            self.assertEqual(status["status"], "verified", case)


if __name__ == "__main__":
    unittest.main()
