import unittest
from itertools import product

from finite_description import (
    accepts_balanced_block,
    balanced_language,
    balanced_word,
    distinguishes_balanced_prefixes,
    even_parity_accepts,
    finite_prefix_of_binary_space,
    parity_length_signature,
    parity_length_state_count,
    signature_witness,
)


class FiniteDescriptionTests(unittest.TestCase):
    def test_binary_generator_enumerates_exact_finite_levels(self):
        words = finite_prefix_of_binary_space(15)
        self.assertEqual(len(words), 15)
        by_length = {}
        for word in words:
            by_length[len(word)] = by_length.get(len(word), 0) + 1
        self.assertEqual(by_length, {0: 1, 1: 2, 2: 4, 3: 8})
        self.assertEqual(len(set(words)), len(words))

    def test_even_parity_dfa_matches_direct_count(self):
        for length in range(9):
            for bits in product("01", repeat=length):
                word = "".join(bits)
                expected = sum(bit == "1" for bit in word) % 2 == 0
                self.assertEqual(even_parity_accepts(word), expected)

    def test_parity_and_length_modulo_have_all_two_k_states(self):
        for modulus in range(1, 8):
            witnessed = set()
            for parity in (0, 1):
                for residue in range(modulus):
                    word = signature_witness(parity, residue, modulus)
                    self.assertEqual(
                        parity_length_signature(word, modulus),
                        (parity, residue),
                    )
                    witnessed.add(parity_length_signature(word, modulus))
            self.assertEqual(len(witnessed), parity_length_state_count(modulus))
            self.assertEqual(parity_length_state_count(modulus), 2 * modulus)

    def test_balanced_language_generator_matches_recursive_description(self):
        generator = balanced_language()
        words = [next(generator) for _ in range(10)]
        self.assertEqual(words, [balanced_word(n) for n in range(10)])
        self.assertEqual(words[0], "")
        self.assertEqual(words[9], "0" * 9 + "1" * 9)

    def test_balanced_language_recognizer_accepts_and_rejects(self):
        for n in range(20):
            self.assertTrue(accepts_balanced_block(balanced_word(n)))
        for bad in ("0", "1", "001", "011", "0101", "00011", "1100", "00110"):
            self.assertFalse(accepts_balanced_block(bad))

    def test_distinct_prefix_lengths_have_distinguishing_suffixes(self):
        for left in range(12):
            for right in range(12):
                if left != right:
                    self.assertTrue(distinguishes_balanced_prefixes(left, right))

    def test_finite_description_constructs_large_finite_instance(self):
        word = balanced_word(5000)
        self.assertEqual(len(word), 10000)
        self.assertTrue(accepts_balanced_block(word))


if __name__ == "__main__":
    unittest.main()
