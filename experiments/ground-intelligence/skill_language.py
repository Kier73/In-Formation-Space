"""PGI-002: induce reusable exact temporal pullback procedures from usage.
All target views are mathematical observations; source qualification remains external.
"""
from dataclasses import dataclass
from itertools import product
from collections import defaultdict
from math import gcd
from ground_network import View, integer, digest, Work, Exhausted

PRIMITIVES=(('advance',1),('advance',2),('stride',2),('stride',3),('flip',0))


def normalize(trace):
    """Apply operations in listed order: current f becomes f(a*t+b) xor c."""
    if type(trace) is not tuple or not 1<=len(trace)<=32:raise ValueError('trace')
    a,b,c=1,0,0
    for op,n in trace:
        integer(n,0)
        if op=='advance':b+=a*n
        elif op=='stride' and n>=1:a*=n
        elif op=='flip' and n==0:c^=1
        else:raise ValueError('operation')
        integer(a,1);integer(b,0)
    return a,b,c

@dataclass(frozen=True)
class Skill:
    trace:tuple
    form:tuple
    @property
    def key(self):return digest(['pgi.skill.v1',self.trace,self.form])


def compile_view(source,form,*,max_work=500000,compact=True):
    a,b,c=form;integer(a,1);integer(b,0)
    if type(source) is not View or type(compact) is not bool or type(c) is not int or c not in (0,1):raise ValueError('pullback contract')
    cutoff=max(0,(source.cutoff-b+a-1)//a);w=Work(max_work)
    prefix=0
    for t in range(cutoff):w.charge();prefix|=(source.bit(a*t+b)^c)<<t
    rad=tuple(m//gcd(a,m) if compact else m for m in source.base)
    base=tuple(m for m in rad if m>1);levels={j:i for i,j in enumerate(j for j,m in enumerate(rad) if m>1)}
    ids={0:c,1:1-c};nodes=[];unique={}
    for i,(j,kids) in enumerate(source.nodes,2):
        m=source.base[j];w.charge(rad[j]+1)
        z=tuple(ids[kids[(a*r+b)%m]] for r in range(rad[j]))
        if len(set(z))==1:ids[i]=z[0];continue
        row=(levels[j],z)
        if row not in unique:unique[row]=len(nodes)+2;nodes.append(row)
        ids[i]=unique[row]
    v=View('pgi-pullback:'+digest([source.key,str(a),str(b),c]),base,tuple(nodes),ids[source.root],cutoff,prefix)
    return v,w.used


class Vocabulary:
    """Bounded, cross-context support; learned facts are independently checked.
    Support scores are advisory; mathematical validity is not learned by frequency.
    """
    def __init__(self,*,max_span=6,min_support=2,max_skills=64):
        if not 2<=max_span<=8 or not 2<=min_support<=64 or not 1<=max_skills<=256:raise ValueError('limits')
        self.max_span=max_span;self.min_support=min_support;self.max_skills=max_skills
        self.evidence=defaultdict(set);self.examples={};self.skills={}

    def observe(self,source,trace,target):
        from verify_skill_language import verify_pullback
        form=normalize(trace);ok,_=verify_pullback(source,target,form)
        if not ok:return False
        # Charge candidate generation separately; deduplicate equivalent forms
        # within an episode and count support only across distinct source views.
        for i in range(len(trace)):
            for j in range(i+2,min(len(trace),i+self.max_span)+1):
                sub=trace[i:j];f=normalize(sub)
                if f in ((1,0,0),)+tuple(normalize((p,)) for p in PRIMITIVES):continue
                if f not in self.evidence and len(self.evidence)>=4096:continue
                if len(self.evidence[f])<1024:self.evidence[f].add(source.key)
                if f not in self.examples or (len(sub),sub)<(len(self.examples[f]),self.examples[f]):self.examples[f]=sub
        if len(trace)>self.max_span and form not in ((1,0,0),)+tuple(normalize((p,)) for p in PRIMITIVES):
            if form in self.evidence or len(self.evidence)<4096:
                if len(self.evidence[form])<1024:self.evidence[form].add(source.key)
                if form not in self.examples or (len(trace),trace)<(len(self.examples[form]),self.examples[form]):self.examples[form]=trace
        return True

    def induce(self):
        from verify_skill_language import verify_skill
        eligible=[f for f,s in self.evidence.items() if len(s)>=self.min_support]
        eligible.sort(key=lambda f:(-len(self.evidence[f])*(len(self.examples[f])-1),f))
        old=self.skills;self.skills={}
        for f in eligible[:self.max_skills]:
            s=Skill(self.examples[f],f)
            if not verify_skill(s):raise ValueError('skill proof')
            self.skills[f]=s
        # Previously admitted callable skills survive a restart; usage scores
        # are session-local. Evict only if the explicit capacity is exhausted.
        for f,s in old.items():
            if len(self.skills)>=self.max_skills:break
            if f not in self.skills:self.skills[f]=s
        return tuple(self.skills.values())

    def packet(self):
        return {'schema':'pgi.vocabulary.v1','skills':[[s.key,[list(p) for p in s.trace],list(s.form)] for s in self.skills.values()]}

    @classmethod
    def restore(cls,packet):
        from verify_skill_language import verify_skill
        if type(packet) is not dict or set(packet)!={'schema','skills'} or packet['schema']!='pgi.vocabulary.v1' or type(packet['skills']) is not list or len(packet['skills'])>256:raise ValueError('vocabulary')
        v=cls(max_skills=256)
        for key,tr,f in packet['skills']:
            s=Skill(tuple(tuple(p) for p in tr),tuple(f))
            if not verify_skill(s) or s.key!=key or s.form in v.skills:raise ValueError('skill admission')
            v.skills[s.form]=s
        return v

    def discover(self,source,target,*,depth=5,max_candidates=1000,max_work=2000000,learned=True,primitive_first=False,compose_skills=False):
        """Goal-only search: caller provides no trace; exact whole-domain checks.
        Primitive search deduplicates equivalent affine normal forms. Work counts
        verifier cells, not Python overhead, induction or source admission.
        """
        from verify_skill_language import verify_pullback
        if not 1<=depth<=8 or not 1<=max_candidates<=100000:raise ValueError('search limits')
        integer(max_work,1);seen=set();attempts=work=0
        def candidates():
            if primitive_first:
                for p in PRIMITIVES:yield Skill((p,),normalize((p,)))
            if learned:
                yield from self.skills.values()
                if compose_skills:
                    # New operators are generated from existing callable skills,
                    # not by pretending an arbitrary target trace was observed.
                    for left,right in product(self.skills.values(),repeat=2):
                        tr=left.trace+right.trace
                        if len(tr)<=32:yield Skill(tr,normalize(tr))
            for n in range(1,depth+1):
                for tr in product(PRIMITIVES,repeat=n):yield Skill(tr,normalize(tr))
        for s in candidates():
            if s.form in seen:continue
            if attempts>=max_candidates or work>=max_work:break
            seen.add(s.form);attempts+=1
            ok,w=verify_pullback(source,target,s.form,max_work=max_work-work);work+=w
            if ok:return s,dict(attempts=attempts,work=work)
        return None,dict(attempts=attempts,work=work)

class SkillIntelligence:
    """PGI-001 extension: learned vocabulary constructs new Grounds."""
    def __init__(self,agent,vocabulary):
        from ground_intelligence import Intelligence
        if type(agent) is not Intelligence or type(vocabulary) is not Vocabulary:raise ValueError('controller')
        self.agent=agent;self.vocabulary=vocabulary

    def express(self,source,skill_key,ordinal,*,max_work=500000):
        from ground_network import select
        from ground_network_verify import verify_selection
        from verify_skill_language import verify_skill,verify_pullback
        s=next((s for s in self.vocabulary.skills.values() if s.key==skill_key),None)
        if s is None or not verify_skill(s):raise ValueError('unknown skill')
        v=self.agent.graph.views[source];integer(ordinal,1)
        try:z,work=compile_view(v,s.form,max_work=max_work)
        except Exhausted:return None
        ok,checked=verify_pullback(v,z,s.form,max_work=max_work)
        if not ok:return None
        self.agent.observe(z,memory=True)
        result=select(z,ordinal,max_work=max_work)
        if result['status']!='FOUND' or not verify_selection(z,ordinal,result['time'],max_work=max_work):return None
        return {'schema':'pgi.skill-expression.v1','source':source,'skill':skill_key,'target':z.key,
                'ordinal':str(ordinal),'time':str(result['time'])},dict(compile_work=work,qualification_work=checked,selection_work=result['work'])
