"""CIG-025 campaign on CIG-024's actual source-qualified decoder and transport."""
import argparse,json
from math import lcm
from run_disjunctive_time import fold
from run_output_time import fixture,circuit_source
from run_temporal_ground import timed,size
from inverse_time import spatial_groups
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_ground import Navigator
from verify_temporal_ground import Receiver
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from temporal_rank import Rank
from verify_temporal_rank import CheckedRank


def trial(k):
    _,_,_,_,ts,g,p,f,initial,P,start,_,markers,desired=fixture(k)
    periods=[len(z) for z in spatial_groups(p)]
    parity=fold('xor',[a for a,b in markers]);alt=('or',fold('and',[a for a,b in markers]),fold('and',[b for a,b in markers]));impossible=('or',('and',*markers[0]),('and',*markers[-1]))
    n,s,q,fs=circuit_source(k,[parity,alt,impossible]);dec,ct=timed(synthesize_shared,n,s,q,fs);assert dec['status']=='COMPLETE' and all(x['status']=='SUFFICIENT' for x in dec['goals']);sec,st=timed(compile_section,n,s,q);rec,rt=timed(Receiver,n,s,q,fs,dec,ts,3,g,initial,section=sec);nav=Navigator(k,3,g,dec)
    (d,r),cm=timed(compile_algebra,nav,initial);a,vm=timed(Admission,rec,r);lang=Language(d,r);assert r['cutoff']==0
    # Independent marker-level inclusion-exclusion. Does not access the MDD or its terms.
    weights={1:1}
    for L in periods:
        new=weights.copy()
        for m,v in weights.items():
            z=lcm(m,L);new[z]=new.get(z,0)-2*v
        weights={m:v for m,v in new.items() if v}
    def oracle(t,i):
        if i==0:
            q,s=divmod(t,P)
            def prefix(h):return (h-sum(v*((h-1-desired%m)//m+1) for m,v in weights.items()))//2
            return q*prefix(P)+prefix(s)
        if i==1:return sum((t-1-x%P)//P+1 for x in (desired,desired+1))
        if i==2:return 0
        return t-oracle(t,1)
    complement=lang.extend('not',1);a.extend(lang.export());assert complement==3
    rows=[]
    for i,name in enumerate(['parity','rare','impossible','dense_complement']):
        x,prep=timed(Rank,lang,i);y,verify=timed(CheckedRank,a,x.packet());assert x.total==oracle(P,i)
        lo=start;hi=lo+P//2;value,ms=timed(lambda:x.rank(hi)-x.rank(lo));other,vs=timed(lambda:y.rank(hi)-y.rank(lo));assert value==other==oracle(hi,i)-oracle(lo,i)
        control=lang.interval(i,lo,hi,max_states=1000)
        if control['status']=='EXACT':assert int(control['count'])==value
        # Very distant ordinal, independently verified by source marker formula.
        ordinal=10**900+173;z,sm=timed(x.select,ordinal);ok,sv=timed(y.verify_select,ordinal,z);assert ok
        full,fm=timed(x.select,ordinal,bounded=False);assert full['status']==z['status'] and full['time']==z['time']
        if z['status']=='FOUND':
            t=int(z['time']);assert oracle(t,i)==ordinal-1 and oracle(t+1,i)==ordinal
        else:assert i==2 and z['status']=='UNREACHABLE'
        rows.append(dict(name=name,terms=len(x.terms),work=x.work,packet_bytes=size(x.packet()),compile_ms=prep,verify_ms=verify,partial_count=str(value),rank_interval_ms=ms,rank_check_ms=vs,old_interval_status=control['status'],select_status=z['status'],select_time=z['time'],select_probes=z['probes'],select_ms=sm,select_verify_ms=sv,full_select_ms=fm,full_select_probes=full['probes']))
    return dict(n=n,observed=k,period=str(P),decoder_ms=ct,section_ms=st,receiver_ms=rt,algebra_ms=cm,algebra_check_ms=vm,oracle_terms=len(weights),results=rows)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='+',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='CIG-025-results.json');args=p.parse_args();rows=[]
    for k in args.sizes:
        row=trial(k);rows.append(row);open(args.output,'w').write(json.dumps(rows,indent=2)+'\n');print(k,[(x['name'],x['terms'],x['partial_count'],round(x['compile_ms']+x['verify_ms'],3),round(x['rank_interval_ms']+x['rank_check_ms'],3),round(x['select_ms']+x['select_verify_ms'],3),x['old_interval_status']) for x in row['results']],flush=True)
