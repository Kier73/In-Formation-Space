"""SPN-004: exhaustive independent controls of parity-rank block receipts."""
import copy
from fractions import Fraction
from random import Random
import unittest

from phase_cycle_bounds import triangle_bound, produce_cycle_receipt
from rank_block_bounds import (parity_basis, parity_coordinates,
    exact_block_minimum, rank_block_bound, exact_rank_ground,
    independent_rank_block_bound,
    produce_rank_receipt, verify_rank_receipt)
from walsh_phase_navigation_probe import (clauses_from_energy_profile,
    spectral_coefficients, conditional_coefficients, violated_count)


def four_circuit_profile():
    # E = 3 + chi_0 + chi_1 + chi_2 - chi_(0,1,2).
    return [3 + sum(1 if not (x & (1 << i)) else -1 for i in range(3))
            - (1 if x.bit_count() % 2 == 0 else -1) for x in range(8)]


def fano_blocks(block_count):
    # Each block has E=2 + sum_{nonempty S subset {a,b,c}} chi_S.
    # Values: 9 at local 000, 1 at each of seven other states.
    clauses = []
    for b in range(block_count):
        variables = (3*b, 3*b+1, 3*b+2)
        for pattern in range(8):
            multiplicity = 9 if pattern == 0 else 1
            clauses.extend([(variables, tuple((pattern >> i) & 1 for i in range(3)))] * multiplicity)
    return clauses, 3 * block_count


class RankBlockBoundsTests(unittest.TestCase):
    def test_rank3_detects_a_four_term_circuit_with_no_triangles(self):
        profile = four_circuit_profile()
        self.assertEqual(sorted(set(profile)), [1, 5])
        clauses = clauses_from_energy_profile(profile)
        coeff = spectral_coefficients(clauses)
        self.assertEqual(set(s for s in coeff if s and coeff[s]), {1, 2, 4, 7})
        old, triples = triangle_bound(coeff)
        self.assertEqual((old, triples), (-8, []))
        lower, blocks = rank_block_bound(coeff, clauses, 3)
        self.assertEqual((lower, blocks), (8, [(1, 2, 4, 7)]))
        self.assertEqual(independent_rank_block_bound(clauses, {}, [[1, 2, 4, 7]], 3), Fraction(1))
        receipt = produce_rank_receipt(clauses, 3, budget=32)
        self.assertEqual(receipt['producer_nodes_visited'], 1)
        self.assertEqual(verify_rank_receipt(clauses, 3, receipt), 'UNSAT')
        self.assertGreater(produce_cycle_receipt(clauses, 3)['producer_nodes_visited'], 1)

    def test_seven_character_rank3_block_but_overlapping_triangles(self):
        clauses, n = fano_blocks(1)
        c = spectral_coefficients(clauses)
        self.assertEqual((c[0], [c.get(s) for s in range(1, 8)]), (16, [8]*7))
        self.assertEqual(triangle_bound(c)[0], -24)
        lower, blocks = rank_block_bound(c, clauses, 3)
        self.assertEqual(lower, 8)
        self.assertEqual(blocks, [(1, 2, 3, 4, 5, 6, 7)])
        self.assertEqual(exact_block_minimum(c, blocks[0]), (-8, 3))
        self.assertEqual(produce_rank_receipt(clauses, n)['proof']['bound'], [1, 1])

    def test_ninety_six_bit_structured_exclusion_has_compact_receipt(self):
        clauses, n = fano_blocks(32)
        self.assertEqual((n, len(clauses)), (96, 512))
        cycle = produce_cycle_receipt(clauses, n, budget=256)
        self.assertEqual(cycle['result'], 'UNKNOWN')
        rank = produce_rank_receipt(clauses, n, budget=256)
        self.assertEqual(rank['result'], 'UNSAT')
        self.assertEqual(rank['producer_nodes_visited'], 1)
        self.assertEqual(rank['proof']['bound'], [32, 1])
        self.assertEqual(len(rank['proof']['blocks']), 32)
        self.assertEqual(verify_rank_receipt(clauses, n, rank), 'UNSAT')

    def test_rank_bases_recover_genuinely_wide_supports(self):
        # Rank is 3 even though the support union spans 121 source indices.
        x, y, z = (1 << 0) | (1 << 120), (1 << 47), (1 << 60)
        masks = [x, y, z, x ^ y ^ z]
        basis = parity_basis(masks)
        self.assertEqual(len(basis), 3)
        self.assertEqual(set(parity_coordinates(s, basis) for s in masks), {1, 2, 4, 7})
        coeff = dict(zip(masks, (8, 8, 8, -8)))
        self.assertEqual(exact_block_minimum(coeff, masks), (-16, 3))

    def test_full_low_rank_ground_is_realizable_with_wide_variable_support(self):
        # This abstract Walsh polynomial spans indices 0..120, but has rank 3.
        a = (1 << 0) | (1 << 120)
        b = 1 << 47
        c = 1 << 60
        coeff = {0: 24, a: 8, b: 8, c: 8, a ^ b ^ c: -8}
        minimum, witness, rank = exact_rank_ground(coeff, 121, rank_budget=3)
        self.assertEqual((minimum, rank), (8, 3))
        self.assertLess(witness, 1 << 121)
        self.assertEqual(sum(amplitude * (-1 if ((mask & witness).bit_count() & 1) else 1)
                             for mask, amplitude in coeff.items()), 8)
        clauses, n = fano_blocks(4)
        with self.assertRaises(ValueError):
            exact_rank_ground(spectral_coefficients(clauses), n, rank_budget=3)

    def test_exhaustive_soundness_of_random_restrictions(self):
        rng = Random(420004)
        for n in range(3, 9):
            for _ in range(30):
                clauses = []
                for _ in range(4*n + 3):
                    vs = tuple(sorted(rng.sample(range(n), 3)))
                    forb = tuple(rng.randrange(2) for _ in range(3))
                    clauses.append((vs, forb))
                coeff = spectral_coefficients(clauses)
                prefix = {v: rng.randrange(2) for v in range(n) if rng.randrange(4) == 0}
                for v, b in prefix.items():
                    coeff = conditional_coefficients(coeff, v, b)
                old, _ = triangle_bound(coeff)
                lower, blocks = rank_block_bound(coeff, clauses, 3)
                self.assertGreaterEqual(lower, old)
                checked = independent_rank_block_bound(clauses, prefix, [list(b) for b in blocks], 3)
                self.assertEqual(checked, Fraction(lower, 8))
                energies = [violated_count(clauses, x) for x in range(1 << n)
                            if all(((x >> v) & 1) == b for v, b in prefix.items())]
                self.assertLessEqual(checked, min(energies))

    def test_forged_claims_and_unsupported_rank_rejected(self):
        clauses, n = fano_blocks(1)
        valid = produce_rank_receipt(clauses, n)
        self.assertEqual(verify_rank_receipt(clauses, n, valid), 'UNSAT')
        for variant in ('bad_bound','reused','missing','rank','hash','fake_sat'):
            bad = copy.deepcopy(valid)
            if variant == 'bad_bound':
                bad['proof']['bound'] = [2, 1]
            if variant == 'reused':
                bad['proof']['blocks'].append(bad['proof']['blocks'][0])
            if variant == 'missing':
                bad['proof']['blocks'][0][0] = 8
            if variant == 'rank':
                bad['rank_cap'] = 2
            if variant == 'hash':
                bad['formula_sha256'] = '0'*64
            if variant == 'fake_sat':
                bad['result'] = 'SAT'
                bad['proof'] = {'kind': 'sat', 'witness': [0, 0, 0]}
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                verify_rank_receipt(clauses, n, bad)

    def test_random_truth_table_and_explicit_budget_unknown(self):
        rng = Random(620004)
        for n in (5, 6, 7, 8):
            for _ in range(25):
                clauses = []
                for _ in range(4*n + 2):
                    vs = tuple(sorted(rng.sample(range(n), 3)))
                    forb = tuple(rng.randrange(2) for _ in range(3))
                    clauses.append((vs, forb))
                sat = any(violated_count(clauses, x) == 0 for x in range(1 << n))
                r = produce_rank_receipt(clauses, n, budget=512)
                self.assertEqual(verify_rank_receipt(clauses, n, r), 'SAT' if sat else 'UNSAT')
        rng = Random(52)
        refused = False
        for _ in range(100):
            clauses = []
            for _ in range(33):
                vs = tuple(sorted(rng.sample(range(8), 3)))
                clauses.append((vs, tuple(rng.randrange(2) for _ in range(3))))
            r = produce_rank_receipt(clauses, 8, budget=1)
            if r['result'] == 'UNKNOWN':
                refused = True
                self.assertEqual(verify_rank_receipt(clauses, 8, r), 'UNKNOWN')
                break
        self.assertTrue(refused)


if __name__ == '__main__':
    unittest.main()