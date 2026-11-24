"""CIG-034A: native graph routes through independent source-qualified Grounds."""
import argparse,json,random,time
from math import lcm
from run_output_time import fixture
from run_cross_ground_seed import make,now
from run_disjunctive_time import fold
from inverse_time import spatial_groups
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from compositional_rank import Memory
from verify_compositional_rank import MemoryReceiver
from test_adaptive_seed import seed_facts
from seed_network import SeedNetwork
from ground_network import compose
from ground_network_verify import verify_edge
from temporal_rank import Rank
from verify_temporal_rank import CheckedRank
from anchor_portfolio import wire_size


def admitted(nav,receiver):
    d,r=compile_algebra(nav,receiver.initial);return Language(d,r),Admission(receiver,r),r


def contracted(on,u0,p,live,shift,extra,transient,seed):
    m=len(p);size=m+extra+int(transient);rng=random.Random(seed);places=list(range(size));rng.shuffle(places)
    main=places[:m];aux=places[m:m+extra];pp=[None]*size;ff=[[0,1] for _ in pp];u=0
    x=on.jump(u0,shift)
    for j,i in enumerate(p):pp[main[j]]=main[i];u|=((x>>(3*j))&1)<<main[j]
    for j,i in enumerate(aux):pp[i]=aux[j-1]
    if aux:u|=1<<aux[0]
    expr=fold('xor',[main[i//3] for i in live]);outputs=[expr]
    if transient:
        e=places[-1];pp[e]=e;ff[e]=[0,0];u|=1<<e;outputs=[('xor',expr,e)]
    if aux:outputs.append(aux[0])
    return make(size,1,pp,ff,u,outputs,seed=seed)


def run(k,queries=16):
    t=now();_,_,_,_,_,_,p,f,u,P,_,_,markers,desired=fixture(k);live=[x for x,_ in markers]
    on,o=make(k,3,p,f,u,[fold('xor',live)]);ol,oa,orr=admitted(on,o);old_ms=now()-t
    t=now();m=Memory(ol);v=MemoryReceiver(oa);phases=[P*j//(queries+1) for j in range(1,queries+1)];seed_facts(m,v,0,phases);seed_ms=now()-t
    t=now();bn,b=contracted(on,u,p,live,1,4,False,3400+k);bl,ba,br=admitted(bn,b);intermediate_ms=now()-t
    t=now();cn,c=contracted(on,u,p,live,3,6,True,4400+k);cl,ca,cr=admitted(cn,c);targets_ms=now()-t
    t=now();g=SeedNetwork();A=g.register(o,orr,0);B=g.register(b,br,0);C=g.register(c,cr,0);g.attach(A,m,v);register_ms=now()-t
    t=now();ab,aw=g.link(A,B,[(0,0),(1,0),(2,0)],cost=3);bc,bw=g.link(B,C,[(0,0),(1,0),(2,0),(2,1)],cost=4);bridge_ms=now()-t
    assert ab and bc and (ab.shift,bc.shift,bc.start)==(1,2,1),(ab,bc)
    path=(bc.key,ab.key)
    # Compare a newly discovered direct edge with a composition of admitted facts.
    t=now();direct,dw=g.link(A,C,[(3,1)],cost=20);direct_ms=now()-t;assert direct
    t=now();summary=compose(g.graph,path,cost=1);compose_ms=now()-t
    assert (summary.shift,summary.start,summary.source_before,summary.target_before)==(direct.shift,direct.start,direct.source_before,direct.target_before)
    ks=[(10**900+j*17)*m.book(0).N+min(m.book(0).N,m.book(0).anchors[phase]+1)-summary.offset for j,phase in enumerate(phases)]
    t=now();rank=Rank(cl,0);checked=CheckedRank(ca,rank.packet());cold_setup=now()-t
    t=now();cold=[rank.select(k) for k in ks];assert all(checked.verify_select(k,z) for k,z in zip(ks,cold));cold_query=now()-t
    t=now();out=[];steps=states=0
    for k1 in ks:
        res,attempts=g.activate(C,k1,budget=128);assert res['status']=='FOUND';assert attempts[0][0].edges==path
        out.append(res);steps+=sum(z['steps'] for _,z,_ in attempts);states+=sum(s for _,_,s in attempts)
    route_ms=now()-t
    t=now();assert g.graph.admit_composite(summary,path);admit_composite_ms=now()-t
    t=now();warm=[];steps2=states2=0;ks2=[k1+31*m.book(0).N for k1 in ks]
    for k1 in ks2:
        res,attempts=g.activate(C,k1,budget=128);assert res['status']=='FOUND';assert attempts[0][0].edges==(summary.key,)
        warm.append(res);steps2+=sum(z['steps'] for _,z,_ in attempts);states2+=sum(s for _,_,s in attempts)
    shortcut_ms=now()-t
    # Independent marker-level arithmetic and terminal source check.
    t=now();weights={1:1}
    for z in spatial_groups(p):
        new=weights.copy()
        for mod,val in weights.items():q=lcm(mod,len(z));new[q]=new.get(q,0)-2*val
        weights={mod:val for mod,val in new.items() if val}
    def oracle(t):return (t-sum(val*((t-1-desired%mod)//mod+1) for mod,val in weights.items()))//2
    for k1,result in zip(ks+ks2,out+warm):
        tt=int(result['time']);assert oracle(tt+3)-summary.offset==k1-1 and oracle(tt+4)-summary.offset==k1
        z=cn.result(c.initial,tt);assert z['outputs'][0]==1 and c.accept(tt,z)
    assert [z['time'] for z in out]==[z['time'] for z in cold]
    terminal_ms=now()-t
    row=dict(original_bits=k,intermediate_bits=b.k,target_bits=c.k,period=str(P),intermediate_period=str(g.graph.views[B].period),target_period=str(g.graph.views[C].period),old_source_ms=old_ms,seed_ms=seed_ms,intermediate_source_ms=intermediate_ms,target_source_ms=targets_ms,register_ms=register_ms,bridge_ms=bridge_ms,bridge_discovery_work=aw+bw,direct_ms=direct_ms,direct_discovery_work=dw,compose_ms=compose_ms,admit_composite_ms=admit_composite_ms,shift=summary.shift,cutoff=summary.start,rank_offset=summary.offset,queries=queries,cold_setup_ms=cold_setup,cold_query_ms=cold_query,route_ms=route_ms,shortcut_ms=shortcut_ms,route_states=states,shortcut_states=states2,phase_steps=steps,shortcut_phase_steps=steps2,terminal_oracle_ms=terminal_ms,retained_anchor_bytes=wire_size(m.book(0).anchors))
    print(json.dumps(row),flush=True);return row

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--sizes',type=int,nargs='+',default=[60,174,384,1023]);ap.add_argument('--output',default='CIG-034A-results.json');a=ap.parse_args();rows=[]
    for k in a.sizes:
        rows.append(run(k));open(a.output,'w').write(json.dumps(rows,indent=2)+'\n')
