#!/usr/bin/env python3
"""Unit tests for CausalEncounterGraph.

Verifies:
1. Basic graph construction and forward/backward relation interpretation.
2. Cycle detection and witness extraction.
3. Transitive reduction (Hasse diagram extraction).
4. Physical timestamp anachronism detection.
5. Non-causal relation isolation.
6. Poset linear extension counting (matching combinatorial invariants).
7. Error handling for duplicate IDs and malformed inputs.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from causal_graph import CausalEncounterGraph, AnachronismViolation


def make_envelope(
    env_id: str,
    observed_at: str | None = None,
    relations: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    return {
        "format": "in-formation.encounter/0.1",
        "id": env_id,
        "observed_at": observed_at,
        "source": {"kind": "test-suite"},
        "payload": {"value": f"data-for-{env_id}"},
        "relations": relations or [],
    }


class CausalEncounterGraphTests(unittest.TestCase):
    """Test suite for causal envelope graph construction and analysis."""

    def test_single_envelope_has_one_extension_and_no_edges(self) -> None:
        graph = CausalEncounterGraph([make_envelope("env-1")])
        report = graph.analyze()
        self.assertEqual(report.envelope_count, 1)
        self.assertEqual(report.internal_nodes, ("env-1",))
        self.assertEqual(report.external_targets, ())
        self.assertFalse(report.has_cycle)
        self.assertEqual(report.direct_edges, ())
        self.assertEqual(report.hasse_edges, ())
        self.assertEqual(report.linear_extension_count, 1)
        self.assertEqual(report.sample_topological_order, ("env-1",))

    def test_forward_and_backward_causal_relations(self) -> None:
        # A precedes B (forward: A -> B)
        # C caused_by B (backward: B -> C)
        env_a = make_envelope("A", relations=[{"kind": "precedes", "target": "B"}])
        env_b = make_envelope("B")
        env_c = make_envelope("C", relations=[{"kind": "caused_by", "target": "B"}])

        graph = CausalEncounterGraph([env_a, env_b, env_c])
        report = graph.analyze()

        self.assertFalse(report.has_cycle)
        self.assertEqual(report.direct_edges, (("A", "B"), ("B", "C")))
        self.assertEqual(report.hasse_edges, (("A", "B"), ("B", "C")))
        self.assertEqual(report.sample_topological_order, ("A", "B", "C"))
        self.assertEqual(report.linear_extension_count, 1)

    def test_external_targets_tracked_at_epistemic_boundary(self) -> None:
        # A depends on an external unretrieved artifact EXT-1
        env_a = make_envelope("A", relations=[{"kind": "depends_on", "target": "EXT-1"}])
        graph = CausalEncounterGraph([env_a])
        report = graph.analyze()

        self.assertEqual(report.envelope_count, 1)
        self.assertEqual(report.internal_nodes, ("A",))
        self.assertEqual(report.external_targets, ("EXT-1",))
        # Edge is EXT-1 -> A
        self.assertEqual(report.direct_edges, (("EXT-1", "A"),))
        self.assertEqual(report.sample_topological_order, ("EXT-1", "A"))

    def test_cycle_detection_extracts_witness(self) -> None:
        # A -> B -> C -> A
        env_a = make_envelope("A", relations=[{"kind": "causes", "target": "B"}])
        env_b = make_envelope("B", relations=[{"kind": "causes", "target": "C"}])
        env_c = make_envelope("C", relations=[{"kind": "causes", "target": "A"}])

        graph = CausalEncounterGraph([env_a, env_b, env_c])
        report = graph.analyze()

        self.assertTrue(report.has_cycle)
        self.assertIsNotNone(report.cycle_witness)
        self.assertEqual(report.linear_extension_count, 0)
        self.assertIsNone(report.sample_topological_order)
        # Cycle witness must start and end at the same node
        self.assertEqual(report.cycle_witness[0], report.cycle_witness[-1])

    def test_transitive_reduction_removes_redundant_shortcuts(self) -> None:
        # A -> B -> C and direct shortcut A -> C
        env_a = make_envelope(
            "A",
            relations=[
                {"kind": "causes", "target": "B"},
                {"kind": "causes", "target": "C"},
            ],
        )
        env_b = make_envelope("B", relations=[{"kind": "causes", "target": "C"}])
        env_c = make_envelope("C")

        graph = CausalEncounterGraph([env_a, env_b, env_c])
        report = graph.analyze()

        self.assertFalse(report.has_cycle)
        # Direct edges include the shortcut (A, C)
        self.assertIn(("A", "C"), report.direct_edges)
        # Hasse diagram removes shortcut (A, C)
        self.assertEqual(report.hasse_edges, (("A", "B"), ("B", "C")))

    def test_non_causal_relations_do_not_induce_temporal_order(self) -> None:
        # A references B and annotates C; neither is a causal predecessor
        env_a = make_envelope(
            "A",
            relations=[
                {"kind": "references", "target": "B"},
                {"kind": "annotates", "target": "C"},
            ],
        )
        env_b = make_envelope("B")
        env_c = make_envelope("C")

        graph = CausalEncounterGraph([env_a, env_b, env_c])
        report = graph.analyze()

        self.assertFalse(report.has_cycle)
        self.assertEqual(report.direct_edges, ())
        self.assertEqual(report.hasse_edges, ())
        # 3 unordered nodes yield 3! = 6 linear extensions
        self.assertEqual(report.linear_extension_count, 6)

    def test_anachronism_detection_identifies_timestamp_violations(self) -> None:
        # Causal order: A causes B (A < B).
        # But A has observed_at = 12:05:00 and B has observed_at = 12:00:00 (A is in the future of B!)
        env_a = make_envelope(
            "A",
            observed_at="2026-11-11T12:05:00Z",
            relations=[{"kind": "causes", "target": "B"}],
        )
        env_b = make_envelope("B", observed_at="2026-11-11T12:00:00Z")

        graph = CausalEncounterGraph([env_a, env_b])
        report = graph.analyze()

        self.assertFalse(report.has_cycle)
        self.assertEqual(len(report.anachronisms), 1)
        viol = report.anachronisms[0]
        self.assertEqual(viol.predecessor_id, "A")
        self.assertEqual(viol.successor_id, "B")
        self.assertEqual(viol.time_skew_seconds, 300.0)

    def test_combinatorial_two_chain_interleaving_count(self) -> None:
        # Two independent chains:
        # Chain 1: C0 -> C1
        # Chain 2: S0 -> S1
        # Number of linear extensions should be binom(2+2, 2) = 6
        c0 = make_envelope("C0", relations=[{"kind": "causes", "target": "C1"}])
        c1 = make_envelope("C1")
        s0 = make_envelope("S0", relations=[{"kind": "causes", "target": "S1"}])
        s1 = make_envelope("S1")

        graph = CausalEncounterGraph([c0, c1, s0, s1])
        report = graph.analyze()

        self.assertFalse(report.has_cycle)
        self.assertEqual(report.linear_extension_count, 6)

    def test_duplicate_envelope_ids_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CausalEncounterGraph([make_envelope("A"), make_envelope("A")])

    def test_empty_or_whitespace_ids_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CausalEncounterGraph([make_envelope("")])
        with self.assertRaises(ValueError):
            CausalEncounterGraph([make_envelope("   ")])


if __name__ == "__main__":
    unittest.main()
