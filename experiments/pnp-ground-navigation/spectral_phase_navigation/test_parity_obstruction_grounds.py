"""SPN-006 independent rational-source checks of signed parity obstructions."""
from __future__ import annotations
import copy
from fractions import Fraction
from random import Random
import unittest

from nonlocal_rank_grounds import parity_cycle_cnf
from parity_obstruction_grounds import (first_inconsistent_circuit,
    obstruction_bound, independent_obstruction_bound,
    produce_obstruction_receipt, verify_obstruction_receipt, xor_masks)
from rank_block_bounds import rank_block_bound
from walsh_phase_navigation_probe import (spectral_coefficients,
    conditional_coefficients, violated_count)


class ParityObstructionTests(unittest.TestCase):
    def test_constructed_cycle_yields_one_certified_circuit(self):
        clauses,n = parity_cycle_cnf(1)
        coeff=spectral_coefficients(clauses)
        circuit, reductions, rank=first_inconsistent_circuit(coeff)
        self.assertEqual((len(circuit),rank),(4,3))
        self.assertEqual(xor_masks(circuit),0)
        self.assertEqual(sum(int(coeff[s]>0) for s in circuit)%2,1)
        bound, blocks, costs=obstruction_bound(coeff)
        self.assertEqual((bound,blocks),(8,[circuit]))
        self.assertEqual(costs['circuit_count'],1)
        self.assertEqual(independent_obstruction_bound(clauses,{},[list(circuit)]),Fraction(1))
        receipt=produce_obstruction_receipt(clauses,n)
        self.assertEqual(receipt['producer_nodes_visited'],1)
        self.assertEqual(receipt['proof']['kind'],'parity_circuit_bound')
        self.assertEqual(verify_obstruction_receipt(clauses,n,receipt),'UNSAT')

    def test_strided_long_range_cycles_certify_without_pair_scan(self):
        clauses,n=parity_cycle_cnf(24)
        receipt=produce_obstruction_receipt(clauses,n,budget=64)
        self.assertEqual(receipt['result'],'UNSAT')
        self.assertEqual(receipt['proof']['bound'],[24,1])
        self.assertEqual(receipt['producer_nodes_visited'],1)
        self.assertEqual(len(receipt['proof']['circuits']),24)
        self.assertEqual(receipt['producer_discovery']['circuit_terms_examined'],96)
        self.assertEqual(verify_obstruction_receipt(clauses,n,receipt),'UNSAT')

    def test_arbitrary_rank_circuit_more_than_three_dimensions(self):
        # A dependent circuit with 8 terms and rank 7, not a rank-3 block.
        atoms=[1 << i for i in range(7)]
        long_mask=xor_masks(atoms)
        coeff={0:8,**{v:8 for v in atoms},long_mask:-8}
        circuit,_,rank=first_inconsistent_circuit(coeff)
        self.assertEqual((len(circuit),rank),(8,7))
        bound,circuits,_=obstruction_bound(coeff)
        self.assertEqual((bound,circuits),(-40,[circuit]))
        brute=min(sum(a*(-1 if (s & x).bit_count()%2 else 1)
                      for s,a in coeff.items()) for x in range(1<<7))
        self.assertEqual(bound,brute)

    def test_consistent_preferences_give_exact_naive_lower_bound(self):
        rng=Random(6006)
        for n in (5,8,14):
            for _ in range(20):
                target=rng.randrange(1<<n)
                supports=set(rng.sample(range(1,1<<n),min(2*n,(1<<n)-1)))
                coeff={s:(1 if (s & target).bit_count()%2 else -1)
                       *rng.randint(1,5) for s in supports}
                circuit,_,_=first_inconsistent_circuit(coeff)
                self.assertIsNone(circuit)
                lower,blocks,_=obstruction_bound(coeff)
                self.assertEqual(blocks,[])
                self.assertEqual(lower,-sum(abs(a) for a in coeff.values()))

    def test_random_restriction_soundness_with_independent_fractions(self):
        rng=Random(66006)
        for n in range(3,9):
            for _ in range(20):
                clauses=[(tuple(sorted(rng.sample(range(n),3))),
                          tuple(rng.randrange(2) for _ in range(3)))
                         for _ in range(4*n+3)]
                prefix={v:rng.randrange(2) for v in range(n) if rng.randrange(4)==0}
                coeff=spectral_coefficients(clauses)
                for v,bit in prefix.items():
                    coeff=conditional_coefficients(coeff,v,bit)
                lower,circuits,cost=obstruction_bound(coeff)
                checked=independent_obstruction_bound(clauses,prefix,
                                     [list(c) for c in circuits])
                self.assertEqual(checked,Fraction(lower,8))
                minimum=min(violated_count(clauses,x) for x in range(1<<n)
                            if all((x>>v)&1==bit for v,bit in prefix.items()))
                self.assertLessEqual(checked,minimum)

    def test_tampering_is_rejected(self):
        clauses,n=parity_cycle_cnf(1)
        valid=produce_obstruction_receipt(clauses,n)
        self.assertEqual(verify_obstruction_receipt(clauses,n,valid),'UNSAT')
        for alteration in ('digest','version','bound','missing','not_xor_zero',
                           'not_frustrated','reused','duplicate','invalid_sat'):
            forged=copy.deepcopy(valid)
            if alteration=='digest':forged['formula_sha256']='0'*64
            elif alteration=='version':forged['version']='SPN-003-v1'
            elif alteration=='bound':forged['proof']['bound']=[2,1]
            elif alteration=='missing':forged['proof']['circuits'][0][0]=(1<<n)
            elif alteration=='not_xor_zero':forged['proof']['circuits'][0]=forged['proof']['circuits'][0][1:]
            elif alteration=='not_frustrated':
                forged['proof']['circuits'][0]=[]
            elif alteration=='reused':
                forged['proof']['circuits'].append(forged['proof']['circuits'][0])
            elif alteration=='duplicate':
                forged['proof']['circuits'][0].insert(1,forged['proof']['circuits'][0][0])
            else:
                forged['result']='SAT'
                forged['proof']={'kind':'sat','witness':[0]*n}
            with self.subTest(alteration=alteration),self.assertRaises(ValueError):
                verify_obstruction_receipt(clauses,n,forged)

    def test_random_receipts_against_exhaustive_reference(self):
        rng=Random(66007)
        for n in (5,6,7,8):
            for _ in range(15):
                clauses=[(tuple(sorted(rng.sample(range(n),3))),
                          tuple(rng.randrange(2) for _ in range(3)))
                         for _ in range(4*n+4)]
                answer='SAT' if any(violated_count(clauses,x)==0 for x in range(1<<n)) else 'UNSAT'
                receipt=produce_obstruction_receipt(clauses,n,budget=256)
                self.assertEqual(receipt['result'],answer)
                self.assertEqual(verify_obstruction_receipt(clauses,n,receipt),answer)

    def test_budget_exhaustion_remains_unknown(self):
        rng=Random(66120)
        for _ in range(100):
            clauses=[(tuple(sorted(rng.sample(range(8),3))),
                      tuple(rng.randrange(2) for _ in range(3)))
                     for _ in range(35)]
            r=produce_obstruction_receipt(clauses,8,budget=1)
            if r['result']=='UNKNOWN':
                self.assertEqual(verify_obstruction_receipt(clauses,8,r),'UNKNOWN')
                break
        else:
            self.fail('no budget refusal in randomized negative control')


if __name__=='__main__':
    unittest.main()

# Tests added after the original suite for the realizable all-signs-compatible case.
class CompatibleGroundTests(unittest.TestCase):
    def test_high_rank_sat_ground_constructed_without_state_enumeration(self):
        from parity_obstruction_grounds import compatible_preference_ground
        from nonlocal_rank_grounds import parity_cycle_cnf
        from spectral_receipts import direct_energy
        clauses,n=parity_cycle_cnf(24,frustrated=False)
        coeff=spectral_coefficients(clauses)
        assignment, minimum, rank=compatible_preference_ground(coeff,n)
        self.assertEqual((n,minimum,rank),(120,0,72))
        self.assertIsNotNone(assignment)
        witness=[(assignment>>i)&1 for i in range(n)]
        self.assertEqual(direct_energy(clauses,witness),0)
        self.assertIsNone(first_inconsistent_circuit(coeff)[0])

    def test_inconsistent_preferences_refuse_ground(self):
        from parity_obstruction_grounds import compatible_preference_ground
        clauses,n=parity_cycle_cnf(1,frustrated=True)
        coeff=spectral_coefficients(clauses)
        x,lower,rank=compatible_preference_ground(coeff,n)
        self.assertIsNone(x)
        self.assertEqual(lower,0)
        self.assertEqual(rank,3)

    def test_abstract_nonlocal_high_rank_consistent_ground(self):
        from parity_obstruction_grounds import compatible_preference_ground
        rng=Random(772)
        n=128
        target=sum((rng.randrange(2)<<i) for i in range(n))
        masks=[1<<i for i in range(n)]
        masks.extend((1<<i)^(1<<(i+1)) for i in range(0,n-1,2))
        coeff={0:1000}
        for s in masks:
            coeff[s]=5 if (s&target).bit_count()%2 else -7
        x, lower, rank=compatible_preference_ground(coeff,n)
        self.assertEqual(rank,128)
        self.assertEqual(lower,1000-sum(abs(a) for s,a in coeff.items() if s))
        self.assertEqual(sum(a*(-1 if (s&x).bit_count()%2 else 1)
                             for s,a in coeff.items()),lower)

class ExactGroundReceiptTests(unittest.TestCase):
    def test_source_checked_high_rank_ground_receipt(self):
        from parity_obstruction_grounds import (produce_compatible_ground_receipt,
                                                verify_compatible_ground_receipt)
        clauses,n=parity_cycle_cnf(24,frustrated=False)
        receipt=produce_compatible_ground_receipt(clauses,n)
        self.assertEqual(receipt['producer_fourier_rank'],72)
        self.assertEqual(receipt['result']['energy'],[0,1])
        self.assertEqual(verify_compatible_ground_receipt(clauses,n,receipt),'EXACT')
        changed=copy.deepcopy(receipt)
        changed['result']['witness'][0]^=1
        with self.assertRaises(ValueError):
            verify_compatible_ground_receipt(clauses,n,changed)
        changed=copy.deepcopy(receipt)
        changed['result']['energy']=[1,1]
        with self.assertRaises(ValueError):
            verify_compatible_ground_receipt(clauses,n,changed)

    def test_refuses_unresolved_energy_ground(self):
        from parity_obstruction_grounds import (produce_compatible_ground_receipt,
                                                verify_compatible_ground_receipt)
        cls,n=parity_cycle_cnf(1)
        receipt=produce_compatible_ground_receipt(cls,n)
        self.assertEqual(receipt['result']['kind'],'unknown')
        self.assertEqual(verify_compatible_ground_receipt(cls,n,receipt),'UNKNOWN')
