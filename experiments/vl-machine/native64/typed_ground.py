"""ELF section metadata as a bounded partition sensor, not execution authority."""
from struct import unpack_from
from byte_ground import Source
from compose_ground import Composite, compose

def elf_boundaries(src):
    # Only little-endian ELF32/64 with ordinary section counts.
    ident=src.read(0,min(16,src.n))
    if len(ident)!=16 or ident[:4]!=b'\x7fELF' or ident[5:7]!=b'\x01\x01' or ident[4] not in (1,2):return ()
    is64=ident[4]==2;size=64 if is64 else 52
    if src.n<size:return ()
    h=src.read(16,size)
    if is64:
        off=unpack_from('<Q',h,24)[0];entsize,count=unpack_from('<HH',h,42)
    else:
        off=unpack_from('<I',h,16)[0];entsize,count=unpack_from('<HH',h,30)
    if not 1<=count<=256 or entsize!=(64 if is64 else 40) or off<size or off+count*entsize>src.n:return ()
    boundaries={0,src.n,size,off,off+count*entsize}
    table=src.read(off,off+count*entsize)
    for i in range(count):
        p=i*entsize;kind=unpack_from('<I',table,p+4)[0]
        if kind in (0,8):continue # null and NOBITS have no file payload
        a,n=unpack_from('<QQ' if is64 else '<II',table,p+(24 if is64 else 16))
        if a>src.n or n>src.n-a:return ()
        if n:boundaries.update((a,a+n))
    return tuple(sorted(boundaries))

def typed_compose(src,minimum=64):
    boundaries=elf_boundaries(src);data=src.read(0,src.n)
    base,bc=compose(Source(data),minimum=minimum)
    cost={'sensor_bytes':src.reads-src.n,'candidate_read_bytes':bc['candidate_read_bytes'],'buffer_copy_bytes':src.n,'intervals':bc['intervals'],'boundaries':list(boundaries),'selected':'midpoint'}
    if not boundaries:return base,cost
    leaves=[]
    for a,b in zip(boundaries,boundaries[1:]):
        g,c=compose(Source(data[a:b]),minimum=minimum);leaves.extend(g.leaves)
        cost['candidate_read_bytes']+=c['candidate_read_bytes'];cost['buffer_copy_bytes']+=b-a;cost['intervals']+=c['intervals']
    typed=Composite(tuple(leaves));cost['typed_wire']=len(typed.encode());cost['midpoint_wire']=len(base.encode())
    if cost['typed_wire']<cost['midpoint_wire']:cost['selected']='elf';return typed,cost
    return base,cost

if __name__=='__main__':
    import json
    from pathlib import Path
    from compose_ground import certify
    data=Path(__file__).with_name('vlm64.elf').read_bytes();s=Source(data);g,c=typed_compose(s);assert g.read(0,len(data))==data
    print(json.dumps({'source_reads':s.reads,'wire':len(g.encode()),'source_sha256':certify(Source(data),g),'leaves':len(g.leaves),**c},indent=2))
