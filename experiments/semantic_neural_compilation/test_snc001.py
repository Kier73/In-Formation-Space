"""SNC-001 positive and adversarial exact semantic compilation tests."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import unittest

from compiler import AtlasRejected, compile_semantics, parse_atlas
from verifier import CertificateError, verify_capsule

EXAMPLES = json.loads((Path(__file__).parent / "examples.json").read_text())


def raw(cap: object) -> bytes:
    return (json.dumps(cap, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True) + "\n").encode("ascii")


def fixture(name: str) -> list[dict[str, object]]:
    return deepcopy(EXAMPLES[name])


class SemanticConstructionTests(unittest.TestCase):
    def test_all_five_exact_models_and_independent_receiver(self) -> None:
        # This independent checker does not import the generator. Inputs are
        # pinned to a separate checked-in source description in examples.json.
        from independent_certificate_checker import hash_bytes, parse_network
        for name, source in EXAMPLES.items():
            with self.subTest(example=name):
                cap = compile_semantics(source)
                result = verify_capsule(raw(cap),
                                        expected_source_sha256=hash_bytes(source))
                self.assertEqual(result["status"],
                                 "exact-all-real-semantic-equivalence-verified")
                self.assertEqual(result["source_semantic_sha256"],
                                 hash_bytes(source))
                self.assertEqual(result["semantic_regions"], len(source))
                self.assertEqual(result["hidden_neurons"], len(source) + 1)
                self.assertEqual(result["output_channels"], len(source[0]["affines"]))
                self.assertFalse(result["authority_granted"])
                network = parse_network(cap["generated_certificate"]["network"])
                self.assertEqual([name for name, _, _ in network], ["relu", "linear"])

    def test_exact_values_across_negative_positive_hinges(self) -> None:
        # Supplement the universal COE-002 check with an independent arithmetic
        # evaluation at breakpoints and interiors.
        from continuous_equivalence import evaluate, layer
        from independent_certificate_checker import parse_network
        for name, source in EXAMPLES.items():
            with self.subTest(example=name):
                cap = compile_semantics(source)
                parsed = parse_network(cap["generated_certificate"]["network"])
                layers = tuple(layer(w, b, act) for act, w, b in parsed)
                regions = parse_atlas(source)
                for q in range(-16, 25):
                    x = Fraction(q, 8)
                    expected = next(tuple(p.at(x) for p in r.output)
                                    for r in regions
                                    if (r.left is None or x >= r.left)
                                    and (r.right is None or x <= r.right))
                    self.assertEqual(evaluate(layers, x), expected)

    def test_same_semantics_different_network_structure(self) -> None:
        from continuous_equivalence import compare, layer
        cap = compile_semantics(fixture("identity"))
        from independent_certificate_checker import parse_network
        parsed = parse_network(cap["generated_certificate"]["network"])
        generated = tuple(layer(w, b, a) for a, w, b in parsed)
        direct = (layer([[1]], [0], "linear"),)
        equivalence = compare(direct, generated)
        self.assertEqual(equivalence["status"], "equivalent")
        self.assertNotEqual(len(direct), len(generated))

    def test_rehashed_parameter_tampering_is_rejected(self) -> None:
        from independent_certificate_checker import hash_bytes
        source = fixture("triangular_bump")
        cap = compile_semantics(source)
        network = cap["generated_certificate"]["network"]
        network["layers"][1]["weights"][0][0] = "47"
        cap["generated_certificate"]["network_sha256"] = hash_bytes(network)
        with self.assertRaises(CertificateError):
            verify_capsule(raw(cap))

    def test_forged_semantics_with_stale_certificate_is_rejected(self) -> None:
        from independent_certificate_checker import hash_bytes
        cap = compile_semantics(fixture("identity"))
        cap["source_semantic_atlas"][0]["affines"][0][1] = "1"
        cap["source_semantic_sha256"] = hash_bytes(cap["source_semantic_atlas"])
        with self.assertRaises(CertificateError):
            verify_capsule(raw(cap))

    def test_receiver_owned_semantic_pin_rejects_replacement(self) -> None:
        from independent_certificate_checker import hash_bytes
        cap = compile_semantics(fixture("constant"))
        with self.assertRaises(CertificateError):
            verify_capsule(raw(cap),
                           expected_source_sha256=hash_bytes(fixture("identity")))
        with self.assertRaises(CertificateError):
            verify_capsule(raw(cap), expected_network_sha256="0" * 64)

    def test_hidden_transition_must_be_disclosed(self) -> None:
        cap = compile_semantics(fixture("identity"))
        cert = cap["generated_certificate"]
        # The output is x across all inputs, but both hidden ReLUs switch at 0.
        self.assertEqual(len(cert["atomic_cells"]), 2)
        cert["atomic_cells"] = [cert["semantic_atlas"][0]]
        with self.assertRaises(CertificateError):
            verify_capsule(raw(cap))

    def test_rejects_noncanonical_and_duplicate_json(self) -> None:
        cap = compile_semantics(fixture("identity"))
        with self.assertRaises(CertificateError):
            verify_capsule(json.dumps(cap).encode())
        with self.assertRaises(CertificateError):
            verify_capsule(raw(cap).replace(b'"schema":', b'"schema":"forged","schema":', 1))
        with self.assertRaises(CertificateError):
            verify_capsule(raw(cap).replace(b'"source_semantic_sha256":',
                                            b'"extra":0,"source_semantic_sha256":', 1))

    def test_rejects_unprovable_source_shapes(self) -> None:
        for source in (
            [],
            [{"left": "-inf", "right": "0", "affines": [["0", "0"]]}],
            [{"left": "-inf", "right": "0", "affines": [["0", "0"]]},
             {"left": "1", "right": "+inf", "affines": [["0", "0"]]}],
            [{"left": "-inf", "right": "0", "affines": [["0", "0"]]},
             {"left": "0", "right": "+inf", "affines": [["1", "1"]]}],
            [{"left": "-inf", "right": "0", "affines": [["0", "0"]]},
             {"left": "0", "right": "+inf", "affines": [["0", "0"]]}],
            [{"left": "-inf", "right": "+inf", "affines": [["2/4", "0"]]}],
            [{"left": "-inf", "right": "+inf", "affines": [["0", "0"], ["1", "0"]]},
             {"left": "+inf", "right": "+inf", "affines": [["0", "0"]]}],
        ):
            with self.subTest(source=source):
                with self.assertRaises(AtlasRejected):
                    compile_semantics(source)

    def test_region_budget_exhaustion_is_not_equivalence(self) -> None:
        source = fixture("triangular_bump")
        with self.assertRaises(AtlasRejected):
            compile_semantics(source, max_regions=3)
        cap = compile_semantics(source)
        from independent_certificate_checker import hash_bytes
        with self.assertRaises(CertificateError):
            verify_capsule(raw(cap), max_cells=1)
        self.assertEqual(verify_capsule(
            raw(cap), expected_source_sha256=hash_bytes(source)
        )["status"], "exact-all-real-semantic-equivalence-verified")


if __name__ == "__main__":
    unittest.main()
