"""Executable neural Ground: real local measurements, no checkpoint payload or kernel claims."""

from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from neural_graph_ir import compile_gpt2_topology
from test_neural_graph_ir import make_topology_nsd
from neural_execution_ground import (
    ExecutableNeuralGround,
    NeuralExecutionGroundError,
    verify_neural_observation_receipt,
)


class ExecutableNeuralGroundTests(unittest.TestCase):
    def graph(self, *, layers=2, tie=None):
        return compile_gpt2_topology(make_topology_nsd(layers=layers, tie=tie))

    def test_two_block_synthetic_graph_runs_and_replays_as_vgi_ground_observations(self):
        graph = self.graph(layers=2)
        ground = ExecutableNeuralGround(graph, seed=31, batch=1, sequence=3)
        manifest = ground.package.manifest()
        self.assertEqual(manifest["local_validation"]["status"], "passed")
        self.assertGreater(manifest["proof_ground"]["unverified_obligations"], 0)

        first_choices = ground.ready()
        first = ground.step()
        self.assertEqual(first["proposal"]["operation_id"], first_choices[0])
        self.assertEqual(first["proposal"]["ready_candidates"], list(first_choices))
        self.assertEqual(first["outcome"], "synthetic_type_shape_conforms")
        self.assertEqual(first["observation_path"]["status"], "query_determined")
        self.assertEqual(
            [item["stage"] for item in first["observation_path"]["events"]],
            ["planned", "dispatched", "admitted", "returned", "interpreted", "query_determined"],
        )
        self.assertEqual(
            first["proposal"]["obligation_id"],
            ground.package.obligation_keys[
                "operation:" + first["proposal"]["operation_id"]
            ],
        )
        self.assertEqual(ground.package.ground.kernel_status(
            first["proposal"]["obligation_id"]
        ), "unverified")

        receipt = ground.run()
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(receipt["operation_count"], 30)
        self.assertEqual(receipt["observation_count"], 30)
        self.assertEqual(len(receipt["records"]), 30)
        self.assertEqual(receipt["vgi_proof_ground"]["kernel_accepted_obligations"], 0)
        self.assertEqual(receipt["evidence_policy"]["tensor_payload_bytes_read"], 0)
        self.assertEqual(receipt["graph_output_refs"]["logits"]["shape"], [1, 3, 16])
        self.assertEqual(receipt["graph_output_refs"]["logits"]["dtype"], "F32")
        self.assertTrue(receipt["graph_output_refs"]["logits"]["finite"])
        self.assertEqual(receipt, verify_neural_observation_receipt(graph, receipt))

        observed_types = {
            graph_operation["operator"]
            for graph_operation in graph["operations"]
            if any(item["proposal"]["operation_id"] == graph_operation["id"] for item in receipt["records"])
        }
        self.assertEqual(observed_types, {
            "embedding.lookup", "tensor.add", "regularization.dropout",
            "normalization.layer_norm", "linear.affine",
            "attention.causal_scaled_dot_product", "activation.gelu_tanh",
        })

    def test_tied_and_untied_output_head_produce_distinct_synthetic_traces(self):
        tied = self.graph(layers=1)
        separate = self.graph(layers=1, tie=False)
        tied_receipt = ExecutableNeuralGround(tied, seed=3).run()
        untied_receipt = ExecutableNeuralGround(separate, seed=3).run()
        self.assertEqual(tied_receipt["status"], "complete")
        self.assertEqual(untied_receipt["status"], "complete")
        self.assertNotEqual(
            tied_receipt["graph_output_refs"]["logits"]["digest"],
            untied_receipt["graph_output_refs"]["logits"]["digest"],
        )
        verify_neural_observation_receipt(tied, tied_receipt)
        verify_neural_observation_receipt(separate, untied_receipt)

    def test_partial_execution_is_replayable_and_does_not_claim_logits(self):
        graph = self.graph(layers=1)
        session = ExecutableNeuralGround(graph, seed=5)
        partial = session.run(max_steps=4)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["observation_count"], 4)
        self.assertEqual(partial["graph_output_refs"], {})
        self.assertEqual(partial, verify_neural_observation_receipt(graph, partial))
        finished = session.run()
        self.assertEqual(finished["status"], "complete")
        self.assertEqual(finished["records"][:4], partial["records"])

    def test_mismatched_numeric_result_stops_and_leaves_proof_unverified(self):
        graph = self.graph(layers=1)
        session = ExecutableNeuralGround(graph)
        with patch("neural_execution_ground._execute", return_value={"embeddings": np.ones((1,), dtype=np.float32)}):
            record = session.step()
        self.assertEqual(record["outcome"], "synthetic_divergence")
        self.assertEqual(record["observation_path"]["status"], "unresolved")
        self.assertEqual(session.status, "divergence")
        self.assertEqual(len(session.package.ground.unresolved_obligations()), len(session.package.ground.obligations))
        with self.assertRaisesRegex(NeuralExecutionGroundError, "cannot observe"):
            session.step()
        with self.assertRaisesRegex(NeuralExecutionGroundError, "deterministic replay"):
            verify_neural_observation_receipt(graph, session.receipt())

    def test_replay_rejects_tampered_proposal_even_if_outer_digest_recomputed(self):
        graph = self.graph(layers=1)
        receipt = ExecutableNeuralGround(graph, seed=7).run(max_steps=5)
        altered = copy.deepcopy(receipt)
        altered["records"][0]["proposal"]["operation_id"] = "fabricated.operation"
        from neural_execution_ground import _digest
        core = {key: value for key, value in altered.items() if key != "receipt_digest"}
        altered["receipt_digest"] = _digest(core)
        with self.assertRaisesRegex(NeuralExecutionGroundError, "deterministic replay"):
            verify_neural_observation_receipt(graph, altered)

    def test_fail_closed_before_large_parameter_materialization(self):
        graph = self.graph(layers=2)
        with self.assertRaisesRegex(NeuralExecutionGroundError, "budget"):
            ExecutableNeuralGround(graph, max_elements=10)

    def test_rejects_large_runtime_activations_before_any_allocation(self):
        graph = self.graph(layers=1)
        with self.assertRaisesRegex(NeuralExecutionGroundError, "activations=.*budget"):
            ExecutableNeuralGround(graph, batch=50_000, sequence=2, max_elements=120_000)

    def test_attention_scratch_is_counted_in_preflight(self):
        graph = self.graph(layers=1)
        # The tiny graph's parameters fit this budget, but its attention
        # activation scratch must still be accounted for.
        full = ExecutableNeuralGround(graph, batch=1, sequence=2, max_elements=120_000)
        self.assertEqual(full.status, "ready")
        with self.assertRaisesRegex(NeuralExecutionGroundError, "attention_scratch="):
            ExecutableNeuralGround(graph, batch=2_000, sequence=8, max_elements=120_000)

    def test_rejects_tampered_graph_before_any_synthetic_execution(self):
        graph = self.graph(layers=1)
        damaged = copy.deepcopy(graph)
        damaged["edges"].pop()
        with self.assertRaises(ValueError):
            ExecutableNeuralGround(damaged)

    def test_attention_is_strictly_causal_on_synthetic_inputs(self):
        from neural_execution_ground import _execute
        operation = {
            "operator": "attention.causal_scaled_dot_product",
            "attributes": {"head_count": 1, "head_width": 1},
            "outputs": [{"name": "context"}],
        }
        # Query and key are zero -> equal attention scores at each unmasked
        # position. Each token should see only current-and-previous values.
        raw = np.array([
            [0., 0., 2.],
            [0., 0., 4.],
            [0., 0., 9.],
        ], dtype=np.float32).reshape((1, 3, 3))
        mask = np.tril(np.ones((1, 1, 3, 3), dtype=np.float32))
        got = _execute(operation, {"fused_query_key_value": raw, "causal_mask": mask})["context"]
        np.testing.assert_allclose(got[0, :, 0], [2., 3., 5.], rtol=1e-6)

    def test_graph_and_receipt_never_contain_numerical_weights(self):
        graph = self.graph(layers=1)
        receipt = ExecutableNeuralGround(graph).run()
        serialized = json.dumps(receipt)
        self.assertNotIn("raw_weights", serialized)
        self.assertNotIn("tensor_payload", serialized.replace("tensor_payload_bytes_read", ""))
        self.assertEqual(receipt["evidence_policy"]["parameter_origin"], "synthetic-prng-not-source-checkpoint")


if __name__ == "__main__":
    unittest.main(verbosity=2)
