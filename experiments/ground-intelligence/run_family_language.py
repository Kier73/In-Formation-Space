"""PGI-003 measured parametric activation; independent oracle outside timed discovery."""
import argparse,json,time,math,random
from family_language import FamilyIntelligence,express
from test_family_language import train,pulse,anonymous,trace
from test_skill_language import random_view
from run_skill_language import train as train_skills
from skill_language import compile_view
from verify_skill_language import verify_pullback
from verify_family_language import verify_expression
from ground_network import View


def ms():return time.perf_counter_ns()/1e6


def unit(rng,P):
    a=rng.randrange(1,P)
    while math.gcd(a,P)!=1:a=rng.randrange(1,P)
    return a


def trial(model,skills,kind,count,base,seed):
    rng=random.Random(seed);P=math.prod(base);rows=[]
    for i in range(count):
        a=pulse(seed+i,base)[0] if kind.startswith('sparse') else random_view(seed+i,base,cutoff=0)
        alpha=unit(rng,P);beta=rng.randrange(P);c=i%2
        if kind=='sparse_contracted':alpha*=base[0]
        if kind=='primitive':alpha,beta,c=1,1,0
        if kind=='unrelated':
            b=View('foreign:'+str(i),(13,),((0,tuple(int(j==i%13) for j in range(13))),),2)
        else:
            b,_=compile_view(a,(alpha,beta,c));b=anonymous(b,seed+i)
        t=ms();form,d=model.discover(a,b);dt=ms()-t
        t=ms();s,old=skills.discover(a,b,depth=5,max_candidates=512,learned=True,primitive_first=True,compose_skills=True);ot=ms()-t
        if form:assert verify_pullback(a,b,form)[0]
        if s:assert verify_pullback(a,b,s.form)[0]
        if kind!='unrelated':assert form,(kind,i,d,b.total)
        else:assert not form
        t=ms();hy,h=model.discover(a,b,primitive_first=True);ht=ms()-t
        assert (hy is not None)==(form is not None)
        if hy:assert verify_pullback(a,b,hy)[0]
        rows.append(dict(hybrid_found=hy is not None,hybrid_ms=ht,hybrid_work=h['work'],hybrid_attempts=h['attempts'],family_found=form is not None,family_ms=dt,**{'family_'+k:v for k,v in d.items()},old_found=s is not None,old_ms=ot,**{'old_'+k:v for k,v in old.items()},form=None if form is None else [str(form[0]),str(form[1]),form[2]]))
    return dict(kind=kind,base=base,period=str(P),queries=count,family_found=sum(x['family_found'] for x in rows),old_found=sum(x['old_found'] for x in rows),family_ms=sum(x['family_ms'] for x in rows),old_ms=sum(x['old_ms'] for x in rows),family_work=sum(x['family_work'] for x in rows),old_work=sum(x['old_work'] for x in rows),family_attempts=sum(x['family_attempts'] for x in rows),old_attempts=sum(x['old_attempts'] for x in rows),hybrid_found=sum(x['hybrid_found'] for x in rows),hybrid_ms=sum(x['hybrid_ms'] for x in rows),hybrid_work=sum(x['hybrid_work'] for x in rows),hybrid_attempts=sum(x['hybrid_attempts'] for x in rows),rows=rows)


def actual(model,skills,k):
    from run_output_time import fixture
    from run_cross_ground_seed import make
    from run_disjunctive_time import fold
    from run_seed_network import admitted
    from seed_network import SeedNetwork
    from ground_network import select
    t=ms();_,_,_,_,_,_,p,f,u,P,_,_,markers,desired=fixture(k)
    rare=('or',fold('and',[a for a,b in markers]),fold('and',[b for a,b in markers]))
    nav,rec=make(k,3,p,f,u,[rare]);lang,ad,receipt=admitted(nav,rec);g=SeedNetwork();A=g.register(rec,receipt,0);a=g.graph.views[A];source_ms=ms()-t
    # Use a genuinely novel unit parameter, then a compact nonunit stride.
    rng=random.Random(340000+k);alpha=unit(rng,P);beta=rng.randrange(P);forms=[(alpha,beta,0),(2*alpha,beta,0)];out=[]
    for j,f in enumerate(forms):
        b,_=compile_view(a,f);b=anonymous(b,(k,j));t=ms();z,d=model.discover(a,b);dt=ms()-t;assert z and verify_pullback(a,b,z)[0],(k,j,d)
        t=ms();s,old=skills.discover(a,b,depth=5,max_candidates=512,primitive_first=True,compose_skills=True);ot=ms()-t
        # independent oracle from original marker phases and supplied held-out form,
        # not the recovered form or target diagram. Equivalent coefficients allowed.
        aa,bb,c=f;div=math.gcd(aa,P);Q=P//div;ph=sorted({((r-bb)//div*pow(aa//div,-1,Q))%Q for r in (desired%P,(desired+1)%P) if (r-bb)%div==0});assert ph and b.total==len(ph)
        t=ms();created,cost=model.instantiate(a,'sparse',z);assert verify_pullback(a,created,z)[0] and verify_pullback(b,created,(1,0,0))[0]
        for i in range(1,9):
            ordinal=10**900+i;packet=express(a,created,z,ordinal);assert packet and verify_expression(a,created,z,ordinal,packet)
            q,r=divmod(ordinal-1,len(ph));tt=int(packet['time']);assert tt==q*Q+ph[r]
            st=z[0]*tt+z[1];receipt=nav.result(rec.initial,st);assert receipt['outputs'][0]==1 and rec.accept(st,receipt)
        elapsed=ms()-t
        out.append(dict(kind='unit' if j==0 else 'contracted',target_period=str(b.period),actual_form=[str(aa),str(bb),c],discovered=[str(z[0]),str(z[1]),z[2]],family_ms=dt,**d,old_found=s is not None,old_ms=ot,old=old,ordinals=8,instantiation=cost,realization_and_terminal_ms=elapsed))
    return dict(bits=k,period=str(P),source_ms=source_ms,results=out)


def ambiguous_control(model):
    # One-hot local parity: each prime's cofactor partition permits many units.
    # Despite huge ambiguity, the first combination may suffice on an XOR law.
    from itertools import product
    base=(3,5,7,11,13,17,19,23,29,31,37,41,43,47,53);P=math.prod(base);nodes=[];roots=(0,1)
    for j in reversed(range(len(base))):
        m=base[j];pair=[]
        for c in (0,1):
            ch=tuple(roots[c^(i==j%m)] for i in range(m));pair.append(len(nodes)+2);nodes.append((j,ch))
        roots=tuple(pair)
    a=View('dense-parity',base,tuple(nodes),roots[0]);rng=random.Random(44);f=(unit(rng,P),rng.randrange(P),1);b,_=compile_view(a,f);b=anonymous(b,'dense-parity');t=ms();z,d=model.discover(a,b);dt=ms()-t;assert z and verify_pullback(a,b,z)[0]
    return dict(period=str(P),nodes=len(a.nodes),work=d['work'],attempts=d['attempts'],ms=dt,form=[str(i) for i in z],actual=[str(i) for i in f])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='*',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='PGI-003-results.json');a=p.parse_args();t=ms();model=train();training_ms=ms()-t;skills,oldtrain=train_skills();out=dict(training=dict(episodes=len(model.examples),families=list(model.families),bytes=len(json.dumps(model.packet(),separators=(',',':')).encode()),ms=training_ms),old_training=oldtrain,heldout=[],actual=[])
    # Separate training from held-out data and retain workload differences.
    for kind,n,base,seed in [('sparse_unit',24,(29,31,37),10000),('sparse_contracted',24,(29,31,37),11000),('dense_unit',24,(29,31,37),12000),('primitive',12,(29,31,37),13000),('unrelated',12,(29,31,37),14000),('sparse_unit',12,(3,5,7,11,13,17,19,23,29,31,37,41,43,47,53),15000),('dense_unit',12,(3,5,7,11,13,17,19,23,29,31,37,41,43,47,53),16000)]:
        r=trial(model,skills,kind,n,base,seed);out['heldout'].append(r);print(json.dumps({k:v for k,v in r.items() if k!='rows'}),flush=True)
    out['ambiguous']=ambiguous_control(model);print(out['ambiguous'],flush=True)
    for k in a.sizes:
        r=actual(model,skills,k);out['actual'].append(r);print(json.dumps(r),flush=True)
        open(a.output,'w').write(json.dumps(out,indent=2)+'\n')
    open(a.output,'w').write(json.dumps(out,indent=2)+'\n')
