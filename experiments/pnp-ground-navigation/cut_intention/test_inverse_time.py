import unittest,random,copy
from temporal_ground import compile_transport,Navigator
from run_temporal_ground import law,encode_law,step
from inverse_time import seek
from verify_inverse_time import verify_seek
D={'contract':'test','circuit':{'gates':[],'outputs':[]}}

class InverseTests(unittest.TestCase):
    def test_random_exhaustive(self):
        rng=random.Random(2121)
        for _ in range(100):
            w=rng.randrange(1,3);m=rng.randrange(1,5);k=w*m;p=list(range(m));rng.shuffle(p);f=[[rng.randrange(1<<w) for _ in range(1<<w)] for _ in p];s=encode_law(k,w,p,f);g=compile_transport(s,k,w);nav=Navigator(k,w,g,D);c=rng.getrandbits(k);mask=rng.getrandbits(k);value=rng.getrandbits(k)&mask;start=rng.randrange(20)
            z=c
            for t in range(start):z=step(z,k,w,p,f)
            seen=set();answer=None;t=start
            while z not in seen:
                if z&mask==value:answer=t;break
                seen.add(z);z=step(z,k,w,p,f);t+=1
            r=seek(nav,c,mask,value,start);self.assertTrue(verify_seek(s,k,w,g,c,mask,value,start,r));self.assertEqual(int(r['time']) if r['status']=='FOUND' else None,answer)
    def test_large_inverse(self):
        k=1023;s,p,f,c,P=law(k,3,long_period=True);g=compile_transport(s,k,3);nav=Navigator(k,3,g,D);start=10**1000+173;desired=start+P//2;mask=(1<<k)-1;value=nav.jump(c,desired);r=seek(nav,c,mask,value,start);self.assertEqual(int(r['time']),desired);self.assertTrue(verify_seek(s,k,3,g,c,mask,value,start,r))
        bad=copy.deepcopy(r);bad['time']=str(desired+P);self.assertFalse(verify_seek(s,k,3,g,c,mask,value,start,bad))
    def test_transient(self):
        s=encode_law(1,1,[0],[[0,0]]);g=compile_transport(s,1,1);nav=Navigator(1,1,g,D);r=seek(nav,1,1,1);self.assertEqual(r['time'],'0');self.assertTrue(verify_seek(s,1,1,g,1,1,1,0,r));r=seek(nav,1,1,1,1);self.assertEqual(r['status'],'UNREACHABLE');self.assertTrue(verify_seek(s,1,1,g,1,1,1,1,r))
    def test_budget(self):
        s,p,f,c,P=law(24,3,long_period=True);g=compile_transport(s,24,3);nav=Navigator(24,3,g,D);r=seek(nav,c,(1<<24)-1,c,max_local=1);self.assertEqual(r['status'],'UNKNOWN');self.assertFalse(verify_seek(s,24,3,g,c,(1<<24)-1,c,0,r,max_local=1))
    def test_target_contract(self):
        s=encode_law(1,1,[0],[[0,1]]);g=compile_transport(s,1,1);nav=Navigator(1,1,g,D);self.assertRaises(ValueError,seek,nav,0,0,1)

if __name__=='__main__':unittest.main()
