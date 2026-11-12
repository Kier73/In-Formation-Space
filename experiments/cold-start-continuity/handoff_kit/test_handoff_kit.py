#!/usr/bin/env python3
"""Tests for the cold-start handoff run kit."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from handoff_kit import (
    MANIFEST_FORMAT,
    audit_run,
    build_manifest,
    main,
    sha256_lf,
    write_manifest,
)


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


class HandoffKitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.packet = self.root / "packet.md"
        self.template = self.root / "report-template.md"
        _write(
            self.packet,
            "# Handoff packet\n\n"
            "**Packet ID:** `relay-case-01`\n\n"
            "| Local tick | Record |\n| ---: | --- |\n| 100 | Command received. |\n",
        )
        _write(
            self.template,
            "# Cold-start handoff report\n\n"
            "## 1. Recovered observations\n\n"
            "## 2. Inferences and limits\n",
        )

        self.run_dir = self.root / "runs" / "run-01"
        self.run_dir.mkdir(parents=True)
        self.prompt = self.run_dir / "prompt.md"
        self.response = self.run_dir / "response.md"
        self.conditions = self.run_dir / "conditions.md"
        self.evaluation = self.run_dir / "evaluation.md"

        _write(
            self.prompt,
            "Use only the material below.\n\n"
            + self.packet.read_text(encoding="utf-8")
            + "\n"
            + self.template.read_text(encoding="utf-8"),
        )
        _write(self.response, "# Report\n\nA report.\n")
        _write(self.conditions, "# Conditions\n\nMaterial-limited.\n")
        _write(self.evaluation, "# Evaluation\n\nSeparate review.\n")

        self.manifest = build_manifest(
            self.run_dir,
            self.packet,
            self.template,
            level="L1",
            recipient_context="test recipient",
            notes="test run",
        )
        write_manifest(self.run_dir, self.manifest)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_valid_l1_manifest_passes(self) -> None:
        result = audit_run(self.run_dir)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.errors, [])
        self.assertTrue(any("L1 scope" in warning for warning in result.warnings))
        self.assertEqual(result.checks[0].name, "manifest")

    def test_manifest_binds_prompt_and_response_hashes(self) -> None:
        with (self.run_dir / "manifest.json").open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["format"], MANIFEST_FORMAT)
        self.assertEqual(manifest["isolation_level"], "L1")
        self.assertEqual(manifest["artifacts"]["prompt"]["sha256_lf"], sha256_lf(self.prompt))
        self.assertEqual(manifest["artifacts"]["response"]["sha256_lf"], sha256_lf(self.response))

    def test_l1_prompt_must_contain_packet(self) -> None:
        _write(self.prompt, "Use only this.\n\n" + self.template.read_text(encoding="utf-8"))
        write_manifest(
            self.run_dir,
            build_manifest(self.run_dir, self.packet, self.template, level="L1"),
        )
        result = audit_run(self.run_dir)
        self.assertFalse(result.ok)
        self.assertTrue(any("packet text" in error for error in result.errors))

    def test_packet_hash_mismatch_fails(self) -> None:
        _write(self.packet, self.packet.read_text(encoding="utf-8") + "\nTampered.\n")
        result = audit_run(self.run_dir)
        self.assertFalse(result.ok)
        self.assertTrue(any("hash mismatch" in error for error in result.errors))

    def test_l2_requires_workspace_isolation(self) -> None:
        write_manifest(
            self.run_dir,
            build_manifest(
                self.run_dir,
                self.packet,
                self.template,
                level="L2",
                tool_instrumentation=True,
                workspace_isolation=False,
            ),
        )
        result = audit_run(self.run_dir)
        self.assertFalse(result.ok)
        self.assertTrue(any("workspace_isolation" in error for error in result.errors))

    def test_l2_with_declared_controls_passes(self) -> None:
        write_manifest(
            self.run_dir,
            build_manifest(
                self.run_dir,
                self.packet,
                self.template,
                level="L2",
                tool_instrumentation=True,
                workspace_isolation=True,
            ),
        )
        result = audit_run(self.run_dir)
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(any("not independently verified" in warning for warning in result.warnings))

    def test_reviewer_guide_in_run_directory_fails(self) -> None:
        _write(self.run_dir / "reviewer-guide.md", "# Reviewer guide\n")
        result = audit_run(self.run_dir)
        self.assertFalse(result.ok)
        self.assertTrue(any("reviewer guide" in error.lower() for error in result.errors))

    def test_missing_response_fails(self) -> None:
        self.response.unlink()
        write_manifest(
            self.run_dir,
            build_manifest(self.run_dir, self.packet, self.template, level="L1"),
        )
        result = audit_run(self.run_dir)
        self.assertFalse(result.ok)
        self.assertTrue(any("response" in error for error in result.errors))

    def test_manifest_records_actual_packet_filename(self) -> None:
        alt_packet = self.root / "packet-rev2-field-note.md"
        _write(alt_packet, self.packet.read_text(encoding="utf-8"))
        manifest = build_manifest(self.run_dir, alt_packet, self.template, level="L1")
        self.assertEqual(
            manifest["supplied_material"],
            ["packet-rev2-field-note.md", "report-template.md"],
        )

    def test_review_artifact_hash_mismatch_is_warning(self) -> None:
        _write(self.evaluation, "# Evaluation\n\nUpdated annotation.\n")
        result = audit_run(self.run_dir)
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(any("hash mismatch" in warning for warning in result.warnings))

    def test_cli_audit_exit_codes(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["audit", "--run-dir", str(self.run_dir)]), 0)

        _write(self.packet, self.packet.read_text(encoding="utf-8") + "\nTampered.\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["audit", "--run-dir", str(self.run_dir)]), 1)

    def test_manifest_cli_refuses_inconsistent_l2(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "manifest",
                        "--run-dir",
                        str(self.run_dir),
                        "--packet",
                        str(self.packet),
                        "--template",
                        str(self.template),
                        "--level",
                        "L2",
                    ]
                )
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
