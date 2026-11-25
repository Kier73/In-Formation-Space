"""Freeze a vocabulary before test; charge its complete wire once per batch."""
from pathlib import Path
from hashlib import sha256
import json, random, zlib, time
from vocabulary import compile_source, discover, qualify, apply, receive

TRAIN=('core.c','application.c','capsule.py','test_core.py')
VALID=('neural.c','test_application.py')
TEST=('kernel.c','test_neural.py','test_process.py','policy_weights.json','vlm64.elf')

def campaign(train,validation,test):
    t=time.perf_counter_ns();tr=[compile_source(p) for p in train];va=[compile_source(p) for p in validation];candidate=discover(tr);v,options=qualify(candidate,va);training_ns=time.perf_counter_ns()-t
    rows=[]
    for name,p in test:
        base=compile_source(p);t=time.perf_counter_ns();wire=apply(base,v);elapsed=time.perf_counter_ns()-t
        g=receive(wire,v,sha256(p).hexdigest());assert g.read(0,len(p))==p
        r=random.Random(42)
        for _ in range(50):
            a,b=sorted((r.randrange(len(p)+1),r.randrange(len(p)+1)));assert g.total(a,b)==sum(p[a:b]);assert g.read(a,b)==p[a:b]
        rows.append({'name':name,'source':len(p),'base_wire':len(base.encode()),'vocab_wire':len(wire),'zlib':len(zlib.compress(p)),'uses_vocab':wire[:4]==b'VLP1','source_sha256':sha256(p).hexdigest(),'apply_ns':elapsed})
    overhead=len(v.encode()) if v.words else 0
    return {'candidate_words':len(candidate.words),'admitted_words':len(v.words),'vocabulary_bytes':overhead,'validation_options':options,'training_ns':training_ns,'sources':rows,'base_total':sum(r['base_wire'] for r in rows),'vocabulary_total':sum(r['vocab_wire'] for r in rows)+overhead,'zlib_total':sum(r['zlib'] for r in rows),'vocabulary_sha256':v.digest.hex(),'words_hex':[w.hex() for w in v.words]}

def synthetic(seed,n):
    # Shared motifs deliberately exist; independent ordering, gaps and random bytes.
    motifs=[random.Random(900+i).randbytes(32) for i in range(12)];r=random.Random(seed)
    for _ in range(n):yield b''.join(r.choice(motifs)+r.randbytes(r.randrange(1,13)) for _ in range(40))

def application_campaign():
    from struct import pack, iter_unpack
    from test_application import workload,execute,ins,jump
    from test_core import affine,ref,MASK
    def stream(seed,count):
        rng=random.Random(seed)
        for i in range(count):
            x,t=rng.getrandbits(32),rng.getrandbits(64)
            p=b''.join(pack('<6I',*[getattr(a,k) for k in ('op','d','a','b','lo','hi')]) for a in workload(x,t))
            yield str(i),p,x,t
    tr=list(stream(511,16));va=list(stream(512,16));te=list(stream(513,64))
    # Use the same frozen training/validation algorithm, then execute its decoded output.
    candidate=discover([compile_source(p) for _,p,_,_ in tr]);v,options=qualify(candidate,[compile_source(p) for _,p,_,_ in va])
    from template_ground import learn,qualify as qualify_template,apply as apply_template,receive as receive_template,Template
    template,template_options=qualify_template(learn([p for _,p,_,_ in tr]),[p for _,p,_,_ in va])
    if template is not None:template=Template.decode(template.encode())
    baseline=encoded=zbytes=template_bytes=0;uses=template_uses=0
    for _,p,x,t in te:
        b=compile_source(p);w=apply(b,v);g=receive(w,v,sha256(p).hexdigest())
        instructions=[ins(*a) for a in iter_unpack('<6I',g.read(0,g.n))]
        nodes,out=affine(3,7,128);b0=ref(nodes,out,0);a0=(ref(nodes,out,1)-b0)&MASK;y=jump(a0,b0,x,t)
        nodes,out=affine(y,7,4);b0=ref(nodes,out,0);a0=(ref(nodes,out,1)-b0)&MASK;z=jump(a0,b0,x,t)
        assert execute(instructions)[:2]==(True,[1,y,1,z,y])
        tw=apply_template(p,template);ti=receive_template(tw,template,sha256(p).hexdigest());instructions=[ins(*a) for a in iter_unpack('<6I',ti.read(0,ti.n))]
        assert execute(instructions)[:2]==(True,[1,y,1,z,y])
        assert ti.total(3,ti.n-7)==sum(p[3:-7])
        template_bytes+=len(tw);template_uses+=tw[:4]==b'VLA1'
        baseline+=len(b.encode());encoded+=len(w);zbytes+=len(zlib.compress(p));uses+=w[:4]==b'VLP1'
    overhead=len(v.encode()) if v.words else 0
    return {'train':len(tr),'validation':len(va),'executed':len(te),'candidate_words':len(candidate.words),'admitted_words':len(v.words),'validation_options':options,'vocabulary_bytes':overhead,'base_total':baseline,'vocabulary_total':encoded+overhead,'zlib_total':zbytes,'uses_vocab':uses,'template_validation':template_options,'template_bytes':len(template.encode()) if template else 0,'template_variables':len(template.groups) if template else 0,'template_variable_positions':sum(map(len,template.groups)) if template else 0,'template_total':template_bytes+(len(template.encode()) if template else 0),'template_uses':template_uses,'template_sha256':template.digest.hex() if template else None,'vocabulary_sha256':v.digest.hex(),'words_hex':[w.hex() for w in v.words]}

def main():
    root=Path(__file__).resolve().parent
    actual=campaign([(root/n).read_bytes() for n in TRAIN],[(root/n).read_bytes() for n in VALID],[(n,(root/n).read_bytes()) for n in TEST])
    mixed=campaign(list(synthetic(1,12)),list(synthetic(2,8)),[(str(i),p) for i,p in enumerate(synthetic(3,24))])
    print(json.dumps({'actual':actual,'synthetic':mixed,'applications':application_campaign()},indent=2,sort_keys=True))
if __name__=='__main__':main()
