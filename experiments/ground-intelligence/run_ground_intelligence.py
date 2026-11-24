"""Reproducible training, held-out, cycle and source-qualified usage campaign."""
import argparse,json,random,time
from math import lcm
from ground_intelligence import Policy,Intelligence,Intention,cycle_reduction,checkpoint
from verify_ground_intelligence import admit_reduction,restore_checkpoint
from ground_network import discover,select
from test_ground_intelligence import learn_pair,pattern

def ms():return time.perf_counter_ns()/1e6

def usage():
    class GlobalPolicy(Policy):
        @staticmethod
        def context(a,b):return ('same','tail')
    p=Policy();global_p=GlobalPolicy();rng=random.Random(4413);data=[]
    for i in range(160):
        grow=bool(i%2);prefix=bool(i%4//2);shift=(5 if grow else -3) if rng.random()<.9 else (-3 if grow else 5)
        data.append((i,grow,prefix,shift))
    training=[]
    for name,policy in [('contextual',p),('global',global_p)]:
        t=ms();attempts=work=0
        for i,grow,prefix,shift in data:
            _,a,b,z=learn_pair(policy,i,shift,grow,prefix=prefix,train=True)
            assert z['status']=='FOUND' and z['time']==select(b,10**100+17)['time']
            attempts+=z['attempts'];work+=z['work']
        training.append(dict(policy=name,episodes=160,attempts=attempts,work=work,ms=ms()-t,policy_bytes=len(json.dumps(policy.packet(),separators=(',',':')).encode())))
    frozen=Policy.restore(p.packet());rows=[];global_frozen=global_p.packet()
    near=Policy(tuple(sorted(p.shifts,key=lambda d:(abs(d),d))))
    for name,n in [('matched',160),('reversed',80),('novel',40),('zero',40)]:
        data=[]
        for i in range(n):
            grow=bool(i%2);prefix=bool(i%4//2);d=5 if grow else -3
            if name=='reversed':d=-3 if grow else 5
            elif name=='novel':d=8
            elif name=='zero':d=0
            elif rng.random()<.1:d=-3 if grow else 5
            data.append((i+1000,grow,prefix,d))
        for label,policy,learned in [('fixed',frozen,False),('nearest',near,False),('global',global_p,True),('contextual',frozen,True)]:
            t=ms();attempts=work=0
            for i,grow,prefix,d in data:
                _,a,b,z=learn_pair(policy,i,d,grow,prefix=prefix,learned=learned)
                assert z['status']=='FOUND' and z['time']==select(b,10**100+17)['time']
                attempts+=z['attempts'];work+=z['work']
            rows.append(dict(regime=name,policy=label,queries=n,attempts=attempts,work=work,ms=ms()-t))
    assert p.packet()==frozen.packet() and global_p.packet()==global_frozen
    return p,dict(training=training,heldout=rows)

def cycles():
    base=(8,9,5,7,11,13,17,19,23,29,31,37,41,43,47)
    a,b,c=[pattern(x,base,j,3,1<<j) for x,j in [('A',0),('B',1),('C',2)]]
    g=Intelligence();A,B,C=[g.observe(x) for x in (a,b,c)]
    t=ms()
    for x,y,d in [(B,A,29),(A,B,1),(C,A,40),(A,C,2)]:
        e,_=discover(g.graph.views[x],g.graph.views[y],[(d,3)]);assert g.graph.admit(e)
    links_ms=ms()-t;t=ms();cc,states=g.discover_cycles(A);r=cycle_reduction(g.graph,A,cc);assert admit_reduction(g.graph,A,cc,r);reduce_ms=ms()-t
    assert r.period==6
    ks=[10**900+j for j in range(1,65)];t=ms();old=[select(a,k) for k in ks];old_ms=ms()-t
    t=ms();new=[select(r,k) for k in ks];new_ms=ms()-t
    assert all(z['status']=='FOUND' for z in old+new)
    assert [z['time'] for z in old]==[z['time'] for z in new]
    # Independent explicit six-phase oracle, including the admitted prefix.
    hits=[i for i in range(3,9) if i%2==0 and i%3!=1];assert hits==[6,8]
    for k,z in zip(ks,new):
        q,j=divmod(k-2,2);assert z['time']==hits[j]+6*q
    g.memories.add(r.key);packet=checkpoint(g);t=ms();restored=restore_checkpoint(json.loads(json.dumps(packet)),expected_views=g.graph.views);restore_ms=ms()-t
    assert restored.realize(Intention(A,ks[0]))['time']==old[0]['time']
    return dict(ambient_period=str(a.period),reduced_period=r.period,cycle_shifts=[g.graph.edges[e].shift for e in cc],cycle_states=states,links_ms=links_ms,reduction_ms=reduce_ms,queries=len(ks),old_work=sum(z['work'] for z in old),new_work=sum(z['work'] for z in new),old_ms=old_ms,new_ms=new_ms,checkpoint_bytes=len(json.dumps(packet,separators=(',',':')).encode()),restore_ms=restore_ms)

def source_usage(policy,k,queries=8):
    from run_output_time import fixture
    from run_cross_ground_seed import make
    from run_disjunctive_time import fold
    from run_seed_network import admitted,contracted
    from compositional_rank import Memory
    from verify_compositional_rank import MemoryReceiver
    from test_adaptive_seed import seed_facts
    from seed_network import SeedNetwork
    from temporal_rank import Rank
    from verify_temporal_rank import CheckedRank
    from inverse_time import spatial_groups
    t=ms();_,_,_,_,_,_,p,f,u,P,_,_,markers,desired=fixture(k);live=[x for x,_ in markers]
    nav,o=make(k,3,p,f,u,[fold('xor',live)]);ol,oa,orr=admitted(nav,o);old_ms=ms()-t
    t=ms();m=Memory(ol);v=MemoryReceiver(oa);phases=[P*j//(queries+1) for j in range(1,queries+1)];seed_facts(m,v,0,phases);seed_ms=ms()-t
    t=ms();nn,b=contracted(nav,u,p,live,5,4,True,511+k);bl,ba,br=admitted(nn,b);target_ms=ms()-t
    t=ms();g=SeedNetwork();A=g.register(o,orr,0);B=g.register(b,br,0);g.attach(A,m,v);reg_ms=ms()-t
    # Frozen trained policy selects candidate order; independently admitted CIG
    # observation snapshots and CIG-029A anchors authorize the realization.
    agent=Intelligence(g.graph,policy);t=ms();e,profile=agent.link(A,B);link_ms=ms()-t;assert e and e.shift==5
    # Same exact search with fixed palette, separate graph so no memory hit.
    t=ms();fresh=Intelligence(policy=policy);fresh.observe(g.graph.views[A]);fresh.observe(g.graph.views[B]);_,control=fresh.link(A,B,learned=False);fixed_ms=ms()-t
    ks=[(10**900+17*j)*m.book(0).N+min(m.book(0).N,m.book(0).anchors[phase]+1)-e.offset for j,phase in enumerate(phases)]
    t=ms();got=[g.activate(B,x,budget=128)[0] for x in ks];warm_ms=ms()-t;assert all(z['status']=='FOUND' for z in got)
    t=ms();r=Rank(bl,0);checked=CheckedRank(ba,r.packet());cold=[r.select(x) for x in ks];assert all(checked.verify_select(x,z) for x,z in zip(ks,cold));cold_ms=ms()-t
    assert [z['time'] for z in got]==[z['time'] for z in cold]
    t=ms();weights={1:1}
    for z in spatial_groups(p):
        nex=weights.copy()
        for mod,c in weights.items():mm=lcm(mod,len(z));nex[mm]=nex.get(mm,0)-2*c
        weights={mod:c for mod,c in nex.items() if c}
    def oracle(t):return (t-sum(c*((t-1-desired%mm)//mm+1) for mm,c in weights.items()))//2
    for x,z in zip(ks,got):
        tt=int(z['time']);assert oracle(tt+5)-e.offset==x-1 and oracle(tt+6)-e.offset==x
        terminal=nn.result(b.initial,tt);assert terminal['outputs'][0]==1 and b.accept(tt,terminal)
    audit_ms=ms()-t
    return dict(original_bits=k,new_bits=b.k,queries=queries,shift=e.shift,cutoff=e.start,offset=e.offset,context=policy.context(g.graph.views[A],g.graph.views[B]),old_source_ms=old_ms,seed_ms=seed_ms,target_source_ms=target_ms,register_ms=reg_ms,learned_discovery=profile,fixed_discovery=control,learned_discovery_ms=link_ms,fixed_discovery_ms=fixed_ms,warm_ms=warm_ms,cold_ms=cold_ms,terminal_oracle_ms=audit_ms)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--sizes',nargs='*',type=int,default=[60,174,384,1023]);ap.add_argument('--output',default='PGI-001-results.json');args=ap.parse_args()
    p,training=usage();out=dict(training=training,cycles=cycles(),source=[]);print(json.dumps(out,indent=2),flush=True)
    for k in args.sizes:
        try:row=source_usage(p,k)
        except AssertionError:raise
        out['source'].append(row);print(json.dumps(row),flush=True)
    with open(args.output,'w') as f:json.dump(out,f,indent=2);f.write('\n')
