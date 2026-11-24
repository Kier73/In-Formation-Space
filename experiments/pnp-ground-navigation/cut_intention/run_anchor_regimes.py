"""Additional hold-out regime change, direct CIG-025 baseline, and cost sweep."""
import argparse,json,random,time
from run_anchor_portfolio import prepare,workloads
from anchor_portfolio import Portfolio,wire_size
from verify_anchor_portfolio import PortfolioReceiver
from temporal_rank import Rank
from verify_temporal_rank import CheckedRank

def run(k,labels=None):
    l,a,oracle,n,P=prepare(k);N=l.count(0);rng=random.Random(303030);rows=[]
    mid=max(1,N//2);hot=[mid]*10
    cases={'hot_cold_hot':hot+[rng.randrange(1,N+1) for _ in range(8)]+hot,
           'clustered':workloads(N,24)['clustered'],'uniform':workloads(N,24)['uniform']}
    for label,js in cases.items():
        if labels is not None and label not in labels:continue
        queries=[(10**900+i*17)*N+j for i,j in enumerate(js)];expected=None
        for mode,price in [('direct',0),('retain',0),('adaptive',0),('adaptive',5),('adaptive',500),('ephemeral',0)]:
            start=time.perf_counter();results=[];opens=[]
            if mode=='direct':
                rank=Rank(l,0);checked=CheckedRank(a,rank.packet());size=wire_size(rank.packet())
                for k0 in queries:
                    z=rank.select(k0);assert checked.verify_select(k0,z);results.append({'status':z['status'],'time':z['time']})
                stats={'rank_opens':1,'resident_rank_byte_queries':size*len(queries)};retained=size
            else:
                v=PortfolioReceiver(a,0);p=Portfolio(l,v,capacity=12,scan=128,full_mode=mode,retention_price_ns=price)
                for k0 in queries:
                    z=p.query(k0);results.append(z);opens.append(p.stats['rank_opens']);assert p.x.anchors==v.anchors
                stats=dict(p.stats);retained=wire_size(p.full.packet()) if p.full else 0
            ms=(time.perf_counter()-start)*1000
            for j,z in zip(queries,results):
                assert z['status']=='FOUND';t=int(z['time']);assert oracle(t)==j-1 and oracle(t+1)==j
            if expected is None:expected=results
            else:assert results==expected
            row=dict(bits=k,n=n,period=str(P),workload=label,mode=mode,price_ns=price,queries=len(queries),elapsed_ms=ms,retained_rank_bytes=retained,open_history=opens,stats=stats)
            rows.append(row);print(label,mode,price,round(ms,2),stats['rank_opens'],stats['resident_rank_byte_queries'],flush=True)
    return rows

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--bits',type=int,default=1023);ap.add_argument('--output',default='CIG-030A-regimes.json');ap.add_argument('--labels',nargs='+',default=['hot_cold_hot']);args=ap.parse_args();rows=run(args.bits,args.labels);open(args.output,'w').write(json.dumps(rows,indent=2)+'\n')
