#!/usr/bin/env python3
"""Unit tests for Universal Observation Equivalence bridge.

Verifies mathematical invariants of QuotientSpace:
1. Reflexivity, symmetry, and witness extraction.
2. Partition soundness, pairwise disjointness, and full domain coverage.
3. Domain applications: Myhill-Nerode language prefix partition, IBV state abstraction,
   and E-CPU structural memory generators.
"""

from __future__ import annotations

import unittest
from typing import Dict, List, Tuple

from demonstration import (
    QuotientSpace,
    ibv_register_obs,
    language_obs,
    structural_gen_obs,
)


class ObservationEquivalenceTests(unittest.TestCase):
    """Test suite for QuotientSpace and domain observation models."""

    def test_reflexivity_and_symmetry(self) -> None:
        """Every object is equivalent to itself; equivalence is symmetric."""
        qs = QuotientSpace[int, int, int](lambda x, z: (x + z) % 5)
        tests = [0, 1, 2, 3, 4]

        # Reflexivity
        for val in range(10):
            equiv, witness = qs.are_equivalent(val, val, tests)
            self.assertTrue(equiv)
            self.assertIsNone(witness)

        # Symmetry
        equiv_ab, _ = qs.are_equivalent(2, 7, tests)
        equiv_ba, _ = qs.are_equivalent(7, 2, tests)
        self.assertEqual(equiv_ab, equiv_ba)
        self.assertTrue(equiv_ab)

        equiv_ac, _ = qs.are_equivalent(2, 3, tests)
        equiv_ca, _ = qs.are_equivalent(3, 2, tests)
        self.assertEqual(equiv_ac, equiv_ca)
        self.assertFalse(equiv_ac)

    def test_witness_extraction(self) -> None:
        """When two objects are not equivalent, returns the exact distinguishing test."""
        qs = QuotientSpace[str, str, bool](language_obs)
        tests = ["", "1", "11", "01"]

        # '0' vs '00' on L = {0^n 1^n}
        # Suffix '1' gives '01' (in L, True) vs '001' (not in L, False)
        equiv, witness = qs.are_equivalent("0", "00", tests)
        self.assertFalse(equiv)
        self.assertEqual(witness, "1")

    def test_partition_soundness_and_coverage(self) -> None:
        """Partitioning covers all objects and separates non-equivalent items."""
        # Modulo 3 equivalence
        qs = QuotientSpace[int, int, int](lambda x, z: (x * z) % 3)
        objects = list(range(12))  # 0 to 11
        tests = [1, 2]

        classes = qs.partition(objects, tests)

        # Total elements preserved
        flattened = [item for c in classes for item in c]
        self.assertEqual(sorted(flattened), objects)

        # 3 classes expected: [0, 3, 6, 9], [1, 4, 7, 10], [2, 5, 8, 11]
        self.assertEqual(len(classes), 3)

        # Check intra-class equivalence and inter-class distinctness
        for c in classes:
            rep = c[0]
            for member in c:
                equiv, _ = qs.are_equivalent(rep, member, tests)
                self.assertTrue(equiv)

        for i in range(len(classes)):
            for j in range(i + 1, len(classes)):
                rep_i = classes[i][0]
                rep_j = classes[j][0]
                equiv, witness = qs.are_equivalent(rep_i, rep_j, tests)
                self.assertFalse(equiv)
                self.assertIsNotNone(witness)

    def test_formal_language_nerode_quotient(self) -> None:
        """Myhill-Nerode prefixes partition into distinct classes."""
        qs = QuotientSpace[str, str, bool](language_obs)
        prefixes = ["", "0", "00", "000", "1", "01"]
        suffixes = ["", "1", "11", "111", "0", "01"]

        classes = qs.partition(prefixes, suffixes)
        # In L = {0^n 1^n}, each of '', '0', '00', '000', '1', '01' has unique future
        self.assertEqual(len(classes), 6)

    def test_ibv_register_abstraction(self) -> None:
        """State abstraction collapses states that agree on property observations."""
        qs = QuotientSpace[Dict[str, int], str, int](ibv_register_obs)
        states = [
            {"rax": 0, "rbx": 100},
            {"rax": 4, "rbx": 200},
            {"rax": 8, "rbx": 300},
            {"rax": 1, "rbx": 400},
            {"rax": 5, "rbx": 500},
        ]
        tests = ["rax_mod_4", "is_zero"]

        classes = qs.partition(states, tests)
        # rax=0 has is_zero=1, rax_mod_4=0
        # rax=4 and rax=8 have is_zero=0, rax_mod_4=0
        # rax=1 and rax=5 have is_zero=0, rax_mod_4=1
        self.assertEqual(len(classes), 3)

    def test_structural_generator_equivalence(self) -> None:
        """Generators with identical trajectories mod M form equivalence classes."""
        qs = QuotientSpace[Tuple[int, int, int], int, int](structural_gen_obs)
        # Generator (a, b, M): x_{k+1} = (a * x_k + b) mod M
        # (1, 2, 10): x_0=1, x_1=3, x_2=5, x_3=7, ...
        # (1, 12, 10): 12 mod 10 = 2, so yields identical trajectory!
        # (2, 1, 10): x_0=1, x_1=3, x_2=7, x_3=5, ...
        gens = [(1, 2, 10), (1, 12, 10), (2, 1, 10)]
        tests = [1, 2, 3, 4]

        classes = qs.partition(gens, tests)
        self.assertEqual(len(classes), 2)
        # Class 0 contains both (1, 2, 10) and (1, 12, 10)
        self.assertEqual(len(classes[0]), 2)
        self.assertEqual(len(classes[1]), 1)

    def test_bounded_suffix_suite_does_not_prove_universal_language_equivalence(self) -> None:
        qs = QuotientSpace[str, str, bool](language_obs)
        left = "0" * 20
        right = "0" * 21
        bounded_suffixes = ["1" * n for n in range(10)]
        finite_equal, witness = qs.are_equivalent(left, right, bounded_suffixes)
        self.assertTrue(finite_equal)
        self.assertIsNone(witness)
        complete_witness = "1" * 20
        self.assertNotEqual(
            language_obs(left, complete_witness),
            language_obs(right, complete_witness),
        )

    def test_unknown_register_mask_is_not_silently_mapped_to_zero(self) -> None:
        with self.assertRaises(ValueError):
            ibv_register_obs({"rax": 3}, "unknown-test")

    def test_affine_generator_rejects_invalid_step_and_modulus(self) -> None:
        with self.assertRaises(ValueError):
            structural_gen_obs((1, 2, 10), -1)
        with self.assertRaises(ValueError):
            structural_gen_obs((1, 2, 0), 2)

if __name__ == "__main__":
    unittest.main()
