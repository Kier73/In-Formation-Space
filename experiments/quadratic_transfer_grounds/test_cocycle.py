"""TCN-003 exact Gauss-cocycle / full scalar-amplitude conformance tests."""
from __future__ import annotations
import copy
import unittest

import numpy as np

from cocycle import (ExactAmplitude, ExactOperator, ExactSchedule,
                     _gauss_cocycle, verify_receipt)
from transfer import Ground, direct_transfer, fidelity


def dense_reference(p, pattern, steps, initial):
    x=np.arange(p)
    v=np.array(initial,dtype=complex)
    for n in range(steps):
        v=np.fft.ifft(v)*np.sqrt(p)
        v*=np.exp(2j*np.pi*((pattern[n%len(pattern)]*x*x)%p)/p)
    return v


def canonical_dense(op):
    return np.array([[op.basis_amplitude(x,y).complex_value()
                      for x in range(op.p)] for y in range(op.p)])


class CocycleTests(unittest.TestCase):
    def test_direct_complex_amplitudes_including_global_phase(self):
        for p in (3,5,7,11,17,31):
            for pattern in ((0,),(3,),(2,5,7)):
                schedule=ExactSchedule(p,pattern)
                x=np.arange(p)
                source=3%p
                v=np.zeros(p,complex)
                v[source]=1
                for n in range(18):
                    op,products=schedule.navigate(n)
                    predicted=np.array([op.basis_amplitude(source,y).complex_value()
                                        for y in range(p)])
                    self.assertLess(float(np.max(abs(predicted-v))),3e-12,
                                    (p,pattern,n,op.signature()))
                    self.assertEqual(op.m,Ground(p,pattern).advance_matrix(n)[0])
                    v=np.fft.ifft(v)*np.sqrt(p)
                    a=pattern[n%len(pattern)]
                    v*=np.exp(2j*np.pi*((a*x*x)%p)/p)

    def test_cocycle_exactly_composes_kernels(self):
        for p in (3,5,7,11,13,17,31):
            rng=np.random.default_rng(123+p)
            gates=[ExactOperator.identity(p)]
            gates.extend(ExactOperator.transfer(p,a) for a in range(min(p,9)))
            # Build noncommuting and nonsplit elements.
            for _ in range(30):
                a,b=rng.choice(len(gates),size=2)
                gates.append(gates[int(a)].compose(gates[int(b)]))
            for _ in range(18):
                a,b=rng.choice(len(gates),size=2)
                first,second=gates[int(a)],gates[int(b)]
                composed=first.compose(second)
                expected=canonical_dense(first)@canonical_dense(second)
                self.assertLess(float(np.max(abs(canonical_dense(composed)-expected))),2e-11,
                                (p,first.signature(),second.signature()))

    def test_inverse_is_full_phase_aware(self):
        for p in (3,5,7,11,17,31):
            schedule=ExactSchedule(p,(1,3,7))
            for n in range(20):
                op,_=schedule.navigate(n)
                self.assertEqual(op.compose(op.inverse()),ExactOperator.identity(p))
                self.assertEqual(op.inverse().compose(op),ExactOperator.identity(p))

    def test_absolute_phase_separates_projectively_equal_operators(self):
        schedule=ExactSchedule(101,(7,13,29))
        earlier,_=schedule.navigate(25)
        later,_=schedule.navigate(178)
        self.assertEqual(earlier.m,later.m)
        self.assertEqual((earlier.quadrant,later.quadrant),(2,0))
        a,b=earlier.basis_amplitude(33,3),later.basis_amplitude(33,3)
        self.assertEqual((a.residue,b.residue),(7,7))
        self.assertLess(abs(a.complex_value()+b.complex_value()),1e-12)
        self.assertEqual(schedule.full_period_bound(),306)
        self.assertEqual(schedule.find_exact_operator_coordinate(later),178)

    def test_hundred_digit_coordinate_full_amplitude(self):
        s=ExactSchedule(101,(7,13,29))
        huge=10**100+123
        op,products=s.navigate(huge)
        self.assertEqual(op.signature(),{'matrix':[[19,67],[59,38]],
                                         'global_quadrant_mod4':2})
        self.assertLess(products,6*huge.bit_length())
        self.assertEqual(op,s.navigate(25)[0])
        amplitude=op.basis_amplitude(33,3)
        self.assertEqual(amplitude.description(),{
            'nonzero':True,'quadrant_mod4':2,'residue_mod_p':7,
            'magnitude':'1/sqrt(p)'})
        self.assertEqual(s.find_exact_operator_coordinate(op),25)
        self.assertEqual(s.navigate(s.full_period_bound())[0],ExactOperator.identity(101))

    def test_arbitrary_input_dense_one_coordinate_and_complete_profile(self):
        p=127
        pattern=(7,13,29)
        rng=np.random.default_rng(2026)
        initial=rng.normal(size=p)+1j*rng.normal(size=p)
        initial=initial/np.linalg.norm(initial)
        schedule=ExactSchedule(p,pattern)
        for n in (0,1,2,17,127,512):
            op,_=schedule.navigate(n)
            actual=dense_reference(p,pattern,n,initial)
            for target in (0,1,34,126):
                self.assertLess(abs(op.apply_coordinate(initial,target)-actual[target]),2e-11)
            if n in (0,2,127):
                self.assertLess(float(np.max(abs(op.apply_full(initial)-actual))),2e-11)

    def test_nonquadratic_input_is_propagated_not_misclassified(self):
        p=31
        x=np.arange(p)
        cubic=np.exp(2j*np.pi*((x*x*x)%p)/p)/np.sqrt(p)
        schedule=ExactSchedule(p,(2,5,7))
        for n in (1,3,9,30):
            op,_=schedule.navigate(n)
            actual=dense_reference(p,schedule.pattern,n,cubic)
            self.assertLess(float(np.max(abs(op.apply_full(cubic)-actual))),2e-11)
        # This does NOT compress the arbitrary input: 31 complex samples read.
        self.assertEqual(cubic.shape,(p,))

    def test_exact_amplitude_probability_delta_vs_flat(self):
        p=11
        schedule=ExactSchedule(p,(3,))
        for n in range(15):
            op,_=schedule.navigate(n)
            probs=[op.basis_amplitude(1,x).probability() for x in range(p)]
            self.assertEqual(sum(probs),1)
            self.assertTrue(all(v.denominator in (1,p) for v in probs))

    def test_nontrivial_gauss_phase_occurs(self):
        for p in (3,7,11,19):
            op=ExactOperator.transfer(p,1)
            combined=op.compose(op)
            self.assertNotEqual(combined.quadrant,0)
            self.assertEqual(combined.quadrant,_gauss_cocycle(op.m,op.m,p))
        for p in (5,13,17):
            op=ExactOperator.transfer(p,1)
            self.assertEqual(op.compose(op).quadrant,0)

    def test_full_unitary_temporal_inversion(self):
        for p in (3,5,7,11,17,31,101):
            for pattern in ((0,), (3,), (3,4,0)):
                s=ExactSchedule(p,pattern)
                period=s.full_period_bound()
                self.assertEqual(s.navigate(period)[0],ExactOperator.identity(p))
                for n in range(min(period,35)):
                    target,_=s.navigate(n)
                    earliest=s.find_exact_operator_coordinate(target)
                    self.assertIsNotNone(earliest)
                    self.assertLessEqual(earliest,n)
                    self.assertEqual(s.navigate(earliest)[0],target)

    def test_hash_recomputation_not_authentication(self):
        s=ExactSchedule(101,(7,13,29))
        rec=s.receipt(10**100+123,33,3)
        self.assertTrue(verify_receipt(rec))
        for key in ('steps_decimal','pattern','operator','amplitude','sha256'):
            tampered=copy.deepcopy(rec)
            if key=='steps_decimal':tampered[key]='178'
            if key=='pattern':tampered[key][1]=12
            if key=='operator':tampered[key]['global_quadrant_mod4']=0
            if key=='amplitude':tampered[key]['residue_mod_p']=17
            if key=='sha256':tampered[key]='f'*64
            self.assertFalse(verify_receipt(tampered))
        rec2=copy.deepcopy(rec)
        rec2['operator']['global_quadrant_mod4']=0
        from hashlib import sha256
        import json
        old=rec2.pop('sha256')
        rec2['sha256']=sha256(json.dumps(rec2,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertFalse(verify_receipt(rec2))
        self.assertFalse(verify_receipt({**rec,'outside_observation':True}))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            ExactOperator.identity(9)
        with self.assertRaises(ValueError):
            ExactOperator(11,((1,0),(0,0)))
        with self.assertRaises(ValueError):
            ExactOperator.transfer(11,'3')
        with self.assertRaises(ValueError):
            ExactOperator.identity(11).power(-1)
        with self.assertRaises(ValueError):
            ExactOperator.identity(11).compose(ExactOperator.identity(13))
        with self.assertRaises(ValueError):
            ExactSchedule(11,())
        with self.assertRaises(ValueError):
            ExactSchedule(11,(1,)).navigate(-2)
        with self.assertRaises(ValueError):
            ExactOperator.identity(11).apply_coordinate(np.ones(10),0)
        with self.assertRaises(ValueError):
            ExactAmplitude(11,False,1)
        with self.assertRaises(ValueError):
            ExactSchedule(11,(1,)).find_exact_operator_coordinate(ExactOperator.identity(13))


if __name__=='__main__':
    unittest.main()
