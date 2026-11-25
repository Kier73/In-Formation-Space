import ctypes as c
import random
import unittest
from test_core import L,U,MASK,load,ref,affine,chart

class Insn(c.Structure):
    _fields_=[(n,U) for n in ('op','d','a','b','lo','hi')]
L.app_begin.argtypes=[U]; L.app_put.argtypes=[U,Insn]
L.app_execute.argtypes=[c.POINTER(U),U,c.POINTER(U)]
L.discover_active.argtypes=[]; L.discover_active.restype=U
L.graph_publish.restype=U; L.graph_release.argtypes=[U]
CONST,BUILD,LEARN,PUBLISH,SPAWN,SEEK,READ,ADD,MUL,XOR,EMIT=range(11)
def ins(op,d=0,a=0,b=0,lo=0,hi=0):return Insn(op,d,a,b,lo,hi)
def execute(code,capacity=128):
    assert L.app_begin(len(code))
    for i,x in enumerate(code):assert L.app_put(i,x)
    out=(U*128)(*([0xdeadbeef]*128));n=U(99)
    ok=L.app_execute(out,capacity,c.byref(n))
    return bool(ok),list(out)[:n.value],out[0]
def jump(a,b,x,n):
    while n:
        if n&1:x=(a*x+b)&MASK
        a,b=a*a&MASK,(a*b+b)&MASK;n>>=1
    return x

def workload(seed,t):
    # First graph creates a result which becomes coefficient of a second graph.
    return [ins(CONST,0,lo=3),ins(CONST,1,lo=7),ins(CONST,2,lo=seed),
            ins(BUILD,a=0,b=1,lo=128),ins(LEARN,3),ins(PUBLISH,4),ins(SPAWN,5,4,2),
            ins(SEEK,a=5,lo=t&MASK,hi=t>>32),ins(READ,6,5),ins(EMIT,a=3),ins(EMIT,a=6),
            ins(BUILD,a=6,b=1,lo=4),ins(LEARN,7),ins(PUBLISH,8),ins(SPAWN,9,8,2),
            ins(SEEK,a=9,lo=t&MASK,hi=t>>32),ins(READ,10,9),ins(EMIT,a=7),ins(EMIT,a=10),
            ins(READ,11,5),ins(EMIT,a=11)]
class Applications(unittest.TestCase):
    def test_self_use(self):
        rng=random.Random(7)
        for _ in range(128):
            x=rng.getrandbits(32);t=rng.getrandbits(64)
            p,o=affine(3,7,128);b=ref(p,o,0);a=(ref(p,o,1)-b)&MASK;y=jump(a,b,x,t)
            p,o=affine(y,7,4);b=ref(p,o,0);a=(ref(p,o,1)-b)&MASK;z=jump(a,b,x,t)
            ok,out,_=execute(workload(x,t));self.assertTrue(ok);self.assertEqual(out,[1,y,1,z,y])
        # 256 published graphs over campaign; no leaked slots.
        handles=[L.graph_publish() for _ in range(8)];self.assertTrue(all(handles));self.assertFalse(L.graph_publish())
        for h in handles:self.assertTrue(L.graph_release(h))
    def test_discovery(self):
        nodes,out=chart(65536,1);load(nodes,out);self.assertEqual(L.discover_active(),2)
        load([(0,0,0,0,0),(3,0,0,0,0)],1);self.assertEqual(L.discover_active(),0)
        load([(0,0,0,0,0),(1,0,0,0,3),(4,0,1,0,0)],2);self.assertEqual(L.discover_active(),0)
    def test_reject_and_cleanup(self):
        for code,cap in [([ins(EMIT,a=1)],128),([ins(CONST,0,lo=1),ins(CONST,0,lo=2)],128),([ins(CONST,0),ins(EMIT,a=0)],0),([ins(CONST,0),ins(SPAWN,1,0,0)],128)]:
            self.assertEqual(execute(code,cap),(False,[],0xdeadbeef))
        load([(0,0,0,0,0),(3,0,0,0,0)],1)
        code=[ins(CONST,0,lo=2),ins(EMIT,a=0),ins(PUBLISH,1),ins(SPAWN,2,1,0),ins(SEEK,a=2,lo=1025)]
        for _ in range(80):self.assertEqual(execute(code),(False,[],0xdeadbeef))
        handles=[L.graph_publish() for _ in range(8)];self.assertTrue(all(handles))
        for h in handles:self.assertTrue(L.graph_release(h))
if __name__=='__main__':unittest.main()
