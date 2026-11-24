"""CIG-006 source-native SAT/#SAT hard-problem controls and forged receipts."""
from __future__ import annotations
import copy, unittest
from heavy_campaign import xor_chain,gates_80,pigeonhole,odd_wheel,random_3sat,unsat_disjoint_k4
from heavy_ground import normalize,compile_ground,accepts,dpll,xor_encoding
from verify_heavy_ground import verify,Reject

class HeavyTests(unittest.TestCase):
    def test_large_exact_parity_count(self):
        n,source,intent=xor_chain(192)
        c,_=compile_ground(source,n,intent=intent)
        self.assertEqual(c['chosen_family'],'exact-source-XOR-GF2')
        self.assertEqual(c['result']['count'],'4')
        self.assertTrue(verify(source,n,c,expected_intention='#SAT'))

    def test_large_gf2_unsat_source_proof(self):
        n,source,intent=xor_chain(192,True)
        c,_=compile_ground(source,n,intent=intent)
        self.assertEqual(c['result']['status'],'UNSAT')
        self.assertTrue(verify(source,n,c,expected_intention='SAT'))
        changed=copy.deepcopy(c)
        changed['evidence']['contradiction_sources']=[0]
        with self.assertRaises(Reject):verify(source,n,changed)

    def test_large_heterogeneous_component_count(self):
        n,clauses,intent=gates_80()
        c,_=compile_ground(clauses,n,intent=intent)
        self.assertEqual(c['chosen_family'],'source-connected-components')
        self.assertEqual(c['result']['count'],str(4**80))
        self.assertEqual(c['evidence']['sizes'],[3]*80)
        self.assertTrue(verify(clauses,n,c,expected_intention='#SAT'))

    def test_direct_unsat_proof_not_guess(self):
        n,clauses,intent=odd_wheel()
        c,_=compile_ground(clauses,n,intent=intent,max_nodes=600,wall_seconds=2)
        self.assertEqual(c['result']['status'],'UNSAT')
        self.assertTrue(verify(clauses,n,c,expected_intention=intent))
        changed=copy.deepcopy(c)
        if changed['chosen_family']=='bounded-source-DPLL':
            changed['evidence']['search']['unsat_proof']={'leaf':'conflict'}
            with self.assertRaises(Reject):verify(clauses,n,changed)

    def test_pigeonhole_unknown_never_becomes_unsat(self):
        n,clauses,intent=pigeonhole(8,7)
        c,_=compile_ground(clauses,n,intent=intent,max_nodes=8,wall_seconds=.3)
        self.assertEqual(c['result']['status'],'UNKNOWN')
        self.assertTrue(verify(clauses,n,c,expected_intention=intent))
        modified=copy.deepcopy(c);modified['result']['status']='UNSAT'
        with self.assertRaises(Reject):verify(clauses,n,modified)

    def test_large_disjoint_unsat_tasks(self):
        n,clauses,intent=unsat_disjoint_k4()
        c,_=compile_ground(clauses,n,intent=intent,max_nodes=100,wall_seconds=.5)
        self.assertEqual(c['result']['status'],'UNSAT')
        self.assertTrue(verify(clauses,n,c,expected_intention='SAT'))

    def test_random3sat_source_finite_reference(self):
        n,clauses,intent=random_3sat(50)
        c,_=compile_ground(clauses,n,intent=intent,max_nodes=300,wall_seconds=1)
        self.assertTrue(verify(clauses,n,c,expected_intention=intent))
        self.assertIn(c['result']['status'],('SAT','UNSAT','UNKNOWN'))
        if c['result']['status']=='SAT':
            self.assertTrue(accepts(normalize(clauses,n),int(c['result']['witness'])))

    def test_contradictory_source_is_exact(self):
        c,_=compile_ground([[1],[-1]],1,intent='#SAT')
        self.assertEqual(c['result']['status'],'UNSAT')
        self.assertTrue(verify([[1],[-1]],1,c,expected_intention='#SAT'))

    def test_literal_empty_clause_is_proof(self):
        c,_=compile_ground([[]],15,intent='SAT')
        self.assertEqual(c['chosen_family'],'explicit-contradiction')
        self.assertTrue(verify([[]],15,c,expected_intention='SAT'))

    def test_source_witness_and_count_tampering(self):
        n,source,_=xor_chain(80)
        c,_=compile_ground(source,n,intent='#SAT')
        for modify in (
            lambda p:p['result'].__setitem__('count','5'),
            lambda p:p['result'].__setitem__('witness','0'),
            lambda p:p['evidence'].__setitem__('rank',12),
            lambda p:p['evidence']['equations'].pop(),
            lambda p:p['budgets'].__setitem__('max_nodes',-1),
            lambda p:p.__setitem__('chosen_family','bounded-source-DPLL'),
        ):
            with self.subTest(fn=str(modify)):
                forged=copy.deepcopy(c);modify(forged)
                with self.assertRaises(Reject):verify(source,n,forged,expected_intention='#SAT')

    def test_xor_exact_recognition_refuses_partial_encoder(self):
        full=xor_encoding((1,2,3),0)
        c,_=compile_ground(full[:-1],3,intent='SAT')
        self.assertNotEqual(c['chosen_family'],'exact-source-XOR-GF2')
        self.assertTrue(verify(full[:-1],3,c))

if __name__=='__main__':unittest.main()
