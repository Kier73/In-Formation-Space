#!/usr/bin/env python3
"""Comprehensive test suite for PosetInterleaver.

Verifies hard constraints and success criteria from brief:d2r-poset-01.
"""

import random
import unittest
from itertools import permutations
from poset_interleaver import PosetCycleError, PosetInterleaver


class TestPosetInterleaver(unittest.TestCase):

    def test_cold_start_split_clock_relay_combinatorics(self):
        """Hard constraint 3: Verify the 4-event controller and 3-event sensor chains yield exactly 35 extensions."""
        poset = PosetInterleaver()
        # Controller chain: C100 < C101 < C105 < C108
        poset.add_chain(["C100", "C101", "C105", "C108"])
        # Sensor chain: S8 < S11 < S14
        poset.add_chain(["S8", "S11", "S14"])

        self.assertEqual(len(poset.events), 7)
        self.assertTrue(poset.is_acyclic())

        # Exact linear extension count
        omega_count = poset.count_linear_extensions()
        self.assertEqual(omega_count, 35, f"Expected exactly 35 extensions, got {omega_count}")

        # Generator check: yielded list must match count
        all_exts = list(poset.generate_linear_extensions())
        self.assertEqual(len(all_exts), 35)

        # Verify each generated extension passes trace verification
        for ext in all_exts:
            valid, reason, edge = poset.verify_trace(ext)
            self.assertTrue(valid, f"Generated extension failed verification: {ext}, reason: {reason}")

    def test_constrained_cross_stream_reduction(self):
        """Adding a cross-stream causal edge strictly reduces the extension count."""
        poset = PosetInterleaver()
        poset.add_chain(["C100", "C101", "C105", "C108"])
        poset.add_chain(["S8", "S11", "S14"])

        # Add cross-stream constraint: worker start C105 must happen before sensor S11
        poset.add_edge("C105", "S11")

        omega_constrained = poset.count_linear_extensions()
        self.assertGreaterEqual(omega_constrained, 1)
        self.assertLess(omega_constrained, 35)

        # Every generated sequence must preserve C105 < S11
        for ext in poset.generate_linear_extensions():
            self.assertLess(ext.index("C105"), ext.index("S11"))

    def test_cycle_detection_and_witness_extraction(self):
        """Hard constraint 2: Cycle detection extracts exact cycle path."""
        poset = PosetInterleaver()
        poset.add_edge("A", "B")
        poset.add_edge("B", "C")
        poset.add_edge("C", "A")  # Cycle A -> B -> C -> A

        self.assertFalse(poset.is_acyclic())
        cycle = poset.find_cycle()
        self.assertIsNotNone(cycle)
        self.assertEqual(cycle[0], cycle[-1], "Cycle witness must start and end at the same node")
        self.assertIn("A", cycle)
        self.assertIn("B", cycle)
        self.assertIn("C", cycle)

        with self.assertRaises(PosetCycleError) as ctx:
            poset.count_linear_extensions()
        self.assertEqual(ctx.exception.cycle, cycle)

    def test_trace_verification_and_edge_blame(self):
        """Hard constraint 4: Trace verification detects violations and identifies violated edge."""
        poset = PosetInterleaver()
        poset.add_chain(["A", "B", "C"])

        # Valid trace
        valid, reason, edge = poset.verify_trace(["A", "B", "C"])
        self.assertTrue(valid)
        self.assertIsNone(reason)
        self.assertIsNone(edge)

        # Inverted trace: B before A
        valid, reason, edge = poset.verify_trace(["B", "A", "C"])
        self.assertFalse(valid)
        self.assertEqual(edge, ("A", "B"))

        # Incomplete trace
        valid, reason, edge = poset.verify_trace(["A", "B"])
        self.assertFalse(valid)
        self.assertIn("match", reason.lower())

    def test_query_immutability(self):
        """Hard constraint 5: Querying properties does not alter poset state."""
        poset = PosetInterleaver()
        poset.add_chain(["X1", "X2"])
        poset.add_chain(["Y1", "Y2"])

        orig_events = poset.events
        orig_edges = poset.edge_count

        _ = poset.count_linear_extensions()
        _ = list(poset.generate_linear_extensions())
        _ = poset.verify_trace(["X1", "Y1", "X2", "Y2"])
        _ = poset.find_cycle()

        self.assertEqual(poset.events, orig_events)
        self.assertEqual(poset.edge_count, orig_edges)

class TestPosetInterleaverAdditionalProperties(unittest.TestCase):
    def test_empty_poset_has_one_empty_linear_extension(self):
        poset = PosetInterleaver()
        self.assertEqual(poset.count_linear_extensions(), 1)
        self.assertEqual(list(poset.generate_linear_extensions()), [[]])
        self.assertEqual(poset.verify_trace([]), (True, None, None))

    def test_queries_do_not_mutate_adjacency_maps(self):
        poset = PosetInterleaver()
        poset.add_event("isolated")
        successors_before = {key: set(value) for key, value in poset._successors.items()}
        predecessors_before = {key: set(value) for key, value in poset._predecessors.items()}
        successor_keys_before = set(poset._successors)
        predecessor_keys_before = set(poset._predecessors)

        poset.find_cycle()
        poset.is_acyclic()
        poset.count_linear_extensions()
        list(poset.generate_linear_extensions())
        poset.verify_trace(["isolated"])

        self.assertEqual(dict(poset._successors), successors_before)
        self.assertEqual(dict(poset._predecessors), predecessors_before)
        self.assertEqual(set(poset._successors), successor_keys_before)
        self.assertEqual(set(poset._predecessors), predecessor_keys_before)

    def test_trace_blame_is_deterministic_in_edge_insertion_order(self):
        poset = PosetInterleaver()
        poset.add_edge("z", "a")
        poset.add_edge("y", "b")
        trace = ["a", "b", "y", "z"]
        observed = [poset.verify_trace(trace)[2] for _ in range(10)]
        self.assertEqual(observed, [("z", "a")] * 10)

    def test_random_small_dags_match_brute_force_and_generator(self):
        rng = random.Random(20261111)
        for n in range(0, 7):
            for sample in range(8):
                with self.subTest(n=n, sample=sample):
                    poset = PosetInterleaver()
                    events = [f"e{i}" for i in range(n)]
                    for event in events:
                        poset.add_event(event)
                    for i in range(n):
                        for j in range(i + 1, n):
                            if rng.random() < 0.38:
                                poset.add_edge(events[i], events[j])

                    brute_count = sum(
                        1 for ordering in permutations(events)
                        if poset.verify_trace(ordering)[0]
                    )
                    dp_count = poset.count_linear_extensions()
                    generated = list(poset.generate_linear_extensions())
                    self.assertEqual(dp_count, brute_count)
                    self.assertEqual(len(generated), brute_count)
                    self.assertTrue(all(poset.verify_trace(ordering)[0] for ordering in generated))

    def test_duplicate_edge_does_not_duplicate_constraint_or_count(self):
        poset = PosetInterleaver()
        poset.add_edge("a", "b")
        poset.add_edge("a", "b")
        self.assertEqual(poset.edge_count, 1)
        self.assertEqual(poset.count_linear_extensions(), 1)
        self.assertEqual(list(poset.generate_linear_extensions()), [["a", "b"]])

    def test_negative_generation_limit_is_rejected(self):
        poset = PosetInterleaver()
        poset.add_event("a")
        with self.assertRaises(ValueError):
            list(poset.generate_linear_extensions(limit=-1))

if __name__ == "__main__":
    unittest.main()
