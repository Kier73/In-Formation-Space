"""Exercise a real guest over COM1, compare to portable reference."""
import pathlib
import subprocess
import sys
import time
import select
import os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from machine import jump, MASK

def until(proc, marker, timeout=10):
    data=b""
    deadline=time.monotonic()+timeout
    while marker not in data:
        remain=deadline-time.monotonic()
        if remain<=0 or not select.select([proc.stdout],[],[],remain)[0]:
            raise AssertionError(data)
        chunk=os.read(proc.stdout.fileno(),1)
        if not chunk: raise AssertionError(data)
        data+=chunk
    return data

def main():
    cmd=["qemu-system-i386","-m","32","-kernel","vlm.elf","-display","none",
         "-serial","stdio","-monitor","none","-no-reboot","-device","isa-debug-exit,iobase=0xf4,iosize=4"]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as p:
        try:
            assert b"VLM-001" in until(p,b"vl> ")
            import random
            rng=random.Random(91)
            cases=[("a",[MASK,1],0),("m",[MASK,MASK],1),("x",[5,3],6),("n",[5,3],1),("l",[0,MASK],1),("l",[MASK,0],0),("s",[0,5,7],7),("s",[MASK,5,7],5)]
            for _ in range(80):
                a,b,x,n=[rng.getrandbits(32) for i in range(4)]
                cases.append(("j",[a,b,x,n],jump(a,b,x,n)[0]))
            cases.append(("j",[3,7,11,0],11))
            for op,args,expected in cases:
                p.stdin.write((op+"".join(f"{v:08x}" for v in args)).encode()); p.stdin.flush()
                data=until(p,b"vl> ")
                assert f"RESULT {expected:08x}".encode() in data,(op,args,data)
            p.stdin.write(b"a!"); p.stdin.flush()
            assert b"REJECT" in until(p,b"vl> ")
            p.stdin.write(b"q"); p.stdin.flush()
            assert p.wait(timeout=5)==33
            print(f"{len(cases)} native parity cases; malformed command rejected")
        finally:
            if p.poll() is None: p.kill()

if __name__=="__main__": main()
