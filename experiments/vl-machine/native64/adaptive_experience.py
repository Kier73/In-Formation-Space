"""VLM-012: generate new experience from a resident tool's own assumptions."""
import json
import random
from hashlib import sha256
from pathlib import Path
from struct import iter_unpack
from experience import canonical, digest, decode, shape
from template_ground import Template, Instance, learn
from compose_ground import compose
from byte_ground import Source
from test_application import execute, CONST, BUILD, LEARN, PUBLISH, SPAWN, SEEK, READ, ADD, MUL, XOR, EMIT
from test_native_template import install, invoke

MASK=(1<<32)-1
PARENT=Path(__file__).with_name('datasets')/'vlm011'/'experience-summary.json'
PARENT_SHA='32a034bf40a36f694346bea6a7e0c3daf3d0e9006bdf0ffc2cbcbc2ee925fdb9'

def load_parent(path=PARENT):
    raw=Path(path).read_bytes()
    if sha256(raw).hexdigest()!=PARENT_SHA:raise ValueError('parent identity')
    report=json.loads(raw)
    return {k:Template.decode(bytes.fromhex(v)) for k,v in report['catalogue'].items()}

def free_positions(t):
    out=[]
    for i,(op,d,a,b,lo,hi) in enumerate(iter_unpack('<6I',t.fixed)):
        if op in (CONST,SEEK):out.extend(range(24*i+16,24*i+(20 if op==CONST else 24)))
    return tuple(out)

def hypotheses(t):
    used={p for g in t.groups for p in g}
    return tuple(sorted(set(free_positions(t))-used | {p for g in t.groups for p in g[1:]}))

def oracle(p):
    """Independent evaluator for the restricted closed affine application language."""
    def power(a,b,n):
        r,s=1,0
        while n:
            if n&1:r,s=r*a&MASK,(r*b+s)&MASK
            a,b=a*a&MASK,(a*b+b)&MASK;n>>=1
        return r,s
    regs={};active=None;procs={};out=[]
    for op,d,a,b,lo,hi in iter_unpack('<6I',p):
        if op==CONST:regs[d]=lo
        elif op in (ADD,MUL,XOR):regs[d]=((regs[a]+regs[b]) if op==ADD else (regs[a]*regs[b]) if op==MUL else (regs[a]^regs[b]))&MASK
        elif op==BUILD:active=power(regs[a],regs[b],lo)
        elif op==LEARN:
            if active is None:raise ValueError('open graph')
            regs[d]=1
        elif op==PUBLISH:regs[d]=active
        elif op==SPAWN:procs[d]=(regs[a],regs[b],0)
        elif op==SEEK:
            law,seed,_=procs[a];procs[a]=(law,seed,(hi<<32)|lo)
        elif op==READ:
            law,seed,time=procs[a];m,c=power(*law,time);regs[d]=(m*seed+c)&MASK
        elif op==EMIT:out.append(regs[a])
        else:raise ValueError('unsupported operation')
    return out

def generate(t,phase,index,positions=()):
    """A compact recipe; each chosen coordinate is intervened on independently."""
    if phase not in ('probe','train','validation','final') or not 0<=index<10000:raise ValueError('recipe address')
    if len(set(positions))!=len(positions) or not set(positions)<=set(hypotheses(t)):raise ValueError('intervention')
    r=random.Random(int(digest([t.digest.hex(),phase,index,list(positions)]),16))
    original=Instance(t,r.randbytes(len(t.groups))).read(0,len(t.fixed));p=bytearray(original)
    for j in positions:p[j]^=r.randrange(1,256)
    return original,bytes(p)

def encounter(t,phase,index,positions):
    original,p=generate(t,phase,index,positions);ok,out,_=execute(decode(p));expected=oracle(p)
    if not ok or out!=expected:raise RuntimeError('native/reference disagreement')
    return {'phase':phase,'index':index,'positions':list(positions),'source_sha256':sha256(p).hexdigest(),'output':out,'old_match':t.match(p) is not None,'changed_output':out!=oracle(original)}

def representation_cost(t,examples):
    total=len(t.encode())
    for p in examples:
        i=t.match(p);total+=len(i.encode()) if i else len(compose(Source(p))[0].encode())
    return total

def campaign():
    catalogue=load_parent();key,t=max(sorted(catalogue.items()),key=lambda kv:len(hypotheses(kv[1])))
    if not hypotheses(t):raise RuntimeError('no remaining assumption')
    rows=[];expanded=[]
    for i,pos in enumerate(hypotheses(t)):
        e=encounter(t,'probe',i,(pos,));rows.append(e)
        if not e['old_match']:expanded.append(pos)
    # Probe identifies an inadequate assumption. Separate examples learn the new law.
    train=[];validation=[]
    for phase,examples in (('train',train),('validation',validation)):
        for i in range(16):
            pos=tuple(expanded) if i%2 else ()
            rows.append(encounter(t,phase,i,pos));examples.append(generate(t,phase,i,pos)[1])
    candidate=learn(train);old_cost=representation_cost(t,validation);new_cost=representation_cost(candidate,validation)
    admitted=False
    if new_cost<old_cost and all(candidate.match(p) is not None for p in validation):
        g=install(candidate)
        for p in validation:
            if invoke(g,candidate.match(p).values)[:2]!=(True,oracle(p)):raise RuntimeError('constructor disagreement')
        admitted=True
    chosen=candidate if admitted else t;g=install(chosen);coverage=0;old_coverage=0
    for i in range(64):
        pos=tuple(expanded) if i%2 else ();row=encounter(t,'final',i,pos);p=generate(t,'final',i,pos)[1];inst=chosen.match(p)
        old_coverage+=row['old_match'];coverage+=inst is not None
        if inst and invoke(g,inst.values)[:2]!=(True,row['output']):raise RuntimeError('final constructor disagreement')
        rows.append(row|{'constructor':inst is not None})
    # The recipe ledger retains the parent identity and exact outcome; no full instruction copies.
    return {'schema':'vlm-adaptive-experience-v1','parent_summary_sha256':PARENT_SHA,'parent_shape':key,'parent_template_sha256':t.digest.hex(),'candidate_template':candidate.encode().hex(),'candidate_sha256':candidate.digest.hex(),'probed_positions':list(hypotheses(t)),'refined_positions':expanded,'probe_changed_outputs':sum(r['changed_output'] for r in rows if r['phase']=='probe'),'old_parameters':len(t.groups),'new_parameters':len(chosen.groups),'validation_cost_old':old_cost,'validation_cost_new':new_cost,'admitted':admitted,'old_final_coverage':old_coverage,'new_final_coverage':coverage,'final_count':64,'encounters':len(rows),'experience_digest':digest(rows),'rows':rows}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output');a=p.parse_args();r=campaign()
    if a.output:Path(a.output).write_bytes(canonical(r)+b'\n')
    print(json.dumps({k:v for k,v in r.items() if k not in ('rows','candidate_template')},indent=2,sort_keys=True))
