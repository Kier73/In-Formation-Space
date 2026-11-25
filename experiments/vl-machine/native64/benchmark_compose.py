"""Compare exact bounded segmentation against single and fixed-size partitions."""
import json,random,zlib
from pathlib import Path
from time import perf_counter_ns
from byte_ground import Source, exact
from compose_ground import Composite, compose, certify, restore, work

def audit(p):
    src=Source(p);unpruned,full=compose(Source(p),prune=False);start=perf_counter_ns();g,c=compose(src);ns=perf_counter_ns()-start
    assert g.encode()==unpruned.encode()
    proof=Source(p);digest=certify(proof,g);wire=g.encode();h=restore(wire,digest)
    assert h.read(0,len(p))==p and h.total(0,len(p))==sum(p)
    fixed=Composite(tuple(exact(Source(p[i:i+256])) for i in range(0,len(p),256)))
    single=Composite((exact(Source(p)),))
    return {'source':len(p),'single_wire':len(single.encode()),'fixed_wire':len(fixed.encode()),'composite_wire':len(wire),'zlib':len(zlib.compress(p)),'leaves':len(g.leaves),'kinds':sorted(set(x.kind for x in g.leaves)),'source_reads':src.reads+proof.reads,'candidate_read_bytes':c['candidate_read_bytes'],'intervals':c['intervals'],'unpruned_candidate_bytes':full['candidate_read_bytes'],'unpruned_intervals':full['intervals'],'pruned':c['pruned'],'sum_work_proxy':sum(work(x) for x in g.leaves),'compile_ns':ns}

def main():
    root=Path(__file__).resolve().parent
    report={n:audit((root/n).read_bytes()) for n in ('core.c','application.c','neural.c','capsule.py','policy_weights.json','vlm64.elf')}
    r=random.Random(83);rows=[]
    for _ in range(100):
        blocks=[bytes(512),r.randbytes(512),r.randbytes(4)*128,bytes((i*3)&255 for i in range(512))];r.shuffle(blocks);rows.append(audit(b''.join(blocks)))
    print(json.dumps({'actual':report,'synthetic_100':{k:sum(row[k] for row in rows) for k in ('source','single_wire','fixed_wire','composite_wire','zlib','source_reads','candidate_read_bytes','intervals','unpruned_candidate_bytes','unpruned_intervals','pruned','compile_ns')}},indent=2,sort_keys=True))
if __name__=='__main__':main()
