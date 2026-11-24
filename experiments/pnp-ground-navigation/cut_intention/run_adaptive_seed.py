"""Usage campaign: source-qualified seed activation, no target provenance supplied."""
import argparse,json,random,time
from math import lcm
from run_compositional_rank import prepare as prepare_pair
from run_output_time import fixture,circuit_source
from run_disjunctive_time import fold
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_ground import Navigator
from verify_temporal_ground import Receiver
from temporal_algebra import compile_algebra,Language,Budget
from verify_temporal_algebra import Admission
from compositional_rank import Memory
from verify_compositional_rank import MemoryReceiver
from adaptive_seed import Seed
from verify_adaptive_seed import SeedReceiver
from test_adaptive_seed import seed_facts,adopt,transfer,majority
from temporal_rank import Rank
from verify_temporal_rank import CheckedRank
from anchor_portfolio import wire_size
from inverse_time import spatial_groups

def now():return time.perf_counter()*1000

def acquire(m,v,ids,phases):
    t=now();terms=0;size=0
    for i in ids:
        r=m.open(i);assert v.book(i).open_rank(r.packet());m.commit_open(r);terms+=len(r.terms);size+=wire_size(r.packet())
        for p in phases:
            z=m.fact(i,p);assert v.admit_fact(i,p,z);m.commit_fact(z)
        m.close(i);v.book(i).close_rank()
    return dict(ms=now()-t,terms=terms,proof_bytes=size)

def trial(m,v,seed,target,phases,oracle,*,max_work=500000,deltas=range(1,9),label=''):
    l=m.lang;a=v.a;P=m.P;N=l.count(target);t=now();sr=SeedReceiver(v,seed.members);desc=seed.descriptor();assert sr.verify_descriptor(desc);manifest_ms=now()-t
    # Cold benchmark uses actual CIG-025.  The caller's oracle produces a
    # clustered test workload; target phases are declared demand context.
    t=now();r=Rank(l,target);cv=CheckedRank(a,r.packet());cold_setup=now()-t
    assert N==oracle(l.D+P)-oracle(l.D)
    ks=[(10**900+j*17)*N+min(N,oracle(l.D+p)-oracle(l.D)+1)+r.before for j,p in enumerate(phases)] if N else [1]
    t=now();baseline=[r.select(k) for k in ks];assert all(cv.verify_select(k,z) for k,z in zip(ks,baseline));cold_queries=now()-t
    # Each returned absolute time is also checked by a separate source formula.
    for k,z in zip(ks,baseline):
        if z['status']=='FOUND':tt=int(z['time']);assert oracle(tt)==k-1 and oracle(tt+1)==k
    t=now();pr=seed.discover(target,deltas=deltas,max_work=max_work,phases=phases);discovery_ms=now()-t
    row=dict(label=label,target=target,period=str(P),count=str(N),queries=len(ks),discovery=pr,discovery_ms=discovery_ms,manifest_bytes=wire_size(desc),manifest_ms=manifest_ms,cold_setup_ms=cold_setup,cold_query_ms=cold_queries,cold_terms=len(r.terms),cold_bytes=wire_size(r.packet()))
    if pr['status']!='FOUND':
        row.update(found=0,exact_phases=0,relation=None,transfer_ms=0,admit_ms=0,residual_ms=0,residual_terms=0,residual_bytes=0,steps=0)
        return row
    t=now();z=adopt(m,v,seed,sr,pr);admit_ms=now()-t
    t=now();residual_terms=residual_bytes=0
    if z['kind']=='residual':
        for i in (z['link']['plus'],z['link']['minus']):
            rr=m.open(i,max_work=4096);assert v.book(i).open_rank(rr.packet());m.commit_open(rr);residual_terms+=len(rr.terms);residual_bytes+=wire_size(rr.packet())
    if z['kind']=='shift':
        delta=z['delta']%P;i=z['base'];b=m.book(i);c=v.book(i);fact=b.span(delta,budget=128);assert c.admit_span(delta,fact,budget=128);b.commit(fact)
        ps=sorted({(p-delta)%P for p in b.anchors})
    else:ps=phases
    residual_ms=now()-t
    t=now();exact=0;steps=0;found=0;max_width=0;checks=[]
    for p in ps:
        q=transfer(m,v,seed,sr,z,p);checks.append((p,q));exact+=q['status']=='EXACT';max_width=max(max_width,int(q['upper'])-int(q['lower']))
    for k,expect in zip(ks,baseline):
        b=m.book(target);c=v.book(target);q=b.select(k,budget=128);assert c.admit_select(k,q,budget=128);b.commit(q);steps+=q['steps']
        if q['status']!='UNKNOWN':assert q['time']==expect['time'] and q['status']==expect['status'];found+=1
    transfer_ms=now()-t
    for p,q in checks:
        truth=oracle(l.D+p)-oracle(l.D);assert int(q['lower'])<=truth<=int(q['upper'])
    if z['kind']=='residual':
        for i in (z['link']['plus'],z['link']['minus']):m.close(i);v.book(i).close_rank()
    row.update(found=found,exact_phases=exact,phase_queries=len(ps),max_width=max_width,relation=z,admit_ms=admit_ms,residual_ms=residual_ms,residual_terms=residual_terms,residual_bytes=residual_bytes,transfer_ms=transfer_ms,steps=steps,relation_bytes=wire_size(z),retained_target_bytes=wire_size(m.book(target).anchors));return row

def pair(k,queries):
    t=now();l,a,n,P,oracle,base=prepare_pair(k);source_ms=now()-t;m=Memory(l);v=MemoryReceiver(a);phases=[P*j//(queries+1) for j in range(1,queries+1)];acq=acquire(m,v,[0],phases);s=Seed(m,[0]);out=[]
    for name,op,offset in [('shift','shift',1),('xor','xor',1),('not_xor','not',None)]:
        if name=='not_xor':
            assert 'xor' in targets;t=l.extend('not',targets['xor']);s=Seed(m,[targets['xor']])
        else:t=l.extend(op,0,offset)
        if name=='shift':# Align requests to known phases after the shift.
            ps=[(p-1)%P for p in phases]
        else:ps=phases
        a.extend(l.export())
        if name=='shift':targets={}
        targets[name]=t;row=trial(m,v,s,t,ps,lambda t:oracle(t,name),label=name);row.update(bits=k,n=n,source_ms=source_ms,acquire=acq)
        out.append(row);print(k,name,row['found'],row['queries'],row['discovery']['relation'],round(row['discovery_ms']+row['admit_ms']+row['residual_ms']+row['transfer_ms'],2),flush=True)
    # Distinct target, deliberately insufficient seed grammar/budget.
    t=l.extend('and',0,1);a.extend(l.export());pr=Seed(m,[0]).discover(t,max_work=1);assert pr['status']=='UNKNOWN';out.append(dict(bits=k,label='forced_budget',discovery=pr))
    return out

def rational(k,queries):
    t=now();_,_,_,_,ts,g,p,f,initial,P,start,_,markers,desired=fixture(k);periods=[len(z) for z in spatial_groups(p)];groups=[list(range(i,len(markers),3)) for i in range(3)]
    if not all(groups):raise ValueError('need >=3 groups')
    expr=[fold('xor',[markers[j][0] for j in group]) for group in groups];expr+=[fold('xor',expr),majority(*expr)]
    # Retain the failed full-source control, then use already admitted regional
    # source predicates at the largest size.  Discovery never reads l.ops.
    direct=(k<1023);direct_control=None
    if not direct:
        n0,s0,q0,fs0=circuit_source(k,expr,seed=3232);t0=now();attempt=synthesize_shared(n0,s0,q0,fs0);direct_control=dict(n=n0,status=attempt['status'],goals=[g['status'] for g in attempt['goals']],ms=now()-t0);del attempt
    n,s,q,fs=circuit_source(k,expr if direct else expr[:3],seed=3232);dec=synthesize_shared(n,s,q,fs);sec=compile_section(n,s,q);rec=Receiver(n,s,q,fs,dec,ts,3,g,initial,section=sec);nav=Navigator(k,3,g,dec);d,r=compile_algebra(nav,initial);a=Admission(rec,r);l=Language(d,r)
    if direct:target=4
    else:
        x=l.extend('xor',0,1);parity=l.extend('xor',x,2)
        ab=l.extend('and',0,1);ac=l.extend('and',0,2);bc=l.extend('and',1,2);u=l.extend('or',ab,ac);target=l.extend('or',u,bc)
        a.extend(l.export())
    m=Memory(l);v=MemoryReceiver(a);assert l.D==0
    source_ms=now()-t
    def weights(ids):
        w={1:1}
        for j in ids:
            new=w.copy()
            for a,b in w.items():z=lcm(a,periods[j]);new[z]=new.get(z,0)-2*b
            w={a:b for a,b in new.items() if b}
        return w
    ws=[weights(group) for group in groups]+[weights(range(len(markers)))]
    def rank(i,t):return (t-sum(c*((t-1-desired%m)//m+1) for m,c in ws[i].items()))//2
    def oracle(t):return (sum(rank(i,t) for i in range(3))-rank(3,t))//2
    phases=[P*j//(queries+1) for j in range(1,queries+1)];known=[0,1,2,3 if direct else parity];acq=acquire(m,v,known,phases);seed=Seed(m,[0,1]).combine(Seed(m,[2,known[-1]]));row=trial(m,v,seed,target,phases,oracle,label='majority',deltas=());row.update(bits=k,n=n,source_ms=source_ms,acquire=acq,source_outputs=direct,direct_source_control=direct_control);print(k,'majority',row['found'],row['queries'],row['discovery']['relation'],round(row['discovery_ms']+row['admit_ms']+row['residual_ms']+row['transfer_ms'],2),flush=True)
    # A seed with only one subgroup has neither a sufficient span nor a
    # sufficiently small residual on the larger trajectories.
    ctrl=Seed(m,[0]).discover(target,deltas=(),max_difference=0)
    return [row,dict(bits=k,label='insufficient_seed',discovery=ctrl)]

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--sizes',nargs='+',type=int,default=[60,174,384,1023]);ap.add_argument('--queries',type=int,default=16);ap.add_argument('--output',default='CIG-032A-results.json');ap.add_argument('--mode',choices=['pair','rational','all'],default='all');args=ap.parse_args();out=[]
    for k in args.sizes:
        for fn in ([pair,rational] if args.mode=='all' else [pair] if args.mode=='pair' else [rational]):
            out+=fn(k,args.queries);open(args.output,'w').write(json.dumps(out,indent=2)+'\n')
