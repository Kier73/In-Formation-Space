#!/usr/bin/env python3
"""Executable demonstration of finite-test observational quotienting.

The mathematical contracts may quantify over all valid continuations. This
module only compares the finite tests explicitly supplied by the caller. A
finite suite can find a counterexample, but cannot generally prove universal
equivalence without a completeness argument.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Generic, List, Optional, Sequence, Set, Tuple, TypeVar


T = TypeVar("T")  # State or object type
Z = TypeVar("Z")  # Test or continuation type
O = TypeVar("O")  # Observation type


class QuotientSpace(Generic[T, Z, O]):
    """Computes equivalence classes of objects under a test suite."""

    def __init__(self, observation_fn: Callable[[T, Z], O]):
        self._obs_fn = observation_fn

    def are_equivalent(self, x: T, y: T, tests: Sequence[Z]) -> Tuple[bool, Optional[Z]]:
        """Check equality over this finite supplied test set.

        True means no supplied test distinguishes x and y; it does not prove
        agreement on every possible future test unless the suite is complete.

        Returns (equivalent_on_supplied_tests, first_distinguishing_test).
        """
        for z in tests:
            if self._obs_fn(x, z) != self._obs_fn(y, z):
                return False, z
        return True, None

    def partition(self, objects: Sequence[T], tests: Sequence[Z]) -> List[List[T]]:
        """Partition objects by their signatures over the supplied finite tests."""
        classes: List[List[T]] = []
        for obj in objects:
            matched = False
            for c in classes:
                rep = c[0]
                equiv, _ = self.are_equivalent(rep, obj, tests)
                if equiv:
                    c.append(obj)
                    matched = True
                    break
            if not matched:
                classes.append([obj])
        return classes


# --- Application 1: Formal Languages (Trial 02 / Myhill-Nerode) ---
def language_obs(prefix: str, suffix: str) -> bool:
    """Language L = {0^n 1^n : n >= 0}. Observation: is prefix + suffix in L?"""
    s = prefix + suffix
    zeros = 0
    ones = 0
    in_ones = False
    for ch in s:
        if ch == "0":
            if in_ones:
                return False
            zeros += 1
        elif ch == "1":
            in_ones = True
            ones += 1
        else:
            return False
    return zeros == ones


# --- Application 2: Machine States & Property Abstraction (IBV) ---
def ibv_register_obs(reg_state: Dict[str, int], test_mask: str) -> int:
    """Observe only register 'rax' modulo 4, ignoring other registers."""
    rax = reg_state.get("rax", 0)
    if test_mask == "rax_mod_4":
        return rax % 4
    elif test_mask == "is_zero":
        return 1 if rax == 0 else 0
    return 0


# --- Application 3: Structural Memory Generators (E-CPU) ---
def structural_gen_obs(generator_params: Tuple[int, int, int], step: int) -> int:
    """Evaluate generator x_{k+1} = (a * x_k + b) mod M at step k."""
    a, b, m = generator_params
    if isinstance(step, bool) or not isinstance(step, int) or step < 0:
        raise ValueError("step must be a non-negative integer")
    if isinstance(m, bool) or not isinstance(m, int) or m <= 0:
        raise ValueError("modulus must be a positive integer")
    # Closed form orbit: x_k = a^k * x_0 + b * (a^k - 1) / (a - 1) mod m
    # For small demonstration: evaluate directly
    x = 1
    for _ in range(step):
        x = (a * x + b) % m
    return x


def main() -> None:
    print("=== OBSERVATION EQUIVALENCE BRIDGE DEMONSTRATION ===")

    # 1. Formal Language Prefixes
    lang_quotient = QuotientSpace[str, str, bool](language_obs)
    prefixes = ["", "0", "00", "000", "1", "01"]
    test_suffixes = ["", "1", "11", "111", "01"]

    classes = lang_quotient.partition(prefixes, test_suffixes)
    print(f"\n1. Myhill-Nerode Prefix Partition on L = {{0^n 1^n}}:")
    print(f"   Tested prefixes: {prefixes}")
    print(f"   Equivalence classes found ({len(classes)} classes):")
    for i, c in enumerate(classes, 1):
        print(f"     Class {i}: {c}")

    equiv, diff = lang_quotient.are_equivalent("0", "00", test_suffixes)
    print(f"   Are '0' and '00' equivalent? {equiv} (Distinguished by suffix: '{diff}')")

    # 2. IBV Machine State Abstraction
    ibv_quotient = QuotientSpace[Dict[str, int], str, int](ibv_register_obs)
    states = [
        {"rax": 0, "rbx": 100, "rcx": 50},
        {"rax": 4, "rbx": 999, "rcx": 0},    # Equivalent under rax mod 4
        {"rax": 8, "rbx": 12, "rcx": 77},     # Equivalent under rax mod 4
        {"rax": 1, "rbx": 100, "rcx": 50},
        {"rax": 5, "rbx": 0, "rcx": 0},      # Equivalent under rax mod 4
    ]
    ibv_tests = ["rax_mod_4"]
    ibv_classes = ibv_quotient.partition(states, ibv_tests)
    print(f"\n2. IBV Machine State Abstraction (Property: rax mod 4):")
    print(f"   Total concrete states: {len(states)}")
    print(f"   Abstract quotient classes ({len(ibv_classes)} classes):")
    for i, c in enumerate(ibv_classes, 1):
        rax_vals = [s["rax"] for s in c]
        print(f"     Abstract State {i}: rax values {rax_vals} (irrelevant rbx/rcx discarded)")

    # 3. E-CPU Structural Memory Generators
    struct_quotient = QuotientSpace[Tuple[int, int, int], int, int](structural_gen_obs)
    # Generator 1: (a=1, b=2, m=10) -> x_{k+1} = x_k + 2 mod 10
    # Generator 2: (a=1, b=12, m=10) -> equivalent because 12 = 2 mod 10
    # Generator 3: (a=2, b=1, m=10) -> distinct dynamics
    generators = [
        (1, 2, 10),
        (1, 12, 10),  # Redundant parameterization
        (2, 1, 10),
    ]
    step_queries = [1, 2, 3, 4, 5]
    gen_classes = struct_quotient.partition(generators, step_queries)
    print(f"\n3. E-CPU Structural Memory Generators:")
    print(f"   Candidate generators: {generators}")
    print(f"   Admitted distinct generator classes ({len(gen_classes)} classes):")
    for i, c in enumerate(gen_classes, 1):
        print(f"     Structural Generator Class {i}: {c}")

    print("\n[OK] Demonstration completed. These are finite-test quotients; universal equivalence requires a complete contract or proof.")


if __name__ == "__main__":
    main()
