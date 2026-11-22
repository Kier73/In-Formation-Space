"""SPN-007 exact-ground verification, adversarial partitions, and oracle checks."""
from __future__ import annotations
import copy
from fractions import Fraction
from random import Random
import unittest

from direct_sum_grounds import (fundamental_components, gf2_rank,
    produce_direct_sum_ground, verify_direct_sum_ground)
from nonlocal_rank_grounds import parity_cycle_cnf
from spectral_receipts import direct_energy
from walsh_phase_navigation_probe import spectral_coefficients


def parity_pair_clauses(x,y,z, target):
    """Two-bit XOR equation expanded into four ordinary width-three clauses."""
    if len({x,y,z})!=3 or target not in (0,1):
        raise ValueError('distinct variables and a binary target are required')
    return [((x,y,z),(a, a^(1-target), aux))
            for a in (0,1) for aux in (0,1)]


def shared_variable_cycle_cnf(count, frustrated=True):
    """Independent Fourier triads with overlapping original source variables.

    Every triangle shares source variable 0 and auxiliary variable 1. The
    original primal constraint graph is connected, even while character
    subspaces of separate triangles are linearly independent.
    """
    if count<1:
        raise ValueError('positive block count required')
    clauses=[]
    for j in range(count):
        a,b=2+2*j,3+2*j
        clauses.extend(parity_pair_clauses(0,a,1,0))
        clauses.extend(parity_pair_clauses(a,b,1,0))
        clauses.extend(parity_pair_clauses(0,b,1,1 if frustrated else 0))
    return clauses,2+2*count


class DirectSumTests(unittest.TestCase):
    def test_shared_variable_nonlocal_quotients(self):
        for blocks in (1,2,8,24):
            clauses,n=shared_variable_cycle_cnf(blocks)
            c=spectral_coefficients(clauses)
            groups,ledger=fundamental_components(s for s,a in c.items() if s and a)
            self.assertEqual(len(groups),blocks)
            self.assertTrue(all(gf2_rank(g)==2 and len(g)==3 for g in groups))
            self.assertEqual(ledger['rank'],2*blocks)
            receipt,audit=produce_direct_sum_ground(clauses,n,rank_cap=2)
            self.assertEqual(receipt['ground_energy'],[blocks,1])
            self.assertEqual(receipt['ground_degeneracy'],str(4*3**blocks))
            self.assertEqual(receipt['result'],'UNSAT')
            self.assertEqual(audit['states_enumerated'],4*blocks)
            self.assertEqual(verify_direct_sum_ground(clauses,n,receipt),'UNSAT')
            self.assertEqual(direct_energy(clauses,receipt['proof']['witness']),blocks)

    def test_sat_control_and_zero_energy(self):
        for blocks in (1,4,12):
            clauses,n=shared_variable_cycle_cnf(blocks,frustrated=False)
            receipt,audit=produce_direct_sum_ground(clauses,n,rank_cap=2)
            self.assertEqual(receipt['result'],'SAT')
            self.assertEqual(receipt['ground_energy'],[0,1])
            self.assertEqual(receipt['ground_degeneracy'],'4')
            self.assertEqual(verify_direct_sum_ground(clauses,n,receipt),'SAT')

    def test_existing_rank_three_nonlocal_family(self):
        clauses,n=parity_cycle_cnf(24)
        receipt,audit=produce_direct_sum_ground(clauses,n,rank_cap=3)
        self.assertEqual(receipt['ground_energy'],[24,1])
        self.assertEqual(audit['largest_component_rank'],3)
        self.assertEqual(audit['states_enumerated'],192)
        self.assertEqual(verify_direct_sum_ground(clauses,n,receipt),'UNSAT')

    def test_high_rank_refusal_is_not_unsat(self):
        rng=Random(772)
        n=14
        clauses=[(tuple(rng.sample(range(n),3)),tuple(rng.randrange(2) for _ in range(3))) for _ in range(50)]
        receipt,audit=produce_direct_sum_ground(clauses,n,rank_cap=3)
        self.assertIsNone(receipt)
        self.assertFalse(audit['supported'])
        self.assertGreater(audit['largest_component_rank'],3)

    def test_enumerated_minimum_matches_exhaustive_random_oracle(self):
        rng=Random(7707)
        for n in range(3,9):
            for case in range(35):
                clauses=[(tuple(rng.sample(range(n),3)),tuple(rng.randrange(2) for _ in range(3))) for _ in range(rng.randrange(1,14))]
                receipt,audit=produce_direct_sum_ground(clauses,n,rank_cap=8)
                self.assertIsNotNone(receipt)
                energies=[direct_energy(clauses,[(bits>>i)&1 for i in range(n)])
                          for bits in range(1<<n)]
                exact=min(energies)
                self.assertEqual(receipt['ground_energy'],[exact,1],(n,case))
                self.assertEqual(receipt['ground_degeneracy'],str(energies.count(exact)))
                self.assertEqual(verify_direct_sum_ground(clauses,n,receipt),
                                 'SAT' if exact==0 else 'UNSAT')

    def test_reject_forged_or_corrupted_exact_ground(self):
        clauses,n=shared_variable_cycle_cnf(3)
        receipt,_=produce_direct_sum_ground(clauses,n,rank_cap=2)
        def rejected(changer):
            altered=copy.deepcopy(receipt)
            changer(altered)
            with self.assertRaises(ValueError):
                verify_direct_sum_ground(clauses,n,altered)
        rejected(lambda r:r.update({'ground_energy':[0,1]}))
        rejected(lambda r:r.update({'formula_sha256':'f'*64}))
        rejected(lambda r:r['proof'].update({'witness':[0,0,1]+[0]*(n-3)}))
        rejected(lambda r:r['proof']['components'][0]['supports'].pop())
        rejected(lambda r:r['proof']['components'][1]['supports'].append(r['proof']['components'][0]['supports'][0]))
        rejected(lambda r:r['proof']['components'][0].update({'minimum':[0,1]}))
        rejected(lambda r:r['proof']['components'][0].update({'rank':3}))
        rejected(lambda r:r['proof']['components'][0].update({'minimizers':1}))
        rejected(lambda r:r.update({'ground_degeneracy':'1'}))
        rejected(lambda r:r.update({'result':'SAT'}))
        # A partition that covers all terms but merges two independent blocks
        # must be rejected when its rank exceeds the claimed cap.
        rejected(lambda r:r['proof']['components'][0]['supports'].extend(
            r['proof']['components'][1]['supports']))

    def test_arbitrary_supports_partition_has_rank_sum(self):
        rng=Random(77)
        for n in (3,7,14,24):
            for _ in range(50):
                supports=[s for s in range(1,1<<min(n,7)) if rng.random()<.2]
                if n>7: supports += [1<<i for i in range(7,n)]
                blocks,cost=fundamental_components(supports)
                self.assertEqual(sum(gf2_rank(b) for b in blocks),gf2_rank(supports))
                self.assertEqual({s for b in blocks for s in b},set(supports))


if __name__=='__main__':
    unittest.main()
