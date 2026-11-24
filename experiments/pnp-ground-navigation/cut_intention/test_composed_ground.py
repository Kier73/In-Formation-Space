"""Independent finite controls and source/receipt mutation regressions."""
from copy import deepcopy
import random
import unittest
from composed_ground import compile_ground, decide_with_hall
from verify_composed_ground import verify, verify_decision
from run_composed_ground import chain, xor_clauses


def php(p,h):
    rows=[tuple(range(i*h+1,(i+1)*h+1)) for i in range(p)]
    rows += [(-(i*h+j+1),-(k*h+j+1)) for j in range(h) for i in range(p) for k in range(i+1,p)]
    return p*h,rows


class Composition(unittest.TestCase):
    def test_random_sources(self):
        for n in range(1,8):
            for seed in range(50):
                rng=random.Random(seed)
                c=[tuple(v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),rng.randrange(0,min(n,3)+1))) for _ in range(seed%12)]
                r=compile_ground(c,n)
                brute=sum(all(any(bool(x&(1<<(abs(l)-1)))==(l>0) for l in row) for row in c) for x in range(1<<n))
                self.assertEqual(int(r['count']),brute);self.assertTrue(verify(c,n,r))
    def test_connected_count(self):
        n,c=chain(16);r=compile_ground(c,n)
        self.assertEqual(r['count'],'18');self.assertEqual(r['peak_scope'],4)
        self.assertGreater(len(r['pivots']),0);self.assertTrue(verify(c,n,r))
    def test_connected_unsat(self):
        n,c=chain(16,contradictory=True);r=compile_ground(c,n)
        self.assertEqual(r['status'],'UNSAT');self.assertTrue(verify(c,n,r))
    def test_hidden_multiplicity(self):
        c=xor_clauses((1,2,3))+[(1,4)]
        r=compile_ground(c,5)
        self.assertEqual(r['free_hidden'],2);self.assertEqual(r['count'],'12');self.assertTrue(verify(c,5,r))
    def test_projection_changes_boolean_count(self):
        c=xor_clauses((1,2))+xor_clauses((2,3))+[(1,4),(-3,-4)]
        r=compile_ground(c,4);self.assertEqual(r['count'],'2');self.assertTrue(verify(c,4,r))
    def test_no_clauses(self):
        r=compile_ground([],100);self.assertEqual(int(r['count']),1<<100);self.assertTrue(verify([],100,r))
    def test_both_parities(self):
        c=xor_clauses((1,2),0)+xor_clauses((1,2),1)
        r=compile_ground(c,2);self.assertEqual(r['count'],'0');self.assertTrue(verify(c,2,r))
    def test_source_mutation(self):
        n,c=chain(4);r=compile_ground(c,n);self.assertFalse(verify(c+[()],n,r))
    def test_count_forgery(self):
        n,c=chain(4);r=compile_ground(c,n);r['count']='999';self.assertFalse(verify(c,n,r))
    def test_row_space_forgery(self):
        n,c=chain(4);r=compile_ground(c,n);r['projected'][0][1]^=1;self.assertFalse(verify(c,n,r))
    def test_pivot_forgery(self):
        n,c=chain(4);r=compile_ground(c,n);r['pivots'][0][2]^=1;self.assertFalse(verify(c,n,r))
    def test_missing_source(self):
        n,c=chain(4);r=compile_ground(c,n);r['residual'].pop();self.assertFalse(verify(c,n,r))
    def test_order_forgery(self):
        n,c=chain(4);r=compile_ground(c,n);r['elimination_order'].pop();self.assertFalse(verify(c,n,r))
    def test_budget_refusal(self):
        n,c=chain(4);r=compile_ground(c,n,max_width=2);self.assertEqual(r['status'],'UNKNOWN')
        self.assertFalse(verify(c,n,r,max_width=2))
    def test_receiver_budget(self):
        n,c=chain(4);r=compile_ground(c,n);self.assertFalse(verify(c,n,r,max_width=5))
    def test_hall_affine_unsat(self):
        n,c=php(8,7);c+=xor_clauses((1,n+1,n+2));n+=2
        r=decide_with_hall(c,n);self.assertEqual(r['status'],'UNSAT');self.assertTrue(verify_decision(c,n,r));self.assertNotIn('count',r)
    def test_hall_affine_sat(self):
        n,c=php(4,4);c+=xor_clauses((1,n+1,n+2));n+=2
        r=decide_with_hall(c,n);self.assertEqual(r['status'],'SAT');self.assertTrue(verify_decision(c,n,r));self.assertNotIn('count',r)
    def test_hall_forgery(self):
        n,c=php(8,7);r=decide_with_hall(c,n);r['hall']['exclusions'].pop();self.assertFalse(verify_decision(c,n,r))

if __name__=='__main__':unittest.main()
