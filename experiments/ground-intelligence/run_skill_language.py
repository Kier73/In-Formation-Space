"""Training and held-out skill discovery, including actual CIG source admission."""
import argparse,json,time
from skill_language import Vocabulary,normalize,compile_view,SkillIntelligence
from verify_skill_language import verify_pullback,verify_skill_expression
from test_skill_language import MOTIFS,random_view,sequential
from ground_intelligence import Intelligence
from ground_network import View

def ms():return time.perf_counter_ns()/1e6

def train():
    v=Vocabulary();t=ms();work=0
    for i in range(36):
        a=random_view(i);tr=MOTIFS[i%len(MOTIFS)];b,w=sequential(a,tr);work+=w;assert v.observe(a,tr,b)
    v.induce();return v,dict(episodes=36,skills=len(v.skills),ms=ms()-t,sequential_work=work,bytes=len(json.dumps(v.packet(),separators=(',',':')).encode()))

def heldout(v):
    rows=[]
    for kind,n in [('matched',60),('primitive',30),('novel',30),('unreachable',15)]:
        tasks=[]
        for i in range(n):
            a=random_view(1000+100*len(rows)+i)
            if kind=='matched':tr=MOTIFS[i%3]
            elif kind=='primitive':tr=(('advance',1),)
            elif kind=='novel':tr=(('stride',3),('stride',3),('advance',2),('advance',2))
            else:tr=None
            if tr:b,w=sequential(a,tr)
            else:b=View('constant:'+str(i),(),(),0);w=0
            tasks.append((a,b,tr,w))
        for label,learned,first in [('primitive',False,False),('learned',True,False),('hybrid',True,True)]:
            start=ms();attempts=work=found=unknown=0
            for a,b,tr,w in tasks:
                s,d=v.discover(a,b,depth=5,max_candidates=512,learned=learned,primitive_first=first)
                attempts+=d['attempts'];work+=d['work']
                if s is None:unknown+=1
                else:
                    found+=1;assert verify_pullback(a,b,s.form)[0];assert tr is not None
            rows.append(dict(regime=kind,policy=label,queries=n,found=found,unknown=unknown,attempts=attempts,work=work,ms=ms()-start))
        if kind=='matched':
            base=fused=0
            for a,b,tr,w in tasks:
                z,c=compile_view(a,normalize(tr));ok,q=verify_pullback(a,z,normalize(tr));assert ok and verify_pullback(a,b,normalize(tr))[0];base+=w;fused+=c+q
            rows.append(dict(regime='known_trace_fusion',queries=n,sequential_work=base,fused_work=fused))
    return rows

def composition_usage(v):
    # A new operator formed from two learned operators. Neither the requested
    # trace nor the new normal form was observed during training.
    tr=MOTIFS[1]+MOTIFS[2];form=normalize(tr);assert form not in v.skills
    rows=[];tasks=[]
    for i in range(12):
        a=random_view(8000+i);b,_=sequential(a,tr);tasks.append((a,b))
    for name,learned,composed in [('primitive',False,False),('retained',True,False),('composed',True,True)]:
        t=ms();attempts=work=found=0
        for a,b in tasks:
            skill,d=v.discover(a,b,depth=5,max_candidates=1000,learned=learned,primitive_first=True,compose_skills=composed)
            attempts+=d['attempts'];work+=d['work'];found+=skill is not None
            if skill:assert verify_pullback(a,b,skill.form)[0]
        rows.append(dict(policy=name,queries=len(tasks),found=found,attempts=attempts,work=work,ms=ms()-t))
    assert rows[-1]['found']==12 and rows[0]['found']==0
    # Acquire the new skill from the checked discoveries, then activate it
    # in an additional independently constructed held-out source.
    for a,b in tasks:
        skill,_=v.discover(a,b,depth=5,max_candidates=1000,compose_skills=True)
        assert skill and skill.form==form and v.observe(a,skill.trace,b)
    # The full combined trace has length ten, greater than the ordinary
    # motif window. Admit it explicitly as a newly composed skill with
    # two-source evidence, rather than increasing the subsequence search.
    from skill_language import Skill
    from verify_skill_language import verify_skill
    # record proof of the whole trace for future induction
    assert len(v.evidence[form])>=2
    v.induce();assert form in v.skills
    a=random_view(9000);b,_=sequential(a,tr);s,d=v.discover(a,b,depth=1,max_candidates=64)
    assert s and s.form==form
    return dict(form=form,rows=rows,retained_after_usage=d,skills=len(v.skills))

def source_usage(v,k):
    from run_output_time import fixture
    from run_cross_ground_seed import make
    from run_disjunctive_time import fold
    from run_seed_network import admitted
    from seed_network import SeedNetwork
    from math import gcd
    t=ms();_,_,_,_,_,_,p,f,u,P,_,_,markers,desired=fixture(k)
    expr=('or',fold('and',[a for a,b in markers]),fold('and',[b for a,b in markers]))
    nav,rec=make(k,3,p,f,u,[expr]);lang,ad,receipt=admitted(nav,rec);g=SeedNetwork();A=g.register(rec,receipt,0);a=g.graph.views[A];source_ms=ms()-t
    tr=MOTIFS[0];form=normalize(tr);b,seq_work=sequential(a,tr)
    controls=[]
    for learned in (False,True):
        t=ms();s,d=v.discover(a,b,depth=5,max_candidates=512,learned=learned);dt=ms()-t
        assert s and verify_pullback(a,b,s.form)[0];controls.append(dict(policy='learned' if learned else 'primitive',form=s.form,**d,ms=dt))
    s=v.skills[form];alpha,beta,c=form;assert c==0 and a.cutoff==0
    from ground_network import select
    wide,wc=compile_view(a,form,compact=False);small,sc=compile_view(a,form);assert verify_pullback(a,wide,form)[0] and verify_pullback(a,small,form)[0]
    wide_result=select(wide,10**900+1);small_result=select(small,10**900+1);assert wide_result['status']==small_result['status']=='FOUND' and wide_result['time']==small_result['time']
    d=gcd(alpha,P);period=P//d;phases=sorted({((r-beta)//d*pow(alpha//d,-1,period))%period for r in (desired%P,(desired+1)%P) if (r-beta)%d==0});assert phases
    agent=Intelligence(g.graph);agent.observe(a,memory=True);worker=SkillIntelligence(agent,v);work=0;t=ms()
    for j in range(1,9):
        ordinal=10**900+j;packet,cost=worker.express(A,s.key,ordinal);assert verify_skill_expression(agent.graph,v,A,s.key,ordinal,packet)
        q,r=divmod(ordinal-1,len(phases));tt=int(packet['time']);assert tt==q*period+phases[r];work+=cost['selection_work']
        z=nav.result(rec.initial,alpha*tt+beta);assert z['outputs'][0]==1 and rec.accept(alpha*tt+beta,z)
    return dict(bits=k,period=str(P),form=form,source_ms=source_ms,discovery=controls,sequential_work=seq_work,ordinals=8,selection_work=work,realization_and_terminal_ms=ms()-t,independent_residue_count=len(phases),compact_period=str(small.period),wide_compile_work=wc,compact_compile_work=sc,wide_selection_work=wide_result['work'],compact_selection_work=small_result['work'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='*',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='PGI-002-results.json');args=p.parse_args()
    v,training=train();res=dict(training=training,heldout=heldout(v),source=[]);res['composition']=composition_usage(v);print(json.dumps(res,indent=2),flush=True)
    for k in args.sizes:
        r=source_usage(v,k);res['source'].append(r);print(json.dumps(r),flush=True);open(args.output,'w').write(json.dumps(res,indent=2)+'\n')
