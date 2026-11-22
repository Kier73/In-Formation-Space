"""SPN-005: exact nonlocal four-circuit grounds, receipt negative controls."""
from __future__ import annotations

import copy
from fractions import Fraction
from random import Random
import unittest

from nonlocal_rank_grounds import (nonlocal_four_circuits,
    nonlocal_rank_bound, parity_cycle_cnf, produce_nonlocal_receipt,
    verify_nonlocal_receipt)
from rank_block_bounds import (rank_block_bound,
    independent_rank_block_bound, produce_rank_receipt)
from spectral_receipts import direct_energy
from walsh_phase_navigation_probe import (spectral_coefficients,
    conditional_coefficients, violated_count)


class NonlocalRankGroundTests(unittest.TestCase):
    def test_four_cycle_exact_nonlocal_certificate(self):
        clauses, n = parity_cycle_cnf(1)
        self.assertEqual((n, len(clauses)), (5, 16))
        coeff = spectral_coefficients(clauses)
        terms = [s for s, a in coeff.items() if s and a]
        self.assertEqual(len(terms), 4)
        self.assertEqual(set(abs(coeff[s]) for s in terms), {4})
        self.assertEqual(coeff[0], 16)
        self.assertEqual(terms[0] ^ terms[1] ^ terms[2] ^ terms[3], 0)
        self.assertLess(sum(1 << i for i in range(n) if any(s & (1 << i) for s in terms)).bit_count(), 5)
        self.assertEqual(min(violated_count(clauses, x) for x in range(1 << n)), 1)
        old, _ = rank_block_bound(coeff, clauses)
        self.assertEqual(old, 0)
        new, blocks, ledger = nonlocal_rank_bound(coeff, clauses)
        self.assertEqual((new, len(blocks)), (8, 1))
        self.assertEqual(ledger['pairs_examined'], 6)
        self.assertEqual(independent_rank_block_bound(clauses, {}, [list(b) for b in blocks], 3), Fraction(1))
        old_receipt = produce_rank_receipt(clauses, n)
        new_receipt = produce_nonlocal_receipt(clauses, n)
        self.assertEqual(old_receipt['producer_nodes_visited'], 7)
        self.assertEqual(new_receipt['producer_nodes_visited'], 1)
        self.assertEqual(verify_nonlocal_receipt(clauses, n, new_receipt), 'UNSAT')

    def test_strided_nonlocal_cycles_wide_variable_span(self):
        clauses, n = parity_cycle_cnf(24, span_layout=True)
        self.assertEqual((n, len(clauses)), (120, 384))
        coeff = spectral_coefficients(clauses)
        new, blocks, ledger = nonlocal_rank_bound(coeff, clauses)
        self.assertEqual((new, len(blocks)), (24*8, 24))
        self.assertEqual(ledger['block_minima_evaluated'], 24)
        self.assertEqual(ledger['total_possible_pairs'], 4560)
        # Pair supports in every certificate extend across 4 variable strata.
        self.assertTrue(all(len({v for s in block for v in range(n) if s & (1 << v)}) == 4
                            for block in blocks))
        receipt = produce_nonlocal_receipt(clauses, n)
        self.assertEqual(receipt['producer_nodes_visited'], 1)
        self.assertEqual(receipt['proof']['bound'], [24, 1])
        self.assertEqual(verify_nonlocal_receipt(clauses, n, receipt), 'UNSAT')

    def test_pair_discovery_budgets_refuse_to_invent_conclusions(self):
        clauses, n = parity_cycle_cnf(1)
        coeff = spectral_coefficients(clauses)
        candidates, metrics = nonlocal_four_circuits(coeff, pair_budget=0)
        self.assertEqual(candidates, [])
        self.assertTrue(metrics['discovery_truncated'])
        lower, blocks, _ = nonlocal_rank_bound(coeff, clauses, pair_budget=0)
        self.assertEqual(lower, 0)
        receipt = produce_nonlocal_receipt(clauses, n, budget=1, pair_budget=0)
        self.assertEqual(receipt['result'], 'UNKNOWN')
        self.assertEqual(verify_nonlocal_receipt(clauses, n, receipt), 'UNKNOWN')
        for args in ({'pair_budget':-1},{'candidate_budget':-1},{'bucket_limit':0}):
            with self.assertRaises(ValueError):
                nonlocal_four_circuits(coeff, **args)

    def test_independent_reconstruction_rejects_tampering(self):
        clauses, n = parity_cycle_cnf(1)
        receipt = produce_nonlocal_receipt(clauses, n)
        for change in ('source','version','bound','missing','reused','zero','rank','fake_sat'):
            forged = copy.deepcopy(receipt)
            if change == 'source':
                forged['formula_sha256'] = '0'*64
            elif change == 'version':
                forged['version'] = 'SPN-004-v1'
            elif change == 'bound':
                forged['proof']['bound'] = [2, 1]
            elif change == 'missing':
                forged['proof']['blocks'][0][0] = (1 << n)
            elif change == 'reused':
                forged['proof']['blocks'].append(forged['proof']['blocks'][0])
            elif change == 'zero':
                forged['proof']['blocks'][0][0] = 0
            elif change == 'rank':
                forged['rank_cap'] = 4
            else:
                forged['proof'] = {'kind': 'sat', 'witness': [0]*n}
                forged['result'] = 'SAT'
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_nonlocal_receipt(clauses, n, forged)

    def test_exhaustive_soundness_of_random_subproblems(self):
        rng = Random(731805)
        for n in range(3, 9):
            for k in range(20):
                clauses = []
                for _ in range(4*n+3):
                    vs = tuple(sorted(rng.sample(range(n), 3)))
                    forb = tuple(rng.randrange(2) for _ in range(3))
                    clauses.append((vs, forb))
                prefix = {v:rng.randrange(2) for v in range(n) if rng.randrange(4)==0}
                coeff = spectral_coefficients(clauses)
                for v,bit in prefix.items():
                    coeff = conditional_coefficients(coeff, v, bit)
                old, _ = rank_block_bound(coeff, clauses)
                new, blocks, _ = nonlocal_rank_bound(coeff, clauses)
                self.assertGreaterEqual(new, old)
                checked = independent_rank_block_bound(clauses, prefix,
                                      [list(b) for b in blocks], 3)
                self.assertEqual(checked, Fraction(new, 8))
                exact = min(violated_count(clauses,x) for x in range(1 << n)
                            if all((x >> v) & 1 == bit for v,bit in prefix.items()))
                self.assertLessEqual(checked, exact)

    def test_random_receipts_against_exhaustive_reference(self):
        rng = Random(731806)
        for n in (5,6,7,8):
            for _ in range(15):
                clauses = [(tuple(sorted(rng.sample(range(n), 3))),
                            tuple(rng.randrange(2) for _ in range(3)))
                           for _ in range(4*n+4)]
                answer = 'SAT' if any(violated_count(clauses,x)==0
                                      for x in range(1 << n)) else 'UNSAT'
                receipt = produce_nonlocal_receipt(clauses,n,budget=256)
                self.assertEqual(receipt['result'], answer)
                self.assertEqual(verify_nonlocal_receipt(clauses,n,receipt),answer)

    def test_term_reuse_is_rejected_even_if_blocks_overlap_only_in_variables(self):
        clauses, n = parity_cycle_cnf(2)
        receipt = produce_nonlocal_receipt(clauses, n)
        self.assertEqual(len(receipt['proof']['blocks']), 2)
        self.assertEqual(verify_nonlocal_receipt(clauses,n,receipt), 'UNSAT')
        forged = copy.deepcopy(receipt)
        forged['proof']['blocks'][1] = forged['proof']['blocks'][0]
        with self.assertRaises(ValueError):
            verify_nonlocal_receipt(clauses,n,forged)


if __name__ == '__main__':
    unittest.main()
