import random, unittest
from hashlib import sha256
from byte_ground import Source,Ground,admit,certify,propose,exact,realize,train,train_cost,benchmark,cost_campaign,corpus,actual_sources

class ByteGround(unittest.TestCase):
    def test_actions(self):
        r=random.Random(8)
        for p in corpus(91,100):
            g=exact(Source(p));self.assertEqual(certify(Source(p),g),sha256(p).hexdigest())
            for _ in range(12):
                a=r.randrange(len(p)+1);b=r.randrange(a,len(p)+1)
                self.assertEqual(g.read(a,b),p[a:b]);self.assertEqual(g.total(a,b),sum(p[a:b]))
    def test_tamper(self):
        p=b'AB'*128;g=propose(Source(p),'period');self.assertTrue(admit(Source(p),g))
        changed=p[:-1]+b'C';self.assertFalse(admit(Source(changed),g))
        with self.assertRaises(ValueError):certify(Source(changed),g)
        for bad in (Ground('period',256,(b'',)),Ground('sparse',256,(((3,1),(3,2)),)),Ground('raw',256,(b'AB',)),Ground('ramp',256,(256,1))):
            self.assertFalse(admit(Source(p),bad))
        result,k,f=realize(Source(changed),{'action':'period'});self.assertTrue(f);self.assertEqual(result.read(0,len(changed)),changed)
    def test_training(self):
        tree=train();report=benchmark(tree)
        self.assertEqual(report['adaptive']['sum_match'],400)
        self.assertLess(report['adaptive']['read_bytes'],report['exact']['read_bytes'])
        cost=cost_campaign(train_cost(4));self.assertEqual(cost['sum_match'],400)
        self.assertLess(cost['read_bytes']+4*cost['encoded_bytes'],report['adaptive']['read_bytes']+4*report['adaptive']['encoded_bytes'])
    def test_actual_sources(self):self.assertEqual(len(actual_sources(train_cost(4))),6)
    def test_small_and_boundaries(self):
        for p in (b'\0',b'X',b'XY',bytes(65536),bytes(range(256))*256):
            g=exact(Source(p));self.assertEqual(g.read(0,len(p)),p);self.assertEqual(g.total(0,len(p)),sum(p))
        for p in (b'',bytes(65537)):
            with self.assertRaises(ValueError):Source(p)

if __name__=='__main__':unittest.main()
