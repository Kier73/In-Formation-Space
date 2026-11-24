"""Reproducible topology and semantic-continuity stress campaign."""
import json,random
from time import perf_counter
from adaptive_ground import initial,revise,realize,Memory,leaf,balanced,wire
from regional_memory import discover,realize as frozen
from run_composed_ground import chain,xor_clauses


def timed(fn,*a,**kw):
    t=perf_counter();r=fn(*a,**kw);return r,round((perf_counter()-t)*1000,3)

def summary(r,ms):
    return dict(count=r['count'],ms=ms,messages=len(r['messages']),bytes=len(wire(r['messages'])),**r['metrics'])

def coords(stages,n):
    p=list(range(1,n+1));random.Random(73).shuffle(p);return p[:stages+1]

def expected(stages,x,extras):
    # Independent threshold oracle for this fixture's monotone bit sequences.
    idx={v:i for i,v in enumerate(x)}
    return sum(all(any((idx[abs(l)]>=t)==(l>0) for l in row) for row in extras) for t in range(stages+2))

def run():
    cases=[]
    for stages in (32,128,256,512,1024):
        n,c=chain(stages);x=coords(stages,n);p,pms=timed(initial,c,n);m=Memory()
        a,ams=timed(realize,c,n,p,m);assert int(a['count'])==stages+2
        extra=[(x[0],-x[stages//2])];d=c+extra
        (q,changes),qms=timed(revise,p,d,n);b,bms=timed(realize,d,n,q,m);f,fms=timed(realize,d,n,q,Memory())
        assert b['count']==f['count']==str(expected(stages,x,extra)) and b['root']==f['root']
        refused=False
        try:frozen(d,n,discover(c,n))
        except OverflowError:refused=True
        assert refused
        (r,back),rms=timed(revise,q,c,n);z,zms=timed(realize,c,n,r,m);assert z['root']==a['root']
        control=None
        if stages<=256:
            from composed_ground import compile_ground
            from verify_composed_ground import verify
            g,gms=timed(compile_ground,d,n);ok,vms=timed(verify,d,n,g);assert ok and g['count']==b['count'];control={'compile_ms':gms,'verify_ms':vms,'count':g['count']}
        cases.append(dict(stages=stages,n=n,clauses=len(c),plan_ms=pms,old=summary(a,ams),adaptive_plan_ms=qms,changes=changes,incremental=summary(b,bms),fresh=summary(f,fms),frozen_refused=refused,restoration_plan_ms=rms,restoration_changes=back,restored=summary(z,zms),cig008=control))
    stages=128;n,c=chain(stages);x=coords(stages,n);p=initial(c,n);m=Memory();realize(c,n,p,m);rng=random.Random(1009);out=[];extras=[]
    for k in range(96):
        if k%4==0:extras=[]
        elif k%4==3:extras.pop(0)
        else:
            u,v=rng.sample(x,2);extras.append((u*rng.choice([-1,1]),v*rng.choice([-1,1])))
        d=c+extras;(p,changes),pms=timed(revise,p,d,n);b,bms=timed(realize,d,n,p,m);f,fms=timed(realize,d,n,p,Memory())
        assert b['count']==f['count']==str(expected(stages,x,extras)) and b['root']==f['root']
        out.append(dict(revision=k,extras=[list(row) for row in extras],count=b['count'],replan_ms=pms,incremental_ms=bms,fresh_ms=fms,changes=changes,metrics=b['metrics'],messages=len(b['messages'])))
    # Heterogeneous connected source, enormous exact count, changed proof with same function.
    n=3;c=[(-1,-2,3),(1,-3),(2,-3)];end=3
    for _ in range(2048):
        n+=2;c+=xor_clauses((end,n-1,n));end=n
    p=initial(c,n,width=3);m=Memory();a,ams=timed(realize,c,n,p,m);assert int(a['count'])==4*2**2048
    d=c+[(1,2,-3)];(q,s),qms=timed(revise,p,d,n,split=False,width=3);b,bms=timed(realize,d,n,q,m);assert a['count']==b['count'] and a['root']!=b['root'];assert b['metrics']['new_full_checks']==1
    f,fms=timed(realize,d,n,q,Memory());assert f['root']==b['root']
    mixed=dict(n=n,clauses=len(c),count_log2=2050,original=summary(a,ams),revision_plan_ms=qms,revision=summary(b,bms),fresh=summary(f,fms))
    n=4096;c=[];leaves=[]
    for v in range(1,n+1,4):
        rows=[(v,v+1),(v+2,v+3)];c+=rows;leaves.append(leaf(range(v,v+4),rows))
    p=balanced(leaves);m=Memory();a,ams=timed(realize,c,n,p,m);assert int(a['count'])==3**2048
    (q,s),qms=timed(revise,p,c,n,split=True);b,bms=timed(realize,c,n,q,m);assert b['count']==a['count']
    (r,t),rms=timed(revise,q,c,n,split=False,merge=True,width=4);z,zms=timed(realize,c,n,r,m);assert z['root']==a['root']
    splitmerge=dict(n=n,clauses=len(c),original=summary(a,ams),split_changes=s,split_plan_ms=qms,split=summary(b,bms),merge_changes=t,merge_plan_ms=rms,merged=summary(z,zms))
    refusals=[]
    for n in (50,100,200,500):
        rng=random.Random(73);c=[tuple(v*rng.choice([-1,1]) for v in rng.sample(range(1,n+1),3)) for _ in range(round(4.26*n))]
        try:p=initial(c,n);realize(c,n,p);status='EXACT';reason=None
        except OverflowError as e:status='UNKNOWN';reason=str(e)
        refusals.append(dict(n=n,clauses=len(c),status=status,reason=reason))
    return dict(cross_region=cases,revision_sequence=out,semantic_quiescence=mixed,split_merge=splitmerge,dense_controls=refusals)

if __name__=='__main__':print(json.dumps(run(),indent=2))
