import unittest,random,copy,json
from temporal_ground import compile_transport,Navigator
from verify_temporal_ground import verify_transport,Receiver
from shared_proof import synthesize_shared
from run_temporal_ground import encode_law,law,step,power_oracle,witness,source,oracle,period_control

D={'contract':'test','circuit':{'gates':[],'outputs':[]}}

class TemporalTests(unittest.TestCase):
    def make(self,k=24):
        s,p,f,_,_=law(k,3);g=compile_transport(s,k,3);self.assertTrue(verify_transport(s,k,3,g));return s,p,f,g,Navigator(k,3,g,D)
    def test_random(self):
        rng=random.Random(21)
        for _ in range(150):
            w=rng.randrange(1,4);m=rng.randrange(1,6);k=w*m;p=list(range(m));rng.shuffle(p);f=[[rng.randrange(1<<w) for _ in range(1<<w)] for _ in p];s=encode_law(k,w,p,f);g=compile_transport(s,k,w);self.assertTrue(verify_transport(s,k,w,g));nav=Navigator(k,w,g,D);c=rng.getrandbits(k);z=c
            for t in range(25):
                self.assertEqual(nav.jump(c,t),z);z=step(z,k,w,p,f)
            t=10**100+47;self.assertEqual(nav.jump(c,t),power_oracle(c,k,w,p,f,t))
    def test_missing(self):
        s,p,f,g,nav=self.make();self.assertFalse(verify_transport(s[:-1],24,3,g));self.assertRaises(ValueError,compile_transport,s[:-1],24,3)
    def test_ambiguous(self):self.assertRaises(ValueError,compile_transport,[(1,2)],1,1)
    def test_nontotal(self):self.assertRaises(ValueError,compile_transport,[(1,),(-2,)],1,1)
    def test_fanout(self):
        s=encode_law(2,1,[0,0],[[0,1],[0,1]]);self.assertRaises(ValueError,compile_transport,s,2,1)
    def test_overlap(self):
        s=encode_law(2,1,[0,1],[[0,1],[0,1]])+[(3,4)];self.assertRaises(ValueError,compile_transport,s,2,1)
    def test_forged_ground(self):
        s,p,f,g,nav=self.make()
        for key,edit in [('depth',lambda x:x.__setitem__(0,x[0]+1)),('entry',lambda x:x.__setitem__(0,(x[0]+1)%len(x))),('pred',lambda x:x.__setitem__(0,x[1])),('tables',lambda x:x[0].__setitem__(0,x[0][0]^1)),('cycles',lambda x:x.pop())]:
            h=copy.deepcopy(g);edit(h[key]);self.assertFalse(verify_transport(s,24,3,h))
    def test_roundtrip(self):
        s,p,f,g,nav=self.make();self.assertTrue(verify_transport(s,24,3,json.loads(json.dumps(g))))
    def test_time_contract(self):
        _,_,_,_,nav=self.make()
        for t in (-1,True,1<<4096):self.assertRaises(ValueError,nav.jump,0,t)
    def test_semigroup(self):
        _,_,_,_,nav=self.make();a,b=10**100+2,10**200+7;self.assertEqual(nav.jump(nav.jump(12345,a),b),nav.jump(12345,a+b))
    def test_long_period(self):self.assertTrue(period_control()['exact'])
    def receiver(self):
        k=24;n,s,q,fs,ids=source(k,True);r=synthesize_shared(n,s,q,fs);ts,p,f,g,_=self.make(k);nav=Navigator(k,3,g,r);c=12345;v=Receiver(n,s,q,fs,r,ts,3,g,c,witness(c,k,True));return k,n,s,q,fs,ids,r,ts,g,nav,c,v
    def test_actual_decoder(self):
        k,n,s,q,fs,ids,r,ts,g,nav,c,v=self.receiver()
        for t in (0,1,2,123,10**1000+173):
            x=nav.jump(c,t);z=nav.result(c,t,witness(x,k,True));self.assertTrue(v.accept(t,z));self.assertEqual(z['outputs'],oracle(x,k,True,ids))
    def test_forged_receipt(self):
        k,n,s,q,fs,ids,r,ts,g,nav,c,v=self.receiver();t=19;x=nav.jump(c,t);z=nav.result(c,t,witness(x,k,True))
        for key,bad in [('initial','0'),('time','18'),('code',str(x^1)),('witness','0'),('key','bad'),('outputs',[True]*len(fs))]:
            h=copy.deepcopy(z);h[key]=bad;self.assertFalse(v.accept(t,h),key)
        self.assertFalse(v.accept(t+1,z));self.assertTrue(v.accept(t,z))
    def test_initial_witness(self):
        k,n,s,q,fs,ids,r,ts,g,nav,c,v=self.receiver();self.assertRaises(ValueError,Receiver,n,s,q,fs,r,ts,3,g,c,0)
    def test_out_of_image(self):
        # q=(x1), source fixes x1=0. T flips the bit: valid transition code but
        # not a source-observable state at t=1. No terminal decoder admission.
        n=1;s=[(-1,)];q=[(1,)];fs=[(1,)];r=synthesize_shared(n,s,q,fs);ts=encode_law(1,1,[0],[[1,0]]);g=compile_transport(ts,1,1);nav=Navigator(1,1,g,r);v=Receiver(n,s,q,fs,r,ts,1,g,0,0);self.assertFalse(v.accept(1,nav.result(0,1,0)));self.assertTrue(v.accept(2,nav.result(0,2,0)))

if __name__=='__main__':unittest.main()
