"""Positive, adversarial and three-repository integration checks for PNF-001."""
import copy
from dataclasses import replace
import hashlib
import unittest
from unittest.mock import patch

import numpy as np

from .formation import Block, FormationError, evaluate, procedural_block, widen
from .verification import verify_conservation, scalar_oracle
from .run import run_case


class FormationTests(unittest.TestCase):
    def setUp(self):
        self.source = procedural_block(4, 8, 3)
        self.child, self.certificate = widen(self.source, 12)

    def rebind(self, child):
        return {**self.certificate, "generated_digest": child.descriptor()["digest"]}

    def test_both_activations_and_partial_or_full_widening(self):
        probes = np.array([[0, 0, 0, 0], [1, -2, 3, -4], [-5, 2, 1, 0.5]])
        for activation in ("relu", "gelu_tanh"):
            source = replace(self.source, activation=activation)
            for width in (9, 12, 16):
                with self.subTest(activation=activation, width=width):
                    child, cert = widen(source, width)
                    self.assertEqual(verify_conservation(source, child, cert)["status"], "passed")
                    np.testing.assert_allclose(evaluate(source, probes), evaluate(child, probes), rtol=1e-12, atol=1e-12)
                    np.testing.assert_allclose(evaluate(child, probes), scalar_oracle(child, probes, [0, 1, 2]), rtol=1e-12, atol=1e-12)

    def test_repeated_widening_and_source_immutability(self):
        original = self.source.descriptor()
        child2, cert2 = widen(self.child, 24)
        self.assertEqual(verify_conservation(self.child, child2, cert2)["status"], "passed")
        self.assertEqual(original, self.source.descriptor())
        self.child.up_weight[0, 0] += 1
        self.assertEqual(original, self.source.descriptor())

    def test_wrong_output_coefficients_rejected_even_with_new_digest(self):
        weight = self.child.down_weight.copy()
        weight[0, 0] += 0.25
        changed = replace(self.child, down_weight=weight)
        with self.assertRaisesRegex(FormationError, "conservation"):
            verify_conservation(self.source, changed, self.rebind(changed))

    def test_incoming_weight_and_bias_rejected(self):
        for key in ("up_weight", "up_bias"):
            array = getattr(self.child, key).copy()
            array.flat[0] += 0.25
            changed = replace(self.child, **{key: array})
            with self.assertRaisesRegex(FormationError, "incoming"):
                verify_conservation(self.source, changed, self.rebind(changed))

    def test_output_bias_and_activation_rejected(self):
        changed = replace(self.child, down_bias=self.child.down_bias + 1)
        with self.assertRaisesRegex(FormationError, "bias"):
            verify_conservation(self.source, changed, self.rebind(changed))
        changed = replace(self.child, activation="relu")
        with self.assertRaisesRegex(FormationError, "activation"):
            verify_conservation(self.source, changed, self.rebind(changed))

    def test_invalid_parent_maps_rejected(self):
        for parents in ([0] * 12, [True] + self.certificate["parent_index"][1:],
                        [-1] + self.certificate["parent_index"][1:], list(range(13))):
            with self.assertRaises(FormationError):
                verify_conservation(self.source, self.child, {**self.certificate, "parent_index": parents})

    def test_identity_and_schema_tampering_rejected(self):
        for field in ("schema", "rule", "source_digest", "generated_digest"):
            with self.assertRaises(FormationError):
                verify_conservation(self.source, self.child, {**self.certificate, field: "changed"})

    def test_subnormal_information_loss_is_refused(self):
        source = procedural_block(1, 1, 1)
        source.down_weight[0, 0] = np.nextafter(np.float32(0), np.float32(1))
        with self.assertRaisesRegex(FormationError, "conservation"):
            widen(source, 2)

    def test_small_unmatched_contribution_cannot_hide_in_rounded_sum(self):
        source = procedural_block(1, 1, 1)
        source.down_weight[0, 0] = np.float32(1e30)
        child, cert = widen(source, 2)
        child.down_weight[:, 0] = [np.float32(1e30), np.float32(1e-30)]
        cert["generated_digest"] = child.descriptor()["digest"]
        with self.assertRaisesRegex(FormationError, "conservation"):
            verify_conservation(source, child, cert)

    def test_budget_refused_before_rng_or_widen_allocation(self):
        with patch("numpy.random.Generator", side_effect=AssertionError("must not allocate")):
            with self.assertRaisesRegex(FormationError, "budget"):
                procedural_block(1000, 1000, 1000, max_elements=10)
        with self.assertRaisesRegex(FormationError, "budget"):
            widen(self.source, 16, max_elements=10)

    def test_bad_dimensions_and_nonfinite_parameters(self):
        for width in (True, 0, 8, 17, 12.0):
            with self.assertRaises(FormationError):
                widen(self.source, width)
        changed = replace(self.source, down_bias=np.full(3, np.nan, dtype=np.float32))
        with self.assertRaises(FormationError):
            widen(changed, 12)

    def test_input_and_oracle_admission(self):
        for probes in (np.ones((2, 5)), np.full((2, 4), np.nan)):
            with self.assertRaises(FormationError):
                evaluate(self.source, probes)
        for selected in ([], [0, 0], [True], [-1], [3]):
            with self.assertRaises(FormationError):
                scalar_oracle(self.source, np.ones((2, 4)), selected)

    def test_real_ecpu_dag_executes_and_restores(self):
        result = run_case(self.source, 12, {"kind": "procedural-test"})
        self.assertTrue(result["restoration_equal"])
        order = result["execution_order"]
        self.assertLess(order.index("construct"), order.index("generated_forward"))
        self.assertEqual(order[-1], "verify")
        self.assertTrue(result["verification"]["rehashed_coefficient_tamper_rejected"])


class SourceTests(unittest.TestCase):
    def setUp(self):
        from experiments.external_neural_structure_reading.test_neural_graph_ir import make_topology_nsd
        from experiments.external_neural_structure_reading.neural_graph_ir import compile_gpt2_topology
        from .source import tensor_names
        self.graph = compile_gpt2_topology(make_topology_nsd())
        self.names = tensor_names()
        block = procedural_block(4, 16, 4)
        self.payloads, self.evidence = {}, []
        for name, key in zip(self.names, ("up_weight", "up_bias", "down_weight", "down_bias")):
            array = getattr(block, key)
            raw = array.astype("<f4").tobytes()
            self.payloads[name] = raw
            self.evidence.append({"name": name, "dtype": "F32", "shape": list(array.shape),
                "size_bytes": len(raw), "shard": "model.safetensors", "shard_header_sha256": "a" * 64,
                "payload_sha256": hashlib.sha256(raw).hexdigest(),
                "payload_sha256_scope": "complete-selected-tensor-payload"})

    def test_read_binding_and_both_repository_graph_adapters(self):
        from .source import observed_block
        from mailcpu.neural_graph_bridge import compile_neural_graph_dag
        from vgi.neural_topology import build_neural_topology_proof_ground
        block = observed_block(self.graph, self.payloads, self.evidence)
        self.assertEqual(block.validate(), (4, 16, 4))
        projection = compile_neural_graph_dag(self.graph)
        proof = build_neural_topology_proof_ground(self.graph)
        self.assertEqual(projection.graph_digest, proof.graph_digest)
        self.assertEqual(len(proof.ground.unresolved_obligations()), len(proof.ground.obligations))

    def test_payload_or_header_tamper_rejected(self):
        from .source import observed_block
        payloads = {**self.payloads, self.names[0]: b"x" * len(self.payloads[self.names[0]])}
        with self.assertRaisesRegex(FormationError, "evidence"):
            observed_block(self.graph, payloads, self.evidence)
        evidence = copy.deepcopy(self.evidence)
        evidence[0]["shard_header_sha256"] = "b" * 64
        with self.assertRaisesRegex(FormationError, "evidence"):
            observed_block(self.graph, self.payloads, evidence)

    def test_extra_payload_or_duplicate_evidence_rejected(self):
        from .source import observed_block
        with self.assertRaises(FormationError):
            observed_block(self.graph, {**self.payloads, "extra": b""}, self.evidence)
        with self.assertRaises(FormationError):
            observed_block(self.graph, self.payloads, [self.evidence[0]] * 4)

    def test_semantic_or_tensor_port_change_rejected(self):
        from .source import observed_block
        graph = copy.deepcopy(self.graph)
        for op in graph["operations"]:
            if op["operator"] == "activation.gelu_tanh":
                op["operator"] = "activation.relu"
        with self.assertRaisesRegex(FormationError, "chain"):
            observed_block(graph, self.payloads, self.evidence)
        graph = copy.deepcopy(self.graph)
        for edge in graph["edges"]:
            if edge["source"] == {"kind": "tensor", "name": self.names[0]}:
                edge["target"]["port"] = "bias"
        with self.assertRaisesRegex(FormationError, "port"):
            observed_block(graph, self.payloads, self.evidence)


if __name__ == "__main__":
    unittest.main()
