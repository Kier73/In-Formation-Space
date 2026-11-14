"""TCR-003 initial native E-CPU operator integration tests.

These are required in CI with the pinned E-CPU checkout. A local environment
without mailcpu skips them rather than pretending to verify Hypervisor behavior.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np

from . import tensor_cut as tcr
from . import transit_tensor as tr
from .test_transit_tensor import ToyBlock
from . import native_admission as native

HAS_ECPU = importlib.util.find_spec("mailcpu") is not None


@unittest.skipUnless(HAS_ECPU, "requires actual pinned E-CPU runtime")
class NativeAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.prepared = self.root / "prepared"
        self.manifest = tcr.prepare(ToyBlock(), {"kind": "procedural-tcr003"}, self.prepared, 4)
        with np.load(self.prepared / "reference.npz", allow_pickle=False) as source:
            self.x = source["inputs"]
        self.req = tr.request_for(self.manifest, 0, self.x, request_id="tcr003-native")

    def test_hypervisor_executes_once_and_replays_matching_operation(self):
        host = native.NativeCut(self.prepared / "shard-0")
        first = host.execute(self.req, sequence=1)
        self.assertTrue(first["accepted"], first)
        self.assertEqual(first["hypervisor_action"], "allow")
        self.assertFalse(first["native_replayed"])
        self.assertEqual(host.calls, 1)
        native.accept_partition(self.manifest, self.req, first, self.root / "native")
        second = host.execute(self.req, sequence=1)
        self.assertTrue(second["native_replayed"])
        self.assertEqual(host.calls, 1)
        tcr.worker(self.prepared / "shard-0", self.root / "baseline")
        a, _ = tcr._accept(self.manifest, self.root / "native", 0)
        b, _ = tcr._accept(self.manifest, self.root / "baseline", 0)
        np.testing.assert_allclose(a, b, rtol=1e-10, atol=1e-9)

    def test_receiver_capability_denial_does_not_call_tensor_handler(self):
        host = native.NativeCut(self.prepared / "shard-0", grant_compute=False)
        denied = host.execute(self.req, sequence=1)
        self.assertFalse(denied["accepted"])
        self.assertEqual(denied["hypervisor_action"], "deny")
        self.assertEqual(host.calls, 0)

    def test_bad_source_partition_and_input_fail_closed(self):
        host = native.NativeCut(self.prepared / "shard-0")
        for update in (
            {"manifest_digest": "0" * 64},
            {"partition_id": 1},
            {"input_digest": "f" * 64},
            {"input_hex": "00"},
        ):
            with self.subTest(update=update):
                with self.assertRaises(tr.TransitTensorError):
                    host.execute({**self.req, **update}, sequence=1)
        self.assertEqual(host.calls, 0)

    def test_wrong_native_contract_and_partial_payload_are_refused(self):
        host = native.NativeCut(self.prepared / "shard-0")
        first = host.execute(self.req, sequence=1)
        self.assertTrue(first["accepted"], first)
        wrong_contract = copy.deepcopy(first)
        wrong_contract["operator_contract_digest"] = "0" * 64
        with self.assertRaises(native.NativeAdmissionError):
            native.accept_partition(self.manifest, self.req, wrong_contract,
                                    self.root / "mismatched-contract")
        wrong_payload = copy.deepcopy(first)
        wrong_payload["partial_hex"] = "00"
        with self.assertRaises(tr.TransitTensorError):
            native.accept_partition(self.manifest, self.req, wrong_payload,
                                    self.root / "mismatched-result")


    def test_complete_four_cut_native_execution_and_dag_reference(self):
        from .run_native_four import execute_four
        outcome = execute_four(self.prepared, self.root / "four-native",
                               self.root / "four-dag-report.json")
        self.assertEqual(outcome["status"], "native-hypervisor-and-numeric-reference-passed")
        self.assertEqual(len(outcome["decisions"]), 4)
        self.assertTrue(all(x["native_replay_confirmed"] for x in outcome["decisions"]))
        self.assertEqual(outcome["separate_receiver_ground_count"], 4)
        self.assertEqual(outcome["numerical_verification"]["status"], "passed")
        self.assertFalse(outcome["network_transport_performed"])


if __name__ == "__main__":
    unittest.main()
