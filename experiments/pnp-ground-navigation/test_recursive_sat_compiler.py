"""SFI-003: the already-built SAT machine improves its own construction.

Independent exact source-CNF truth-table checks, meta-proof mutation attacks,
non-regression, constrained budgets, self-application, and cost measurements.
"""
from __future__ import annotations

from copy import deepcopy
import random
import unittest

from morphic_sat import (compile_ground, encode_function, execute, normalize,
                        seeded_circuit, digest)
from morphic_verifier import verify, independent_count, check_partition
from recursive_sat_compiler import refine, audit_refinement
from self_selecting_sat import choose, realize

# Deterministic satisfiable CNF discovered by random instance exploration.
# Its CNF says nothing about a preferred interpreter: four functional
# orientations are present; the original broadest-first greedy choice retains
# one output, while two compatible inferred gates can be jointly selected.
REPAIRABLE=[
    (-5,6),(-4,-5),(-4,6),(-1,-2),(2,-4),(-3,5,-6),(-2,-3,-4),
    (-1,-5,-6),(1,3,6),(2,-4,5),(3,-5,-6),(3,-4,6),(4,5,-6),
    (-1,-4,-5,6),(-1,-2,-4,5),(-1,-2,3,4),(-1,2,4,-5),
    (2,-3,4,6),(2,3,-4,-5),(3,-4,5,6),
]


def reference_count(source, n):
    cnf=normalize(source,n)
    return sum(all(any(bool((x>>(abs(l)-1))&1)==(l>0) for l in c)
                   for c in cnf) for x in range(1<<n))


class RecursiveCompilerTests(unittest.TestCase):
    def test_previous_sat_interpreter_optimizes_its_own_gate_choices(self):
        g0,_=compile_ground(REPAIRABLE,6)
        g,r=refine(REPAIRABLE,6)
        self.assertEqual(len(g0['registers']),5)
        self.assertEqual(len(g['registers']),4)
        self.assertEqual(r['candidate_pool_size'],4)
        self.assertEqual(r['outcome'],'IMPROVED_BY_OWN_SAT_INTERPRETER')
        self.assertTrue(r['candidate_optimum_certified_by_meta_search'])
        self.assertTrue(any(s['status']=='SAT' and 'witness_decimal' in s
                            for s in r['meta_attempts']))
        self.assertTrue(any(s['status']=='UNSAT' for s in r['meta_attempts']))
        self.assertTrue(all(s['meta_ground_digest'] and
                            s['meta_coordinates_checked']>=1 for s in r['meta_attempts']))
        audit=audit_refinement(REPAIRABLE,6,g,r)
        self.assertTrue(audit['candidate_pool_optimum_checked'])
        self.assertEqual(audit['verified_register_reduction'],1)
        self.assertTrue(verify(g)['proven'])
        r0=execute(g0,intent='COUNT',max_coordinates=64,partition_size=16)
        r1=execute(g,intent='COUNT',max_coordinates=64,partition_size=16)
        self.assertEqual(r0['models'],r1['models'])
        self.assertEqual(r1['models'],reference_count(REPAIRABLE,6))
        self.assertEqual(r0['checked'],32)
        self.assertEqual(r1['checked'],16)
        for receipt in r1['partition_receipts']:
            self.assertTrue(check_partition(g,receipt,maximum=64,partition_size=16))

    def test_larger_direct_sat_benchmark_preserves_exact_solution_count(self):
        # Eleven isolated source variables increase BOTH exact search spaces
        # without altering the discovered SAT meta-problem.
        before,_=compile_ground(REPAIRABLE,17)
        after,report=refine(REPAIRABLE,17)
        audit_refinement(REPAIRABLE,17,after,report)
        self.assertEqual(report['baseline_coordinates'],1<<16)
        self.assertEqual(report['refined_coordinates'],1<<15)
        a=execute(before,intent='COUNT',max_coordinates=65536,partition_size=1024)
        b=execute(after,intent='COUNT',max_coordinates=65536,partition_size=1024)
        self.assertEqual(a['models'],5*(1<<11))
        self.assertEqual(b['models'],a['models'])
        self.assertEqual(a['checked'],2*b['checked'])
        self.assertEqual(len(a['partition_receipts']),64)
        self.assertEqual(len(b['partition_receipts']),32)

    def test_96_random_cnfs_preserve_truth_and_no_regression(self):
        r=random.Random(26021)
        for index in range(96):
            n=r.randrange(2,9)
            clauses=[]
            for _ in range(r.randrange(0,23)):
                variables=r.sample(range(1,n+1),r.randrange(1,min(4,n)+1))
                clauses.append(tuple(v if r.randrange(2) else -v for v in variables))
            initial,_=compile_ground(clauses,n)
            improved,report=refine(clauses,n)
            audit=audit_refinement(clauses,n,improved,report)
            self.assertTrue(audit['source_equivalence_verified'],index)
            self.assertLessEqual(len(improved['registers']),len(initial['registers']),index)
            actual=execute(improved,intent='COUNT',max_coordinates=256,partition_size=64)
            self.assertEqual(actual['models'],reference_count(clauses,n),index)
            self.assertEqual(independent_count(improved,max_free=8),actual['models'],index)
            self.assertTrue(verify(improved,max_free=8)['proven'])

    def test_self_refinement_never_assumes_gates_exist(self):
        # Random 3-SAT with no complete local function stays an ordinary
        # Boolean search; optimization alone never proves SAT/UNSAT.
        source=[(1,2,3),(-1,3,4),(2,-3,4)]
        before,_=compile_ground(source,4)
        after,report=refine(source,4)
        self.assertEqual(after,before)
        self.assertEqual(report['outcome'],'PRESERVED_BASELINE')
        self.assertTrue(audit_refinement(source,4,after,report)['non_regression_verified'])

    def test_tight_limits_preserve_baseline_without_claiming_optimality(self):
        for limits in ({'max_gates':3}, {'meta_budget':1},
                       {'max_rounds':1}, {'max_meta_clauses':1},
                       {'candidate_budget':1}):
            before,_=compile_ground(REPAIRABLE,6,max_candidates=limits.get('candidate_budget',4000))
            after,receipt=refine(REPAIRABLE,6,**limits)
            self.assertEqual(after,before,limits)
            self.assertEqual(receipt['outcome'],'PRESERVED_BASELINE',limits)
            self.assertFalse(receipt['candidate_optimum_certified_by_meta_search'],limits)
            self.assertTrue(audit_refinement(REPAIRABLE,6,after,receipt)['non_regression_verified'])

    def test_larger_candidate_pool_refuses_recursive_exploration(self):
        clauses,n,_=seeded_circuit(9,gates=12)
        base,_=compile_ground(clauses,n)
        result,ledger=refine(clauses,n)
        self.assertEqual(result,base)
        self.assertGreater(ledger['candidate_pool_size'],10)
        self.assertFalse(ledger['candidate_optimum_certified_by_meta_search'])
        self.assertEqual(ledger['outcome'],'PRESERVED_BASELINE')
        self.assertTrue(audit_refinement(clauses,n,result,ledger)['source_equivalence_verified'])

    def test_cyclic_or_competing_orientations_are_not_invented_as_free_state(self):
        # Two parity relations on intersecting scopes generate competing gate
        # directions. No selected cycle can enter a verified interpreter.
        c=encode_function(1,(2,3),[0,1,1,0])+\
          encode_function(2,(1,4),[0,1,1,0])
        g,r=refine(c,4)
        self.assertTrue(audit_refinement(c,4,g,r)['source_equivalence_verified'])
        self.assertTrue(verify(g)['proven'])
        self.assertEqual(execute(g,max_coordinates=16,partition_size=16)['models'],reference_count(c,4))

    def test_recomputed_meta_witness_forgery_refused(self):
        g,receipt=refine(REPAIRABLE,6)
        attack=deepcopy(receipt)
        witness=next(x for x in attack['meta_attempts'] if x['status']=='SAT')
        witness['witness_decimal']='0'
        attack['digest']=digest({k:v for k,v in attack.items() if k!='digest'})
        with self.assertRaises(ValueError):audit_refinement(REPAIRABLE,6,g,attack)

    def test_recomputed_meta_unsat_forgery_refused(self):
        g,receipt=refine(REPAIRABLE,6)
        attack=deepcopy(receipt)
        witness=next(x for x in attack['meta_attempts'] if x['status']=='SAT')
        witness['status']='UNSAT'
        witness.pop('witness_decimal')
        attack['digest']=digest({k:v for k,v in attack.items() if k!='digest'})
        with self.assertRaises(ValueError):audit_refinement(REPAIRABLE,6,g,attack)

    def test_recomputed_optimality_forgery_refused(self):
        g,receipt=refine(REPAIRABLE,6)
        attack=deepcopy(receipt)
        attack['baseline_registers']-=1
        attack['digest']=digest({k:v for k,v in attack.items() if k!='digest'})
        with self.assertRaises(ValueError):audit_refinement(REPAIRABLE,6,g,attack)

    def test_recomputed_source_or_gate_forgery_refused(self):
        g,receipt=refine(REPAIRABLE,6)
        for mode in ('source','table'):
            copy_g=deepcopy(g);copy_r=deepcopy(receipt)
            if mode=='source':
                wrong=[(1,),*REPAIRABLE]
                with self.assertRaises(ValueError):audit_refinement(wrong,6,copy_g,copy_r)
            else:
                copy_g['instructions'][0]['table'][0]^=1
                copy_g['digest']=digest({k:v for k,v in copy_g.items() if k!='digest'})
                copy_r['refined_ground_sha256']=copy_g['digest']
                copy_r['digest']=digest({k:v for k,v in copy_r.items() if k!='digest'})
                with self.assertRaises(ValueError):audit_refinement(REPAIRABLE,6,copy_g,copy_r)


    def test_previous_sfi002_selector_can_opt_in_without_changing_default(self):
        previous=choose(REPAIRABLE,6,maximum_coordinates=64,resolution_attempts=1000)
        upgraded=choose(REPAIRABLE,6,maximum_coordinates=64,
                        resolution_attempts=1000,self_refine=True)
        self.assertNotIn('self_refinement',previous)
        self.assertEqual(previous['constructive_candidates']['local-Boolean-functions']['registers'],5)
        self.assertEqual(upgraded['constructive_candidates']['local-Boolean-functions']['registers'],4)
        self.assertEqual(upgraded['self_refinement']['outcome'],
                         'IMPROVED_BY_OWN_SAT_INTERPRETER')
        self.assertEqual(realize(previous)['count'],realize(upgraded)['count'])
        self.assertEqual(realize(upgraded)['count'],5)
        with self.assertRaises(ValueError):
            choose(REPAIRABLE,6,self_refine='yes')

    def test_self_application_has_no_implicit_unbounded_recursion(self):
        g,r=refine(REPAIRABLE,6,max_rounds=3)
        self.assertLessEqual(len(r['meta_attempts']),3)
        self.assertTrue(audit_refinement(REPAIRABLE,6,g,r)['source_equivalence_verified'])
        for override in ({'max_gates':11},{'meta_budget':1025},{'max_rounds':33},
                         {'candidate_budget':0},{'max_meta_clauses':0}):
            with self.assertRaises(ValueError):refine(REPAIRABLE,6,**override)

if __name__=='__main__': unittest.main()
