"""Usage of topology-free temporal Seed transfer to a contracted processor."""
import argparse,json,random
from math import lcm,prod
from run_cross_ground_seed import make,now
from run_output_time import fixture
from run_disjunctive_time import fold
from run_temporal_ground import step
from inverse_time import spatial_groups
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from compositional_rank import Memory
from verify_compositional_rank import MemoryReceiver
from test_adaptive_seed import seed_facts
from adaptive_seed import Seed
from verify_adaptive_seed import SeedReceiver
from trajectory_bridge import discover_trajectory
from verify_trajectory_bridge import TrajectoryAdmission
from temporal_rank import Rank
from verify_temporal_rank import CheckedRank
from anchor_portfolio import wire_size


def run(k,queries=16):
    t=now();_,_,_,_,_,_,p,f,u,P,_,_,markers,desired=fixture(k);live=[x for x,_ in markers];on,o=make(k,3,p,f,u,[fold('xor',live)]);d,r=compile_algebra(on,u);l=Language(d,r);a=Admission(o,r);old_source_ms=now()-t
    t=now();m=Memory(l);v=MemoryReceiver(a);phases=[P*j//(queries+1) for j in range(1,queries+1)];seed_facts(m,v,0,[1]+phases);assert SeedReceiver(v,[0]).verify_descriptor(Seed(m,[0]).descriptor());seed_ms=now()-t
    # Contract unused local symbol dimensions, shuffle, add unrelated ring,
    # and use a shifted initial state. No map or port hints given to discovery.
    t=now();rng=random.Random(33033+k);loc=list(range(len(p)+4));rng.shuffle(loc);al=loc[:len(p)];extra=loc[len(p):];pp=[None]*len(loc);ff=[[0,1] for _ in loc];uu=0;x=step(u,k,3,p,f)
    for j,i in enumerate(p):pp[al[j]]=al[i];uu|=((x>>(3*j))&1)<<al[j]
    for j,i in enumerate(extra):pp[i]=extra[j-1]
    uu|=1<<extra[0];nn,b=make(len(loc),1,pp,ff,uu,[fold('xor',[al[i//3] for i in live]),extra[0]],seed=333);new_source_ms=now()-t
    t=now();e,s=compile_algebra(nn,uu);ll=Language(e,s);aa=Admission(b,s);new_algebra_ms=now()-t
    t=now();q=discover_trajectory(l,0,ll,0,deltas=(0,1,2,3));discovery_ms=now()-t;assert q['status']=='FOUND' and q['delta']==1,q
    t=now();ad=TrajectoryAdmission(o,b,r,s,v,0,0,q['delta']);admit_ms=now()-t
    ctrl=discover_trajectory(l,0,ll,1,deltas=(0,1,2,3));assert ctrl['status']=='UNKNOWN',ctrl
    t=now();rr=Rank(ll,0);cr=CheckedRank(aa,rr.packet());cold_setup_ms=now()-t
    weights={1:1}
    for z in spatial_groups(p):
        nex=weights.copy()
        for mod,c in weights.items():mm=lcm(mod,len(z));nex[mm]=nex.get(mm,0)-2*c
        weights={mod:c for mod,c in nex.items() if c}
    def oracle(t):return (t-sum(c*((t-1-desired%mm)//mm+1) for mm,c in weights.items()))//2
    assert ad.offset==oracle(1);N=l.count(0);ks=[(10**900+j*17)*N+min(N,oracle(p)+1)-ad.offset for j,p in enumerate(phases)]
    t=now();cold=[rr.select(k) for k in ks];assert all(cr.verify_select(k,z) for k,z in zip(ks,cold));cold_ms=now()-t
    t=now();results=[];steps=0
    for ordinal in ks:
        z=m.book(0).compact(ordinal+ad.offset,budget=128);packet=dict(bridge=ad.key,output=0,ordinal=str(ordinal),rank=z);res=ad.accept(ordinal,packet);assert res and res['status']=='FOUND';m.book(0).commit(z);results.append(res);steps+=z['steps']
    warm_ms=now()-t
    t=now()
    for k1,x,y in zip(ks,results,cold):
        assert x['time']==y['time'];tt=int(x['time']);assert oracle(tt+1)-oracle(1)==k1-1 and oracle(tt+2)-oracle(1)==k1
        z=nn.result(uu,tt);assert z['outputs'][0]==1 and b.accept(tt,z)
    oracle_ms=now()-t
    row=dict(old_bits=k,new_bits=b.k,old_variables=o.n,new_variables=b.n,old_period=str(P),new_period=str(prod(e.base)),old_source_ms=old_source_ms,seed_ms=seed_ms,new_source_ms=new_source_ms,new_algebra_ms=new_algebra_ms,discovery_ms=discovery_ms,discovery_work=q['work'],admit_ms=admit_ms,cold_setup_ms=cold_setup_ms,cold_query_ms=cold_ms,warm_ms=warm_ms,oracle_and_terminal_ms=oracle_ms,queries=queries,steps=steps,delta=q['delta'],unrelated_output=ctrl['status'],cold_terms=len(rr.terms),cold_bytes=wire_size(rr.packet()),retained_anchor_bytes=wire_size(m.book(0).anchors))
    print(row,flush=True);return row

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='+',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='CIG-033A-trajectory-results.json');a=p.parse_args();rows=[]
    for k in a.sizes:rows.append(run(k));open(a.output,'w').write(json.dumps(rows,indent=2)+'\n')
