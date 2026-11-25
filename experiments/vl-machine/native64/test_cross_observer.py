import unittest
from cross_observer import kernel,discover,verify,navigate,observations,train,campaign,iterative

class CrossObserver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.k=kernel()
    def test_projection(self):
        p=[('mul',0,3),('add',0,7),('addr',1,2),('addr',2,1)]
        g,v,w=discover(self.k,p,0);self.assertTrue(verify(p,0,g));self.assertEqual(g['ids'],[0])
        for t in (0,1,17,1<<40):
            self.assertEqual(navigate(g,[11,5,8,13],0,t),self.k.evaluate([11,5,8,13],p,t)['registers'][0])
        g['matrix'][0][0]^=1;self.assertFalse(verify(p,0,g))
    def test_multistep_dependency(self):
        p=[('addr',0,1),('addr',1,2),('add',2,3)];g,_,_=discover(self.k,p,0)
        self.assertEqual(g['ids'],[0,1,2]);self.assertTrue(verify(p,0,g));self.assertFalse(verify(p,0,{'ids':[0,1],'matrix':[[1,1,0],[0,1,0],[0,0,1]]}))
        self.assertEqual(navigate(g,[1,2,3,4],0,11),iterative(p,[1,2,3,4],11)[0])
    def test_basis_counterexample(self):
        p=[('mulr',0,1)];g,_,_=discover(self.k,p,0)
        self.assertEqual(g['matrix'][0],[0,0]);self.assertFalse(verify(p,0,g));self.assertEqual(self.k.evaluate([2,3,0,0],p,1)['registers'][0],6)
    def test_neural_and_native(self):
        rows=list(observations(self.k,190,120));w=train(rows);s,r=campaign(self.k,w,list(observations(self.k,195,40,True)))
        self.assertEqual(s['queries'],160);self.assertEqual(s['eligible'],s['symbolic_baseline_eligible']);self.assertEqual(s['projected']+s['missed'],s['eligible'])
if __name__=='__main__':unittest.main()
