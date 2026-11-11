"""Tests for Trial 07: Epistemic frontier mapping.

Covers:
  - Empty envelope collection returns empty frontier
  - Disconnected forest: all nodes are on the frontier
  - Single causal edge removes predecessor from frontier
  - Forward and backward relation kinds both induce edges correctly
  - Non-causal relations do not shrink the frontier
  - External target identification
  - Cycle detection removes no node from frontier (cycle reported separately)
  - Verification ratio calculation
  - Digest mismatch is reported as unverified (False), not not_checkable (None)
  - Reference-only payloads are not_checkable
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import unittest
from pathlib import Path

# Adjust path so we can import from the trial directory directly
sys.path.insert(0, str(Path(__file__).parent))
from epistemic_frontier import (
    FrontierReport,
    NodeSummary,
    analyze_frontier,
    _verify_digest,
    _detect_cycle,
    to_encounter_payload,
)


# ---------------------------------------------------------------------------
# Minimal envelope factory
# ---------------------------------------------------------------------------

def _env(
    eid: str,
    *,
    relations: list | None = None,
    value: object = None,
    reference: str | None = None,
    algo: str | None = None,
    canon: str | None = None,
    digest: str | None = None,
    observed_at: str | None = "2026-01-01T00:00:00+00:00",
) -> dict:
    doc: dict = {
        "format": "in-formation.encounter/0.1",
        "id": eid,
        "source": {"label": "test"},
        "observed_at": observed_at,
    }
    if relations is not None:
        doc["relations"] = relations
    payload: dict = {}
    if value is not None:
        payload["value"] = value
    if reference is not None:
        payload["reference"] = reference
    if payload:
        doc["payload"] = payload
    if algo and canon and digest:
        doc["integrity"] = {"algorithm": algo, "canonicalization": canon, "digest": digest}
    elif algo and canon:
        doc["integrity"] = {"algorithm": algo, "canonicalization": canon}
    return doc


def _inline_digest(value: object) -> str:
    s = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(s).hexdigest()


# ---------------------------------------------------------------------------
# Unit test: _verify_digest
# ---------------------------------------------------------------------------

class VerifyDigestTests(unittest.TestCase):

    def test_correct_json_sort_digest_returns_true(self):
        value = {"a": 1, "b": 2}
        digest = _inline_digest(value)
        doc = _env("x", value=value, algo="sha256", canon="json-sort-keys-utf8-v1", digest=digest)
        self.assertIs(_verify_digest(doc), True)

    def test_wrong_digest_returns_false(self):
        value = {"a": 1}
        doc = _env("x", value=value, algo="sha256", canon="json-sort-keys-utf8-v1", digest="bad" * 16)
        self.assertIs(_verify_digest(doc), False)

    def test_reference_payload_returns_none(self):
        doc = _env("x", reference="file://somewhere.json", algo="sha256", canon="json-sort-keys-utf8-v1", digest="a" * 64)
        self.assertIsNone(_verify_digest(doc))

    def test_no_integrity_returns_none(self):
        doc = _env("x", value={"a": 1})
        self.assertIsNone(_verify_digest(doc))

    def test_no_digest_field_returns_none(self):
        doc = _env("x", value={"a": 1}, algo="sha256", canon="json-sort-keys-utf8-v1")
        self.assertIsNone(_verify_digest(doc))

    def test_utf8_raw_v1_string_value_verified(self):
        value = "hello world"
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        doc = _env("x", value=value, algo="sha256", canon="utf8-raw-v1", digest=digest)
        self.assertIs(_verify_digest(doc), True)

    def test_utf8_raw_v1_non_string_returns_none(self):
        doc = _env("x", value={"not": "a string"}, algo="sha256", canon="utf8-raw-v1", digest="a" * 64)
        self.assertIsNone(_verify_digest(doc))


# ---------------------------------------------------------------------------
# Unit test: _detect_cycle
# ---------------------------------------------------------------------------

class CycleDetectionTests(unittest.TestCase):

    def test_no_cycle_in_chain(self):
        adj = {"a": {"b"}, "b": {"c"}, "c": set()}
        self.assertIsNone(_detect_cycle(["a", "b", "c"], adj))

    def test_cycle_detected(self):
        adj = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
        result = _detect_cycle(["a", "b", "c"], adj)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)

    def test_self_loop_detected(self):
        adj = {"a": {"a"}}
        result = _detect_cycle(["a"], adj)
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# Integration tests via tmp directory
# ---------------------------------------------------------------------------

import tempfile
import os


def _write_envelopes(tmpdir: str, envelopes: list[dict]) -> Path:
    root = Path(tmpdir)
    for i, doc in enumerate(envelopes):
        p = root / f"env-{i:04d}.json"
        p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return root


class FrontierIntegrationTests(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def _write(self, envelopes: list[dict]) -> Path:
        return _write_envelopes(self._tmpdir, envelopes)

    def test_empty_root_has_empty_frontier(self):
        root = Path(self._tmpdir)
        report = analyze_frontier(root)
        self.assertEqual(report.envelope_count, 0)
        self.assertEqual(report.frontier_ids, [])
        self.assertIsNone(report.verification_ratio)

    def test_single_node_is_its_own_frontier(self):
        root = self._write([_env("alpha")])
        report = analyze_frontier(root)
        self.assertEqual(report.envelope_count, 1)
        self.assertEqual(report.frontier_ids, ["alpha"])

    def test_disconnected_nodes_all_on_frontier(self):
        envs = [_env("a"), _env("b"), _env("c")]
        root = self._write(envs)
        report = analyze_frontier(root)
        self.assertEqual(set(report.frontier_ids), {"a", "b", "c"})
        self.assertEqual(report.causal_edge_count, 0)

    def test_forward_causes_removes_predecessor_from_frontier(self):
        # a causes b => a -> b; b is on frontier, a is not
        env_a = _env("a", relations=[{"kind": "causes", "target": "b"}])
        env_b = _env("b")
        root = self._write([env_a, env_b])
        report = analyze_frontier(root)
        self.assertIn("b", report.frontier_ids)
        self.assertNotIn("a", report.frontier_ids)
        self.assertEqual(report.causal_edge_count, 1)

    def test_backward_depends_on_removes_dependent_from_frontier(self):
        # b depends_on a => a -> b; b is not on frontier
        env_a = _env("a")
        env_b = _env("b", relations=[{"kind": "depends_on", "target": "a"}])
        root = self._write([env_a, env_b])
        report = analyze_frontier(root)
        self.assertIn("b", report.frontier_ids)
        self.assertNotIn("a", report.frontier_ids)
        self.assertEqual(report.causal_edge_count, 1)

    def test_references_is_non_causal_does_not_shrink_frontier(self):
        env_a = _env("a", relations=[{"kind": "references", "target": "b"}])
        env_b = _env("b")
        root = self._write([env_a, env_b])
        report = analyze_frontier(root)
        self.assertIn("a", report.frontier_ids)
        self.assertIn("b", report.frontier_ids)
        self.assertEqual(report.causal_edge_count, 0)

    def test_external_target_is_identified(self):
        env_a = _env("a", relations=[{"kind": "causes", "target": "external-b"}])
        root = self._write([env_a])
        report = analyze_frontier(root)
        self.assertIn("external-b", report.external_target_ids)
        self.assertNotIn("external-b", report.frontier_ids)

    def test_cycle_is_flagged(self):
        env_a = _env("a", relations=[{"kind": "causes", "target": "b"}])
        env_b = _env("b", relations=[{"kind": "causes", "target": "a"}])
        root = self._write([env_a, env_b])
        report = analyze_frontier(root)
        self.assertTrue(report.has_cycle)
        self.assertIsNotNone(report.cycle_witness)

    def test_verification_ratio_all_verified(self):
        value = {"key": 42}
        digest = _inline_digest(value)
        env = _env("v", value=value, algo="sha256", canon="json-sort-keys-utf8-v1", digest=digest)
        root = self._write([env])
        report = analyze_frontier(root)
        self.assertEqual(report.verified_count, 1)
        self.assertEqual(report.verification_ratio, 1.0)

    def test_verification_ratio_mismatch(self):
        value = {"key": 42}
        env = _env("v", value=value, algo="sha256", canon="json-sort-keys-utf8-v1", digest="wrong" * 12 + "0000")
        root = self._write([env])
        report = analyze_frontier(root)
        self.assertEqual(report.unverified_count, 1)
        self.assertEqual(report.verification_ratio, 0.0)

    def test_verification_ratio_not_checkable_for_reference(self):
        # A reference-only payload cannot be digest-checked.
        # With 1 frontier node, 0 verified, ratio = 0 / 1 = 0.0 (not None).
        # None is reserved for the empty frontier case.
        env = _env("r", reference="file://something.json")
        root = self._write([env])
        report = analyze_frontier(root)
        self.assertEqual(report.not_checkable_count, 1)
        self.assertEqual(report.verified_count, 0)
        self.assertEqual(report.verification_ratio, 0.0)

    def test_encounter_payload_serializable(self):
        envs = [_env("x"), _env("y")]
        root = self._write(envs)
        report = analyze_frontier(root)
        payload = to_encounter_payload(report)
        # Must be JSON-serializable without error
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        recovered = json.loads(serialized)
        self.assertEqual(recovered["envelope_count"], 2)
        self.assertEqual(recovered["frontier_size"], 2)


if __name__ == "__main__":
    unittest.main()
