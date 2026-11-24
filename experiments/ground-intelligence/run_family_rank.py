"""Actual CIG source rank memory transferred to new dense pullback Grounds."""
import argparse,json,random,time
from math import gcd,lcm
from run_family_language import ms,unit
from test_family_language import train,anonymous
from skill_language import compile_view
from verify_skill_language import verify_pullback
from family_rank import seed_packet,TransportedRank
from verify_family_rank import RankSeedAdmission
from run_output_time import fixture
from run_cross_ground_seed import make
from run_disjunctive_time import fold
from run_seed_network import admitted
from seed_network import SeedNetwork
from inverse_time import spatial_groups


def run(model,k):
    t=ms();_,_,_,_,_,_,p,f,u,P,_,_,markers,desired=fixture(k);expr=fold('xor',[a for a,b in markers]);nav,rec=make(k,3,p,f,u,[expr]);lang,ad,receipt=admitted(nav,rec);g=SeedNetwork();key=g.register(rec,receipt,0);a=g.graph.views[key];source_ms=ms()-t
    t=ms();p0=seed_packet(a);check=RankSeedAdmission(a,p0);seed_ms=ms()-t
    rng=random.Random(721+k);alpha=unit(rng,P);beta=rng.randrange(P);rows=[]
    weights={1:1}
    for group in spatial_groups(p):
        new=weights.copy()
        for m,c in weights.items():q=lcm(m,len(group));new[q]=new.get(q,0)-2*c
        weights={m:c for m,c in new.items() if c}
    for index,form in enumerate([(alpha,beta,0),(2*alpha,beta,1)]):
        b,_=compile_view(a,form);b=anonymous(b,(k,index));dt=None;dis=None
        if index==0:
            t=ms();dis,discovery_profile=model.discover(a,b);dt=ms()-t;assert dis and verify_pullback(a,b,dis)[0]
        # Nonunit dense route is intentionally supplied parameters; no discovery claim.
        used=dis if dis is not None else form
        t=ms();r=TransportedRank(a,b,p0,used);v=check.activate(b,r.recipe);assert r.terms==v.terms;transfer_ms=ms()-t
        # Fair direct fresh arithmetic comparison, same independent source-term audit.
        t=ms();fresh=seed_packet(b);fresh_check=RankSeedAdmission(b,fresh);fresh_ms=ms()-t
        # Independent direct marker parity arithmetic for the held-out original form.
        aa,bb,c=form;terms=[]
        for mod,val in weights.items():
            d=gcd(aa,mod);rhs=desired%mod-bb
            if rhs%d:continue
            q=mod//d;r0=(rhs//d*pow(aa//d,-1,q))%q if q>1 else 0;terms.append((r0,q,val))
        def oracle(t):
            parity=(t-sum(v*((t-1-r)//m+1) for r,m,v in terms))//2
            return t-parity if c else parity
        ks=[10**900+j*19 for j in range(1,9)];t=ms();results=[r.select(x) for x in ks];assert all(v.verify(x,y) for x,y in zip(ks,results));select_ms=ms()-t
        t=ms()
        for kk,o in zip(ks,results):
            assert o['status']=='FOUND';tt=int(o['time']);assert oracle(tt)==kk-1 and oracle(tt+1)==kk
            st=used[0]*tt+used[1];rr=nav.result(rec.initial,st);assert rr['outputs'][0]^used[2]==1 and rec.accept(st,rr)
        audit_ms=ms()-t
        rows.append(dict(kind='unit_discovered' if index==0 else 'nonunit_supplied',form=[str(x) for x in form],used=[str(x) for x in used],discovery_ms=dt,discovery=discovery_profile if index==0 else None,target_period=str(b.period),seed_terms=len(p0['terms']),derived_terms=len(r.terms),fresh_terms=len(fresh['terms']),transfer_ms=transfer_ms,fresh_ms=fresh_ms,transfer_work=r.work+v.work,relation_work=r.relation_work+v.relation_work,fresh_work=fresh['work']+fresh_check.work,recipe_bytes=len(json.dumps(r.recipe,separators=(',',':')).encode()),fresh_bytes=len(json.dumps(fresh,separators=(',',':')).encode()),ordinals=len(ks),selection_ms=select_ms,oracle_and_terminal_ms=audit_ms))
    return dict(bits=k,period=str(P),source_ms=source_ms,seed_ms=seed_ms,seed_bytes=len(json.dumps(p0,separators=(',',':')).encode()),rows=rows)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='*',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='PGI-003-rank-results.json');a=p.parse_args();m=train();rows=[]
    for k in a.sizes:
        r=run(m,k);rows.append(r);print(json.dumps(r),flush=True);open(a.output,'w').write(json.dumps(rows,indent=2)+'\n')
