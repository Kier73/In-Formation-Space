"""Drive the actual booted machine through its descriptor ABI."""
import subprocess
import select
import os
import time
import random
from test_core import affine,chart,ref,MASK
from test_application import workload,jump
from test_neural import model,forward

def until(p,marker):
    buf=b""
    deadline=time.monotonic()+10
    while marker not in buf:
        t=deadline-time.monotonic()
        if t<=0 or not select.select([p.stdout],[],[],t)[0]: raise AssertionError(buf)
        s=os.read(p.stdout.fileno(),1)
        if not s: raise AssertionError(buf)
        buf+=s
    return buf

def main():
    cmd=["qemu-system-x86_64","-m","32","-cpu","qemu64","-kernel","vlm64.elf","-display","none","-serial","stdio","-monitor","none","-no-reboot","-device","isa-debug-exit,iobase=0xf4,iosize=4"]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as p:
        try:
            assert b"VLM-002 x86-64" in until(p,b"vl64> ")
            def send(op,*args):
                p.stdin.write((op+"".join(f"{v:08x}" for v in args)+"\n").encode());p.stdin.flush()
                return until(p,b"vl64> ")
            def ok(op,*args): assert b"OK\n" in send(op,*args)
            def result(op,args,y,w):
                assert f"RESULT {y:08x} {w:08x}".encode() in send(op,*args)
            def load(nodes,out):
                ok("b",len(nodes),out)
                for i,node in enumerate(nodes): ok("p",i,*node)
                ok("c")
            nodes,out=affine(3,7,128)
            load(nodes,out)
            rng=random.Random(5)
            xs=[rng.getrandbits(32) for _ in range(32)]
            for x in xs: result("r",[x],ref(nodes,out,x),256)
            b=ref(nodes,out,0);a=(ref(nodes,out,1)-b)&MASK
            assert b"REJECT" in send("g",a^1,b)
            ok("g",a,b)
            for x in xs: result("r",[x],ref(nodes,out,x),2)
            x=11;n=2**40+31;z=x;aa=a;bb=b;k=0;left=n
            while left:
                if left&1:z=(aa*z+bb)&MASK;k+=1
                aa,bb=(aa*aa)&MASK,(aa*bb+bb)&MASK
                left>>=1;k+=1
            result("j",[x,n>>32,n&MASK],z,k)
            ok("b",2,1)
            assert b"REJECT" in send("p",0,2,0,0,0,0)
            assert b"REJECT" in send("c")
            result("r",[11],ref(nodes,out,11),2)
            load([(0,0,0,0,0),(1,0,0,0,3),(4,0,1,0,0)],2)
            assert b"REJECT" in send("g",1,3)
            result("r",[5],6,1)
            nodes,out=chart(65536,1);load(nodes,out)
            assert b"REJECT" in send("h",65537,1)
            ok("h",65536,1)
            result("r",[11],ref(nodes,out,11),11)
            z=11
            for _ in range(93):z=ref(nodes,out,z)
            result("j",[11,0,93],z,12)
            def handle(op,*args):
                data=send(op,*args)
                assert b"HANDLE " in data,data
                return int(data.split(b"HANDLE ")[1][:8],16)
            graph=handle("P");p1=handle("S",graph,11);p2=handle("S",graph,19)
            t=10**12
            result("T",[p1,t>>32,t&MASK],0,0)
            result("O",[p2],19,12)
            def shear(x,k):return (x+k*(x&65535)**3)&MASK
            expected=shear((shear(11,65536)+t)&MASK,-65536)
            result("O",[p1],expected,12)
            assert f"CHECKPOINT {graph:08x} 0000000b {t>>32:08x} {t&MASK:08x}".encode() in send("K",p1)
            assert b"REJECT" in send("D",graph)
            ok("X",p1);p3=handle("R",graph,11,t>>32,t&MASK)
            assert p3!=p1 and b"REJECT" in send("O",p1)
            result("O",[p3],expected,12)
            ok("X",p2);ok("X",p3);ok("D",graph)
            assert b"REJECT" in send("R",graph,11,t>>32,t&MASK)
            seed,t=11,10**12
            program=workload(seed,t)
            ok("A",len(program))
            for i,ins in enumerate(program):
                ok("I",i,*[getattr(ins,f) for f in ("op","d","a","b","lo","hi")])
            nodes,out=affine(3,7,128);b=ref(nodes,out,0);a=(ref(nodes,out,1)-b)&MASK
            y=jump(a,b,seed,t)
            nodes,out=affine(y,7,4);b=ref(nodes,out,0);a=(ref(nodes,out,1)-b)&MASK
            z=jump(a,b,seed,t)
            expected="APPLICATION 00000005 "+" ".join(f"{v:08x}" for v in [1,y,1,z,y])
            assert expected.encode() in send("E")
            # Exercise the actual guest neural wire ABI with nonzero recurrence.
            weights=[rng.randrange(-127,128) for _ in range(147)]
            def stage_weights(weights):
                ok("N")
                for i,value in enumerate(weights):ok("W",i,value+127)
            stage_weights(weights);ok("V")
            sessions=[handle("U"),handle("U")];states=[[0]*8 for _ in sessions]
            for _ in range(16):
                for i,session in enumerate(sessions):
                    x=[rng.randrange(-127,128) for _ in range(6)]
                    states[i],logits=forward(weights,x,states[i])
                    expected="NEURAL "+" ".join(f"{v&MASK:08x}" for v in logits)
                    assert expected.encode() in send("F",session,*[v+127 for v in x])
            stage_weights(model());assert b"REJECT" in send("V")
            for session in sessions:ok("Y",session)
            ok("V")
            assert b"REJECT" in send("F",sessions[0],*[127]*6)
            nodes,out=affine(3,7,128);load(nodes,out)
            result("Z",[],1,1)
            nodes,out=chart(65536,1);nodes[13]=(1,0,0,0,nodes[13][4]^1);load(nodes,out)
            result("Z",[],2,0)
            p.stdin.write(b"q\n");p.stdin.flush()
            assert p.wait(timeout=5)==33
            print("guest boot, DAG, Ground, 64-bit jump, rejection and replacement verified")
        finally:
            if p.poll() is None:p.kill()

if __name__=="__main__":main()
