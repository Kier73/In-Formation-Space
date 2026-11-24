"""CIG-005 tests: independent original-source and observer-intention adversaries."""
from __future__ import annotations
import copy
import unittest

from joint_intention_ground import (make_branching_source,compile_ground,
    DEFAULT_PRICES, _offer_polynomials, _pullback, _eval, GroundRefusal)
from verify_joint_intention import verify,Reject


class JointIntentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=make_branching_source()
        cls.cert,_=compile_ground(cls.source,[0,1,2,3,4])

    def test_independent_source_verification(self):
        self.assertTrue(verify(self.source,self.cert))
        self.assertEqual(self.cert['source_result']['count'],str(1<<41))
        self.assertEqual(self.cert['ledger']['original_cnf_clauses'],106)

    def test_dimension_and_intention_gap(self):
        c=self.cert
        self.assertEqual(c['individual_dimensions'],[4,3,4])
        self.assertEqual(c['whole_future']['dimension'],9)
        self.assertEqual(c['eventual']['stable_linear_dimension'],3)
        self.assertEqual(c['eventual']['horizon'],3)
        self.assertEqual(c['quotient']['image_size'],4)
        self.assertEqual(c['quotient']['minimum_binary_bits'],2)

    def test_three_stable_polynomials_and_nonlinear_dependency(self):
        c=self.cert
        self.assertEqual(c['eventual']['stable_anf_masks'],[[3],[3,4],[3,7]])
        rows=tuple(tuple(p) for p in c['operator_rows'])
        stable=[tuple(p) for p in c['eventual']['stable_anf_masks']]
        for p in stable:self.assertEqual(_pullback(p,rows),p)
        for state in range(1<<7):
            y,j,z=(_eval(p,state) for p in stable)
            self.assertEqual(z,y&j)
        self.assertEqual(c['quotient']['histogram_active_support'],
                         {'0':3,'1':1,'2':3,'7':1})

    def test_cheaper_observer_policy_is_source_checked(self):
        p=self.cert['policy']
        self.assertEqual(p['selected'],['j','y_xor_j'])
        self.assertEqual(p['declared_cost'],3)
        self.assertEqual(p['decoder'],[0,7,1,2])
        self.assertTrue(verify(self.source,self.cert))

    def test_declared_price_change_is_new_intention(self):
        price={**DEFAULT_PRICES,'y':0,'j':0,'z':0,'y_xor_j':200,'y_and_j':200}
        c,_=compile_ground(self.source,[0,1,2,3,4],prices=price)
        self.assertEqual(c['policy']['selected'],['y','j'])
        with self.assertRaises(Reject):verify(self.source,c)
        self.assertTrue(verify(self.source,c,expected_prices=price))

    def test_many_timestamps_without_linear_stepping(self):
        for timestamp in (0,1,2,3,4,7,33,10**100+173):
            for initial in (0,3,7,127):
                c,_=compile_ground(self.source,[0,1,2,3,4],
                                   steps=timestamp,initial=initial)
                self.assertTrue(verify(self.source,c))

    def test_modified_source_clause_rejected(self):
        altered=copy.deepcopy(self.source)
        altered['coupling'][0][0]*=-1
        with self.assertRaises(Reject):verify(altered,self.cert)
        with self.assertRaises((GroundRefusal,ValueError)):
            compile_ground(altered,[0,1,2,3,4])

    def test_forged_joint_rank_rejected(self):
        c=copy.deepcopy(self.cert)
        c['whole_future']['dimension']-=1
        with self.assertRaises(Reject):verify(self.source,c)

    def test_forged_matrix_rejected(self):
        c=copy.deepcopy(self.cert)
        c['whole_future']['matrix_rows'][0]^=1
        with self.assertRaises(Reject):verify(self.source,c)

    def test_forged_orbit_basis_rejected(self):
        c=copy.deepcopy(self.cert)
        c['whole_future']['basis'][1]=c['whole_future']['basis'][0]
        with self.assertRaises(Reject):verify(self.source,c)

    def test_forged_stable_anf_rejected(self):
        c=copy.deepcopy(self.cert)
        c['eventual']['stable_anf_masks'][2]=[3]
        with self.assertRaises(Reject):verify(self.source,c)

    def test_forged_quotient_rejected(self):
        c=copy.deepcopy(self.cert)
        c['quotient']['minimum_binary_bits']=1
        with self.assertRaises(Reject):verify(self.source,c)

    def test_forged_nonlinear_decoder_rejected(self):
        c=copy.deepcopy(self.cert)
        c['policy']['decoder'][1]^=1
        with self.assertRaises(Reject):verify(self.source,c)

    def test_forged_price_rejected(self):
        c=copy.deepcopy(self.cert)
        c['policy']['prices']['z']=0
        with self.assertRaises(Reject):verify(self.source,c)

    def test_forged_measurement_selection_rejected(self):
        c=copy.deepcopy(self.cert)
        c['policy']['selected']=['j','z']
        with self.assertRaises(Reject):verify(self.source,c)

    def test_forged_satisfying_witness_rejected(self):
        c=copy.deepcopy(self.cert)
        c['source_result']['witness'][6]=1
        with self.assertRaises(Reject):verify(self.source,c)

    def test_forged_time_observation_rejected(self):
        c=copy.deepcopy(self.cert)
        c['navigation']['observed']^=1
        with self.assertRaises(Reject):verify(self.source,c)

    def test_fixed_point_source_vs_nonfixed_initial(self):
        c,_=compile_ground(self.source,[0,1,2,3,4],initial=3,steps=3)
        self.assertEqual(c['navigation']['eventual_observed'],7)
        self.assertTrue(verify(self.source,c))

    def test_invalid_input_admission(self):
        for bad in (-1,1.5,1<<30):
            with self.assertRaises((GroundRefusal,ValueError)):
                compile_ground(self.source,[0,1,2,3,4],initial=bad)
        for invalid in ({}, {'y':1}, {**DEFAULT_PRICES,'z':-1}):
            with self.assertRaises((GroundRefusal,ValueError)):
                compile_ground(self.source,[0,1,2,3,4],prices=invalid)

    def test_wrong_observer_cut_rejected(self):
        with self.assertRaises((GroundRefusal,ValueError)):
            compile_ground(self.source,[100])


if __name__=='__main__':unittest.main()
