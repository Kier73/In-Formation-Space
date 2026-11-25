import unittest, random
from hashlib import sha256
from byte_ground import Source, Ground
from compose_ground import Composite, compose, decode, restore, certify

class Compose(unittest.TestCase):
    def test_mixed(self):
        r=random.Random(3)
        p=bytes(512)+r.randbytes(512)+b'AB'*256+bytes(range(256))*2
        s=Source(p);g,cost=compose(s);self.assertEqual(s.reads,len(p));self.assertLess(len(g.encode()),len(p)//2)
        d=certify(Source(p),g);self.assertEqual(d,sha256(p).hexdigest());h=restore(g.encode(),d);self.assertEqual(h,g)
        for _ in range(1000):
            a,b=sorted((r.randrange(len(p)+1),r.randrange(len(p)+1)))
            self.assertEqual(h.read(a,b),p[a:b]);self.assertEqual(h.total(a,b),sum(p[a:b]))
    def test_pruning(self):
        r=random.Random(19)
        for w in (0,1,16):
            for p in (bytes(4096),b'AB'*1024,r.randbytes(1024),bytes(range(256))*4):
                g,c=compose(Source(p),weight=w);h,d=compose(Source(p),weight=w,prune=False)
                self.assertEqual(g.encode(),h.encode());self.assertLessEqual(c['candidate_read_bytes'],d['candidate_read_bytes'])
        self.assertGreater(compose(Source(bytes(4096)))[1]['pruned'],0)
    def test_wire(self):
        p=b'AB'*128;g,_=compose(Source(p));w=g.encode();d=sha256(p).hexdigest()
        for bad in (w[:-1],w+b'X',b'X'+w[1:],w[:12]+bytes([99])+w[13:]):
            with self.assertRaises(ValueError):decode(bad)
        with self.assertRaises(ValueError):restore(w,'0'*64)
        x=bytearray(w);x[-1]^=1
        with self.assertRaises(ValueError):restore(bytes(x),d)
    def test_boundaries(self):
        for p in (b'X',bytes(65536),bytes(range(256))*256):
            g,_=compose(Source(p),minimum=256);self.assertEqual(decode(g.encode()).read(0,len(p)),p)
        with self.assertRaises(ValueError):Composite((Ground('raw',1,(b'',)),))
    def test_random(self):
        r=random.Random(6)
        for _ in range(60):
            p=r.randbytes(r.randrange(1,2048));g,_=compose(Source(p));self.assertEqual(g.read(0,len(p)),p);self.assertLessEqual(len(g.encode()),len(p)+17)
if __name__=='__main__':unittest.main()
