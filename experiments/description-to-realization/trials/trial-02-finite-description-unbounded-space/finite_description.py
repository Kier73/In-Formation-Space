"""Finite descriptions that denote unbounded languages and state distinctions.

This is a formal computational experiment. It does not claim that an infinite
set is physically materialized. The generators produce finite members lazily.
"""

from __future__ import annotations

from itertools import count, islice, product
from typing import Iterator, Tuple


def all_binary_strings() -> Iterator[str]:
    """Lazily enumerate the countably infinite language {0,1}* by length."""
    for length in count():
        for bits in product("01", repeat=length):
            yield "".join(bits)


def parity_step(state: int, bit: str) -> int:
    """Two-state DFA transition: state 0 = even, state 1 = odd."""
    if state not in (0, 1):
        raise ValueError("parity state must be 0 or 1")
    if bit not in ("0", "1"):
        raise ValueError("binary input must contain only '0' and '1'")
    return state ^ int(bit)


def even_parity_accepts(word: str) -> bool:
    """Recognize strings containing an even number of 1s using two states."""
    state = 0
    for bit in word:
        state = parity_step(state, bit)
    return state == 0


def parity_length_signature(word: str, length_modulus: int) -> Tuple[int, int]:
    """Track two independent distinctions: parity and length modulo k."""
    if length_modulus < 1:
        raise ValueError("length_modulus must be positive")
    parity = 0
    for bit in word:
        if bit not in ("0", "1"):
            raise ValueError("binary input must contain only '0' and '1'")
        parity ^= int(bit)
    return parity, len(word) % length_modulus


def signature_witness(parity: int, residue: int, modulus: int) -> str:
    """Construct a finite word realizing any parity/length-mod-k signature."""
    if parity not in (0, 1):
        raise ValueError("parity must be 0 (even) or 1 (odd)")
    if modulus < 1:
        raise ValueError("modulus must be positive")
    if not 0 <= residue < modulus:
        raise ValueError("residue must be in range(modulus)")

    # For residue zero, use a positive length equal to the modulus.
    length = residue if residue else modulus
    if parity:
        return "1" + "0" * (length - 1)
    return "0" * length


def parity_length_state_count(length_modulus: int) -> int:
    """The product construction has 2*k reachable states."""
    if length_modulus < 1:
        raise ValueError("length_modulus must be positive")
    return 2 * length_modulus


def balanced_word(n: int) -> str:
    """Generate the nth word of S -> 0 S 1 | epsilon: 0^n 1^n."""
    if n < 0:
        raise ValueError("n must be non-negative")
    return "0" * n + "1" * n


def balanced_language() -> Iterator[str]:
    """Lazily enumerate the infinite context-free language {0^n 1^n | n>=0}."""
    for n in count():
        yield balanced_word(n)


def accepts_balanced_block(word: str) -> bool:
    """Recognize 0^n 1^n with a counter (unbounded state as n grows)."""
    zero_count = 0
    index = 0
    while index < len(word) and word[index] == "0":
        zero_count += 1
        index += 1

    suffix = word[index:]
    if any(bit != "1" for bit in suffix):
        return False
    return len(suffix) == zero_count


def distinguishes_balanced_prefixes(left: int, right: int) -> bool:
    """Use suffix 1^left to distinguish prefixes 0^left and 0^right."""
    if left < 0 or right < 0:
        raise ValueError("prefix lengths must be non-negative")
    if left == right:
        return False
    suffix = "1" * left
    left_accepts = accepts_balanced_block("0" * left + suffix)
    right_accepts = accepts_balanced_block("0" * right + suffix)
    return left_accepts and not right_accepts


def finite_prefix_of_binary_space(size: int) -> list[str]:
    """Return a finite prefix of the infinite binary-string enumeration."""
    if size < 0:
        raise ValueError("size must be non-negative")
    return list(islice(all_binary_strings(), size))
