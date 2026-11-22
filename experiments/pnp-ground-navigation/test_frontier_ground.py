"""Independent exhaustive small-state references and negative controls."""
import random
import unittest
from frontier_ground import (brute_count, chain, clause_factor, min_fill_order,
                             random_3cnf, solve, verify_assignment)


class FrontierGroundTests(unittest.TestCase):
    def test_clause_tables(self):
        f = clause_factor((1, -3))
        self.assertEqual(f.scope, (1, 3))
        self.assertEqual(f.values, (1, 1, 0, 1))

    def test_count_and_witness_by_exhaustive_reference(self):
        rng = random.Random(2107)
        for n in range(2, 9):
            for case in range(30):
                cls = []
                for _ in range(2 * n + 3):
                    vs = rng.sample(range(1, n + 1), rng.randint(1, min(3, n)))
                    cls.append(tuple(v if rng.randrange(2) else -v for v in vs))
                count, witness, ledger = solve(cls, n)
                self.assertEqual(count, brute_count(cls, n), (n, case))
                self.assertEqual(witness is not None, count > 0)
                if count:
                    self.assertTrue(verify_assignment(cls, witness))
                self.assertEqual(sorted(ledger['elimination_order']), list(range(1, n + 1)))

    def test_one_bit_observer_local_truth_is_not_global_truth(self):
        cls = [(1, 2), (1, -2), (-1, 2), (-1, -2)]
        self.assertTrue(all(brute_count([c], 2) > 0 for c in cls))
        self.assertEqual(solve(cls, 2)[0], 0)

    def test_chain_96_and_contradiction(self):
        cnt, witness, ledger = solve(chain(96), 96)
        self.assertEqual(cnt, 1)
        self.assertEqual(set(witness.values()), {1})
        self.assertLessEqual(ledger['max_scope'], 2)
        self.assertEqual(solve(chain(96, True), 96)[0], 0)

    def test_no_clauses_free_variables(self):
        self.assertEqual(solve([], 9)[0], 512)

    def test_tautology_and_duplicate_literals(self):
        self.assertEqual(solve([(1, -1), (2, 2)], 2)[0], 2)

    def test_reject_invalid(self):
        for clauses, n in [([()], 2), ([(0,)], 2), ([(3,)], 2), ([(1,)], 0)]:
            with self.assertRaises(ValueError):
                solve(clauses, n)

    def test_seeded_repeatability(self):
        c = random_3cnf(12, 48, 73)
        a = solve(c, 12)
        b = solve(c, 12)
        self.assertEqual(a[0:2], b[0:2])
        self.assertEqual(a[2]['elimination_order'], b[2]['elimination_order'])


if __name__ == '__main__':
    unittest.main()
