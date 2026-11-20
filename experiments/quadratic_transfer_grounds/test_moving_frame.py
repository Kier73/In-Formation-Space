"""TCN-006: dense-oracle, algebraic and refusal tests."""
import copy
import math
import unittest

import numpy as np

from cocycle import ExactOperator, ExactSchedule
from moving_frame import (MovingFrameGround, PhaseBlock, symplectic,
                          canonical_axis, cubic_echo_strength, dense_reference)


def assert_close(test, ground, reference, *, tol=2e-10):
    for y in range(ground.p):
        test.assertLess(abs(ground.amplitude(y, max_work=10**7)-reference[y]), tol, (y,ground.record()))


class MovingFrameTests(unittest.TestCase):
    def test_weyl_conjugation_noncommuting_directions(self):
        for p in (7,11,17):
            x=np.arange(p)
            half=pow(2,-1,p)
            rng=np.random.default_rng(p)
            v=rng.normal(size=p)+1j*rng.normal(size=p)
            def W(q,k,z):
                return np.exp(2j*np.pi*(k*(x-q*half)%p)/p)*np.roll(z,q)
            for a in (0,1,3):
                op=ExactOperator.transfer(p,a)
                for q,k in ((1,0),(0,1),(2,3)):
                    u=op.apply_full(W(q,k,op.inverse().apply_full(v)))
                    (A,B),(C,D)=op.m
                    qq=(A*q+B*k)%p
                    kk=(C*q+D*k)%p
                    self.assertLess(float(np.max(abs(u-W(qq,kk,v)))),2e-12)
            self.assertEqual(symplectic((1,0),(0,1),p),1)

    def test_moving_frame_single_nonquadratic_cubic(self):
        for p in (7,17,31):
            for a in (0,2):
                g=MovingFrameGround.start(p, source=3).after_cubic(5).after_schedule((a,),1)
                target=dense_reference(p,3,[{'kind':'cubic','c':5},{'kind':'transfer','a':a}])
                self.assertEqual(len(g.blocks),1)
                self.assertTrue(g.all_commute)
                assert_close(self,g,target)

    def test_harmonic_after_cubic_same_axis(self):
        p=31
        g=MovingFrameGround.start(p,4).after_cubic(8).after_harmonic(.7).after_harmonic(-.2)
        self.assertEqual(len(g.blocks),1)
        self.assertEqual(g.blocks[0].cubic,8)
        self.assertEqual(g.blocks[0].harmonics,((1,.49999999999999994),))
        target=dense_reference(p,4,[{'kind':'cubic','c':8},{'kind':'harmonic','strength':.7},{'kind':'harmonic','strength':-.2}])
        assert_close(self,g,target)
        self.assertLess(g.estimated_work(3),50)

    def test_cubic_echo_F_squared(self):
        p=31
        first=MovingFrameGround.start(p,4).after_cubic(7)
        op,products=ExactSchedule(p,(0,)).navigate(2)
        self.assertEqual(cubic_echo_strength(op,7),7)
        cancelled=first.after_clifford(op,products).after_cubic(7)
        self.assertEqual(len(cancelled.blocks),0)
        ref=dense_reference(p,4,[{'kind':'cubic','c':7},{'kind':'transfer','a':0},
                                 {'kind':'transfer','a':0},{'kind':'cubic','c':7}])
        assert_close(self,cancelled,ref)
        self.assertEqual(cancelled.estimated_work(1),1)

    def test_dilation_echo_arbitrary_symplectic(self):
        p=41
        a=2; d=pow(a,-1,p)
        op=ExactOperator(p,((a,0),(0,d)))
        strength=cubic_echo_strength(op,13)
        g=MovingFrameGround.start(p,8).after_cubic(13).after_clifford(op).after_cubic(strength)
        self.assertEqual(g.blocks,())
        ref=dense_reference(p,8,[{'kind':'cubic','c':13},{'kind':'clifford','op':op},{'kind':'cubic','c':strength}])
        assert_close(self,g,ref)

    def test_giant_echo_consistent_with_periodic_F(self):
        p=17
        n=10**100+2
        op,products=ExactSchedule(p,(0,)).navigate(n)
        self.assertEqual(cubic_echo_strength(op,5),5)
        g=MovingFrameGround.start(p,9).after_cubic(5).after_clifford(op,products).after_cubic(5)
        self.assertEqual(len(g.blocks),0)
        self.assertLess(g.clifford_products,750)
        target=ExactSchedule(p,(0,)).navigate(2)[0]
        self.assertEqual(g.core,target)
        self.assertAlmostEqual(abs(g.amplitude(9)),0)
        self.assertAlmostEqual(abs(g.amplitude((-9)%p)),1)

    def test_gate_after_one_fourier_does_not_echo(self):
        p=17
        op=ExactOperator.transfer(p,0)
        with self.assertRaisesRegex(ValueError,'noncommuting'):
            cubic_echo_strength(op,7)
        g=MovingFrameGround.start(p,4).after_cubic(7).after_clifford(op).after_cubic(7)
        self.assertEqual(len(g.blocks),2)
        self.assertFalse(g.all_commute)
        self.assertEqual(g.admission([1],max_work=200)['status'],'refused_cost')
        with self.assertRaisesRegex(ValueError,'refused'):
            g.amplitude(1,max_work=200)
        ref=dense_reference(p,4,[{'kind':'cubic','c':7},{'kind':'transfer','a':0},{'kind':'cubic','c':7}])
        assert_close(self,g,ref)

    def test_interleaved_mixing_and_phase_preservation(self):
        p=17
        g=MovingFrameGround.start(p,5)
        events=[]
        for kind,amount in [('cubic',4),('transfer',2),('harmonic',.31),('transfer',0),('cubic',-9)]:
            if kind=='transfer':
                g=g.after_schedule((amount,),1)
                events.append({'kind':kind,'a':amount})
            elif kind=='cubic':
                g=g.after_cubic(amount)
                events.append({'kind':kind,'c':amount})
            else:
                g=g.after_harmonic(amount)
                events.append({'kind':kind,'strength':amount})
        ref=dense_reference(p,5,events)
        assert_close(self,g,ref)
        self.assertLess(abs(np.linalg.norm(ref)-1),1e-12)

    def test_harmonic_echo_after_F_squared(self):
        p=31
        g=MovingFrameGround.start(p,3).after_harmonic(.55).after_schedule((0,),2).after_harmonic(-.55)
        self.assertEqual(g.blocks,())
        ref=dense_reference(p,3,[{'kind':'harmonic','strength':.55},
                                 {'kind':'transfer','a':0},{'kind':'transfer','a':0},
                                 {'kind':'harmonic','strength':-.55}])
        assert_close(self,g,ref)

    def test_explicit_error_and_input_refusal(self):
        with self.assertRaises(ValueError):
            MovingFrameGround.start(9)
        with self.assertRaises(ValueError):
            MovingFrameGround.start(17, 17)
        g=MovingFrameGround.start(17,4)
        with self.assertRaises(ValueError):
            g.after_harmonic(float('nan'))
        with self.assertRaises(ValueError):
            g.after_cubic(0.3)
        with self.assertRaises(ValueError):
            g.after_schedule((2,),-1)
        with self.assertRaises(ValueError):
            g.admission((1,1),100)
        with self.assertRaises(ValueError):
            PhaseBlock(17,(0,0))
        with self.assertRaises(ValueError):
            canonical_axis((0,0),17)


if __name__=='__main__':
    unittest.main()
