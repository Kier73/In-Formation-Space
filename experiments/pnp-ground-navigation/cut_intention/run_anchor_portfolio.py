"""Source-qualified usage benchmark; cold preparation, online and forecast controls."""
import argparse,json,random,time
from math import lcm
from run_disjunctive_time import fold
from run_output_time import fixture,circuit_source
from run_temporal_ground import timed
from inverse_time import spatial_groups
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_ground import Navigator
from verify_temporal_ground import Receiver
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from anchor_portfolio import Portfolio,wire_size
from verify_anchor_portfolio import PortfolioReceiver

def prepare(k,rare=False):
    _,_,_,_,ts,g,p,f,initial,P,start,_,markers,desired=fixture(k)
    periods=[len(z) for z in spatial_groups(p)]
    e=fold('and' if rare else 'xor',[a for a,b in markers]);n,s,q,fs=circuit_source(k,[e]);dec=synthesize_shared(n,s,q,fs);sec=compile_section(n,s,q)
    rec=Receiver(n,s,q,fs,dec,ts,3,g,initial,section=sec);nav=Navigator(k,3,g,dec);d,r=compile_algebra(nav,initial);a=Admission(rec,r);lang=Language(d,r)
    assert r['cutoff']==0
    if rare:
        def oracle(t):return (t-1-desired%P)//P+1
    else:
        weights={1:1}
        for L in periods:
            new=weights.copy()
            for m,v in weights.items():z=lcm(m,L);new[z]=new.get(z,0)-2*v
            weights={m:v for m,v in new.items() if v}
        def oracle(t):return (t-sum(v*((t-1-desired%m)//m+1) for m,v in weights.items()))//2
    assert lang.count(0)==oracle(P)
    return lang,a,oracle,n,P

def workloads(N,count,seed=3030):
    rng=random.Random(seed);lo=max(1,N//5);mid=max(1,N//2);hi=max(1,4*N//5)
    def cluster(c):return max(1,min(N,c+rng.randrange(-12,13)))
    return {'clustered':[cluster(mid) for _ in range(count)],'drifting':[max(1,min(N,mid+i*12)) for i in range(count)],'recurring':[cluster([lo,mid,hi][i%3]) for i in range(count)],'uniform':[rng.randrange(1,N+1) for _ in range(count)],'regime_shift':[cluster(lo if i<count//2 else hi) for i in range(count)],'repeat':[mid]*count}

def run(k,count,rare=False, labels=None, modes=None):
    (l,a,oracle,n,P),source_ms=timed(prepare,k,rare);N=l.count(0);rows=[]
    for label,js in workloads(N,count).items():
        if (rare and label!='recurring') or (labels is not None and label not in labels):continue
        queries=[(10**900+i*17)*N+j for i,j in enumerate(js)];baseline=None
        for mode in ('full','lru','demand','forecast','bad_forecast','ephemeral','adaptive'):
            if (modes is not None and mode not in modes) or (mode=='ephemeral' and label not in ('clustered','uniform','repeat')):continue
            start=time.perf_counter();v=PortfolioReceiver(a,0);p=Portfolio(l,v,capacity=0 if mode=='full' else 12,scan=128,policy=mode if mode in ('full','lru','demand') else 'demand',full_mode=mode if mode in ('ephemeral','adaptive') else 'retain',partial_budget=64 if mode=='ephemeral' else 0)
            chosen=[]
            if mode in ('forecast','bad_forecast'):
                forecast=workloads(N,count,seed=5050)[label] if mode=='forecast' else [max(1,N//9)]*count
                chosen=p.acquire(forecast,slots=4,full_cost=2048,seed_cost=2048,retention_price=16)
            times=[];results=[]
            for ordinal in queries:
                t0=time.perf_counter();z=p.query(ordinal);times.append((time.perf_counter()-t0)*1000);results.append(z)
            ms=(time.perf_counter()-start)*1000
            for ordinal,z in zip(queries,results):
                assert z['status']=='FOUND',(k,label,mode,z);t=int(z['time']);assert oracle(t)==ordinal-1 and oracle(t+1)==ordinal,(k,label,mode)
            if baseline is None:baseline=results
            else:assert results==baseline
            assert p.x.anchors==v.anchors and len(p.x.anchors)-2<=p.capacity
            row=dict(bits=k,n=n,rare=rare,period=str(P),events=str(N),source_ms=source_ms,workload=label,mode=mode,queries=count,elapsed_ms=ms,median_query_ms=sorted(times)[len(times)//2],forecast_seeds=list(map(str,chosen)),retained_anchor_bytes=wire_size(p.x.anchors),retained_rank_bytes=wire_size(p.full.packet()) if p.full else 0,stats=dict(p.stats))
            rows.append(row);print(k,label,mode,round(ms,2),p.stats['anchor_hits'],p.stats['local_hits'],p.stats['full_hits'],p.stats['rank_opens'],flush=True)
    return rows

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--sizes',nargs='+',type=int,default=[60,174,384,1023]);ap.add_argument('--count',type=int,default=32);ap.add_argument('--output',default='CIG-030A-results.json');args=ap.parse_args();rows=[]
    for k in args.sizes:
        rows+=run(k,args.count);open(args.output,'w').write(json.dumps(rows,indent=2)+'\n')
    rows+=run(args.sizes[-1],args.count,rare=True);open(args.output,'w').write(json.dumps(rows,indent=2)+'\n')
