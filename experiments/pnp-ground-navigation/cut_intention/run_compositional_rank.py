"""Source-qualified usage, including unfamiliar targets after old proof eviction."""
import argparse,json,time,random
from math import lcm
from run_disjunctive_time import fold
from run_output_time import fixture,circuit_source
from inverse_time import spatial_groups
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_ground import Navigator
from verify_temporal_ground import Receiver
from temporal_algebra import compile_algebra,Language,Budget
from verify_temporal_algebra import Admission
from temporal_rank import Rank
from verify_temporal_rank import CheckedRank
from compositional_rank import Memory,make_link
from verify_compositional_rank import MemoryReceiver
from anchor_portfolio import wire_size


def prepare(k):
    _,_,_,_,ts,g,p,f,initial,P,start,_,markers,desired=fixture(k)
    periods=[len(z) for z in spatial_groups(p)]
    parity=fold('xor',[a for a,b in markers]);rare=('or',fold('and',[a for a,b in markers]),fold('and',[b for a,b in markers]))
    n,s,q,fs=circuit_source(k,[parity,rare]);dec=synthesize_shared(n,s,q,fs);sec=compile_section(n,s,q);rec=Receiver(n,s,q,fs,dec,ts,3,g,initial,section=sec);nav=Navigator(k,3,g,dec);d,r=compile_algebra(nav,initial);a=Admission(rec,r);l=Language(d,r);assert l.D==0
    weights={1:1}
    for L in periods:
        new=weights.copy()
        for m,v in weights.items():z=lcm(m,L);new[z]=new.get(z,0)-2*v
        weights={m:v for m,v in new.items() if v}
    def base(t):return (t-sum(v*((t-1-desired%m)//m+1) for m,v in weights.items()))//2
    rare_phases=sorted({desired%P,(desired+1)%P})
    def rare_rank(t):return sum((t-1-x)//P+1 for x in rare_phases)
    def joint(t):return sum((t-1-x)//P+1 for x in rare_phases if sum(x%L==desired%L for L in periods)%2)
    def oracle(t,kind):
        b=base(t);r=rare_rank(t);j=joint(t)
        if kind=='xor':return b+r-2*j
        if kind=='or':return b+r-j
        if kind=='not_xor':return t-b-r+2*j
        if kind=='and':return j
        if kind=='shift':return base(t+1)-base(1)
        raise ValueError('kind')
    assert l.count(0)==base(P);assert l.count(1)==rare_rank(P)
    return l,a,n,P,oracle,base


def run(k,queries=16):
    t0=time.perf_counter();l,a,n,P,oracle,base=prepare(k);source_ms=(time.perf_counter()-t0)*1000
    m=Memory(l);v=MemoryReceiver(a)
    rng=random.Random(31031);phases=sorted({max(0,min(P-1,P*j//(queries+1)+rng.randrange(-2,3))) for j in range(1,queries+1)})
    t0=time.perf_counter();r=m.open(0);assert v.book(0).open_rank(r.packet());m.commit_open(r)
    for p in phases:
        z=m.fact(0,p);assert v.admit_fact(0,p,z);m.commit_fact(z);assert int(z['rank'])==base(p)
    seed_ms=(time.perf_counter()-t0)*1000;seed_bytes=wire_size(r.packet());base_terms=len(r.terms);m.close(0);v.book(0).close_rank();del r
    rows=[];targets={}
    for kind in ('xor','or','not_xor','and','shift'):
        t0=time.perf_counter()
        if kind=='not_xor':target=l.extend('not',targets['xor'])
        elif kind=='shift':target=l.extend('shift',0,1)
        else:target=l.extend(kind,0,1)
        a.extend(l.export());common_ms=(time.perf_counter()-t0)*1000;targets[kind]=target
        N=l.count(target);assert N==oracle(P,kind)
        ks=[(10**900+j*17)*N+min(N,oracle(p,kind)+1) for j,p in enumerate(phases)] if N else [1]
        t0=time.perf_counter();cold=Rank(l,target);cv=CheckedRank(a,cold.packet());cold_setup=(time.perf_counter()-t0)*1000
        t0=time.perf_counter();baseline=[cold.select(x) for x in ks];assert all(cv.verify_select(x,z) for x,z in zip(ks,baseline));cold_query=(time.perf_counter()-t0)*1000
        for ordinal,z in zip(ks,baseline):
            if z['status']=='FOUND':tt=int(z['time']);assert oracle(tt,kind)==ordinal-1 and oracle(tt+1,kind)==ordinal
        t0=time.perf_counter();link=make_link(l,0,target,kind=='not_xor');a.extend(l.export());assert v.admit_link(link);m.commit_link(link);link_ms=(time.perf_counter()-t0)*1000
        truths={p:oracle(p,kind) for p in phases}
        t0=time.perf_counter();coarse=[]
        for p in phases:
            truth=truths[p];threshold=max(0,truth-3);z=m.transfer(target,p,threshold=threshold);assert v.verify(target,p,threshold,z);m.commit_transfer(z);assert int(z['lower'])<=truth<=int(z['upper']);coarse.append(z)
        coarse_ms=(time.perf_counter()-t0)*1000
        t0=time.perf_counter();residual_terms=0;residual_bytes=0;status='READY'
        for i in (link['plus'],link['minus']):
            try:
                rr=m.open(i,max_work=4096);assert v.book(i).open_rank(rr.packet());m.commit_open(rr);residual_terms+=len(rr.terms);residual_bytes+=wire_size(rr.packet())
            except Budget:status='UNKNOWN';break
        residual_ms=(time.perf_counter()-t0)*1000
        t0=time.perf_counter();exact_phases=0;local_steps=0;found=0;bounds=[]
        for p in phases:
            z=m.transfer(target,p);assert v.verify(target,p,None,z);m.commit_transfer(z);truth=truths[p];assert int(z['lower'])<=truth<=int(z['upper']);bounds.append(int(z['upper'])-int(z['lower']));exact_phases+=z['status']=='EXACT'
        for ordinal,expect in zip(ks,baseline):
            book=m.book(target);checked=v.book(target);z=book.select(ordinal,budget=128);assert checked.admit_select(ordinal,z,budget=128);book.commit(z);local_steps+=z['steps']
            if z['status']!='UNKNOWN':assert z['time']==expect['time'] and z['status']==expect['status'];found+=1
        transfer_ms=(time.perf_counter()-t0)*1000
        row=dict(bits=k,n=n,period=str(P),kind=kind,queries=len(ks),source_ms=source_ms,common_ms=common_ms,base_seed_ms=seed_ms,base_seed_bytes=seed_bytes,base_terms=base_terms,base_anchor_bytes=wire_size(m.book(0).anchors),cold_terms=len(cold.terms),cold_bytes=wire_size(cold.packet()),cold_setup_ms=cold_setup,cold_query_ms=cold_query,link_ms=link_ms,coarse_ms=coarse_ms,coarse_resolved=sum(z['status']!='UNKNOWN' for z in coarse),coarse_max_width=max(int(z['upper'])-int(z['lower']) for z in coarse),residual_status=status,residual_terms=residual_terms,residual_bytes=residual_bytes,residual_ms=residual_ms,exact_phases=exact_phases,phase_queries=len(phases),transfer_ms=transfer_ms,local_steps=local_steps,found=found,retained_target_bytes=wire_size(m.book(target).anchors),diff_counts=[str(m.count(link['plus'])),str(m.count(link['minus']))],max_final_width=max(bounds))
        print(k,kind,found,len(ks),exact_phases,status,'cold',round(cold_setup+cold_query,2),'transfer',round(link_ms+coarse_ms+residual_ms+transfer_ms,2),flush=True);rows.append(row)
        for i in (link['plus'],link['minus']):m.close(i);v.book(i).close_rank()
        # Isolated alternative using only already-admitted base anchors.
        # It starts without the target facts learned in the residual trial.
        if kind in ('shift','not_xor'):
            old_m,old_v=m,v;m=Memory(l);v=MemoryReceiver(a)
            known=0 if kind=='shift' else targets['xor']
            # Copy previously independently admitted books for this in-process
            # counterfactual, not as an untrusted wire import.
            m.books[known]=old_m.book(known);v.books[known]=old_v.book(known)
            t0=time.perf_counter()
            if kind=='shift':
                z=dict(kind='shift',base=0,target=target,delta=1);assert v.admit_shift(z)
                b=m.book(0);c=v.book(0);fact=b.span(1,budget=1);assert c.admit_span(1,fact,budget=1);b.commit(fact)
                ps=[(p-1)%P for p in phases]
            else:
                z=dict(kind='linear',target=target,constant=1,terms=[[known,-1]]);assert v.admit_linear(z);ps=phases
            m.commit_link(z);proof_ms=(time.perf_counter()-t0)*1000
            t0=time.perf_counter();hits=steps=exact=0
            for p in ps:
                x=m.transfer(target,p);assert v.verify(target,p,None,x);m.commit_transfer(x);exact+=x['status']=='EXACT'
            for ordinal,expect in zip(ks,baseline):
                b=m.book(target);c=v.book(target);x=b.select(ordinal,budget=128);assert c.admit_select(ordinal,x,budget=128);b.commit(x);steps+=x['steps']
                if x['status']!='UNKNOWN':assert x['status']==expect['status'] and x['time']==expect['time'];hits+=1
            direct_ms=(time.perf_counter()-t0)*1000
            row['direct_identity']=dict(proof_ms=proof_ms,query_ms=direct_ms,found=hits,exact_phases=exact,steps=steps,retained_target_bytes=wire_size(m.book(target).anchors),link_bytes=wire_size(z))
            print(k,kind,'direct',hits,len(ks),exact,round(proof_ms+direct_ms,2),flush=True)
            m,v=old_m,old_v
    return rows

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--sizes',nargs='+',type=int,default=[60,174,384,1023]);ap.add_argument('--queries',type=int,default=16);ap.add_argument('--output',default='CIG-031A-results.json');args=ap.parse_args();out=[]
    for k in args.sizes:
        out+=run(k,args.queries);open(args.output,'w').write(json.dumps(out,indent=2)+'\n')
