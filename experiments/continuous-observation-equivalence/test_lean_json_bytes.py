"""COE-013 raw-byte bridge: no JSON parsing, no value interpretation."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from certificate_producer import canonical_bytes, produce
from coe_fixtures import fixtures
from emit_lean_certificates import TranslationRefused
from emit_lean_json_bytes import render, nat_bytes


class RawJSONBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, layers in fixtures().items():
            (self.root / f"{name}.json").write_bytes(
                canonical_bytes(produce(layers)) + b"\n")

    def test_all_five_actual_source_files_have_independent_kernel_obligations(self):
        code, receipt = render(self.root)
        self.assertEqual(receipt["count"], 5)
        self.assertIn("import GeneratedWireProofs", code)
        self.assertIn("import COE013Json", code)
        for name in fixtures():
            raw = (self.root / f"{name}.json").read_bytes()
            self.assertEqual(
                receipt["files"][name]["original_file_sha256"], sha256(raw).hexdigest())
            self.assertEqual(receipt["files"][name]["length_bytes"], len(raw))
            self.assertIn(f"def {name}_raw : COE013Json.Bytes", code)
            self.assertIn(
                f"(COE013Json.parseEnvelope {name}_raw).map COE013Json.Envelope.wire = some COE012.{name}_wire",
                code)
            self.assertIn(f"COE013Json.acceptBytes {name}_raw = true", code)
            self.assertIn(f"-- original-file-sha256: {sha256(raw).hexdigest()}", code)
        self.assertEqual(code, render(self.root)[0])

    def test_malformed_json_is_transported_without_interpretation(self):
        original = (self.root / "identity.json").read_bytes()
        variants = (
            original.replace(b'"atomic_cells":', b'"atomic_cells":null,"atomic_cells":', 1),
            original.replace(b'"network":', b'"net" : ', 1),
            original.replace(b'"schema":', b'"schema":"evil","schema":', 1),
            original[:-1],
            original + b"\n",
            original.replace(b'"+inf"', b'"-inf"'),
            original.replace(b'"1"', b'"1e4"', 1),
        )
        for invalid in variants:
            (self.root / "identity.json").write_bytes(invalid)
            code, receipt = render(self.root)
            self.assertIn(nat_bytes(invalid), code)
            self.assertEqual(
                receipt["files"]["identity"]["original_file_sha256"],
                sha256(invalid).hexdigest())
        # Each malformed object is transported, *not accepted*: only Lean
        # owns the acceptance claim and its exact byte-level decision.

    def test_missing_or_extra_files_rejected_by_filename_manifest(self):
        (self.root / "identity.json").unlink()
        with self.assertRaisesRegex(TranslationRefused, "manifest mismatch"):
            render(self.root)
        (self.root / "identity.json").write_bytes(b"{}")
        (self.root / "other.json").write_bytes(b"{}")
        with self.assertRaisesRegex(TranslationRefused, "manifest mismatch"):
            render(self.root)

    def test_arbitrary_uninterpreted_bytes_are_preserved(self):
        raw = b'{"data":"\\u0030"}\n'
        self.assertEqual(nat_bytes(raw), "[" + ", ".join(map(str, raw)) + "]")
        self.assertEqual(nat_bytes(b"\x00\xff"), "[0, 255]")
        with self.assertRaises(TranslationRefused):
            nat_bytes(b"")


if __name__ == "__main__":
    unittest.main()
