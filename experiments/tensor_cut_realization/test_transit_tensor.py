"""TCR-002 receiver-local source, cut, replay, identity and numerical checks."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from . import tensor_cut as tcr
from . import transit_tensor as tr


class ToyBlock:
    def __init__(self):
        rng = np.random.default_rng(73)
        self.up_weight = rng.uniform(-.5, .5, (5, 13)).astype(np.float32)
        self.up_bias = rng.uniform(-.5, .5, 13).astype(np.float32)
        self.down_weight = rng.uniform(-.5, .5, (13, 4)).astype(np.float32)
        self.down_bias = rng.uniform(-.5, .5, 4).astype(np.float32)
        self.activation = "gelu_tanh"

    def validate(self):
        return (5, 13, 4)

    def descriptor(self):
        record = {"schema": "ifs.feed-forward-block.v1", "dimensions": [5, 13, 4],
                  "activation": self.activation,
                  "tensors": {k: {"shape": list(getattr(self, k).shape), "dtype": "F32",
                                  "sha256": __import__("hashlib").sha256(getattr(self, k).tobytes()).hexdigest()}
                              for k in ("up_weight", "up_bias", "down_weight", "down_bias")}}
        return {**record, "digest": tcr._hash(record)}


class TransitTensorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.prepared = self.root / "prepared"
        self.manifest = tcr.prepare(ToyBlock(), {"kind": "local-synthetic"}, self.prepared, 4)
        self.host = tr.ResidentShard(self.prepared / "shard-0")
        with np.load(self.prepared / "reference.npz", allow_pickle=False) as src:
            self.inputs = src["inputs"]
        self.request = tr.request_for(self.manifest, 0, self.inputs, request_id="identity-A")

    def test_worker_computes_and_matches_reference_partition(self):
        response = self.host.handle(self.request)
        self.assertTrue(response["accepted"])
        tr.accept_response(self.request, response, self.manifest, self.root / "results")
        expected = tcr.worker(self.prepared / "shard-0", self.root / "independent")
        actual, _ = tcr._accept(self.manifest, self.root / "results", 0)
        truth, _ = tcr._accept(self.manifest, self.root / "independent", 0)
        np.testing.assert_array_equal(actual, truth)
        self.assertEqual(response["receipt"]["output_digest"], expected["output_digest"])

    def test_replayed_request_does_not_recompute(self):
        response = self.host.handle(self.request)
        replayed = self.host.handle(self.request)
        self.assertFalse(response["replayed"])
        self.assertTrue(replayed["replayed"])
        self.assertEqual(self.host.executions, 1)
        self.assertEqual(replayed["receiver_compute_ns_local"], 0)
        self.assertEqual(response["partial_hex"], replayed["partial_hex"])

    def test_receiver_rejects_manifest_source_and_partition_changes(self):
        for key, change in (("manifest_digest", "0" * 64), ("partition_id", 3),
                            ("input_digest", "1" * 64), ("input_hex", "zz")):
            with self.subTest(key=key):
                response = self.host.handle({**self.request, key: change})
                self.assertFalse(response["accepted"])
        self.assertEqual(self.host.executions, 0)

    def test_conflicting_request_identity_is_not_admitted(self):
        self.assertTrue(self.host.handle(self.request)["accepted"])
        bad = dict(self.request, input_hex="0" * len(self.request["input_hex"]))
        self.assertFalse(self.host.handle(bad)["accepted"])
        self.assertEqual(self.host.executions, 1)

    def test_local_tampered_shard_rejected_before_service(self):
        packet = self.prepared / "shard-0" / "shard.npz"
        with np.load(packet, allow_pickle=False) as data:
            arrays = {key: data[key] for key in data.files}
        arrays["down_weight"][0, 0] += 1
        np.savez(packet, **arrays)
        with self.assertRaisesRegex(tr.TransitTensorError, "receiver local tensor identity"):
            tr.ResidentShard(packet.parent)

    def test_rehashed_malicious_response_fails_numeric_oracle(self):
        response = self.host.handle(self.request)
        corrupt = copy.deepcopy(response)
        raw = np.frombuffer(bytes.fromhex(corrupt["partial_hex"]), dtype="<f8").copy()
        raw[0] += 0.2
        corrupt["partial_hex"] = raw.tobytes().hex()
        corrupt["receipt"]["output_digest"] = tcr._typed_digest(raw.reshape(2, 4))
        tr.accept_response(self.request, corrupt, self.manifest, self.root / "results")
        for index in range(1, 4):
            tcr.worker(self.prepared / f"shard-{index}", self.root / "results")
        import importlib.util
        if importlib.util.find_spec("mailcpu") is not None:
            with self.assertRaisesRegex(tcr.TensorCutError, "numerical mismatch"):
                tcr.aggregate(self.prepared, self.root / "results", self.root / "bad-report.json")

    def test_wrong_response_identity_or_payload_rejected(self):
        answer = self.host.handle(self.request)
        for field, value in (("worker_id", "other"), ("request_sha256", "0" * 64),
                             ("partial_hex", "00"), ("accepted", False)):
            with self.subTest(field=field):
                with self.assertRaises(tr.TransitTensorError):
                    tr.accept_response(self.request, {**answer, field: value},
                                       self.manifest, self.root / "results")


if __name__ == "__main__":
    unittest.main()
