"""SFI-002 selection and heterogeneous exact component-composition tests."""
from __future__ import annotations
import random
import unittest
from morphic_sat import seeded_circuit,encode_function
from self_selecting_sat import choose,realize,choose_composite
from algebraic_ground import planted_dense,random_cubic_tseitin
from frontier_ground import random_3cnf,brute_count


def combined_sources():
    functional,n,_=seeded_circuit(5,gates=56)
    parity,_,_=planted_dense(40,4,22,False)
    merged=functional+[tuple((abs(l)+n)*(1 if l>0 else -1) for l in c) for c in parity]
    return merged,n+40


class MetaInterpreterTests(unittest.TestCase):
    def test_chooser_uses_discovered_nonaffine_structure(self):
        clauses,n,_=seeded_circuit(5,gates=56)
        plan=choose(clauses,n)
        self.assertEqual(plan['selected'],'local-Boolean-functions')
        self.assertEqual(plan['constructive_candidates']['local-Boolean-functions']['registers'],8)
        self.assertGreater(plan['constructive_candidates']['affine-proof-ground']['registers'],40)
        self.assertEqual(realize(plan)['count'],168)

    def test_affine_global_refutation_preferred_to_large_nonaffine_space(self):
        clauses,n,_=random_cubic_tseitin(40)
        plan=choose(clauses,n)
        self.assertEqual(plan['selected'],'affine-proof-ground')
        self.assertEqual(plan['constructive_candidates']['affine-proof-ground']['status'],'refutation')
        self.assertEqual(realize(plan)['status'],'UNSAT')
        self.assertEqual(realize(plan)['checked'],0)

    def test_composition_succeeds_where_both_monolithic_interpreters_refuse(self):
        clauses,n=combined_sources()
        one=choose(clauses,n)
        self.assertEqual(one['selected'],'undetermined')
        parts=choose_composite(clauses,n)
        self.assertEqual(parts['status'],'SAT')
        self.assertEqual(parts['count'],168*16)
        self.assertEqual(parts['component_count'],2)
        self.assertEqual(parts['selected'],['local-Boolean-functions','affine-proof-ground'])
        self.assertTrue(parts['source_factorization_verified'])

    def test_inserting_single_cross_clause_merges_components_and_refuses(self):
        clauses,n=combined_sources()
        plan=choose_composite(clauses+[(1,65)],n)
        self.assertEqual(plan['component_count'],1)
        self.assertEqual(plan['status'],'UNKNOWN')
        self.assertIsNone(plan['count'])

    def test_small_disjoint_mixed_sat_vs_full_reference(self):
        # Four-variable connected nonlinear function and independent XOR
        # relation; count is multiplicative only under disjoint support.
        function=encode_function(3,(1,2),[0,1,1,1])
        parity=encode_function(6,(4,5),[0,1,1,0])
        mixed=function+parity
        ans=choose_composite(mixed,6)
        self.assertEqual(ans['status'],'SAT')
        self.assertEqual(ans['count'],brute_count(mixed,6))
        self.assertGreaterEqual(ans['component_count'],2)

    def test_small_seeded_random_cases_complete_and_exact(self):
        for seed in range(6):
            c=random_3cnf(9,19,seed)
            plan=choose_composite(c,9,maximum_coordinates=512)
            self.assertEqual(plan['count'],brute_count(c,9),seed)

    def test_empty_clause_is_proven_unsat(self):
        r=choose_composite([()],8)
        self.assertEqual(r['status'],'UNSAT')
        self.assertEqual(r['count'],0)


if __name__=='__main__':unittest.main()
