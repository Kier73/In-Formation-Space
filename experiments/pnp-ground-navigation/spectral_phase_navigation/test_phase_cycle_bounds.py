"""SPN-003 phase-cycle arithmetic, proof soundness and negative controls."""
import copy
from fractions import Fraction
from random import Random
import unittest

from phase_cycle_bounds import (find_positive_triangles, triangle_bound,
    independent_triangle_bound, produce_cycle_receipt, verify_cycle_receipt)
from spectral_receipts import produce_receipt
from walsh_phase_navigation_probe import (spectral_coefficients,
    conditional_coefficients, clauses_from_energy_profile, violated_count)


def frustrated_blocks(blocks):
    """Every three-variable block has energy 2 + chi_a + chi_b + chi_(a xor b).

    It takes values 5 at (a,b)=(0,0) and 1 elsewhere. Every block
    comprises 16 ordinary width-three clauses, with the third bit free.
    """
    clauses = []
    for index in range(blocks):
        variables = tuple(range(3 * index, 3 * index + 3))
        for pattern in range(8):
            count = 5 if (pattern & 3) == 0 else 1
            clauses.extend([(variables, tuple((pattern >> i) & 1 for i in range(3)))] * count)
    return clauses, 3 * blocks


class PhaseCycleBoundsTests(unittest.TestCase):
    def test_single_root_unsat_with_strict_phase_gain(self):
        clauses, n = frustrated_blocks(1)
        coeff = spectral_coefficients(clauses)
        naive = coeff[0] - sum(abs(a) for s, a in coeff.items() if s)
        lower, triangles = triangle_bound(coeff)
        self.assertEqual(naive, -8)
        self.assertEqual(lower, 8)
        self.assertEqual(triangles, [(1, 2, 3)])
        self.assertEqual(find_positive_triangles(coeff), [(16, (1, 2, 3))])
        self.assertEqual(independent_triangle_bound(clauses, {}, [[1, 2, 3]]), Fraction(1))
        old = produce_receipt(clauses, n, budget=32)
        new = produce_cycle_receipt(clauses, n, budget=32)
        self.assertEqual(old['producer_nodes_visited'], 3)
        self.assertEqual(new['producer_nodes_visited'], 1)
        self.assertEqual(verify_cycle_receipt(clauses, n, new), 'UNSAT')

    def test_96_variables_32_constant_size_certificates(self):
        clauses, n = frustrated_blocks(32)
        self.assertEqual((n, len(clauses)), (96, 512))
        old = produce_receipt(clauses, n, budget=256)
        self.assertEqual(old['result'], 'UNKNOWN')
        new = produce_cycle_receipt(clauses, n, budget=256)
        self.assertEqual(new['result'], 'UNSAT')
        self.assertEqual(new['producer_nodes_visited'], 1)
        self.assertEqual(len(new['proof']['triangles']), 32)
        self.assertEqual(new['proof']['bound'], [32, 1])
        self.assertEqual(verify_cycle_receipt(clauses, n, new), 'UNSAT')

    def test_no_phase_gain_for_satisfiable_parity_triangle(self):
        # E=3-chi_0-chi_1-chi_0chi_1 has one zero and negative phase product.
        p = [0 if (x & 3) == 0 else 4 for x in range(8)]
        clauses = clauses_from_energy_profile(p)
        c = spectral_coefficients(clauses)
        self.assertEqual(find_positive_triangles(c), [])
        lower, triangles = triangle_bound(c)
        self.assertEqual(lower, 0)    # 3 - 3 = 0, scaled by 8.
        self.assertEqual(triangles, [])
        receipt = produce_cycle_receipt(clauses, 3)
        self.assertEqual(verify_cycle_receipt(clauses, 3, receipt), 'SAT')

    def test_sound_against_exhaustive_energy_for_random_prefixes(self):
        rng = Random(730003)
        for n in range(3, 9):
            for _ in range(30):
                clauses = []
                for _ in range(3 * n + 4):
                    vs = tuple(sorted(rng.sample(range(n), 3)))
                    b = tuple(rng.randrange(2) for _ in range(3))
                    clauses.append((vs, b))
                coeff = spectral_coefficients(clauses)
                prefix = {v: rng.randrange(2) for v in range(n) if rng.randrange(3) == 0}
                for v, b in prefix.items():
                    coeff = conditional_coefficients(coeff, v, b)
                lower, tri = triangle_bound(coeff)
                checked = independent_triangle_bound(clauses, prefix, [list(t) for t in tri])
                self.assertEqual(checked, Fraction(lower, 8))
                residual = [violated_count(clauses, x) for x in range(1 << n)
                            if all(((x >> v) & 1) == b for v, b in prefix.items())]
                self.assertLessEqual(checked, min(residual))

    def test_certificates_forgery_refusals(self):
        clauses, n = frustrated_blocks(2)
        valid = produce_cycle_receipt(clauses, n)
        self.assertEqual(verify_cycle_receipt(clauses, n, valid), 'UNSAT')
        bad = copy.deepcopy(valid)
        bad['proof']['bound'] = [3, 1]
        with self.assertRaises(ValueError):
            verify_cycle_receipt(clauses, n, bad)
        bad = copy.deepcopy(valid)
        bad['proof']['triangles'][0] = [1, 2, 4]
        with self.assertRaises(ValueError):
            verify_cycle_receipt(clauses, n, bad)
        bad = copy.deepcopy(valid)
        bad['proof']['triangles'].append(bad['proof']['triangles'][0])
        with self.assertRaises(ValueError):
            verify_cycle_receipt(clauses, n, bad)
        bad = copy.deepcopy(valid)
        bad['formula_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            verify_cycle_receipt(clauses, n, bad)
        bad = copy.deepcopy(valid)
        bad['proof'] = {'kind': 'sat', 'witness': [0] * n}
        bad['result'] = 'SAT'
        with self.assertRaises(ValueError):
            verify_cycle_receipt(clauses, n, bad)
        bad = copy.deepcopy(valid)
        bad['proof']['triangles'] = [[1, 2, 3], [1, 2, 3]]
        with self.assertRaises(ValueError):
            verify_cycle_receipt(clauses, n, bad)

    def test_unknown_budget_and_randomized_exhaustive_checks(self):
        rng = Random(20261123)
        for n in (5, 6, 7, 8):
            for _ in range(25):
                clauses = []
                for _ in range(4 * n + 1):
                    vs = tuple(sorted(rng.sample(range(n), 3)))
                    b = tuple(rng.randrange(2) for _ in range(3))
                    clauses.append((vs, b))
                sat = any(violated_count(clauses, x) == 0 for x in range(1 << n))
                receipt = produce_cycle_receipt(clauses, n, budget=512)
                self.assertEqual(verify_cycle_receipt(clauses, n, receipt),
                                 'SAT' if sat else 'UNSAT')
        clauses, n = frustrated_blocks(1)
        # A budget of one is still enough because the root bound is positive.
        self.assertEqual(produce_cycle_receipt(clauses, n, budget=1)['result'], 'UNSAT')
        # A satisfiable-search miss with budget one has no right to claim UNSAT.
        # Take a custom nontrivial profile for a case needing further branching.
        rng = Random(33)
        found_unknown = False
        for _ in range(100):
            clauses = []
            for _ in range(34):
                vs = tuple(sorted(rng.sample(range(8), 3)))
                b = tuple(rng.randrange(2) for _ in range(3))
                clauses.append((vs, b))
            receipt = produce_cycle_receipt(clauses, 8, budget=1)
            if receipt['result'] == 'UNKNOWN':
                found_unknown = True
                self.assertEqual(verify_cycle_receipt(clauses, 8, receipt), 'UNKNOWN')
                break
        self.assertTrue(found_unknown)


if __name__ == '__main__':
    unittest.main()