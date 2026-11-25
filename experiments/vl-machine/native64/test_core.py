import ctypes as c
import random
import unittest
from pathlib import Path

U=c.c_uint32
MASK=2**32-1
class Node(c.Structure):
    _fields_=[(n,U) for n in ('op','a','b','c','k')]
L=c.CDLL(str(Path(__file__).resolve().with_name('libcore.so')))
L.begin.argtypes=[U,U]
L.put.argtypes=[U,Node]
L.admit.argtypes=[U,U]
L.admit_chart.argtypes=[U,U]
L.run.argtypes=[U,c.POINTER(U),c.POINTER(U)]
L.navigate.argtypes=[U,c.c_uint64,c.POINTER(U),c.POINTER(U)]

def load(nodes,out):
    assert L.begin(len(nodes),out)
    for i,node in enumerate(nodes): assert L.put(i,Node(*node))
    assert L.commit()

def call(fn,*args):
    y,w=U(),U()
    assert fn(*args,c.byref(y),c.byref(w))
    return y.value,w.value

def ref(nodes,out,x):
    vals=[]
    for op,a,b,d,k in nodes:
        if op==0:y=x
        elif op==1:y=k
        else:
            u,v=vals[a],vals[b]
            y=[lambda:u+v,lambda:u*v,lambda:u^v,lambda:u&v,lambda:int(u<v),lambda:v if u else vals[d]][op-2]()
        vals.append(y&MASK)
    return vals[out]

def affine(a,b,depth):
    nodes=[(0,0,0,0,0),(1,0,0,0,a),(1,0,0,0,b)]
    pos=0
    for _ in range(depth):
        nodes.append((3,pos,1,0,0));nodes.append((2,len(nodes)-1,2,0,0));pos=len(nodes)-1
    return nodes,pos

def chart(k,d):
    return [(0,0,0,0,0),(1,0,0,0,65535),(5,0,1,0,0),
            (3,2,2,0,0),(3,3,2,0,0),(1,0,0,0,k),(3,4,5,0,0),
            (2,0,6,0,0),(1,0,0,0,d),(2,7,8,0,0),(5,9,1,0,0),
            (3,10,10,0,0),(3,11,10,0,0),(1,0,0,0,(-k)&MASK),
            (3,12,13,0,0),(2,9,14,0,0)],15

class Tests(unittest.TestCase):
    def test_nonlinear_chart(self):
        nodes,out=chart(65536,1);load(nodes,out)
        self.assertNotEqual((ref(nodes,out,2)-2*ref(nodes,out,1)+ref(nodes,out,0))&MASK,0)
        self.assertFalse(L.admit(1,1));self.assertTrue(L.admit_chart(65536,1))
        r=random.Random(501)
        for _ in range(200):
            k=r.randrange(65536)<<16;d=r.getrandbits(32);x=r.getrandbits(32)
            nodes,out=chart(k,d);load(nodes,out)
            self.assertFalse(L.admit_chart(k^1,d));self.assertFalse(L.admit_chart(k,d^1))
            self.assertTrue(L.admit_chart(k,d))
            self.assertEqual(call(L.run,x),(ref(nodes,out,x),11))
            n=r.randrange(100);z=x
            for _ in range(n):z=ref(nodes,out,z)
            self.assertEqual(call(L.navigate,x,n),(z,12))
            h=call(L.navigate,x,10**12)[0]
            self.assertEqual(call(L.navigate,h,10**12)[0],call(L.navigate,x,2*10**12)[0])
            nodes[14]=(2,12,13,0,0);load(nodes,out)
            self.assertFalse(L.admit_chart(k,d))

    def test_random_dags(self):
        r=random.Random(283)
        for _ in range(300):
            nodes=[(0,0,0,0,0),(1,0,0,0,r.getrandbits(32))]
            for i in range(2,64):
                op=r.randrange(2,8)
                nodes.append((op,r.randrange(i),r.randrange(i),r.randrange(i) if op==7 else 0,0))
            out=r.randrange(len(nodes));load(nodes,out)
            for _ in range(10):
                x=r.getrandbits(32);self.assertEqual(call(L.run,x)[0],ref(nodes,out,x))
    def test_admit_and_jump(self):
        r=random.Random(90)
        for _ in range(120):
            a,b,x=[r.getrandbits(32) for _ in range(3)]
            nodes,out=affine(a,b,128);load(nodes,out)
            self.assertEqual(call(L.run,x),(ref(nodes,out,x),256))
            B=ref(nodes,out,0);A=(ref(nodes,out,1)-B)&MASK
            self.assertFalse(L.admit(A^1,B));self.assertTrue(L.admit(A,B))
            self.assertEqual(call(L.run,x),(ref(nodes,out,x),2))
            n=r.randrange(200);z=x
            for _ in range(n):z=(A*z+B)&MASK
            self.assertEqual(call(L.navigate,x,n)[0],z)
            half=call(L.navigate,x,2**40)[0]
            self.assertEqual(call(L.navigate,half,2**40)[0],call(L.navigate,x,2**41)[0])
    def test_transaction(self):
        nodes,out=affine(3,7,1);load(nodes,out)
        self.assertTrue(L.admit(3,7));self.assertTrue(L.begin(2,1))
        self.assertFalse(L.put(0,Node(2,0,0,0,0)));self.assertFalse(L.commit())
        self.assertEqual(call(L.run,11),(40,2))
        load([(0,0,0,0,0),(3,0,0,0,0)],1)
        self.assertFalse(L.admit(1,0));self.assertEqual(call(L.run,11),(121,1))
        y,w=U(),U();self.assertFalse(L.navigate(11,9,c.byref(y),c.byref(w)))

if __name__=='__main__':unittest.main()
