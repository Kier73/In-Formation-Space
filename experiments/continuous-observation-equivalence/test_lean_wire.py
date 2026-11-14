"""COE-012: wire transport preserves exact strings; Lean owns decoding."""
from __future__ import annotations

from hashlib import sha256
import json
import tempfile
from pathlib import Path
import unittest

from certificate_producer import canonical_bytes, produce
from coe_fixtures import fixtures
from emit_lean_certificates import TranslationRefused
from emit_lean_wire import render, literal, wire_cell


class WireTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, layers in fixtures().items():
            (self.root / f"{name}.json").write_bytes(
                canonical_bytes(produce(layers)) + b"\n")

    def test_actual_five_source_wires_match_existing_typed_fixtures(self):
        code, receipt = render(self.root)
        self.assertEqual(receipt["model_count"], 5)
        self.assertIn("import GeneratedCertificateProofs", code)
        self.assertIn("import COE012Wire", code)
        for name in fixtures():
            self.assertIn(f"def {name}_wire :", code)
            self.assertIn(f"COE012Wire.decodeCert {name}_wire = some COE007.{name}", code)
            self.assertIn(f"COE012Wire.acceptWire {name}_wire = true", code)
            raw = (self.root / f"{name}.json").read_bytes()
            self.assertEqual(
                receipt["original_certificate_file_sha256"][name], sha256(raw).hexdigest()
            )
        self.assertEqual(render(self.root)[0], code)

    def test_fraction_tokens_are_transported_not_normalized(self):
        self.assertEqual(literal("-6/4"), '"-6/4"')
        self.assertEqual(literal("1e4"), '"1e4"')
        self.assertEqual(literal('1"); #eval 42'), json.dumps('1"); #eval 42'))
        self.assertIn('"2/4"', wire_cell({
            "left": "-inf", "right": "+inf",
            "affines": [["2/4", "0"]]
        }))
        obj = produce(fixtures()["identity"])
        obj["atomic_cells"][0]["affines"][0][0] = "2/4"
        (self.root / "identity.json").write_bytes(canonical_bytes(obj) + b"\n")
        code, _ = render(self.root)
        self.assertIn('"2/4"', code)
        self.assertIn("identity_wire_decoded", code)
        # The Python bridge must not reject a syntactically transported
        # but semantically noncanonical fraction: the Lean decoder does.

    def test_wrong_endpoint_sentinel_reaches_lean_as_plain_data(self):
        obj = produce(fixtures()["identity"])
        obj["atomic_cells"][0]["left"] = "+inf"
        (self.root / "identity.json").write_bytes(canonical_bytes(obj) + b"\n")
        code, _ = render(self.root)
        self.assertIn('left := "+inf"', code)

    def test_pinned_source_substitution_is_denied(self):
        obj = produce(fixtures()["identity"])
        obj["network"]["layers"][0]["bias"][0] = "5"
        (self.root / "identity.json").write_bytes(canonical_bytes(obj) + b"\n")
        with self.assertRaisesRegex(TranslationRefused, "not pinned"):
            render(self.root)

    def test_unapproved_extra_or_missing_source_is_denied(self):
        (self.root / "identity.json").unlink()
        with self.assertRaisesRegex(TranslationRefused, "manifest mismatch"):
            render(self.root)
        (self.root / "identity.json").write_bytes(b"{}")
        (self.root / "unapproved.json").write_bytes(b"{}")
        with self.assertRaisesRegex(TranslationRefused, "manifest mismatch"):
            render(self.root)

    def test_canonical_bytes_must_be_preserved(self):
        raw = (self.root / "identity.json").read_bytes()
        (self.root / "identity.json").write_bytes(raw[:-1])
        with self.assertRaisesRegex(TranslationRefused, "canonical JSON"):
            render(self.root)

    def test_duplicate_json_keys_are_not_accepted(self):
        raw = (self.root / "identity.json").read_bytes()
        (self.root / "identity.json").write_bytes(
            raw.replace(b'"schema":', b'"schema":"forged","schema":', 1)
        )
        with self.assertRaises(TranslationRefused):
            render(self.root)


if __name__ == "__main__":
    unittest.main()
