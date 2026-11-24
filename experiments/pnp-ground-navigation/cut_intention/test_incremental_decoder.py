import unittest,random,copy
from test_interpolant_ground import chain
from shared_proof import synthesize_shared,evaluate
from incremental_decoder import DecoderState
from verify_incremental_decoder import EventReceiver

class Events(unittest.TestCase):
    def setup(self):
        n,s,q,f=chain(5);fs=[f,(-f[0],),q[0]];r=synthesize_shared(n,s,q,fs);return (n,s,q,fs,r),DecoderState(r['circuit'],len(q),0),EventReceiver(n,s,q,fs,r,0)
    def test_all_events(self):
        a,p,v=self.setup();rng=random.Random(20)
        for _ in range(200):
            code=rng.randrange(32);r=p.update(code);self.assertTrue(v.accept(r));self.assertEqual(r['outputs'],evaluate(a[-1]['circuit'],code,5))
    def test_atomic_forgery(self):
        a,p,v=self.setup();r=p.update(31);self.assertTrue(r['checks']);old=(v.epoch,v.code,v.values.copy())
        for change in ('missing','bit','epoch','circuit','extra','output'):
            z=copy.deepcopy(r)
            if change=='missing':z['checks'].pop()
            if change=='bit':z['checks'][0][1]^=1
            if change=='epoch':z['epoch']+=1
            if change=='circuit':z['circuit']='forged'
            if change=='extra':z['checks'].append(z['checks'][-1])
            if change=='output':z['outputs'][0]^=1
            self.assertFalse(v.accept(z),change);self.assertEqual(old,(v.epoch,v.code,v.values))
        self.assertTrue(v.accept(r));self.assertFalse(v.accept(r))
    def test_no_change(self):
        _,p,v=self.setup();r=p.update(0);self.assertEqual(r['checks'],[]);self.assertTrue(v.accept(r))
    def test_invalid_code(self):
        _,p,v=self.setup()
        for code in (-1,32,True):
            with self.assertRaises(ValueError):p.update(code)
    def test_source_binding(self):
        a,p,v=self.setup();n,s,q,fs,r=a
        with self.assertRaises(ValueError):EventReceiver(n,s[:-1],q,fs,r,0)
    def test_unknown_output(self):
        n=3;s=[];q=[(1,)];fs=[(1,),(2,)];r=synthesize_shared(n,s,q,fs);p=DecoderState(r['circuit'],1,0);v=EventReceiver(n,s,q,fs,r,0);z=p.update(1);self.assertEqual(z['outputs'],[1,None]);self.assertTrue(v.accept(z))
    def test_adaptive(self):
        a,p,v=self.setup();rng=random.Random(2120)
        modes=set()
        for _ in range(100):
            code=rng.randrange(32);r=p.update(code,mode='auto');modes.add(r.get('mode','delta'))
            self.assertTrue(v.accept(r));self.assertEqual(r['outputs'],evaluate(a[-1]['circuit'],code,5))
        self.assertEqual(modes,{'full','delta'})
    def test_full_forgery(self):
        a,p,v=self.setup();r=p.update(31,mode='full');z=copy.deepcopy(r);z['outputs'][0]^=1
        self.assertFalse(v.accept(z));self.assertEqual(v.epoch,0);self.assertTrue(v.accept(r));self.assertTrue(v.accept(p.update(30)))
    def test_many_topologies(self):
        rng=random.Random(2000)
        for k in (3,5,8,16,32):
            for mixed in (True,False):
                n,s,q,f=chain(k,mixed);fs=[f,(-f[0],),q[0]];r=synthesize_shared(n,s,q,fs);p=DecoderState(r['circuit'],k,0);v=EventReceiver(n,s,q,fs,r,0)
                for _ in range(50):
                    code=rng.getrandbits(k);z=p.update(code);self.assertTrue(v.accept(z));self.assertEqual(z['outputs'],evaluate(r['circuit'],code,k))

if __name__=='__main__':unittest.main()
