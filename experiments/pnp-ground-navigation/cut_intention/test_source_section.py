import unittest,copy,random
from source_section import compile_section,section_witness
from verify_source_section import verify_section
from verify_temporal_ground import Receiver,check_witness
from run_temporal_ground import source,law,witness,oracle
from shared_proof import synthesize_shared
from temporal_ground import compile_transport,Navigator

class SectionTests(unittest.TestCase):
    def test_source_section(self):
        for mixed in (True,False):
            n,s,q,fs,ids=source(6,mixed);r=compile_section(n,s,q);self.assertIsNotNone(r);self.assertTrue(verify_section(n,s,q,r))
            for c in range(64):self.assertTrue(check_witness(n,s,q,c,section_witness(n,q,r,c)))
    def test_signed_and_free(self):
        n=3;s=[];q=[(-1,2)];r=compile_section(n,s,q);self.assertTrue(verify_section(n,s,q,r))
        for c in (0,1):self.assertTrue(check_witness(n,s,q,c,section_witness(n,q,r,c)))
    def test_not_surjective(self):self.assertIsNone(compile_section(1,[(-1,)],[(1,)]))
    def test_overlapping(self):self.assertIsNone(compile_section(2,[],[(1,),(1,2)]))
    def test_forgery(self):
        n,s,q,_,_=source(6,True);r=compile_section(n,s,q)
        for key,edit in [('gates',lambda x:x.pop()),('gates',lambda x:x[0]['table'].__setitem__(0,x[0]['table'][0]^1)),('free',lambda x:x.append(abs(q[0][0])))]:
            h=copy.deepcopy(r);edit(h[key]);self.assertFalse(verify_section(n,s,q,h))
        self.assertFalse(verify_section(n,s+[(q[0][0],)],q,r))
    def test_temporal_receiver(self):
        k=24;n,s,q,fs,ids=source(k,True);r=synthesize_shared(n,s,q,fs);ts,p,f,_,_=law(k,3);g=compile_transport(ts,k,3);sec=compile_section(n,s,q);v=Receiver(n,s,q,fs,r,ts,3,g,12345,section=sec);nav=Navigator(k,3,g,r)
        for t in (0,1,2,10**1000+173):
            z=nav.result(12345,t);self.assertTrue(v.accept(t,z));self.assertEqual(z['outputs'],oracle(int(z['code']),k,True,ids))
        bad=copy.deepcopy(sec);bad['gates'].pop();self.assertRaises(ValueError,Receiver,n,s,q,fs,r,ts,3,g,12345,section=bad)
    def test_uncovered_clause(self):
        n,s,q,_,_=source(6,True);self.assertIsNone(compile_section(n,s+[(q[0][0],q[1][0])],q))

if __name__=='__main__':unittest.main()
