"""Native authority, conservation, replay and forged-contribution controls."""
import base64
import copy
import unittest
from unittest.mock import patch

import numpy as np

from experiments.tensor_cut_realization import tensor_cut as tcr
from experiments.tensor_cut_realization.native_admission import NativeCut
from .capsule import pack_pair
from .formation import FormationError, procedural_block, widen
from .native_execution import execute_capsule
from .receiver import Assembly, CHUNK
from .test_capsule import rewrite, rehash


def pair(activation="gelu_tanh", inputs=8):
    source = procedural_block(inputs, 16, 8, activation=activation)
    generated, certificate = widen(source, 24)
    return pack_pair(source, generated, certificate, {"kind": "procedural"}, [[.5] * inputs])


class NativeExecutionTests(unittest.TestCase):
    def test_both_activations_four_native_grounds_and_exact_replay(self):
        for activation in ("relu", "gelu_tanh"):
            with self.subTest(activation=activation):
                raw, policy = pair(activation)
                with patch("experiments.procedural_neural_formation.formation.widen", side_effect=AssertionError):
                    report = execute_capsule(raw, policy)
                self.assertEqual(report["status"], "executed")
                self.assertEqual(report["cut_model_digest"], policy["generated_digest"])
                self.assertNotEqual(report["cut_model_digest"], policy["source_digest"])
                self.assertEqual(report["native_handler_calls"], 4)
                self.assertEqual(len({d["receiver_node"] for d in report["decisions"]}), 4)
                self.assertEqual(report["native_runtime_count"], 4)
                self.assertTrue(all(d["native_replayed"] for d in report["decisions"]))
                self.assertTrue(report["dag_restoration_equal"])
                self.assertEqual(report["output_coordinates_checked"], 16)
                self.assertLess(report["max_abs_parent_scalar_error"], 1e-9)

    def test_denial_keeps_capsule_valid_but_never_calls_native_handler(self):
        report = execute_capsule(*pair(), grant_compute=False)
        self.assertEqual(report["status"], "denied")
        self.assertEqual(report["native_handler_calls"], 0)
        self.assertTrue(all(d["action"] == "deny" for d in report["decisions"]))
        self.assertNotIn("output_digest", report)

    def test_wrong_external_identity_never_creates_native_ground(self):
        raw, policy = pair()
        with patch("experiments.procedural_neural_formation.native_execution.NativeCut") as host:
            with self.assertRaises(FormationError):
                execute_capsule(raw, {**policy, "generated_digest": "0" * 64})
            host.assert_not_called()

    def test_rehashed_bad_widening_law_never_creates_native_ground(self):
        raw, policy = pair()
        wrong = rewrite(raw, lambda h: h["certificate"]["parent_index"].__setitem__(0, 1))
        with patch("experiments.procedural_neural_formation.native_execution.NativeCut") as host:
            with self.assertRaises(FormationError):
                execute_capsule(wrong, rehash(wrong, policy))
            host.assert_not_called()

    def test_rehashed_wrong_native_partial_fails_numerical_verification(self):
        class ForgedCut(NativeCut):
            def execute(self, request, **kwargs):
                answer = copy.deepcopy(super().execute(request, **kwargs))
                y = np.frombuffer(bytes.fromhex(answer["partial_hex"]), dtype="<f8").copy()
                y[0] += 10
                y = y.reshape(answer["receipt"]["output_shape"])
                answer["partial_hex"] = y.astype("<f8").tobytes().hex()
                answer["receipt"]["output_digest"] = tcr._typed_digest(y)
                return answer
        with patch("experiments.procedural_neural_formation.native_execution.NativeCut", ForgedCut):
            with self.assertRaisesRegex(tcr.TensorCutError, "numerical mismatch"):
                execute_capsule(*pair())

    def test_changed_replay_receipt_is_rejected(self):
        class ChangedReplay(NativeCut):
            def execute(self, request, **kwargs):
                answer = copy.deepcopy(super().execute(request, **kwargs))
                if answer["native_replayed"]:
                    answer["event_fingerprint"] = "0" * 64
                return answer
        with patch("experiments.procedural_neural_formation.native_execution.NativeCut", ChangedReplay):
            with self.assertRaisesRegex(FormationError, "replay"):
                execute_capsule(*pair())

    def test_sender_cannot_add_compute_authority_to_completion(self):
        raw, policy = pair()
        receiver = Assembly(policy, "test", native_execution=True, grant_compute=False)
        for i, start in enumerate(range(0, len(raw), CHUNK)):
            receiver.accept(i + 1, {"request_id": "test", "kind": "chunk", "index": i,
                                   "data": base64.b64encode(raw[start:start + CHUNK]).decode()})
        with self.assertRaisesRegex(FormationError, "completion frame"):
            receiver.accept(receiver.next_index + 1, {"request_id": "test", "kind": "verify",
                                                      "grant_compute": True})
        receiver.accept(receiver.next_index + 1, {"request_id": "test", "kind": "verify"})
        self.assertEqual(receiver.report["status"], "verified")
        self.assertEqual(receiver.report["native_execution"]["status"], "denied")

    def test_native_work_budget_and_policy_types(self):
        with self.assertRaisesRegex(FormationError, "budget"):
            execute_capsule(*pair(inputs=4000))
        with self.assertRaisesRegex(FormationError, "boolean"):
            execute_capsule(*pair(), grant_compute="false")


if __name__ == "__main__":
    unittest.main()
