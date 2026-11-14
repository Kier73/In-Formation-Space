"""Ground task, addressed parameters, storage integrity and recovery controls."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mailcpu.structural_memory import StructuralMemoryRefused
from mailcpu.virtual_layer import VirtualLayerError
from .ground_model import GroundModelHost, affine_at, canonical, sha, task
from .run_benchmark import benchmark, cases, run_process_benchmark


class GroundModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_complete_ground_tasks_and_independent_large_coordinate(self):
        host = GroundModelHost(self.root)
        report = benchmark(host)
        self.assertEqual(report["successful_ground_tasks"], 16)
        self.assertEqual(report["baseline_candidate_attempts"], 28)
        self.assertEqual(report["ranked_candidate_attempts"], 16)
        self.assertEqual(report["native_handler_calls"], 16)
        self.assertEqual(report["persisted_dense_weight_payload_bytes"], 0)
        self.assertTrue(all(c["verification_class"] == "witness_grounded" for c in report["cases"]))

    def test_two_inference_paths_and_scalar_reference_agree(self):
        dense = GroundModelHost(self.root / "dense", engine="dense-reference")
        scalar = GroundModelHost(self.root / "scalar")
        features = [[0, 1], [1, 2], [2**24, 2**24]]
        a = dense.infer(features)["result"]
        with patch("experiments.ground_model_addressability.ground_model.evaluate", side_effect=AssertionError):
            b = scalar.infer(features)["result"]
        words = [affine_at(1664525, 1013904223, 2**32, 31, t) for t in (10**12, 10**12 + 1)]
        expected = [-(row[0] * (1024 + words[0] % 1024) * 1024 + row[1] * (1 + words[1] % 1024)) / 1048576
                    for row in features]
        self.assertEqual(a, b)
        self.assertEqual(b["scores"], expected)
        self.assertNotEqual(dense.spec.digest, scalar.spec.digest)

    def test_same_event_replays_without_another_handler_call(self):
        host = GroundModelHost(self.root)
        first = host.infer([[1, 2]])
        second = host.infer([[1, 2]])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["result"], second["result"])
        self.assertEqual(host.calls, 1)

    def test_withheld_escape_blocks_ground_admission(self):
        host = GroundModelHost(self.root)
        case = cases()[4]
        trace = case["trace"].copy()
        trace[12] = (trace[12] + 1) % 97
        with self.assertRaisesRegex(StructuralMemoryRefused, "witness mismatch"):
            task(host, trace, 97, "escaping", 1)
        self.assertEqual(host.calls, 1)
        self.assertIsNone(host.system.structural_memory.active_version("pnf004.task.escaping"))

    def test_fresh_receiver_compute_denial_after_restore(self):
        host = GroundModelHost(self.root)
        policy = host.save()
        restored = GroundModelHost(self.root, restored_policy=policy, grant_compute=False)
        self.assertEqual(restored.infer([[0, 1]])["status"], "denied")
        self.assertEqual(restored.calls, 0)

    def test_fresh_receiver_memory_read_denial_after_restore(self):
        host = GroundModelHost(self.root)
        restored = GroundModelHost(self.root, restored_policy=host.save(), grant_read=False)
        with self.assertRaisesRegex(VirtualLayerError, "read.*permission"):
            restored.infer([[0, 1]])
        self.assertEqual(restored.calls, 0)

    def test_wrong_context_or_certificate_refuses_parameter_binding(self):
        for field in ("context", "certificate_digest"):
            with self.subTest(field=field):
                host = GroundModelHost(self.root / field)
                wrong = {"context": {"role": "unrelated"}} if field == "context" else {"certificate_digest": "0" * 64}
                host.references = (replace(host.references[0], **wrong), host.references[1])
                with self.assertRaises(VirtualLayerError):
                    host.infer([[0, 1]])
                self.assertEqual(host.calls, 0)

    def test_rehashed_checkpoint_cannot_replace_external_pin(self):
        host = GroundModelHost(self.root)
        policy = host.save()
        doc = json.loads((self.root / "system.json").read_text())
        doc["state"]["pnf004_untrusted_extra_state"] = True
        doc["digest"] = sha(canonical(doc["state"]))
        # A replacement that recomputes its own checksum still lacks the external pin.
        (self.root / "system.json").write_bytes(canonical(doc))
        with self.assertRaisesRegex(ValueError, "checkpoint pin"):
            GroundModelHost(self.root, restored_policy=policy)

    def test_corrupt_m1_page_refused_before_inference(self):
        host = GroundModelHost(self.root)
        policy = host.save()
        with patch.object(type(host.store.page_backing), "get_page", return_value=b"x" * 4096):
            with self.assertRaises(ValueError):
                GroundModelHost(self.root, restored_policy=policy)

    def test_external_model_and_manifest_pins_are_required(self):
        host = GroundModelHost(self.root)
        policy = host.save()
        for key in ("model_digest", "manifest_digest"):
            bad = {**policy, key: "0" * 64}
            with self.assertRaisesRegex(ValueError, "pin mismatch"):
                GroundModelHost(self.root, restored_policy=bad)

    def test_rebound_unknown_decoder_is_not_executable_code(self):
        host = GroundModelHost(self.root)
        policy = host.save()
        wrong = copy.deepcopy(host.model)
        wrong["coefficient_decoder"] = "sender-defined-code"
        manifest = host.store.put_bytes(canonical(wrong), media_type="application/json")
        policy.update(manifest=manifest.to_dict(), manifest_digest=manifest.manifest_digest,
                      model_digest=manifest.content_digest)
        with self.assertRaisesRegex(ValueError, "model contract"):
            GroundModelHost(self.root, restored_policy=policy)

    def test_multiple_restores_keep_model_address_and_fresh_execution_identity(self):
        host = GroundModelHost(self.root)
        expected = host.infer([[3, 2]])["result"]
        for generation in (2, 3):
            host = GroundModelHost(self.root, restored_policy=host.save())
            self.assertEqual(host.generation, generation)
            self.assertEqual(host.infer([[3, 2]])["result"], expected)

    def test_input_encoding_has_strict_bounds(self):
        host = GroundModelHost(self.root)
        for features in ([], [[True, 1]], [[-1, 1]], [[1.0, 2]], [[2**24 + 1, 1]]):
            with self.assertRaises(ValueError):
                host.infer(features)
        self.assertEqual(host.calls, 0)

    def test_forced_process_stop_preserves_task_grounds_and_model(self):
        report = run_process_benchmark()
        self.assertEqual(report["status"], "passed")
        self.assertNotEqual(report["before"]["pid"], report["after"]["pid"])
        self.assertEqual(report["before"]["benchmark"]["inference_engine"], "dense-reference")
        self.assertEqual(report["after"]["benchmark"]["inference_engine"], "addressed-scalar")


if __name__ == "__main__":
    unittest.main()
