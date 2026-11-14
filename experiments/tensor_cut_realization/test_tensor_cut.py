"""Offline numerical, adversarial, and E-CPU dependency tests for TCR-001."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from . import tensor_cut as tcr


class FixtureBlock:
    def __init__(self, inputs=5, hidden=17, outputs=4, activation="gelu_tanh"):
        rng = np.random.default_rng(32)
        self.up_weight = rng.integers(-8, 9, (inputs, hidden)).astype(np.float32) / 16
        self.up_bias = rng.integers(-8, 9, hidden).astype(np.float32) / 16
        self.down_weight = rng.integers(-8, 9, (hidden, outputs)).astype(np.float32) / 16
        self.down_bias = rng.integers(-8, 9, outputs).astype(np.float32) / 16
        self.activation = activation

    def validate(self):
        return (self.up_weight.shape[0], self.up_weight.shape[1], self.down_weight.shape[1])

    def descriptor(self):
        tensors = {}
        for name in ("up_weight", "up_bias", "down_weight", "down_bias"):
            a = getattr(self, name)
            tensors[name] = {"shape": list(a.shape), "dtype": "F32",
                             "sha256": __import__("hashlib").sha256(a.tobytes()).hexdigest()}
        record = {"schema": "ifs.feed-forward-block.v1", "dimensions": list(self.validate()),
                  "activation": self.activation, "tensors": tensors}
        return {**record, "digest": tcr._hash(record)}


class TensorCutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prepared = self.root / "prepared"
        self.results = self.root / "results"
        self.block = FixtureBlock()

    def execute(self, block=None, partitions=4):
        block = block or self.block
        manifest = tcr.prepare(block, {"kind": "fixture", "seed": 32}, self.prepared, partitions)
        for index in range(partitions):
            receipt = tcr.worker(self.prepared / f"shard-{index}", self.results)
            self.assertEqual(receipt["partition_id"], index)
        with np.load(self.prepared / "reference.npz", allow_pickle=False) as source:
            expected = source["reference_y"]
            bias = source["down_bias"]
        combined = np.zeros_like(expected)
        for index in range(partitions):
            partial, receipt = tcr._accept(manifest, self.results, index)
            combined += partial
        combined += bias
        tcr._compare(combined, expected, "unit test dense equivalence")
        return manifest

    def test_gelu_uneven_partition_and_complete_coverage(self):
        manifest = self.execute()
        self.assertEqual([(p["start"], p["stop"]) for p in manifest["partitions"]],
                         [(0, 5), (5, 9), (9, 13), (13, 17)])
        self.assertEqual(manifest["hidden_dim"], 17)

    def test_relu_and_single_partition(self):
        self.execute(FixtureBlock(3, 5, 2, activation="relu"), 1)

    def test_tampered_shard_rejected_before_operation(self):
        manifest = tcr.prepare(self.block, {"kind": "fixture"}, self.prepared)
        packet = self.prepared / "shard-0"
        with np.load(packet / "shard.npz", allow_pickle=False) as src:
            arrays = {name: src[name] for name in src.files}
        arrays["up_weight"][0, 0] += 0.5
        np.savez(packet / "shard.npz", **arrays)
        with self.assertRaisesRegex(tcr.TensorCutError, "parameters"):
            tcr.worker(packet, self.results)
        self.assertEqual(len(manifest["partitions"]), 4)

    def test_wrong_assignment_or_manifest_rejected(self):
        tcr.prepare(self.block, {"kind": "fixture"}, self.prepared)
        packet = self.prepared / "shard-0"
        assignment = tcr._read_json(packet / "assignment.json")
        tcr._write_json(packet / "assignment.json", {**assignment, "partition_id": 1})
        with self.assertRaisesRegex(tcr.TensorCutError, "parameters"):
            tcr.worker(packet, self.results)
        tcr._write_json(packet / "assignment.json", assignment)
        manifest = tcr._read_json(packet / "manifest.json")
        manifest["output_dim"] += 1
        tcr._write_json(packet / "manifest.json", manifest)
        with self.assertRaisesRegex(tcr.TensorCutError, "manifest digest"):
            tcr.worker(packet, self.results)

    def test_missing_partial_or_changed_digest_rejected(self):
        manifest = self.execute()
        (self.results / "partial-0.npy").unlink()
        with self.assertRaises(FileNotFoundError):
            tcr._accept(manifest, self.results, 0)
        manifest = self.execute()
        file = self.results / "partial-0.npy"
        value = np.load(file, allow_pickle=False)
        value[0, 0] += 0.125
        np.save(file, value, allow_pickle=False)
        with self.assertRaisesRegex(tcr.TensorCutError, "digest mismatch"):
            tcr._accept(manifest, self.results, 0)

    def test_rehashed_malicious_partial_is_not_verified_equivalence(self):
        manifest = self.execute()
        file = self.results / "partial-1.npy"
        receipt_file = self.results / "receipt-1.json"
        value = np.load(file, allow_pickle=False)
        value[0, 0] += 0.5
        np.save(file, value, allow_pickle=False)
        receipt = tcr._read_json(receipt_file)
        receipt["output_digest"] = tcr._typed_digest(value)
        tcr._write_json(receipt_file, receipt)
        # Payload integrity passes, but the aggregate's independent reference must reject it.
        tcr._accept(manifest, self.results, 1)
        if importlib.util.find_spec("mailcpu") is not None:
            with self.assertRaisesRegex(tcr.TensorCutError, "numerical mismatch"):
                tcr.aggregate(self.prepared, self.results, self.root / "report.json")

    @unittest.skipUnless(importlib.util.find_spec("mailcpu") is not None, "needs pinned E-CPU")
    def test_real_ecpu_dag_commit_and_replay(self):
        self.execute()
        report = tcr.aggregate(self.prepared, self.results, self.root / "report.json")
        self.assertEqual(report["verification"]["status"], "passed")
        self.assertTrue(report["dag_restoration_equal"])
        self.assertEqual(report["operation_order"][-2:], ["reduce", "verify"])
        self.assertEqual(len([n for n in report["operation_order"] if n.startswith("part.")]), 4)
        persisted = json.loads((self.root / "report.json").read_text())
        self.assertEqual(persisted["result_digest"], report["result_digest"])
        self.assertNotIn("raw_weights", persisted)


if __name__ == "__main__":
    unittest.main()
