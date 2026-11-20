"""TCN-005: independent dense-FFT parity, witness and refusal tests."""
import copy
import unittest
import numpy as np
from adaptive_ground import (PhaseCarrier, choose_ground, choice_receipt,
                             verify_choice_receipt)
from branch import StructuredState, gate_phases, dense_quadratic_reference
from cocycle import ExactOperator, ExactSchedule


class AdaptiveGroundTests(unittest.TestCase):
    def setUp(self):
        self.p=127
        self.base=StructuredState.flat(self.p,7,13)

    def test_cubic_carrier_and_dense_fft_reference(self):
        for p in (31,71,127):
            base=StructuredState.flat(p,7,3)
            targets=(0,1,3,p//2,p-1)
            choice=choose_ground(base,'cubic',5,(2,7,9),13,targets,max_terms=7,
                                 error_budget=0,max_query_work=7*p*len(targets),
                                 cubic_frame_scan=True)
            self.assertEqual(choice.representation,'carrier')
            self.assertEqual(choice.sparse_probe['status'],'refused')
            self.assertGreater(choice.sparse_probe['minimum_rank'],7)
            reference=dense_quadratic_reference(p,(2,7,9),13,
                      gate_phases(p,'cubic',5)*base.dense())
            self.assertLess(max(abs(z-reference[y]) for z,y in
                                zip(choice.amplitudes(),targets)),2e-12)

    def test_harmonic_sparse_with_bounded_error(self):
        targets=(0,9,21,30)
        result=choose_ground(self.base,'harmonic',.7,(3,5),17,targets,
                             max_terms=7,error_budget=.01,max_query_work=1000)
        self.assertEqual(result.representation,'sparse')
        self.assertLess(result.estimated_query_work,100)
        reference=dense_quadratic_reference(self.p,(3,5),17,
                      gate_phases(self.p,'harmonic',.7)*self.base.dense())
        self.assertLess(max(abs(z-reference[y]) for z,y in zip(result.amplitudes(),targets)),
                        result.approximation_error_bound+3e-12)

    def test_zero_error_requires_untruncated_carrier(self):
        result=choose_ground(self.base,'harmonic',.7,(3,5),17,(4,),
                             max_terms=7,error_budget=0,exact_gate=True,
                             max_query_work=127)
        self.assertEqual(result.representation,'carrier')
        self.assertEqual(result.approximation_error_bound,0)

    def test_query_budget_refuses(self):
        choice=choose_ground(self.base,'cubic',5,(3,5),17,(2,8),
                             max_terms=5,error_budget=0,max_query_work=50)
        self.assertEqual(choice.decision,'refused')
        with self.assertRaises(ValueError):
            choice.amplitudes()

    def test_hundred_nonquadratic_gates_fuse_before_transport(self):
        state=PhaseCarrier.start(self.base)
        for _ in range(100):
            state=state.apply_gate('cubic',3).apply_gate('harmonic',.01)
        self.assertEqual(state.cubic,300%self.p)
        self.assertEqual(state.interventions,200)
        self.assertAlmostEqual(state.harmonic,1.0,places=12)
        op,products=ExactSchedule(self.p,(2,5,9)).navigate(10**100+23)
        carrier=state.after_operator(op)
        self.assertLess(products,1000)
        input_vector=(gate_phases(self.p,'cubic',state.cubic)*
                      gate_phases(self.p,'harmonic',state.harmonic)*self.base.dense())
        for y in (0,7,15):
            self.assertLess(abs(carrier.amplitude(y)-op.apply_coordinate(input_vector,y)),1e-12)

    def test_pending_mixing_gate_requires_reanchor(self):
        carrier=PhaseCarrier.start(self.base).apply_gate('cubic',5)
        mixed=carrier.after_operator(ExactOperator.transfer(self.p,2))
        with self.assertRaisesRegex(ValueError,'re-anchoring'):
            mixed.apply_gate('harmonic',.2)
        new,receipt=mixed.reanchor(max_terms=7,budget=.01)
        self.assertIsNone(new)
        self.assertEqual(receipt['decision'],'refused')
        self.assertEqual(mixed.interventions,1)

    def test_permutation_kernel_readout_is_cheap(self):
        carrier=PhaseCarrier.start(self.base).apply_gate('cubic',5)
        self.assertEqual(carrier.estimated_query_work((1,2,3)),3)
        for y in (0,1,5):
            expected=gate_phases(self.p,'cubic',5)[y]*self.base.value(y)
            self.assertLess(abs(carrier.amplitude(y)-expected),1e-12)

    def test_delta_source_independent_dense_reference(self):
        base=StructuredState.delta(31,7,.3+.2j)
        targets=(0,3,9)
        choice=choose_ground(base,'cubic',5,(3,4),11,targets,
                             error_budget=0,max_query_work=31*len(targets))
        self.assertEqual(choice.representation,'carrier')
        reference=dense_quadratic_reference(31,(3,4),11,
                      gate_phases(31,'cubic',5)*base.dense())
        self.assertLess(max(abs(z-reference[y]) for z,y in zip(choice.amplitudes(),targets)),2e-12)

    def test_receipt_replay_and_tampering(self):
        receipt=choice_receipt(self.base,'cubic',5,(2,5),7,(3,10),
                               max_terms=7,error_budget=0,max_query_work=500)
        self.assertTrue(verify_choice_receipt(receipt))
        self.assertIn('not external',receipt['scope'])
        changed=copy.deepcopy(receipt)
        changed['predictions'][0][0]=float(10).hex()
        self.assertFalse(verify_choice_receipt(changed))
        changed=copy.deepcopy(receipt)
        changed['sha256']='0'*64
        self.assertFalse(verify_choice_receipt(changed))
        changed=copy.deepcopy(receipt)
        changed['options']['max_query_work']=1
        self.assertFalse(verify_choice_receipt(changed))

    def test_refused_receipt_remains_refused_on_recheck(self):
        receipt=choice_receipt(self.base,'cubic',5,(2,5),7,(3,10),
                               max_terms=7,error_budget=0,max_query_work=2)
        self.assertEqual(receipt['choice']['decision'],'refused')
        self.assertEqual(receipt['predictions'],[])
        self.assertTrue(verify_choice_receipt(receipt))

    def test_huge_coordinate_matches_period_alias(self):
        n=10**100+123
        schedule=ExactSchedule(31,(3,4,7))
        period=schedule.full_period_bound()
        carrier=PhaseCarrier.start(StructuredState.flat(31,4,1)).apply_gate('cubic',3)
        long,_=carrier.after_schedule((3,4,7),n)
        short,_=carrier.after_schedule((3,4,7),n%period)
        for y in (0,1,13):
            self.assertLess(abs(long.amplitude(y)-short.amplitude(y)),3e-13)

    def test_invalid_inputs_refused(self):
        for coordinates in ((-1,),(127,),(3,3),(),('3',)):
            with self.assertRaises(ValueError):
                choose_ground(self.base,'cubic',5,(2,3),10,coordinates)
        with self.assertRaises(ValueError):
            choose_ground(self.base,'harmonic',float('nan'),(2,3),10,(3,))
        with self.assertRaises(ValueError):
            choose_ground(self.base,'cubic',5,(2,3),-1,(3,))
        with self.assertRaises(ValueError):
            choose_ground(self.base,'cubic',5,(2,3),10,(3,),max_query_work=-1)
        with self.assertRaises(ValueError):
            PhaseCarrier.start(self.base).after_operator(ExactOperator.identity(31))


if __name__=='__main__':
    unittest.main()
