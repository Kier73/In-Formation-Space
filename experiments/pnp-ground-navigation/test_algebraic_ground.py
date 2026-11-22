"""PNG-002 independent differential, adversarial, and refusal tests."""
import copy
import random
import unittest

from algebraic_ground import (
    compile_ground, decode, eliminate, encode_xor, frontier_estimate, parity_formula,
    planted_dense, random_cubic_tseitin, solve, verify_compilation, verify_refutation,
)
from ground_verifier import check, digest_ground, digest_source


def exhaustive_count(clauses, n):
    # Independent truth-table reference, not imported from either solver.
    return sum(all(any(((bits >> (abs(lit)-1)) & 1) == (lit > 0)
                       for lit in clause) for clause in clauses)
               for bits in range(1 << n))


class AlgebraicGroundTests(unittest.TestCase):
    def test_equation_encoding_exact_for_all_arity_up_to_4(self):
        for k in range(1, 5):
            for rhs in (0, 1):
                mask = (1 << k) - 1
                clauses = encode_xor(mask, rhs)
                self.assertEqual(len(clauses), 1 << (k-1))
                for z in range(1 << k):
                    allowed = all(any(((z >> (abs(lit)-1)) & 1) == (lit > 0)
                                      for lit in clause) for clause in clauses)
                    self.assertEqual(allowed, z.bit_count() % 2 == rhs)

    def test_compiler_is_lossless_and_detects_all_complete_parity_blocks(self):
        clauses = parity_formula(6, [(0b00111, 1), (0b111000, 0)])
        # Unrelated extra constraint remains; a duplicate is semantically inert.
        clauses.extend([(-1, 4), (-1, 4)])
        g = compile_ground(clauses, 6)
        self.assertEqual(len(g['equations']), 2)
        self.assertEqual(g['residual'], [(-1, 4)])
        self.assertTrue(verify_compilation(clauses, 6, g))
        tampered = copy.deepcopy(g)
        tampered['equations'][0] = (tampered['equations'][0][0], 1-tampered['equations'][0][1])
        self.assertFalse(verify_compilation(clauses, 6, tampered))

    def test_randomized_mixed_formula_exact_counts_against_brute(self):
        rng = random.Random(200200)
        for n in range(2, 10):
            for trial in range(35):
                equations = []
                for _ in range(rng.randrange(1, n+2)):
                    size = rng.randint(1, min(n,4))
                    scope = rng.sample(range(n), size)
                    equations.append((sum(1 << v for v in scope), rng.randrange(2)))
                clauses = parity_formula(n, equations)
                for _ in range(rng.randint(0,n)):
                    size = rng.randint(1,min(n,4))
                    vs = rng.sample(range(1,n+1),size)
                    clauses.append(tuple(v if rng.randrange(2) else -v for v in vs))
                if rng.randrange(5)==0:
                    clauses.append((1,-1))
                result, g = solve(clauses,n,node_budget=30000)
                self.assertNotEqual(result['status'], 'undetermined', (n, trial))
                self.assertTrue(verify_compilation(clauses,n,g))
                self.assertEqual(result['count'], exhaustive_count(clauses,n), (n,trial))
                verified = check(clauses,n,g,result,max_enumerated_free=9)
                self.assertTrue(verified['count_verified'], (n,trial))

    def test_large_dense_planted_exact_count_and_independent_verifier(self):
        clauses, planted, equations = planted_dense(96,8,22)
        self.assertEqual(len(equations), 88)
        result, g = solve(clauses,96)
        self.assertEqual((result['method'],result['count']),('affine-rank',256))
        self.assertEqual((result['ledger']['rank'],result['ledger']['free_dimension']),(88,8))
        self.assertTrue(check(clauses,96,g,result)['count_verified'])
        estimate = frontier_estimate(clauses,96)
        self.assertGreater(estimate['width'],25)
        self.assertGreater(estimate['projected_entries'], 10**9)

    def test_large_mixed_residual_accurate_count(self):
        clauses, planted, equations = planted_dense(96,8,22,True)
        result, g = solve(clauses,96)
        self.assertEqual(result['method'],'affine-reduced-search')
        self.assertEqual(result['count'], 176)
        self.assertEqual(len(g['residual']),3)
        self.assertTrue(check(clauses,96,g,result)['count_verified'])

    def test_global_parity_refutation_independent(self):
        clauses, n, equations = random_cubic_tseitin(80,7301)
        self.assertEqual((n,len(equations)), (120,80))
        result,g = solve(clauses,n)
        self.assertEqual(result['status'],'unsat')
        self.assertEqual(result['method'],'gf2-refutation')
        self.assertEqual(result['ledger']['rank'], 79)
        self.assertEqual(len(result['refutation_equation_indices']),80)
        indices = result['refutation_equation_indices']
        self.assertTrue(verify_refutation(g['equations'],sum(1<<i for i in indices),n))
        check_report = check(clauses,n,g,result)
        self.assertTrue(check_report['refutation_verified'])
        self.assertTrue(check_report['decision_verified'])
        # Individually each lifted local constraint admits satisfying rows.
        self.assertTrue(all(exhaustive_count(encode_xor(mask,rhs),mask.bit_length())>0
                            for mask,rhs in equations[:5]))

    def test_incomplete_parity_is_not_promoted(self):
        clauses = parity_formula(8, [(15,1)])[:-1]
        result,g=solve(clauses,8)
        self.assertEqual(g['equations'],[])
        self.assertEqual(result['count'],144)
        self.assertEqual(result['count'],exhaustive_count(clauses,8))
        self.assertTrue(check(clauses,8,g,result)['count_verified'])

    def test_empty_clause_and_pure_free_variables(self):
        r,g=solve([()],10)
        self.assertEqual((r['status'],r['method'],r['count']),('unsat','empty-clause',0))
        self.assertTrue(check([()],10,g,r)['count_verified'])
        r,g=solve([],70)
        self.assertEqual((r['method'],r['count']),('affine-rank',1<<70))
        self.assertTrue(check([],70,g,r)['count_verified'])

    def test_safe_refusal_does_not_claim_unsat(self):
        rng=random.Random(101)
        clauses=[]
        for _ in range(190):
            vs=rng.sample(range(1,36),3)
            clauses.append(tuple(v if rng.getrandbits(1) else -v for v in vs))
        r,g=solve(clauses,35,free_budget=5,frontier_entry_budget=100)
        self.assertEqual((r['status'],r['method'],r['count']),
                         ('undetermined','budget-refusal',None))
        self.assertFalse(check(clauses,35,g,r)['decision_verified'])
        # Forced budget refusal within an otherwise exactly compilable hybrid.
        clauses,_,_=planted_dense(50,10,3,True)
        r,g=solve(clauses,50,node_budget=1)
        self.assertEqual(r['status'],'undetermined')
        self.assertIsNone(r['count'])

    def test_narrow_nonaffine_ordinary_frontier_fallback(self):
        clauses=[(1,i,i+1) for i in range(2,25)]
        r,g=solve(clauses,25,free_budget=4)
        self.assertEqual(r['method'],'ordinary-frontier')
        self.assertEqual(r['status'],'sat')
        self.assertTrue(check(clauses,25,g,r)['decision_verified'])

    def test_hybrid_no_false_fallback_when_free_budget_exceeded(self):
        clauses=parity_formula(30,[(3,0)])+[(3,4,5)]
        r,g=solve(clauses,30,free_budget=0,frontier_entry_budget=100000)
        self.assertEqual((r['status'],r['method']),('undetermined','unsupported-hybrid-refusal'))

    def test_tamper_proof_source_count_and_witness_are_detected(self):
        clauses,_,_=planted_dense(24,4,22,True)
        r,g=solve(clauses,24)
        self.assertTrue(check(clauses,24,g,r)['count_verified'])
        source_hash=digest_source(clauses,24)
        ground_hash=digest_ground(g)
        self.assertTrue(check(clauses,24,g,r,source_digest=source_hash,
                              ground_digest=ground_hash)['count_verified'])
        with self.assertRaises(ValueError):
            check(clauses+[(-1,)],24,g,r)
        with self.assertRaises(ValueError):
            check(clauses,24,g,r,source_digest='0'*64)
        with self.assertRaises(ValueError):
            check(clauses,24,g,r,ground_digest='0'*64)
        forged=copy.deepcopy(r)
        forged['count']+=1
        with self.assertRaises(ValueError):
            check(clauses,24,g,forged)
        forged=copy.deepcopy(r)
        forged['witness']={i:0 for i in range(1,25)}
        with self.assertRaises(ValueError):
            check(clauses,24,g,forged)
        clauses,n,_=random_cubic_tseitin(20,3)
        r,g=solve(clauses,n)
        forged=copy.deepcopy(r)
        forged['refutation_equation_indices']=[0]
        with self.assertRaises(ValueError):
            check(clauses,n,g,forged)

    def test_invalid_literals_rejected(self):
        for clauses,n in [([(0,)],3), ([(4,)],3), ([()],0), ([(True,)],3)]:
            with self.assertRaises(ValueError):
                solve(clauses,n)


if __name__=='__main__':
    unittest.main()
