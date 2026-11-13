"""Cross-language tests for the independent HFR-002 graph verifier."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

try:
    from .neural_graph_ir import compile_gpt2_topology
    from .test_neural_graph_ir import make_topology_nsd
except ImportError:
    from neural_graph_ir import compile_gpt2_topology
    from test_neural_graph_ir import make_topology_nsd


ROOT = Path(__file__).parent
GO_SOURCE = ROOT / "independent_verifier" / "main.go"


class IndependentGoTopologyVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("go") is None:
            raise unittest.SkipTest("Go is required for the independent verifier tests")
        cls.temp = tempfile.TemporaryDirectory(prefix="hfr002-go-verifier-")
        cls.binary = Path(cls.temp.name) / "hfr002-independent-verifier"
        environment = os.environ.copy()
        environment["GO111MODULE"] = "off"
        built = subprocess.run(
            ["go", "build", "-o", str(cls.binary), str(GO_SOURCE)],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if built.returncode != 0:
            raise RuntimeError(
                "could not build independent Go verifier:\n"
                + built.stdout
                + built.stderr
            )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def verify(self, nsd, graph):
        with tempfile.TemporaryDirectory(prefix="hfr002-case-") as directory:
            root = Path(directory)
            nsd_path = root / "observation.nsd.json"
            graph_path = root / "topology.json"
            report_path = root / "verification.json"
            nsd_path.write_text(json.dumps(nsd), encoding="utf-8")
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            environment = os.environ.copy()
            environment["GO111MODULE"] = "off"
            completed = subprocess.run(
                [
                    str(self.binary),
                    "--nsd", str(nsd_path),
                    "--graph", str(graph_path),
                    "--report", str(report_path),
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            return completed, report

    def fixture(self):
        nsd = make_topology_nsd(layers=2)
        graph = compile_gpt2_topology(nsd)
        return nsd, graph

    def test_independent_implementation_reconstructs_two_block_graph(self):
        nsd, graph = self.fixture()
        completed, report = self.verify(nsd, graph)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["observed_tensor_count"], 30)
        self.assertEqual(report["operation_count"], 30)
        self.assertEqual(report["expected_edge_count"], 67)
        self.assertEqual(report["actual_edge_count"], 67)
        self.assertEqual(report["weight_payload_bytes_read"], 0)

    def test_rejects_removed_directed_edge(self):
        nsd, graph = self.fixture()
        damaged = copy.deepcopy(graph)
        damaged["edges"].pop(0)

        completed, report = self.verify(nsd, damaged)

        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["status"], "failed")
        failed_ids = {
            item["id"] for item in report["checks"] if item["status"] == "failed"
        }
        self.assertIn("independently-derived-directed-edges", failed_ids)
        self.assertIn("single-producer-complete-use", failed_ids)

    def test_rejects_graph_tensor_dtype_rebinding(self):
        nsd, graph = self.fixture()
        damaged = copy.deepcopy(graph)
        tensor = next(item for item in damaged["tensors"] if item["name"] == "wte.weight")
        tensor["dtype"] = "F16"

        completed, report = self.verify(nsd, damaged)

        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["status"], "failed")
        failed_ids = {
            item["id"] for item in report["checks"] if item["status"] == "failed"
        }
        self.assertIn("graph-tensor-catalog", failed_ids)
        self.assertIn("edge-endpoint-types-and-shapes", failed_ids)

    def test_rejects_observation_shape_tampering(self):
        nsd, graph = self.fixture()
        damaged_nsd = copy.deepcopy(nsd)
        damaged_nsd["observed"]["tensor_manifest"][0]["shape"][0] += 1

        completed, report = self.verify(damaged_nsd, graph)

        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["status"], "failed")
        failed_ids = {
            item["id"] for item in report["checks"] if item["status"] == "failed"
        }
        self.assertIn("nsd-gpt2-tensor-template", failed_ids)
        self.assertIn("nsd-tensor-shapes-and-shards", failed_ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
