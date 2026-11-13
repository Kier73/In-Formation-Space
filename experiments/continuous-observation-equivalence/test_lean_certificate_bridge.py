"""COE-007 adapter tests: transport-only, deterministic, full manifest, safe bytes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from certificate_producer import canonical_bytes, produce
from coe_fixtures import fixtures
from emit_lean_certificates import (
    TranslationRefused, lean_rational, ordered_bytes,
    render, strict_json, FILENAMES, EXPECTED_NETWORK_DIGESTS
)
from make_lean_negative_certificates import make_negatives


class LeanCertificateBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "certs"
        self.source.mkdir()
        for name, layers in fixtures().items():
            cert = produce(layers)
            (self.source / (name + ".json")).write_bytes(canonical_bytes(cert) + b"\n")

    def test_five_pinned_sources_emit_five_closed_lean_obligations(self):
        code, metadata = render(self.source)
        self.assertEqual(metadata["model_count"], 5)
        self.assertEqual(metadata["cell_count"], 12)
        self.assertEqual(len(metadata["models"]), 5)
        for name in sorted(EXPECTED_NETWORK_DIGESTS):
            self.assertIn(f"def {name} : COEWireCheck.Cert", code)
            self.assertIn(f"theorem {name}_arith_verified : COEWireCheck.verify {name} = true := by decide", code)
            raw = (self.source / f"{name}.json").read_bytes()
            self.assertEqual(metadata["models"][name]["certificate_file_sha256"],
                             hashlib.sha256(raw).hexdigest())
            self.assertIn(f"-- source-file-sha256: {hashlib.sha256(raw).hexdigest()}", code)
        self.assertEqual(code, render(self.source)[0])

    def test_rational_tokens_preserve_exact_negative_and_fraction_values(self):
        self.assertEqual(lean_rational("-3/2"), "((-3 : Rat) / (2 : Rat))")
        self.assertEqual(lean_rational("0"), "(0 : Rat)")
        self.assertEqual(lean_rational("-1"), "(-1 : Rat)")
        for bad in ("1/1", "-0", "2/4", "01", "1e3", "1.5", "0/0", "1/0",
                    '1"); #eval 42'):
            with self.assertRaises((TranslationRefused, ZeroDivisionError)):
                lean_rational(bad)

    def test_source_parameter_substitution_is_denied_by_independent_manifest(self):
        raw = strict_json((self.source / "identity.json").read_bytes())
        original = deepcopy(raw)
        raw["network"]["layers"][0]["bias"][0] = "1"
        raw["network_sha256"] = hashlib.sha256(ordered_bytes(raw["network"])).hexdigest()
        (self.source / "identity.json").write_bytes(ordered_bytes(raw) + b"\n")
        with self.assertRaisesRegex(TranslationRefused, "not pinned"):
            render(self.source)
        self.assertEqual(original["network"]["layers"][0]["bias"][0], "0")

    def test_missing_or_extra_fixtures_fail_closed(self):
        (self.source / "identity.json").unlink()
        with self.assertRaisesRegex(TranslationRefused, "manifest mismatch"):
            render(self.source)
        (self.source / "identity.json").write_text("{}", encoding="utf-8")
        (self.source / "unapproved.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(TranslationRefused, "manifest mismatch"):
            render(self.source)

    def test_duplicate_keys_noncanonical_bytes_and_wrong_schema_fail(self):
        original = (self.source / "identity.json").read_bytes()
        for invalid in (
            original[:-1],
            original + b"\n",
            b" " + original,
            original.replace(b'"schema":', b'"schema":"spoof","schema":', 1)
        ):
            with self.assertRaises(TranslationRefused):
                strict_json(invalid)
        bad = strict_json(original)
        bad["schema"] = "other"
        with self.assertRaisesRegex(TranslationRefused, "schema"):
            strict_json(ordered_bytes(bad) + b"\n")

    def test_adversarial_certificates_reach_lean_as_falsifiable_claims(self):
        negatives = self.root / "negatives"
        make_negatives(self.source, negatives)
        positive_code, _ = render(self.source)
        for name in ("hidden-root", "wrong-slope", "cover-gap"):
            code, report = render(negatives / name)
            self.assertEqual(report["model_count"], 5)
            self.assertNotEqual(code, positive_code)
            self.assertIn(" := by decide", code)
            # The adapter does not trust or silently discard the bad claim.
            self.assertEqual(set((negatives / name).iterdir()),
                             {negatives / name / filename for filename in FILENAMES})


if __name__ == "__main__":
    unittest.main()
