import random
import unittest
from dataclasses import replace
from machine import *

class Tests(unittest.TestCase):
    def test_general(self):
        p = Program((Node("input"),Node("const",value=3),Node("and",(0,1)),
                     Node("lt",(2,1)),Node("xor",(0,1)),Node("select",(3,4,0))),5)
        for x in range(100): self.assertEqual(demand(p,x)[0],reference(p,x))
        self.assertIsNone(discover(p))

    def test_demand_dead(self):
        p = Program((Node("input"),Node("mul",(0,0)),Node("const",value=7)),2)
        self.assertEqual(demand(p,9),(7,0))
        self.assertTrue(verify(p,discover(p)))

    def test_affine_fuzz(self):
        r = random.Random(47)
        m = Machine()
        for _ in range(300):
            p = affine(r.getrandbits(32),r.getrandbits(32))
            g = discover(p)
            self.assertTrue(verify(p,g))
            self.assertFalse(verify(p,replace(g,b=g.b^1)))
            m.admit(p,g)
            for _ in range(12):
                x = r.getrandbits(32)
                self.assertEqual(m.observe(p,x)["output"],reference(p,x))

    def test_jump(self):
        r = random.Random(11)
        for _ in range(300):
            a,b,x = (r.getrandbits(32) for _ in range(3))
            n = r.randrange(256)
            y=x
            for i in range(n): y=(a*y+b)&MASK
            self.assertEqual(jump(a,b,x,n)[0],y)
        x=jump(3,7,11,10**12)[0]
        self.assertEqual(jump(3,7,x,10**12)[0],jump(3,7,11,2*10**12)[0])
        self.assertLess(jump(3,7,11,10**12)[1],81)

    def test_session_isolation(self):
        m=Machine(); p=affine(3,7)
        m.open("a",11); m.open("b",11)
        self.assertEqual(m.advance("a",p,100)["route"],"iteration")
        m.admit(p,discover(p))
        self.assertEqual(m.advance("b",p,100)["end"],m._sessions["a"][0])
        self.assertEqual(m.advance("b",p,0)["end"],m._sessions["a"][0])
        with self.assertRaises(ValueError): m.open("b",0)

    def test_learn_layered(self):
        r=random.Random(99)
        m=Machine()
        for depth in [0,1,2,8,128]:
            p=layered_affine(r.getrandbits(32),r.getrandbits(32),depth)
            report=m.learn(p)
            self.assertEqual(report["admitted"],depth>1)
            for _ in range(32):
                x=r.getrandbits(32)
                result=m.observe(p,x)
                self.assertEqual(result["output"],reference(p,x))
                self.assertEqual(result["word_ops"],2 if depth>1 else 2*depth)

    def test_parse(self):
        p=parse_program('{"nodes":[{"op":"input"},{"op":"const","value":7},{"op":"xor","args":[0,1]}],"output":2}')
        self.assertEqual(demand(p,2),(5,1))
        self.assertFalse(Machine().learn(p)["admitted"])
        for raw in ['[]','{"nodes":[{"op":[] }],"output":0}','{"nodes":[{"op":"input","args":1}],"output":0}']:
            with self.assertRaises(ValueError): parse_program(raw)

    def test_reject(self):
        with self.assertRaises(ValueError): Program((Node("add",(0,0)),),0)
        with self.assertRaises(ValueError): affine(-1,0)
        p=affine(3,7)
        with self.assertRaises(ValueError): Machine().admit(p,discover(affine(3,8)))
        with self.assertRaises(ValueError): jump(3,7,0,-1)
        m=Machine(); m.open("a",0)
        with self.assertRaises(ValueError): m.advance("a",p,100001)
        self.assertEqual(m._sessions["a"],(0,0))

if __name__ == "__main__": unittest.main()
