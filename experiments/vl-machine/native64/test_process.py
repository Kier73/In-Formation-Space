import ctypes as c
import random
import unittest
from test_core import L,U,MASK,load,call,ref,affine,chart

T=c.c_uint64
for name,args in {
    'graph_publish':[], 'graph_release':[U], 'proc_spawn':[U,U], 'proc_close':[U],
    'proc_seek':[U,T,c.POINTER(U)], 'proc_read':[U,c.POINTER(U),c.POINTER(U)],
    'proc_checkpoint':[U,c.POINTER(U),c.POINTER(U),c.POINTER(T)],
    'proc_restore':[U,U,T]}.items():
    f=getattr(L,name);f.argtypes=args;f.restype=U

def seek(h,t):
    w=U();assert L.proc_seek(h,t,c.byref(w));return w.value

def checkpoint(h):
    g,s,t=U(),U(),T();assert L.proc_checkpoint(h,c.byref(g),c.byref(s),c.byref(t));return g.value,s.value,t.value

class Processes(unittest.TestCase):
    def test_fleet_and_restore(self):
        rng=random.Random(318)
        nodes,out=chart(65536,1);load(nodes,out);self.assertTrue(L.admit_chart(65536,1));g=L.graph_publish();self.assertTrue(g)
        nodes2,out2=affine(3,7,1);load(nodes2,out2);self.assertTrue(L.admit(3,7));g2=L.graph_publish();self.assertTrue(g2)
        fleet=[]
        for i in range(64):
            seed=rng.getrandbits(32);graph=g if i%2 else g2;h=L.proc_spawn(graph,seed);self.assertTrue(h);fleet.append((h,graph,seed))
        self.assertEqual(L.proc_spawn(g,0),0);self.assertFalse(L.graph_release(g))
        for _ in range(16):
            for h,graph,seed in fleet:
                t=rng.randrange(1<<64);self.assertEqual(seek(h,t),0)
                if graph==g:
                    def shear(x,k):return (x+k*(x&65535)**3)&MASK
                    expected=shear((shear(seed,65536)+t)&MASK,-65536)
                else:
                    a,b=3,7;expected=seed;n=t
                    while n:
                        if n&1:expected=(a*expected+b)&MASK
                        a,b=a*a&MASK,(a*b+b)&MASK;n>>=1
                self.assertEqual(call(L.proc_read,h)[0],expected)
        for h,graph,seed in fleet:
            rec=checkpoint(h);expected=call(L.proc_read,h);self.assertTrue(L.proc_close(h));self.assertFalse(L.proc_close(h));self.assertEqual(rec[:2],(graph,seed));new=L.proc_restore(*rec);self.assertTrue(new);self.assertNotEqual(new,h);self.assertEqual(call(L.proc_read,new),expected);self.assertTrue(L.proc_close(new))
        self.assertTrue(L.graph_release(g));self.assertTrue(L.graph_release(g2));self.assertEqual(L.proc_restore(g,11,9),0)
    def test_fallback_and_handles(self):
        nodes=[(0,0,0,0,0),(1,0,0,0,3),(4,0,1,0,0)];load(nodes,2);g=L.graph_publish();h=L.proc_spawn(g,5)
        self.assertEqual(seek(h,7),7);self.assertEqual(call(L.proc_read,h),(6,0));w=U();self.assertFalse(L.proc_seek(h,6,c.byref(w)));self.assertFalse(L.proc_seek(h,1032,c.byref(w)));self.assertEqual(call(L.proc_read,h),(6,0));self.assertEqual(seek(h,8),1);self.assertEqual(call(L.proc_read,h),(5,0))
        a,b,t=U(),U(),T();self.assertFalse(L.proc_checkpoint(h,c.byref(a),c.byref(b),c.byref(t)));self.assertEqual(L.proc_restore(g,5,8),0)
        self.assertTrue(L.proc_close(h));self.assertTrue(L.graph_release(g));new=L.graph_publish();self.assertNotEqual(new,g);self.assertEqual(L.proc_spawn(g,0),0);self.assertTrue(L.graph_release(new))
    def test_graph_capacity(self):
        nodes,out=affine(3,7,1);load(nodes,out);handles=[L.graph_publish() for _ in range(8)];self.assertEqual(len(set(handles)),8);self.assertTrue(all(handles));self.assertEqual(L.graph_publish(),0)
        for g in handles:self.assertTrue(L.graph_release(g))

if __name__=='__main__':unittest.main()
