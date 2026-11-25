import ctypes as c
import json
import random
import unittest
from pathlib import Path
from test_core import L,U,MASK,load,affine,chart
from test_application import ins,execute,CONST,BUILD,EMIT
I=c.c_int32
for name,args,result in [('nn_begin',[],c.c_int),('nn_put',[U,U],c.c_int),('nn_commit',[],c.c_int),('nn_open',[],U),('nn_close',[U],c.c_int),('nn_step',[U,c.POINTER(I),c.POINTER(I)],c.c_int),('nn_policy',[c.POINTER(U),c.POINTER(U)],c.c_int),('graph_features',[c.POINTER(I)],c.c_int),('try_ground_kind',[U],U)]:
    f=getattr(L,name);f.argtypes=args;f.restype=result

def stage(w):
    assert L.nn_begin()
    for i,v in enumerate(w):assert L.nn_put(i,v+127)

def install(w):
    stage(w);assert L.nn_commit()

def forward(w,x,h):
    z=[16*w[112+i]+sum(w[6*i+j]*x[j] for j in range(6))+sum(w[48+8*i+j]*h[j] for j in range(8)) for i in range(8)]
    h=[min(127,max(0,v//16)) for v in z] # negative quotient clips to zero
    return h,[16*w[144+i]+sum(w[120+8*i+j]*h[j] for j in range(8)) for i in range(3)]

def graphs(seed,n):
    r=random.Random(seed)
    for _ in range(n):
        kind=r.randrange(10);a=r.getrandbits(32);b=r.getrandbits(32)
        if kind<3: p,o=affine(a,b,r.randrange(1,130))
        elif kind<6:p,o=chart((a&65535)<<16,b)
        elif kind==6:p,o=chart((a&65535)<<16,b);p[13]=(1,0,0,0,p[13][4]^1)
        elif kind==7:p,o=[(0,0,0,0,0),(3,0,0,0,0)],1
        elif kind==8:p,o=[(0,0,0,0,0),(1,0,0,0,a),(4,0,1,0,0)],2
        else:p,o=[(0,0,0,0,0),(1,0,0,0,a),(1,0,0,0,b),(2,1,2,0,0),(3,0,3,0,0)],4
        yield p,o

def dataset(seed,n):
    for p,o in graphs(seed,n):
        load(p,o);x=(I*6)();assert L.graph_features(x)
        y=L.discover_active();yield p,o,list(x),y

def campaign(w,seed,n):
    install(w);counts={'cases':n,'correct_proposal':0,'admitted':0,'available':0,'false_admission':0,'missed':0,'rejected_proposal':0}
    for p,o,x,y in dataset(seed,n):
        load(p,o);a,b=U(),U();assert L.nn_policy(c.byref(a),c.byref(b))
        _,logits=forward(w,x,[0]*8);assert a.value==max(range(3),key=lambda i:logits[i])
        counts['correct_proposal']+=a.value==y;counts['available']+=bool(y);counts['admitted']+=bool(b.value)
        counts['false_admission']+=bool(b.value and b.value!=y);counts['missed']+=bool(y and not b.value);counts['rejected_proposal']+=bool(a.value and not b.value)
    return counts

def model():return json.loads(Path(__file__).with_name('policy_weights.json').read_text())['weights']

class Neural(unittest.TestCase):
    def test_recurrent_parity(self):
        r=random.Random(711);w=[r.randrange(-127,128) for _ in range(147)];install(w)
        hs=[L.nn_open() for _ in range(8)];self.assertTrue(all(hs));self.assertFalse(L.nn_open())
        states=[[0]*8 for _ in hs]
        stage([0]*147);self.assertFalse(L.nn_commit())
        for _ in range(128):
            for i,h in enumerate(hs):
                x=[r.randrange(-127,128) for _ in range(6)];out=(I*3)();self.assertTrue(L.nn_step(h,(I*6)(*x),out));states[i],expected=forward(w,x,states[i]);self.assertEqual(list(out),expected)
        out=(I*3)();self.assertFalse(L.nn_step(hs[0],(I*6)(128,0,0,0,0,0),out))
        states[0],expected=forward(w,[0]*6,states[0]);self.assertTrue(L.nn_step(hs[0],(I*6)(),out));self.assertEqual(list(out),expected)
        for h in hs:self.assertTrue(L.nn_close(h));self.assertFalse(L.nn_close(h))
        self.assertTrue(L.nn_commit());new=L.nn_open();self.assertNotEqual(new,hs[0]);self.assertFalse(L.nn_step(hs[0],(I*6)(),out));self.assertTrue(L.nn_close(new))
    def test_policy(self):
        result=campaign(model(),20261125,1000);print('held-out',json.dumps(result,sort_keys=True));self.assertEqual(result['false_admission'],0);self.assertGreater(result['admitted'],600);self.assertGreater(result['rejected_proposal'],0)
    def test_application(self):
        install(model());code=[ins(CONST,0,lo=3),ins(CONST,1,lo=7),ins(BUILD,a=0,b=1,lo=128),ins(11,2),ins(EMIT,a=2)]
        self.assertEqual(execute(code)[:2],(True,[1]))
        p,o=chart(65536,1);p[13]=(1,0,0,0,p[13][4]^1);load(p,o)
        self.assertEqual(execute([ins(11,0),ins(EMIT,a=0)])[:2],(True,[0]))

if __name__=='__main__':unittest.main()
