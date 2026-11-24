"""Reproducible CIG-012 cross-partition and revision campaign."""
import json, random
from time import perf_counter_ns
from architecture_memory import Archive, choose, coarsen
from architecture_navigation import packed
from adaptive_ground import realize, balanced, Memory, revise
from run_architecture_navigation import cycle, oracle

def timed(fn,*a,**kw):
    t=perf_counter_ns();out=fn(*a,**kw);return out,(perf_counter_ns()-t)/1e6

def compact(r,ms):
    return dict(ms=ms,metrics=r['metrics'],messages=len(r['messages']),root=r['root'],audit_ms=r['audit_ns']/1e6,navigation_ms=r['navigation_ns']/1e6,witness_ms=r['witness_ns']/1e6)

def campaign(sizes=(32,128,512,2048,4096)):
    rows=[]
    for k in sizes:
        n,c,_=cycle(k);a=balanced(packed(c,n,'walk',3));b=coarsen(a,8);d=balanced(packed(c,n,'walk',8));cat={'fine':a,'aligned_coarse':b,'independent_coarse':d}
        count=str(oracle(k));m=Archive();cold_choice,choice_ms=timed(choose,c,n,cat,m)
        old,old_ms=timed(realize,c,n,a,m);warm_choice,warm_choice_ms=timed(choose,c,n,cat,m,message_weight=1)
        coarse,coarse_ms=timed(realize,c,n,b,m);fresh,fresh_ms=timed(realize,c,n,b,Archive())
        legacy_mem=Memory();realize(c,n,a,legacy_mem);legacy,legacy_ms=timed(realize,c,n,b,legacy_mem)
        unrelated,unrelated_ms=timed(realize,c,n,d,m);unrelated_cold,unrelated_cold_ms=timed(realize,c,n,d,Archive())
        back,back_ms=timed(realize,c,n,a,m)
        reverse=Archive();realize(c,n,b,reverse);stay,stay_ms=timed(choose,c,n,cat,reverse);rev,rev_ms=timed(realize,c,n,a,reverse)
        assert all(x['count']==count for x in (old,coarse,fresh,legacy,unrelated,unrelated_cold,back,rev))
        assert coarse['root']==fresh['root']==legacy['root'] and back['root']==old['root'] and unrelated['root']==unrelated_cold['root']
        assert coarse['metrics'].get('new_full_checks',0)==0
        row=dict(n=n,clauses=len(c),count=count,initial=compact(old,old_ms),aligned_warm=compact(coarse,coarse_ms),aligned_cold=compact(fresh,fresh_ms),legacy=compact(legacy,legacy_ms),independent_warm=compact(unrelated,unrelated_ms),independent_cold=compact(unrelated_cold,unrelated_cold_ms),restored=compact(back,back_ms),reverse_cold_coarse_to_fine=compact(rev,rev_ms),cold_choice={k:v for k,v in cold_choice.items() if k!='tree'},cold_selection_ms=choice_ms,warm_choice={k:v for k,v in warm_choice.items() if k!='tree'},warm_selection_ms=warm_choice_ms,coarse_resident_choice={k:v for k,v in stay.items() if k!='tree'},coarse_resident_selection_ms=stay_ms)
        rows.append(row); print('completed',n,'aligned',coarse['metrics'],'cold',fresh['metrics'],'ms',round(coarse_ms,2),round(fresh_ms,2),'choices',cold_choice['selected'],warm_choice['selected'],stay['selected'],flush=True)
    return rows

def revisions(k=128,repeats=16):
    n,c,x=cycle(k);base=balanced(packed(c,n,'walk',3));coarse=coarsen(base);m=Archive();realize(c,n,base,m);realize(c,n,coarse,m);rng=random.Random(1209);out=[]
    for i in range(repeats):
        u=rng.randrange(k);b=rng.randrange(2);extra=[(x[u] if b else -x[u],)];expected=oracle(k,{u:b})
        if i%4==3:extra.append((-extra[0][0],));expected=0
        src=c+extra; a,_=revise(base,src,n,split=False);d,_=revise(coarse,src,n,split=False)
        choice,sel_ms=timed(choose,src,n,{'fine':a,'coarse':d},m,check_weight=4,message_weight=1)
        r,ms=timed(realize,src,n,choice['tree'],m);fresh,fms=timed(realize,src,n,choice['tree'],Archive());other=realize(src,n,d if choice['selected']=='fine' else a,m)
        assert r['count']==fresh['count']==other['count']==str(expected)
        out.append(dict(i=i,selected=choice['selected'],count=r['count'],selection_ms=sel_ms,warm=compact(r,ms),cold=compact(fresh,fms),alternate_metrics=other['metrics']))
    print('completed',repeats,'revision checks',flush=True);return out

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',default='CIG-012-results.json');p.add_argument('--max-k',type=int,default=4096);args=p.parse_args()
    report=dict(cross_partition=campaign(tuple(k for k in (32,128,512,2048,4096) if k<=args.max_k)),revisions=revisions())
    with open(args.output,'w') as f:json.dump(report,f,indent=2)
