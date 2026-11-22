"""SPN-009: direct SAT/#SAT language selection with independent truth references."""
import copy
import random
import unittest

from direct_sat_compiler import check_assignment
from language_choice_sat import (compile_language, verify_language_receipt,
    _frontier_independent_count, _projected_factor_cost, _all_xor_count,
    _sfi_available)
from test_direct_sat_compiler import encode_xor_equations, parity_cycle_family
from test_direct_sum_grounds import shared_variable_cycle_cnf


def from_spectral(clauses):
    """Recover original CNF from the SPN forbidden-assignment encoding."""
    return [tuple(v+1 if b==0 else -(v+1) for v,b in zip(scope,bits))
            for scope,bits in clauses]


def brute_count(clauses,n):
    return sum(check_assignment(clauses,[(a>>i)&1 for i in range(n)])
               for a in range(1<<n))


class LanguageSelectionTests(unittest.TestCase):
    def test_random_small_direct_sat_and_exact_counts(self):
        rng=random.Random(9009)
        for n in range(3,9):
            for k in range(25):
                clauses=[]
                for j in range(2*n+5):
                    scope=rng.sample(range(1,n+1),rng.randint(1,3))
                    clauses.append(tuple(v if rng.randrange(2) else -v for v in scope))
                count=brute_count(clauses,n)
                decision=compile_language(clauses,n,goal='decision',node_budget=1024)
                exact=compile_language(clauses,n,goal='count',frontier_cell_cap=100000)
                self.assertEqual(decision['result'],'SAT' if count else 'UNSAT',(n,k))
                self.assertEqual(exact['result'],str(count),(n,k))
                self.assertEqual(verify_language_receipt(clauses,n,decision),decision['result'])
                self.assertEqual(verify_language_receipt(clauses,n,exact),str(count))

    def test_ordinary_and_parity_inconsistent_cases(self):
        clauses=[(1,2),(1,-2),(-1,2),(-1,-2)]
        self.assertEqual(compile_language(clauses,2,goal='decision')['result'],'UNSAT')
        self.assertEqual(compile_language(clauses,2,goal='count')['result'],'0')
        clauses,n=parity_cycle_family(6,True)
        for goal in ('decision','count'):
            r=compile_language(clauses,n,goal=goal)
            self.assertEqual(r['language'],'source_xor')
            self.assertEqual(r['result'],'UNSAT' if goal=='decision' else '0')
            self.assertEqual(verify_language_receipt(clauses,n,r),r['result'])
        clauses,n=parity_cycle_family(4,False)
        r=compile_language(clauses,n,goal='count')
        self.assertEqual(r['language'],'source_xor')
        self.assertGreater(int(r['result']),0)
        self.assertEqual(verify_language_receipt(clauses,n,r),r['result'])

    def test_rank_two_ground_and_large_formula(self):
        for count in (4,8,24,64):
            clauses,n=shared_variable_cycle_cnf(count,frustrated=True)
            clauses=from_spectral(clauses)
            r=compile_language(clauses,n,goal='count',rank_cap=2)
            self.assertEqual(r['language'],'spectral_direct_sum')
            self.assertEqual(r['result'],'0')
            self.assertEqual(verify_language_receipt(clauses,n,r),'0')
            if count>=24:
                d=compile_language(clauses,n,goal='decision',rank_cap=2)
                self.assertEqual(d['result'],'UNSAT')
                self.assertEqual(d['language'],'source_dpll_pilot')
        clauses,n=shared_variable_cycle_cnf(32,frustrated=False)
        clauses=from_spectral(clauses)
        r=compile_language(clauses,n,goal='count',rank_cap=2)
        self.assertEqual(r['result'],'4')
        self.assertEqual(verify_language_receipt(clauses,n,r),'4')

    def test_refusal_budget_safely_unknown(self):
        rng=random.Random(12122)
        n=14
        clauses=[tuple(v if rng.randrange(2) else -v
                        for v in rng.sample(range(1,n+1),3)) for _ in range(64)]
        # Force the expensive exact-count route to refuse rather than declaring UNSAT.
        r=compile_language(clauses,n,goal='count',rank_cap=1,
                           frontier_cell_cap=10,allow_sfi=False)
        self.assertEqual(r['result'],'UNKNOWN')
        self.assertEqual(verify_language_receipt(clauses,n,r),'UNKNOWN')

    def test_empty_clauses_and_free_variables(self):
        for cls,n,count in [([()],3,0),([],9,512),([(1,-1)],4,16)]:
            r=compile_language(cls,n,goal='count')
            self.assertEqual(r['result'],str(count))
            self.assertEqual(verify_language_receipt(cls,n,r),str(count))

    def test_tamper_source_count_witness_and_obligation(self):
        source,n=shared_variable_cycle_cnf(4,True)
        source=from_spectral(source)
        original=compile_language(source,n,goal='count',rank_cap=2)
        def expect_bad(change):
            altered=copy.deepcopy(original)
            change(altered)
            with self.assertRaises(ValueError):
                verify_language_receipt(source,n,altered)
        expect_bad(lambda r:r.update(source_sha256='b'*64))
        expect_bad(lambda r:r.update(result='1000'))
        expect_bad(lambda r:r['proof'].update(count='500'))
        expect_bad(lambda r:r['proof']['receipt'].update(ground_energy=[0,1]))
        # Costs are observations; forged timing must not change the theorem.
        altered=copy.deepcopy(original)
        altered['cost_ledger']={'total_ms':-10}
        self.assertEqual(verify_language_receipt(source,n,altered),'0')
        source=[(1,2),(1,-2),(-1,2)]
        r=compile_language(source,2,goal='count')
        if r['proof']['kind']=='frontier_replay':
            bad=copy.deepcopy(r)
            bad['proof']['witness']=[0,0]
            with self.assertRaises(ValueError):verify_language_receipt(source,2,bad)

    def test_frontier_checker_count_independent_from_producer(self):
        rng=random.Random(49)
        for n in range(2,9):
            for case in range(10):
                clauses=[tuple(v if rng.randrange(2) else -v
                  for v in rng.sample(range(1,n+1),rng.randint(1,min(3,n))))
                  for _ in range(n*2)]
                self.assertEqual(_frontier_independent_count(clauses,n,100000),
                                 brute_count(clauses,n))
                costs=_projected_factor_cost(clauses,n)
                self.assertLessEqual(costs['max_scope'],n-1)

    def test_formed_sfi_count_when_sibling_modules_are_present(self):
        if _sfi_available() is None:
            self.skipTest('SFI-001 source modules not mounted in local staging')
        # Two guarded clauses for the exact x1 == x2 relation; g remains free.
        clauses=[(1,-2,3),(1,-2,-3),(-1,2,3),(-1,2,-3)]
        r=compile_language(clauses,3,goal='count',rank_cap=1,
                           allow_sfi=True,frontier_cell_cap=100000,spectral_state_cap=1)
        self.assertEqual(r['result'],'4')
        self.assertEqual(verify_language_receipt(clauses,3,r),'4')
        # The formed proof also needs to survive JSON transport without
        # Python tuple/list identity becoming part of its mathematics.
        self.assertEqual(verify_language_receipt(clauses,3,
            __import__('json').loads(__import__('json').dumps(r))),'4')
        self.assertIn(r['language'],('source_formed_interpreter','factor_frontier'))
        if r['language']=='source_formed_interpreter':
            forged=copy.deepcopy(r)
            forged['proof']['parts'][0]['models']+=1
            with self.assertRaises(ValueError):verify_language_receipt(clauses,3,forged)

    def test_invalid_goal_and_no_false_certificate(self):
        with self.assertRaises(ValueError):compile_language([(1,)],1,goal='optimistic')
        with self.assertRaises(ValueError):compile_language([(1,)],1,frontier_cell_cap=0)
        src=[(1,2),(1,-2)]
        r=compile_language(src,2,goal='decision')
        spoof=copy.deepcopy(r)
        spoof['goal']='count';spoof['result']='1'
        with self.assertRaises(ValueError):verify_language_receipt(src,1,spoof)

if __name__=='__main__':unittest.main()
