"""Cold re-admission of a source-bound Seed on a freshly reconstructed Ground."""
import argparse,json,time
from run_compositional_rank import prepare
from compositional_rank import Memory
from verify_compositional_rank import MemoryReceiver
from adaptive_seed import Seed
from verify_adaptive_seed import SeedReceiver,restore_capsule
from test_adaptive_seed import adopt,transfer
from anchor_portfolio import wire_size
from temporal_rank import Rank
from verify_temporal_rank import CheckedRank

def now():return time.perf_counter()*1000

def run(k):
    t=now();l,a,n,P,oracle,base=prepare(k);source_ms=now()-t;m=Memory(l);v=MemoryReceiver(a);phases=[P*j//17 for j in range(1,17)]
    t=now();r=m.open(0);proof=r.packet();assert v.book(0).open_rank(proof);m.commit_open(r)
    for p in phases:
        z=m.fact(0,p);assert v.admit_fact(0,p,z);m.commit_fact(z)
    m.close(0);v.book(0).close_rank();seed_ms=now()-t;seed=Seed(m,[0]);t=now();capsule=seed.capsule({0:proof});capsule_build_ms=now()-t;t=now();recipe=seed.recipe();recipe_build_ms=now()-t
    t=now();ll,aa,nn,PP,_,_=prepare(k);fresh_source_ms=now()-t;assert n==nn and P==PP
    row=dict(bits=k,n=n,period=str(P),source_ms=source_ms,fresh_source_ms=fresh_source_ms,seed_ms=seed_ms,capsule_bytes=wire_size(capsule),recipe_bytes=wire_size(recipe),capsule_build_ms=capsule_build_ms,recipe_build_ms=recipe_build_ms,rank_terms=len(proof['terms']))
    for label,packet in [('capsule',capsule),('recipe',recipe)]:
        t=now();restored=restore_capsule(aa,packet);elapsed=now()-t;assert restored is not None;rv,rs=restored;assert rs.verify_descriptor(seed.descriptor());assert rv.book(0).exact is None;row[label+'_restore_ms']=elapsed
    # Reconstitute the producer mirror from the independently admitted recipe.
    mm=Memory(ll);mm.book(0)._anchors=rv.book(0).anchors;ss=Seed(mm,[0]);assert rs.verify_descriptor(ss.descriptor());target=ll.extend('shift',0,1);aa.extend(ll.export());t=now();z=adopt(mm,rv,ss,rs,ss.discover(target));assert z['kind']=='shift';b=mm.book(0);c=rv.book(0);x=b.span(1,budget=1);assert c.admit_span(1,x,budget=1);b.commit(x)
    facts=[];outputs=[]
    for p in phases:
        q=transfer(mm,rv,ss,rs,z,(p-1)%P);assert q['status']=='EXACT';facts.append(q)
    N=ll.count(target)
    for j,q in enumerate(facts):
        ordinal=(10**900+j)*N+min(N,int(q['lower'])+1);b=mm.book(target);c=rv.book(target);x=b.select(ordinal,budget=128);assert c.admit_select(ordinal,x,budget=128);b.commit(x);assert x['status']=='FOUND';outputs.append((ordinal,int(x['time'])))
    row['activation_and_queries_ms']=now()-t;row['verified_queries']=len(outputs)
    for ordinal,t in outputs:assert oracle(t,'shift')==ordinal-1 and oracle(t+1,'shift')==ordinal
    print(k,row,flush=True);return row
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='+',type=int,default=[60,384,1023]);p.add_argument('--output',default='CIG-032A-restore.json');a=p.parse_args();out=[]
    for k in a.sizes:out.append(run(k));open(a.output,'w').write(json.dumps(out,indent=2)+'\n')
