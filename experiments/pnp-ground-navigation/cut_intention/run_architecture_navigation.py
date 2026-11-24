"""CIG-011 stress campaign: mixed affine/nonlinear cyclic source, independent 2x2 oracle."""
import json,random
from time import perf_counter_ns
from architecture_navigation import select,select_widths,score,optimize_order,packed,pareto
from adaptive_ground import realize,Memory,balanced,initial
from run_composed_ground import xor_clauses,chain


def cycle(k,seed=73,contradiction=False):
    # z_i=0 plus z_i = x_i XOR x_{i+1} (even i), AND (odd i).
    # Original labels and rows shuffled, no decomposition hints supplied.
    n=2*k; ids=list(range(1,n+1));rng=random.Random(seed);rng.shuffle(ids);x=ids[:k];z=ids[k:];rows=[]
    for i in range(k):
        a,b,h=x[i],x[(i+1)%k],z[i]
        rows+=list(xor_clauses((a,b,h))) if i%2==0 else [(-a,-b,h),(a,-h),(b,-h)]
        rows.append((-h,))
    if contradiction:rows.extend([(x[0],),(-x[1],)])
    rng.shuffle(rows)
    return n,rows,x


def oracle(k,pins=None):
    """Trace of transfer-matrix product, with optional fixed x coordinates."""
    pins=pins or {};p=[[1,0],[0,1]]
    for i in range(k):
        a=[[int((u==v if i%2==0 else not(u and v)) and (i not in pins or pins[i]==u)) for v in (0,1)] for u in (0,1)]
        p=[[sum(p[r][j]*a[j][c] for j in (0,1)) for c in (0,1)] for r in (0,1)]
    return p[0][0]+p[1][1]


def timed(fn,*a,**kw):
    t=perf_counter_ns();r=fn(*a,**kw);return r,(perf_counter_ns()-t)/1e6


def run_cycles(sizes=(32,128,512,1024,2048,4096)):
    cases=[]
    for k in sizes:
        n,rows,x=cycle(k);choice=select_widths(rows,n)
        assert choice['status']=='SELECTED',choice
        mem=Memory();result,ms=timed(realize,rows,n,choice['tree'],mem)
        assert int(result['count'])==oracle(k)
        # Matched balanced alternative with the same leaf partition as a qualified candidate.
        old=None
        for method in ('walk',):
            try:
                tree=balanced(packed(rows,n,method));s=score(rows,n,tree)
                alt,altms=timed(realize,rows,n,tree,mem)
                assert alt['count']==result['count']
                cold,coldms=timed(realize,rows,n,tree,Memory())
                assert cold['count']==result['count']
                # Reverse transition: warm previous wide layout -> selected architecture.
                warm_memory=Memory();realize(rows,n,tree,warm_memory)
                warm,wm=timed(realize,rows,n,choice['tree'],warm_memory)
                assert warm['count']==result['count']
                old=dict(method=method,score=s,transition_ms=altms,transition=alt['metrics'],cold_ms=coldms,cold=cold['metrics'],wide_to_selected_ms=wm,wide_to_selected=warm['metrics']);break
            except OverflowError:pass
        cases.append(dict(n=n,clauses=len(rows),count=result['count'],selection_ms=choice['selection_ns']/1e6,selected=choice['selected'],leaf_budget=choice['leaf_budget'],score=choice['score'],candidates=choice['candidates'],realize_ms=ms,metrics=result['metrics'],alternate=old))
    return cases

def run_revisions():
    revisions=[];n,rows,x=cycle(512);p=select_widths(rows,n);mem=Memory();base=realize(rows,n,p['tree'],mem)
    from adaptive_ground import revise
    rng=random.Random(1109)
    for i in range(24):
        # Pin one independently selected ring variable; every fourth revision contradiction.
        u=rng.randrange(512);b=rng.randrange(2);extra=[(x[u] if b else -x[u],)];pins={u:b}
        if i%4==3:extra.append((-extra[0][0],));expected=0
        else:expected=oracle(512,pins)
        current=rows+extra
        tree,changes=revise(p['tree'],current,n,split=False)
        warm,ms=timed(realize,current,n,tree,mem);fresh,fms=timed(realize,current,n,tree,Memory())
        assert warm['count']==fresh['count']==str(expected)
        revisions.append(dict(i=i,count=warm['count'],warm_ms=ms,cold_ms=fms,metrics=warm['metrics']))
    controls=[]
    for n in (50,100,200,500):
        rng=random.Random(73);rows=[tuple(v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),3)) for _ in range(round(4.26*n))]
        p=select(rows,n);controls.append(dict(n=n,status=p['status'],candidates=p['candidates'],selection_ms=p['selection_ns']/1e6))
    return dict(revisions=revisions,controls=controls)

def run_transitions(sizes=(512,2048,4096)):
    transitions=[]
    for k in sizes:
        n,c,x=cycle(k);ls=packed(c,n,'walk',8);a=balanced(ls);b,dp=optimize_order(ls);m=Memory()
        old,ams=timed(realize,c,n,a,m);new,bms=timed(realize,c,n,b,m);cold,cms=timed(realize,c,n,b,Memory());restored,rms=timed(realize,c,n,a,m)
        assert int(old['count'])==oracle(k) and old['count']==new['count']==cold['count']==restored['count']
        assert new['root']==cold['root'] and old['root']==restored['root']
        transitions.append(dict(n=n,old=score(c,n,a),new=score(c,n,b),dp=dp,old_ms=ams,warm_ms=bms,cold_ms=cms,restore_ms=rms,warm=new['metrics'],fresh=cold['metrics'],restore=restored['metrics']))
    return transitions

def run_pricing():
    n,c,x=cycle(4096); priced=select_widths(c,n,message_weight=64)
    p=realize(c,n,priced['tree']);assert int(p['count'])==oracle(4096)
    pricing=dict(weight=64,selected=priced['selected'],leaf_budget=priced['leaf_budget'],score=priced['score'],metrics=p['metrics'],selection_ms=priced['selection_ns']/1e6,frontier=pareto(priced['candidates']))
    return pricing

def run():
    return dict(cycles=run_cycles(),**run_revisions(),reassociation=run_transitions(),pricing=run_pricing())

if __name__=='__main__':print(json.dumps(run(),indent=2))
