"""PNG-003 randomized and adversarial checks for proof-carrying CNF inference."""
import copy
import random
import unittest

from algebraic_ground import compile_ground, encode_xor, planted_dense, random_cubic_tseitin
from derived_ground import (compile_proven_ground, implication_equalities,
                            split_guard)
from derived_verifier import verify_receipt
from frontier_ground import brute_count, random_3cnf


class NonlocalGroundTests(unittest.TestCase):
    def test_guarded_pure_96_discovery_and_exact_count(self):
        src, _, _ = planted_dense(96, 8, 22)
        guarded = split_guard(split_guard(src, guard_id=97), guard_id=98)
        self.assertEqual(len(compile_ground(guarded, 98)['equations']), 0)
        r = compile_proven_ground(guarded, 98)
        self.assertEqual(r['result']['status'], 'sat')
        self.assertEqual(r['result']['count'], 1024)
        self.assertEqual(len(r['base_equations']), 88)
        self.assertEqual(r['compilation_ledger']['contraction']['contractions'], 2112)
        self.assertTrue(verify_receipt(r)['count_verified'])

    def test_guarded_mixed_96_exact_count(self):
        src, _, _ = planted_dense(96, 8, 22, True)
        masked = split_guard(split_guard(src, guard_id=97), guard_id=98)
        self.assertEqual(len(compile_ground(masked, 98)['equations']), 0)
        r = compile_proven_ground(masked, 98)
        self.assertEqual(r['result']['count'], 704)
        self.assertEqual(len(r['base_residual']), 3)
        self.assertTrue(verify_receipt(r)['count_verified'])

    def test_guarded_global_unsat_independent(self):
        clauses, n, _ = random_cubic_tseitin(80, 7301)
        r = compile_proven_ground(split_guard(clauses, guard_id=n+1), n+1)
        self.assertEqual(r['result']['status'], 'unsat')
        self.assertEqual(r['result']['method'], 'gf2-refutation')
        rep = verify_receipt(r)
        self.assertTrue(rep['refutation_verified'])
        self.assertTrue(rep['count_verified'])

    def test_non_twin_implication_chain_produces_nonlocal_equations(self):
        clauses, n = implication_equalities(12)
        self.assertEqual(len(compile_ground(clauses,n)['equations']),0)
        r = compile_proven_ground(clauses,n)
        self.assertEqual(len(r['contract_steps']),0)
        self.assertEqual(len(r['base_equations']),0)
        self.assertEqual(r['result']['count'],2)
        self.assertEqual(r['result']['ledger']['free_dimension'],1)
        self.assertGreaterEqual(len(r['learned_equations']), n-1)
        self.assertGreater(len(r['resolution_steps']), 0)
        self.assertTrue(verify_receipt(r)['count_verified'])

    def test_nonlocal_resolution_unsat_certificate(self):
        clauses,n=implication_equalities(5)
        clauses += [(1,),(-5,)]
        r=compile_proven_ground(clauses,n)
        self.assertTrue(r['resolution_empty'])
        self.assertEqual(r['result']['count'],0)
        self.assertTrue(verify_receipt(r)['count_verified'])

    def test_missing_guard_copy_proves_no_false_parity(self):
        full = split_guard(encode_xor(0b1111,1),guard_id=5)
        damaged = full[:-1]
        r=compile_proven_ground(damaged,5)
        self.assertFalse(r['base_equations'])
        self.assertFalse(r['learned_equations'])
        self.assertEqual(r['result']['count'],17)
        self.assertEqual(brute_count(damaged,5),17)
        self.assertTrue(verify_receipt(r)['count_verified'])

    def test_140_seeded_small_formula_differential_checks(self):
        rng=random.Random(3107)
        for n in range(2,9):
            for case in range(20):
                clauses=[]
                for _ in range(rng.randrange(2, 2*n+4)):
                    k=rng.randint(1,min(3,n))
                    vs=rng.sample(range(1,n+1),k)
                    clauses.append(tuple(v if rng.randrange(2) else -v for v in vs))
                r=compile_proven_ground(clauses,n)
                self.assertEqual(r['result']['count'],brute_count(clauses,n),(n,case))
                self.assertTrue(verify_receipt(r)['count_verified'],(n,case))

    def test_30_seeded_guarded_xor_differential_checks(self):
        rng=random.Random(1553)
        for trial in range(30):
            n=rng.randrange(3,8)
            clauses=[]
            for _ in range(rng.randrange(1,5)):
                k=rng.randint(2,min(4,n))
                scope=rng.sample(range(n),k)
                mask=sum(1<<i for i in scope)
                clauses.extend(encode_xor(mask,rng.randrange(2)))
            guarded = split_guard(clauses,guard_id=n+1)
            r=compile_proven_ground(guarded,n+1)
            self.assertEqual(r['result']['count'],brute_count(guarded,n+1),trial)
            self.assertTrue(verify_receipt(r)['count_verified'],trial)

    def test_invalid_consensus_proof_rejected(self):
        src=split_guard(encode_xor(0b111,0),guard_id=4)
        original=compile_proven_ground(src,4)
        self.assertTrue(verify_receipt(original)['count_verified'])
        variants=[]
        forged=copy.deepcopy(original)
        forged['contract_steps'][0]['child']=[1,2,3,4]
        variants.append(forged)
        forged=copy.deepcopy(original)
        forged['contract_steps'][0]['negative']=forged['contract_steps'][0]['positive']
        variants.append(forged)
        forged=copy.deepcopy(original)
        forged['contract_steps']=forged['contract_steps'][:-1]
        variants.append(forged)
        for f in variants:
            with self.assertRaises((ValueError,KeyError)):
                verify_receipt(f)

    def test_invalid_resolution_proof_rejected(self):
        src,n=implication_equalities(6)
        original=compile_proven_ground(src,n)
        self.assertGreater(len(original['resolution_steps']),0)
        forged=copy.deepcopy(original)
        forged['resolution_steps'][0]['child']=[1,2,3]
        with self.assertRaises(ValueError):
            verify_receipt(forged)
        forged=copy.deepcopy(original)
        forged['resolution_steps']=forged['resolution_steps'][:-1]
        with self.assertRaises(ValueError):
            verify_receipt(forged)
        forged=copy.deepcopy(original)
        mask, rhs = forged['learned_equations'][0]
        forged['learned_equations'][0] = (mask, 1-rhs)
        with self.assertRaises((ValueError,TypeError)):
            verify_receipt(forged)

    def test_forged_count_and_source_rejected(self):
        src,n=implication_equalities(5)
        original=compile_proven_ground(src,n)
        forged=copy.deepcopy(original)
        forged['result']['count']=123
        with self.assertRaises(ValueError):
            verify_receipt(forged)
        forged=copy.deepcopy(original)
        forged['original_clauses'].append((1,))
        with self.assertRaises(ValueError):
            verify_receipt(forged)

    def test_resolution_budget_and_complexity_refusal(self):
        src,n=implication_equalities(8)
        r=compile_proven_ground(src,n,max_resolution_attempts=1)
        self.assertTrue(r['compilation_ledger']['resolution']['cutoff'])
        # Even partial resolution closure may prove some clauses.
        # A cutoff must never grant unproved equations.
        self.assertLessEqual(r['compilation_ledger']['resolution']['attempts'], 2)
        self.assertTrue(verify_receipt(r)['count_verified'])
        hard=random_3cnf(35,140,73)
        r=compile_proven_ground(hard,35,max_resolution_attempts=1)
        self.assertEqual(r['result']['status'],'undetermined')
        self.assertIsNone(r['result']['count'])
        self.assertFalse(verify_receipt(r)['count_verified'])

    def test_consensus_budget_still_exact(self):
        src=split_guard(encode_xor(0b1111,1),guard_id=5)
        r=compile_proven_ground(src,5,max_contracts=1)
        self.assertTrue(r['compilation_ledger']['contraction']['cutoff'])
        self.assertEqual(r['result']['count'],16)
        self.assertTrue(verify_receipt(r)['count_verified'])


if __name__=='__main__':
    unittest.main()
