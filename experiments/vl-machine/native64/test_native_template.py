"""Lower learned templates into native typed immediate bindings."""
import ctypes as c
import random
import unittest
from hashlib import sha256
from struct import pack,iter_unpack
from time import perf_counter_ns
from template_ground import learn,qualify,Template
from test_application import L,U,Insn,ins,workload,execute,jump
from test_core import affine,ref,MASK

B=c.c_uint8
for name,args in [('tpl_begin',[U,U]),('tpl_put',[U,Insn]),('tpl_patch',[U,U]),('tpl_commit',[]),('tpl_execute',[U,c.POINTER(B),U,c.POINTER(U),U,c.POINTER(U)])]:
    f=getattr(L,name);f.argtypes=args;f.restype=U

def stream(seed,count):
    r=random.Random(seed)
    for _ in range(count):
        x,t=r.getrandbits(32),r.getrandbits(64)
        yield b''.join(pack('<6I',*[getattr(a,k) for k in ('op','d','a','b','lo','hi')]) for a in workload(x,t)),x,t

def stage(t):
    assert len(t.fixed)%24==0
    assert L.tpl_begin(len(t.fixed)//24,len(t.groups))
    for i,a in enumerate(iter_unpack('<6I',t.fixed)):assert L.tpl_put(i,ins(*a))
    for j,g in enumerate(t.groups):
        for i in g:assert L.tpl_patch(i,j)

def install(t):
    stage(t);g=L.tpl_commit();assert g;return g

def invoke(g,values,cap=128):
    out=(U*128)(*([0xdeadbeef]*128));n=U(99)
    ok=L.tpl_execute(g,(B*len(values))(*values),len(values),out,cap,c.byref(n))
    return bool(ok),list(out)[:n.value],out[0]

def oracle(x,t):
    p,o=affine(3,7,128);b=ref(p,o,0);a=(ref(p,o,1)-b)&MASK;y=jump(a,b,x,t)
    p,o=affine(y,7,4);b=ref(p,o,0);a=(ref(p,o,1)-b)&MASK;z=jump(a,b,x,t)
    return [1,y,1,z,y]

class NativeTemplate(unittest.TestCase):
    def test_heldout(self):
        t,stats=qualify(learn([p for p,_,_ in stream(511,16)]),[p for p,_,_ in stream(512,16)])
        self.assertIsNotNone(t);g=install(Template.decode(t.encode()))
        for p,x,time in stream(514,256):
            values=t.match(p).values;self.assertEqual(invoke(g,values)[:2],(True,oracle(x,time)))
    def test_fencing_and_rejection(self):
        t=learn([p for p,_,_ in stream(511,16)]);g=install(t);p,x,time=next(stream(515,1));values=t.match(p).values
        self.assertEqual(invoke(g,values,4),(False,[],0xdeadbeef));self.assertEqual(invoke(g,values[:-1]),(False,[],0xdeadbeef))
        for pos in (0,4,8,12,20,24*3+16):
            stage(t);self.assertFalse(L.tpl_patch(pos,0));self.assertFalse(L.tpl_commit());self.assertEqual(invoke(g,values)[:2],(True,oracle(x,time)))
        self.assertTrue(L.tpl_begin(1,1));self.assertTrue(L.tpl_put(0,ins(0,0)));self.assertFalse(L.tpl_commit())
        self.assertTrue(L.tpl_begin(1,0));self.assertTrue(L.tpl_put(0,ins(10,a=1)));self.assertFalse(L.tpl_commit())
        new=install(t);self.assertNotEqual(g,new);self.assertEqual(invoke(g,values),(False,[],0xdeadbeef))
        self.assertEqual(invoke(new,values)[:2],(True,oracle(x,time)))
    def test_all_immediate_values(self):
        t=learn([p for p,_,_ in stream(511,16)]);g=install(t)
        for value in (0,255):
            v=bytes([value])*len(t.groups);from template_ground import Instance
            p=Instance(t,v).read(0,len(t.fixed));self.assertEqual(invoke(g,v)[:2],execute([ins(*a) for a in iter_unpack('<6I',p)])[:2])

def benchmark():
    training=[p for p,_,_ in stream(511,16)];validation=[p for p,_,_ in stream(512,16)]
    start=perf_counter_ns();t,stats=qualify(learn(training),validation);learn_ns=perf_counter_ns()-start
    start=perf_counter_ns();g=install(t);install_ns=perf_counter_ns()-start
    rows=[(p,t.match(p).values,oracle(x,time)) for p,x,time in stream(516,1000)]
    start=perf_counter_ns()
    for p,v,expected in rows:assert execute([ins(*a) for a in iter_unpack('<6I',p)])[:2]==(True,expected)
    raw_ns=perf_counter_ns()-start
    start=perf_counter_ns()
    for p,v,expected in rows:assert invoke(g,v)[:2]==(True,expected)
    direct_ns=perf_counter_ns()-start
    print({'cases':len(rows),'learn_qualify_ns':learn_ns,'install_ns':install_ns,'raw_ns':raw_ns,'direct_ns':direct_ns,'template_bytes':len(t.encode()),'instance_parameters':len(t.groups),'static_instruction_checks_raw':len(rows)*len(t.fixed)//24,'static_instruction_checks_direct':len(t.fixed)//24,'staged_instructions_raw':len(rows)*len(t.fixed)//24,'staged_instructions_direct':len(t.fixed)//24})
if __name__=='__main__':
    import sys
    if '--benchmark' in sys.argv:benchmark()
    else:unittest.main()
