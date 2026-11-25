import random, unittest
from hashlib import sha256
from template_ground import Template,learn,apply,qualify,receive

class Templates(unittest.TestCase):
    def test_action(self):
        def make(a,b):return b'header'+bytes([a,b])+bytes(32)+bytes([b,a])+b'end'
        t=learn([make(1,2),make(4,3),make(6,8)]);self.assertEqual(len(t.groups),2);self.assertEqual(Template.decode(t.encode()),t)
        r=random.Random(77)
        for _ in range(100):
            p=make(r.randrange(256),r.randrange(256));inst=t.match(p);self.assertIsNotNone(inst);g=receive(inst.encode(),t,sha256(p).hexdigest())
            for _ in range(10):
                a,b=sorted((r.randrange(len(p)+1),r.randrange(len(p)+1)));self.assertEqual(g.read(a,b),p[a:b]);self.assertEqual(g.total(a,b),sum(p[a:b]))
    def test_counterexample_and_tamper(self):
        p=b'A'*80+b'B'*2;t=learn([p,b'A'*80+b'C'*2]);g=t.match(p);w=g.encode()
        for bad in (w[:-1],w+b'X',w[:4]+bytes(32)+w[36:],w[:-1]+bytes([99])):
            with self.assertRaises(ValueError):receive(bad,t,sha256(p).hexdigest())
        changed=p[:-1]+b'X';self.assertIsNone(t.match(changed));self.assertEqual(receive(apply(changed,t),t,sha256(changed).hexdigest()).read(0,len(changed)),changed)
        for bad in (t.encode()[:-1],t.encode()+b'X'):
            with self.assertRaises(ValueError):Template.decode(bad)
        with self.assertRaises(ValueError):Template(bytes(8),((1,2),(2,3)))
    def test_admission(self):
        r=random.Random(1);examples=[r.randbytes(128) for _ in range(5)];t=learn(examples);self.assertIsNone(qualify(t,examples)[0])
if __name__=='__main__':unittest.main()
