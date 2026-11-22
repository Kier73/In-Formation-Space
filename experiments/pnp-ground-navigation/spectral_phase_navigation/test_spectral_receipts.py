"""Independent receipt validation, negative controls and bounded refusals."""
import copy
import random
import unittest
from fractions import Fraction

from walsh_phase_navigation_probe import (clauses_from_energy_profile,
                                          spectral_coefficients,
                                          conditional_coefficients,
                                          violated_count)
from spectral_receipts import (independent_residual_coefficients,
                               independent_lower_bound, produce_receipt,
                               verify_receipt)


class SpectralReceiptsTests(unittest.TestCase):
    def setUp(self):
        self.sat = clauses_from_energy_profile([0, 1, 1, 2, 1, 2, 2, 1])
        self.unsat = clauses_from_energy_profile([1, 1, 1, 1, 1, 1, 1, 3])

    def test_phase_twins_require_distinct_conclusions(self):
        a = produce_receipt(self.sat, 3)
        b = produce_receipt(self.unsat, 3)
        self.assertEqual(verify_receipt(self.sat, 3, a), 'SAT')
        self.assertEqual(verify_receipt(self.unsat, 3, b), 'UNSAT')
        self.assertNotEqual(a['formula_sha256'], b['formula_sha256'])

    def test_checker_coefficients_independent_from_producer(self):
        rng = random.Random(24011)
        for n in (3, 5, 7):
            for _ in range(50):
                cls = [(tuple(rng.sample(range(n), 3)),
                        tuple(rng.randrange(2) for _ in range(3))) for j in range(2*n + 2)]
                coeff = spectral_coefficients(cls)
                prefix = {}
                for step in range(n + 1):
                    independent = independent_residual_coefficients(cls, prefix)
                    self.assertEqual({k: Fraction(v, 8) for k, v in coeff.items() if v},
                                     {k: v for k, v in independent.items() if v})
                    if step < n:
                        variable = step
                        bit = rng.randrange(2)
                        prefix[variable] = bit
                        coeff = conditional_coefficients(coeff, variable, bit)

    def test_lower_bound_valid_for_all_completions(self):
        rng = random.Random(173)
        for _ in range(75):
            n = 6
            cls = [(tuple(rng.sample(range(n), 3)),
                    tuple(rng.randrange(2) for i in range(3))) for j in range(22)]
            prefix = {0: rng.randrange(2), 3: rng.randrange(2)}
            lb = independent_lower_bound(cls, prefix)
            for a in range(1 << n):
                if any(((a >> v) & 1) != b for v,b in prefix.items()):
                    continue
                self.assertLessEqual(lb, violated_count(cls, a))

    def test_tampering_rejected(self):
        receipt = produce_receipt(self.unsat, 3)
        tests = [copy.deepcopy(receipt) for _ in range(4)]
        tests[0]['result'] = 'SAT'
        tests[1]['formula_sha256'] = '0'*64
        tests[2]['proof'] = {'kind': 'positive_lower_bound', 'bound': [3, 1]}
        tests[3]['proof'] = {'kind': 'sat', 'witness': [0, 0, 0]}
        for item in tests:
            with self.assertRaises(ValueError):
                verify_receipt(self.unsat, 3, item)

    def test_explicit_unknown_on_budget(self):
        receipt = produce_receipt(self.unsat, 3, budget=1)
        self.assertEqual(receipt['result'], 'UNKNOWN')
        self.assertEqual(verify_receipt(self.unsat, 3, receipt), 'UNKNOWN')

    def test_random_finite_sat_unsat_ground_truth(self):
        rng = random.Random(2246)
        counts = {'SAT': 0, 'UNSAT': 0, 'UNKNOWN': 0}
        for n in (5, 6, 7):
            for _ in range(45):
                cls = [(tuple(sorted(rng.sample(range(n), 3))),
                        tuple(rng.randrange(2) for i in range(3))) for j in range(4*n+2)]
                receipt = produce_receipt(cls, n, budget=512)
                actual = 'SAT' if any(violated_count(cls, x) == 0 for x in range(1 << n)) else 'UNSAT'
                self.assertEqual(verify_receipt(cls, n, receipt), receipt['result'])
                if receipt['result'] != 'UNKNOWN':
                    self.assertEqual(receipt['result'], actual)
                counts[receipt['result']] += 1
        print('certificate campaign:', counts)


if __name__ == '__main__':
    unittest.main()