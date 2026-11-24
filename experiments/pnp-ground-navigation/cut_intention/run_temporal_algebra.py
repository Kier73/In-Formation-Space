"""CIG-024: exact full-period set algebra on proof-derived wide goals."""
import argparse,json,random
from math import lcm,prod
from run_disjunctive_time import fold
from run_output_time import fixture,circuit_source,expr_eval
from run_temporal_ground import timed,power_oracle,size
from inverse_time import spatial_groups
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_ground import Navigator
from verify_temporal_ground import Receiver
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from disjunctive_time import seek
from verify_disjunctive_time import verify

def parity_count(periods,P):
    # Independent inclusion-exclusion on synchronized marker events.
    # Sum_t (-1)^parity = sum_S (-2)^|S| P/lcm(S).
    weights={1:1}
    for L in periods:
        new=weights.copy()
        for m,v in weights.items():
            z=lcm(m,L);new[z]=new.get(z,0)-2*v
        weights=new
    return (P-sum(v*(P//m) for m,v in weights.items()))//2

def trial(k):
    _,_,_,_,ts,g,p,f,initial,P,start,_,markers,desired=fixture(k)
    periods=[len(z) for z in spatial_groups(p)]
    parity=fold('xor',[a for a,b in markers]);A=fold('and',[a for a,b in markers]);B=fold('and',[b for a,b in markers]);alt=('or',A,B);impossible=('or',('and',*markers[0]),('and',*markers[-1]))
    n,s,q,fs=circuit_source(k,[parity,alt,impossible]);dec,ct=timed(synthesize_shared,n,s,q,fs);assert dec['status']=='COMPLETE' and all(x['status']=='SUFFICIENT' for x in dec['goals']);sec,st=timed(compile_section,n,s,q);rec,rt=timed(Receiver,n,s,q,fs,dec,ts,3,g,initial,section=sec);nav=Navigator(k,3,g,dec)
    (d,r),cm=timed(compile_algebra,nav,initial);a,vm=timed(Admission,rec,r);lang=Language(d,r)
    expected=[parity_count(periods,P),2,0];assert prod(d.base)==P
    counts=[]
    for i,ex in enumerate(expected):
        count,cms=timed(lang.count,i);other,vms=timed(a.count,i);assert count==other==ex
        counts.append(dict(root=i,count=str(count),producer_ms=cms,receiver_ms=vms))
    # A set not asked for during original proof compilation: correlate future times.
    def extend():
        shifted=lang.extend('shift',1,1);both=lang.extend('and',1,shifted);either=lang.extend('or',1,shifted);notalt=lang.extend('not',1);cross=lang.extend('and',0,1);xor=lang.extend('xor',1,shifted);return [shifted,both,either,notalt,cross,xor]
    ids,em=timed(extend);_,ev=timed(a.extend,lang.export());exs=[2,1,3,P-2,len(markers)%2,2]
    for i,ex in zip(ids,exs):assert lang.count(i)==a.count(i)==ex,(i,ex,lang.count(i))
    queries=[]
    for name,i,phase in [('parity',0,None),('rare',1,[desired,desired+1]),('impossible',2,[]),('shift_intersection',ids[1],[desired]),('shift_union',ids[2],[desired-1,desired,desired+1])]:
        rr,tm=timed(lang.next,i,start);ok,vt=timed(a.verify_next,i,start,rr);assert ok,(name,rr['status'])
        if phase is None:
            # Direct modular marker oracle, independent of decision diagram.
            t=start
            while sum((t-desired)%L==0 for L in periods)%2==0:t+=1
            expected_time=t
        else:expected_time=min((start+(x-start)%P for x in phase),default=None)
        assert (int(rr['time']) if rr['time'] is not None else None)==expected_time,(name,rr,expected_time)
        queries.append(dict(name=name,offset=None if expected_time is None else str(expected_time-start),status=rr['status'],states=len(rr['trace']),producer_ms=tm,receiver_ms=vt,receipt_bytes=size(rr)))
    windows=[]
    # Whole-period arithmetic counts an enormous interval in a single multiplication.
    # The rare set also supports a nonperiod-aligned remainder via CRT classes.
    for name,i,hi,ex in [('parity_whole_periods',0,start+P*10**900,expected[0]*10**900),('rare_window',1,start+P*10**900+P//2+1,2*10**900+1)]:
        z,im=timed(lang.interval,i,start,hi);ok,iv=timed(a.verify_interval,i,start,hi,z);assert ok and int(z['count'])==ex,(name,z,ex)
        windows.append(dict(name=name,count=z['count'],states=z['states'],producer_ms=im,receiver_ms=iv))
    # Deliberate budget control on a broad, non-period-aligned interval.
    control=lang.interval(0,start,start+P//2,max_states=1000)
    if control['status']=='EXACT':assert a.verify_interval(0,start,start+P//2,control,max_states=1000)
    else:assert not a.verify_interval(0,start,start+P//2,control,max_states=1000)
    # Repeated new start coordinates, retained diagram vs CIG-023 rebuild.
    rng=random.Random(24);times=[start+rng.randrange(P) for _ in range(8)]
    def warm():
        for t in times:
            z=lang.next(1,t);assert a.verify_next(1,t,z);assert int(z['time'])==min(t+(x-t)%P for x in (desired,desired+1))
    def old():
        for t in times:
            z=seek(nav,initial,[None,1,None],t,interval_steps=0);assert verify(rec,[None,1,None],t,z,interval_steps=0);assert int(z['time'])==min(t+(x-t)%P for x in (desired,desired+1))
    _,warm_ms=timed(warm);_,old_ms=timed(old)
    return dict(n=n,observed=k,period=str(P),base=r['base'],decoder_ms=ct,section_ms=st,admit_ms=rt,local_cells=r['cells'],base_nodes=len(r['nodes']),base_arcs=sum(len(x[1]) for x in r['nodes']),base_bytes=size(r),diagram_work=r['work'],compile_ms=cm,verify_ms=vm,counts=counts,extension_ms=em,extension_verify_ms=ev,extended_nodes=len(d.nodes),extended_bytes=size(lang.export()),new_counts=list(map(str,exs)),queries=queries,windows=windows,interval_control=control,repeat8_warm_ms=warm_ms,repeat8_cig023_ms=old_ms)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='+',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='CIG-024-results.json');args=p.parse_args();rows=[]
    for k in args.sizes:
        r=trial(k);rows.append(r);open(args.output,'w').write(json.dumps(rows,indent=2)+'\n');print(json.dumps(r),flush=True)
