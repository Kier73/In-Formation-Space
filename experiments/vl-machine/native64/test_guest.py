"""Drive the actual booted machine through its descriptor ABI."""
import subprocess
import select
import os
import time
import random
from test_core import affine,ref,MASK

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
            p.stdin.write(b"q\n");p.stdin.flush()
            assert p.wait(timeout=5)==33
            print("guest boot, DAG, Ground, 64-bit jump, rejection and replacement verified")
        finally:
            if p.poll() is None:p.kill()

if __name__=="__main__":main()
