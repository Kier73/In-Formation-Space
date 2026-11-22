"""SPN-007 decision/exact-goal admission, refusal, and producer-policy controls."""
from __future__ import annotations
import copy
from random import Random
import unittest

from adaptive_ground_compiler import produce_adaptive_receipt,verify_adaptive_receipt
from spectral_receipts import direct_energy
from test_direct_sum_grounds import shared_variable_cycle_cnf,parity_pair_clauses
from walsh_phase_navigation_probe import clauses_from_energy_profile


class AdaptiveGroundTests(unittest.TestCase):
    def test_source_bound_adaptive_exact_certificate(self):
        clauses,n=shared_variable_cycle_cnf(24)
        receipt=produce_adaptive_receipt(clauses,n,goal='exact_ground',rank_cap=2)
        self.assertEqual(receipt['result'],'UNSAT')
        self.assertEqual(receipt['ground_energy'],[24,1])
        self.assertEqual(receipt['ground_degeneracy'],str(4*3**24))
        self.assertEqual(receipt['producer_policy']['selected_method'],'direct_sum_ground')
        self.assertEqual(verify_adaptive_receipt(clauses,n,receipt),'UNSAT')
        self.assertEqual(len(receipt['proof']['receipt']['proof']['components']),24)

    def test_witness_first_goal_relative_compiler(self):
        clauses,n=shared_variable_cycle_cnf(12,frustrated=False)
        receipt=produce_adaptive_receipt(clauses,n,goal='decision',rank_cap=2)
        self.assertEqual(receipt['result'],'SAT')
        self.assertEqual(receipt['proof']['kind'],'sat_witness')
        self.assertIsNone(receipt['ground_energy'])
        self.assertEqual(verify_adaptive_receipt(clauses,n,receipt),'SAT')

    def test_termwise_exact_handles_uncoupled_random_cnf(self):
        # A width-three encoding of XOR(x0,x1)=0 has a single term.
        cls=parity_pair_clauses(0,1,2,0)
        receipt=produce_adaptive_receipt(cls,3,goal='exact_ground',rank_cap=1)
        self.assertEqual(receipt['result'],'SAT')
        self.assertEqual(receipt['proof']['kind'],'termwise_exact')
        self.assertEqual(receipt['ground_energy'],[0,1])
        self.assertEqual(receipt['ground_degeneracy'],'4')
        self.assertEqual(verify_adaptive_receipt(cls,3,receipt),'SAT')

    def test_exact_refusal_is_not_unsat(self):
        rng=Random(711)
        clauses=[(tuple(rng.sample(range(12),3)),tuple(rng.randrange(2) for _ in range(3))) for _ in range(46)]
        receipt=produce_adaptive_receipt(clauses,12,goal='exact_ground',rank_cap=2)
        self.assertEqual(receipt['result'],'UNKNOWN')
        self.assertIsNone(receipt['ground_energy'])
        self.assertEqual(receipt['proof']['reason'],'exact_ground_not_admitted')
        self.assertEqual(verify_adaptive_receipt(clauses,12,receipt),'UNKNOWN')
        changed=copy.deepcopy(receipt)
        changed['result']='UNSAT'
        with self.assertRaises(ValueError):
            verify_adaptive_receipt(clauses,12,changed)

    def test_fallback_gaussian_decision_admission(self):
        cls=clauses_from_energy_profile([1,1,1,1,1,1,1,3])
        receipt=produce_adaptive_receipt(cls,3,goal='decision',rank_cap=2,pair_budget=0)
        self.assertEqual(receipt['result'],'UNSAT')
        self.assertEqual(receipt['proof']['kind'],'decision_proof')
        self.assertEqual(receipt['proof']['method'],'gaussian_circuits')
        self.assertEqual(verify_adaptive_receipt(cls,3,receipt),'UNSAT')

    def test_pair_gating_is_explicit_and_accounted(self):
        cls=clauses_from_energy_profile([1,1,1,1,1,1,1,3])
        receipt=produce_adaptive_receipt(cls,3,goal='decision',rank_cap=2,
                                         pair_budget=64,candidate_budget=100)
        self.assertEqual(receipt['proof']['method'],'nonlocal_pair_scan')
        self.assertEqual(verify_adaptive_receipt(cls,3,receipt),'UNSAT')
        self.assertLessEqual(receipt['producer_policy']['possible_pairs'],64)

    def test_exact_and_decision_requests_do_not_interchange(self):
        cls=clauses_from_energy_profile([0,1,1,2,1,2,2,1])
        decision=produce_adaptive_receipt(cls,3,goal='decision')
        self.assertEqual(decision['result'],'SAT')
        modified=copy.deepcopy(decision)
        modified['goal']='exact_ground'
        with self.assertRaises(ValueError):
            verify_adaptive_receipt(cls,3,modified)

    def test_forged_nested_source_and_witness(self):
        clauses,n=shared_variable_cycle_cnf(2)
        receipt=produce_adaptive_receipt(clauses,n,goal='exact_ground',rank_cap=2)
        tampered=copy.deepcopy(receipt)
        tampered['proof']['receipt']['formula_sha256']='bad'
        with self.assertRaises(ValueError):
            verify_adaptive_receipt(clauses,n,tampered)
        tampered=copy.deepcopy(receipt)
        tampered['proof']['receipt']['proof']['components'][0]['minimum']=[0,1]
        with self.assertRaises(ValueError):
            verify_adaptive_receipt(clauses,n,tampered)
        tampered=copy.deepcopy(receipt)
        tampered['proof']['receipt']['proof']['components'][0]['minimum']=[1.0,1]
        with self.assertRaises(ValueError):
            verify_adaptive_receipt(clauses,n,tampered)
        # Telemetry is an untrusted annotation and changing it does not
        # alter the proof. This is intentional and documented in SPN-007.
        telemetry=copy.deepcopy(receipt)
        telemetry['producer_policy']={'observed_total_ms':-5}
        self.assertEqual(verify_adaptive_receipt(clauses,n,telemetry),'UNSAT')

    def test_randomized_decision_crosscheck_vs_bruteforce(self):
        rng=Random(207)
        for n,m in ((6,20),(8,32),(10,42)):
            for k in range(25):
                clauses=[(tuple(sorted(rng.sample(range(n),3))),
                          tuple(rng.randrange(2) for _ in range(3))) for _ in range(m)]
                actual='SAT' if any(direct_energy(clauses,[(bits>>i)&1 for i in range(n)])==0
                                    for bits in range(1<<n)) else 'UNSAT'
                receipt=produce_adaptive_receipt(clauses,n,goal='decision',rank_cap=3,node_budget=256)
                self.assertEqual(receipt['result'],actual,(n,k))
                self.assertEqual(verify_adaptive_receipt(clauses,n,receipt),actual)


if __name__=='__main__':
    unittest.main()
