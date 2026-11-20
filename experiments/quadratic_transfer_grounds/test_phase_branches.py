"""TCN-004 independent dense-FFT baselines, exact phase and refusal tests."""
import math
import unittest

import numpy as np

from branch import (SparseGround, StructuredState, dense_quadratic_reference,
                    fit_frame, gate_phases, harmonic_taylor_modes)
from cocycle import ExactSchedule, ExactOperator
from witness import harmonic_receipt, recheck_harmonic_receipt, restore_state


class AlgebraicFrameTests(unittest.TestCase):
    def test_dense_reference_independent_of_cocycle(self):
        for p in (5,11,31,71):
            rng=np.random.default_rng(p)
            src=rng.normal(size=p)+1j*rng.normal(size=p)
            source=src/np.linalg.norm(src)
            for pat,n in (((1,),1),((2,4),7),((1,3,7),14)):
                op,_=ExactSchedule(p,pat).navigate(n)
                actual=op.apply_full(source)
                baseline=dense_quadratic_reference(p,pat,n,source)
                self.assertLess(np.linalg.norm(actual-baseline),3e-12)

    def test_phase_aware_interference_multiple_modes(self):
        for p in (5,11,31,71,127):
            rng=np.random.default_rng(p+700)
            coeffs=tuple((b, complex(rng.normal(),rng.normal())) for b in (0,1,4))
            for kind in ('flat','delta'):
                st=StructuredState(p,kind,3 if kind=='flat' else None,coeffs)
                for pattern,n in (((3,),1),((2,5),6),((5,1,7),11),((0,4,8),23)):
                    nexts,products=st.after_schedule(pattern,n)
                    independent=dense_quadratic_reference(p,pattern,n,st.dense())
                    self.assertLess(np.max(np.abs(nexts.dense()-independent)),2e-11)
                    self.assertEqual(len(nexts.terms),len(st.terms))
                    self.assertLessEqual(products,2*n+len(pattern))

    def test_inverse_phase_and_long_coordinate(self):
        for p in (31,127):
            pattern=(2,5,9)
            cycle=ExactSchedule(p,pattern)
            period=cycle.full_period_bound()
            st=StructuredState.flat(p,3,4,coefficient=.5+.2j)
            st=StructuredState(p,st.kind,st.a,st.terms+((9,.2-.25j),))
            huge=10**100+1234567
            long,products=st.after_schedule(pattern,huge)
            short,_=st.after_schedule(pattern,huge%period)
            self.assertLess(np.max(abs(long.dense()-short.dense())),2e-11)
            self.assertLess(products,1000)
            self.assertEqual(long.error_l2_ideal,0)

    def test_cayley_noncommutativity_is_preserved(self):
        st=StructuredState.flat(31,4,2)
        first,_=st.after_schedule((1,3),2)
        reversed_,_=st.after_schedule((3,1),2)
        self.assertGreater(np.linalg.norm(first.dense()-reversed_.dense()),0.1)


class NonquadraticTests(unittest.TestCase):
    def test_procedural_gate_exact_amplitudes_with_bound(self):
        for p in (11,31,127,257):
            for g in (0.2,0.7,1.2):
                st=StructuredState.flat(p,2,3)
                out,rec=st.after_harmonic(g,taylor_order=14,max_terms=11,
                                          absolute_error_budget=.2)
                self.assertIsNotNone(out)
                reference=gate_phases(p,'harmonic',g)*st.dense()
                error=float(np.linalg.norm(out.dense()-reference))
                self.assertLessEqual(error,rec['cumulative_error_bound_ideal']+1e-10)
                self.assertEqual(rec['input_kind'],'flat')
                self.assertEqual(rec['procedural_without_full_state'],True)
                self.assertLessEqual(len(out.terms),11)

    def test_taylor_remainder_is_valid_pointwise(self):
        for g in (0.0,.2,0.7,2.0):
            coeffs,bound=harmonic_taylor_modes(g,12)
            angles=np.linspace(0,2*np.pi,4096,endpoint=False)
            approximation=sum(h*np.exp(1j*k*angles) for k,h in coeffs.items())
            truth=np.exp(1j*g*np.cos(angles))
            self.assertLessEqual(float(np.max(abs(approximation-truth))),bound+1e-13)

    def test_delta_gate_does_not_generate_branches(self):
        st=StructuredState(31,'delta',None,((4,.25+.3j),(7,.7-.4j)))
        out,receipt=st.after_harmonic(.7,taylor_order=0,max_terms=2,
                                       absolute_error_budget=0)
        self.assertIsNotNone(out)
        self.assertEqual(out.error_l2_ideal,0)
        self.assertEqual(len(out.terms),2)
        self.assertLess(np.max(abs(out.dense()-gate_phases(31,'harmonic',.7)*st.dense())),1e-14)

    def test_composition_error_accumulates_and_refuses(self):
        p=127
        st=StructuredState.flat(p,7,13)
        truth=st.dense()
        st,_=st.after_schedule((2,7,9),37)
        truth=dense_quadratic_reference(p,(2,7,9),37,truth)
        st,rec=st.after_harmonic(.7,taylor_order=12,max_terms=7,absolute_error_budget=.01)
        self.assertIsNotNone(st)
        truth*=gate_phases(p,'harmonic',.7)
        self.assertLessEqual(np.linalg.norm(st.dense()-truth),st.error_l2_ideal+1e-10)
        old=st
        st,_=st.after_schedule((2,7,9),56)
        truth=dense_quadratic_reference(p,(2,7,9),56,truth)
        self.assertLessEqual(np.linalg.norm(st.dense()-truth),st.error_l2_ideal+1e-10)
        refused,rec2=st.after_harmonic(.7,taylor_order=12,max_terms=7,absolute_error_budget=.01)
        self.assertIsNone(refused)
        self.assertEqual(rec2['status'],'refused')
        self.assertGreater(rec2['cumulative_error_bound_ideal'],.01)
        self.assertEqual(len(old.terms),7) # transaction does not mutate old state
        self.assertEqual(rec['status'],'admitted')

    def test_cubic_refuses_when_rugged(self):
        for p in (31,71,127):
            st=SparseGround.quadratic(p,7,3)
            refused,report=st.after_gate('cubic',5,max_terms=8,max_omission=.1)
            self.assertIsNone(refused)
            self.assertEqual(report['status'],'refused')
            self.assertGreater(report['rank_required_for_single_step'],8)

    def test_full_scan_energy_agrees_with_orthonormal_projection(self):
        p=31
        v=gate_phases(p,'cubic',5)*StructuredState.flat(p,3,2).dense()
        fit=fit_frame(v,p=p,max_terms=5,max_relative_omission=.1)
        reconstructed=StructuredState(p,'flat',fit.a,fit.terms).dense()
        self.assertAlmostEqual(np.linalg.norm(v-reconstructed),fit.omitted_l2,places=10)
        self.assertEqual(fit.candidates,p)
        self.assertGreater(fit.required_rank,5)
        self.assertLess(fit.relative_energy(),.95)

    def test_difference_between_procedural_and_general_cost(self):
        p=127
        st=StructuredState.flat(p,3,2)
        v=gate_phases(p,'harmonic',.7)*st.dense()
        baseline=fit_frame(v,p=p,max_terms=5)
        proc,rec=st.after_harmonic(.7,taylor_order=12,max_terms=5,absolute_error_budget=.02)
        self.assertIsNotNone(proc)
        self.assertEqual(baseline.candidates,p)
        self.assertLessEqual(rec['generated_taylor_modes'],25)
        self.assertEqual(rec['kept_modes'],5)
        self.assertLess(np.linalg.norm(v-proc.dense()),.02)

    def test_reconstructable_witness_and_tamper(self):
        import copy
        st=StructuredState.flat(31,4,2)
        record=harmonic_receipt(st,.7,order=12,rank=7,budget=.01)
        self.assertTrue(recheck_harmonic_receipt(record))
        copy1=copy.deepcopy(record)
        copy1['output']['terms'][0][1]=float(50).hex()
        self.assertFalse(recheck_harmonic_receipt(copy1))
        copy2=copy.deepcopy(record)
        copy2['decision']['cumulative_error_bound_ideal']=0.0
        self.assertFalse(recheck_harmonic_receipt(copy2))
        copy3=copy.deepcopy(record)
        copy3['sha256']='0'*64
        self.assertFalse(recheck_harmonic_receipt(copy3))

    def test_refusal_witness_stays_refusal(self):
        st=StructuredState.flat(31,4,2)
        rec=harmonic_receipt(st,2.0,order=4,rank=1,budget=0.01)
        self.assertEqual(rec['decision']['status'],'refused')
        self.assertTrue(recheck_harmonic_receipt(rec))
        self.assertIsNone(rec['output'])

    def test_bad_inputs_are_refused(self):
        st=StructuredState.flat(31,2,3)
        for v in [float('nan'),float('inf'),5.2]:
            with self.assertRaises(ValueError):
                st.after_harmonic(v,taylor_order=6,max_terms=4,absolute_error_budget=.1)
        with self.assertRaises(ValueError):
            st.after_harmonic(.4,taylor_order=-1,max_terms=4,absolute_error_budget=.1)
        with self.assertRaises(ValueError):
            st.after_harmonic(.4,taylor_order=4,max_terms=0,absolute_error_budget=.1)
        with self.assertRaises(ValueError):
            st.after_operator(ExactOperator.identity(37))
        with self.assertRaises(ValueError):
            StructuredState(31,'flat',3,((1,1+0j),(1,2+0j)))
        with self.assertRaises(ValueError):
            SparseGround.quadratic(31,3,1).after_gate('cubic',5,max_terms=4,max_omission=-.1)


if __name__=='__main__':
    unittest.main()
