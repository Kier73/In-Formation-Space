"""CIG-013: charged retention and actual source-revision workload."""
import json
from collections import Counter
from time import perf_counter_ns
from adaptive_ground import leaf, balanced, realize
from architecture_memory import Archive
from architecture_navigation import packed
from anticipatory_memory import Portfolio, Retained, leaves, region
from run_architecture_navigation import cycle, oracle


def timed(f,*a,**kw):
    t=perf_counter_ns(); r=f(*a,**kw); return r,(perf_counter_ns()-t)/1e6


def make_case(k, repeats=8):
    n, cs, x=cycle(k)
    tree=balanced(packed(cs,n,'walk',8))
    base=leaves(cs,n,tree); pos={v:i for i,v in enumerate(x)}
    eligible=[(cov,tuple(v for v in cov[0] if v not in b and v in pos)) for cov,b in base]
    hot=dict((cov,vs) for cov,vs in eligible[::3] if vs)
    def case(i, changed=False):
        pins={}; additions={}
        for j,(cov,vs) in enumerate(hot.items()):
            v=vs[i%len(vs)]; u=pos[v]
            bit=int((u//2+i//2)%3==0)
            extra=[(v if bit else -v,)]
            if j==0 and (i%4==3 or changed):extra.append((-extra[0][0],))
            pins[u]=bit; additions[cov]=extra
        def rebuild(t):
            if isinstance(t,dict):
                cov=region(t['scope'],t['clauses'])
                return leaf(t['scope'],[*cov[1],*additions.get(cov,[])])
            return [rebuild(z) for z in t]
        new=cs+[c for block in additions.values() for c in block]
        # Canonical source and unique clause ownership audited by realize/Portfolio.
        return new,rebuild(tree),0 if i%4==3 or changed else oracle(k,pins)
    return n,cs,tree,[case(i) for i in range(repeats)],case(0,True),len(hot)


def campaign(k):
    n,cs,tree,forecasts,replacement,hot=make_case(k)
    out=dict(n=n,clauses=len(cs),queries=len(forecasts),hot_regions=hot)
    def plan(rich):
        p=Portfolio(cs,n,tree,price=1,rich=rich)
        for i,(source,t,_) in enumerate(forecasts):p.add(i,source,t)
        return p
    for name,rich in [('current_only',False),('anticipatory',True)]:
        p,planning=timed(plan,rich)
        selected,meta=p.selection(); m,preparation=timed(Retained,p)
        totals=Counter(); elapsed=0; checked=0
        for source,t,count in forecasts:
            r,ms=timed(realize,source,n,t,m.session()); assert int(r['count'])==count
            elapsed+=ms; totals.update(r['metrics']);checked+=1
        out[name]=dict(plan=meta,selection_ms=planning,prepare_ms=preparation,prepare=dict(m.stats),retained_wire_bytes=m.bytes,queries_ms=elapsed,queries_metrics=dict(totals),checked=checked)
        if rich:
            old=p.touched;_,replace_ms=timed(p.replace,0,replacement[0],replacement[1]);delta=p.touched-old
            q=Portfolio(cs,n,tree,price=1,rich=True)
            def fresh():
                for i,(source,t,_) in enumerate([replacement,*forecasts[1:]]):q.add(i,source,t)
            _,fresh_ms=timed(fresh)
            assert p.selection()[0]==q.selection()[0] and p.selection()[1]['objective']==q.selection()[1]['objective']
            result=realize(replacement[0],n,replacement[1],m.session());assert int(result['count'])==replacement[2]
            out['replacement']=dict(groups_refreshed=delta,all_groups=len(p.current),update_ms=replace_ms,fresh_plan_ms=fresh_ms,verified_count=result['count'])
    totals=Counter(); elapsed=0
    for source,t,count in forecasts:
        r,ms=timed(realize,source,n,t,Archive());assert int(r['count'])==count
        elapsed+=ms;totals.update(r['metrics'])
    out['cold']=dict(queries_ms=elapsed,queries_metrics=dict(totals),checked=len(forecasts))
    out['counts']=[str(c) for _,_,c in forecasts]
    return out


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='+',type=int,default=[32,256,1024,4096]);p.add_argument('--output',default='CIG-013-results.json');a=p.parse_args()
    rows=[]
    for k in a.sizes:
        r=campaign(k);rows.append(r)
        with open(a.output,'w') as f:json.dump(rows,f,indent=2);f.write('\n')
        print('completed',r['n'],'hot',r['hot_regions'],'cold',r['cold']['queries_metrics']['producer_cells'],'current',r['current_only']['queries_metrics']['producer_cells'],'anticipatory',r['anticipatory']['queries_metrics'].get('producer_cells',0),'restriction',r['anticipatory']['queries_metrics'].get('restriction_cells',0),'times',round(r['cold']['queries_ms']),round(r['anticipatory']['queries_ms']),flush=True)
