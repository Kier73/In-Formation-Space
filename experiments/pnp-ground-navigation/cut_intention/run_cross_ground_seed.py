"""Source-qualified usage: transfer a parity Seed to a wider shuffled processor."""
import argparse,json,random,time
from math import lcm,prod
from run_output_time import fixture,circuit_source
from run_disjunctive_time import fold
from run_temporal_ground import encode_law
from temporal_ground import compile_transport,Navigator
from verify_temporal_ground import Receiver,digest
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from temporal_rank import Rank
from verify_temporal_rank import CheckedRank
from compositional_rank import Memory
from verify_compositional_rank import MemoryReceiver
from adaptive_seed import Seed
from verify_adaptive_seed import SeedReceiver
from cross_ground_seed import discover
from verify_cross_ground_seed import BridgeAdmission
from inverse_time import spatial_groups
from test_adaptive_seed import seed_facts
from anchor_portfolio import wire_size

def now():return time.perf_counter()*1000

def make(k,w,p,f,initial,exprs,seed=331):
    n,s,q,fs=circuit_source(k,exprs,seed);dec=synthesize_shared(n,s,q,fs);sec=compile_section(n,s,q)
    ts=encode_law(k,w,p,f,seed);g=compile_transport(ts,k,w)
    return Navigator(k,w,g,dec),Receiver(n,s,q,fs,dec,ts,w,g,initial,section=sec)

def expand(w,p,f,u,live,seed=333,extra=4):
    """Fixture only. Hide the full coordinate map from discovery."""
    rng=random.Random(seed);m=len(p);nw=w+1;na=1<<nw;n=m+extra
    loc=list(range(n));rng.shuffle(loc);a=loc[:m];unused=loc[m:]
    perm=[];mask=[];enc=[];dec=[];liveblocks={i//w for i in live}
    for i in range(m):
        r=list(range(nw));rng.shuffle(r);perm.append(r);b=rng.randrange(1<<w)
        for bit in live:
            if bit//w==i:b &= ~(1<<(bit%w))
        mask.append(b)
        E=[sum(((x>>j&1)^(b>>j&1))<<r[j] for j in range(nw)) for x in range(na)]
        D=[0]*na
        for x,y in enumerate(E):D[y]=x
        enc.append(E);dec.append(D)
    pp=[None]*n;ff=[None]*n;uu=0
    for j,i in enumerate(p):
        pp[a[j]]=a[i];ff[a[j]]=[enc[j][f[j][dec[i][x]&((1<<w)-1)]] for x in range(na)]
        x=(u>>(w*j))&((1<<w)-1);uu|=enc[j][x|(1<<w)]<<(nw*a[j])
    for j,z in enumerate(unused):
        pp[z]=unused[j-1];ff[z]=list(range(na))
    if unused:uu|=1<<(nw*unused[0])
    ports=[(i//w,i%w,a[i//w],perm[i//w][i%w],(mask[i//w]>>(i%w))&1) for i in live]
    return nw,pp,ff,uu,ports,a,enc

def run(k,queries=16):
    if 4*(k//3+4)>1024:
        return dict(old_bits=k,new_bits=4*(k//3+4),status="UNKNOWN",reason="inherited 1024-coordinate observer contract")
    t=now();_,_,_,_,_,_,p,f,u,P,_,_,markers,desired=fixture(k);live=[x for x,_ in markers];e=fold('xor',live)
    on,old=make(k,3,p,f,u,[e]);d,r=compile_algebra(on,u);ol=Language(d,r);oa=Admission(old,r);source_ms=now()-t
    t=now();m=Memory(ol);v=MemoryReceiver(oa);phases=[P*j//(queries+1) for j in range(1,queries+1)];seed_facts(m,v,0,phases);s=Seed(m,[0]);assert SeedReceiver(v,[0]).verify_descriptor(s.descriptor());seed_ms=now()-t
    t=now();w,pp,ff,uu,ports,_,_=expand(3,p,f,u,live,seed=k+333);nk=w*len(pp);ne=fold('xor',[w*j+b for _,_,j,b,_ in ports]);nn,new=make(nk,w,pp,ff,uu,[ne],seed=332);new_source_ms=now()-t
    t=now();proposal=discover(old,new,0,0,ports=ports);discovery_ms=now()-t;assert proposal['status']=='FOUND',proposal
    z=proposal['proof'];t=now();ad=BridgeAdmission(old,new,r,v,z);bridge_ms=now()-t
    t=now();nd,nr=compile_algebra(nn,uu);nl=Language(nd,nr);na=Admission(new,nr);rank=Rank(nl,0);cr=CheckedRank(na,rank.packet());cold_setup_ms=now()-t
    periods=[len(z) for z in spatial_groups(p)];weights={1:1}
    for L in periods:
        nxt=weights.copy()
        for a,b in weights.items():q=lcm(a,L);nxt[q]=nxt.get(q,0)-2*b
        weights={a:b for a,b in nxt.items() if b}
    def oracle(t):return (t-sum(c*((t-1-desired%m)//m+1) for m,c in weights.items()))//2
    N=ol.count(0);ks=[(10**900+j*17)*N+min(N,oracle(p)+1) for j,p in enumerate(phases)]
    t=now();cold=[rank.select(q) for q in ks];assert all(cr.verify_select(q,x) for q,x in zip(ks,cold));cold_ms=now()-t
    t=now();out=[];steps=0;bytes_=0;key=digest(z)
    for q in ks:
        b=m.book(0);rr=b.compact(q,budget=128);packet=dict(bridge=key,output=0,ordinal=str(q),rank=rr);res=ad.accept(q,packet);assert res and res['status']=='FOUND',res
        b.commit(rr);out.append(res);steps+=rr['steps'];bytes_+=wire_size(packet)
    warm_ms=now()-t
    t=now()
    for q,a,b in zip(ks,out,cold):
        assert a['time']==b['time'];tt=int(a['time']);assert oracle(tt)==q-1 and oracle(tt+1)==q
        terminal=nn.result(uu,tt);assert new.accept(tt,terminal) and terminal['outputs']==[1]
    oracle_ms=now()-t
    row=dict(old_bits=k,new_bits=nk,old_variables=old.n,new_variables=new.n,old_period=str(P),new_period=str(prod(nd.base)),old_cutoff=ol.D,new_cutoff=nl.D,ports=len(ports),mapping_blocks=len(p),new_blocks=len(pp),mapping_work=proposal['work'],attempts=proposal['attempts'],diagram_work=proposal['diagram_work'],diagram_nodes=len(z['nodes']),bridge_bytes=wire_size(z),source_ms=source_ms,new_source_ms=new_source_ms,seed_ms=seed_ms,discovery_ms=discovery_ms,bridge_ms=bridge_ms,cold_setup_ms=cold_setup_ms,cold_query_ms=cold_ms,warm_ms=warm_ms,oracle_and_terminal_ms=oracle_ms,queries=queries,steps=steps,query_bytes=bytes_,cold_terms=len(rank.terms),cold_bytes=wire_size(rank.packet()))
    print(row,flush=True);return row

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--sizes',type=int,nargs='+',default=[60,174,384,756,1023]);ap.add_argument('--output',default='CIG-033A-results.json');a=ap.parse_args();out=[]
    for k in a.sizes:out.append(run(k));open(a.output,'w').write(json.dumps(out,indent=2)+'\n')
