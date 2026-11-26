"""VLM-016: cost-bounded acquisition plans; uncertainty is not proof."""
from dataclasses import dataclass,asdict
from functools import lru_cache
from collections import Counter
from hashlib import sha256
from pathlib import Path
import json,os
from transfer_policy import PROBES,MASK,portable,polynomial_affine
from experience_contract import kernel,k1_law,digest,canonical,require
from external_descriptor import projection,record,MAX

PARENT='af9a38fec72539c39a0dca0d322ae28530664bc8e3f494c706a0576e35d3dbe6'
# Units are explicitly configured acquisition prices, not measured runtime.
@dataclass(frozen=True)
class Intention:
    name:str
    budget:int
    proof_cost:int
    proof_allowed:bool
    refute_reward:int
    certify_reward:int
    def __post_init__(self):
        require(type(self.name) is str and type(self.proof_allowed) is bool and all(type(x) is int and 0<=x<=1000 for x in (self.budget,self.proof_cost,self.refute_reward,self.certify_reward)) and self.budget>=2 and self.proof_cost>=1,'intention domain')

INTENTS=(Intention('observation_only',5,6,False,20,0),Intention('resolve_expensive_proof',10,6,True,20,20),Intention('qualify',8,6,True,0,20),Intention('resolve_cheap_proof',5,2,True,20,20))

def eligible(row):return row.get('polynomial_eligible',row['eligible'])

def learn(rows,intent):
    """Exact empirical Bellman search of up to three distinct probes and terminal proof.
    The only continuing branch is no counterexample; refutation terminates.
    Uses only training evidence. Utility = reward - modeled acquisition cost.
    """
    require(bool(rows),'empty training cohort');n=len(rows);allrows=(1<<n)-1
    bad=[sum(int(bool(r['bad'][i]))<<j for j,r in enumerate(rows)) for i in range(len(PROBES))]
    yes=sum(int(eligible(r))<<j for j,r in enumerate(rows))
    @lru_cache(None)
    def dp(s,available,budget,depth):
        count=s.bit_count();best=(0,())
        if not count:return best
        if intent.proof_allowed and budget>=intent.proof_cost:
            score=(s&yes).bit_count()*intent.certify_reward-count*intent.proof_cost
            if score>best[0]:best=(score,('proof',))
        if budget and depth:
            for i,mask in enumerate(bad):
                if not (available>>i)&1:continue
                hits=(s&mask).bit_count()
                if not hits:continue
                v,tail=dp(s&~mask,available^(1<<i),budget-1,depth-1)
                option=(hits*intent.refute_reward-count+v,(i,)+tail)
                if option[0]>best[0] or option[0]==best[0] and len(option[1])<len(best[1]):best=option
        return best
    score,plan=dp(allrows,(1<<len(PROBES))-1,intent.budget-2,3)
    return list(plan) if score>2*n else []

def validate_plan(plan,intent):
    require(type(plan) is list and len(plan)<=4,'plan extent');seen=set();cost=2 if plan else 0
    for j,op in enumerate(plan):
        if op=='proof':require(intent.proof_allowed and j==len(plan)-1,'proof authority/order');cost+=intent.proof_cost
        else:
            require(type(op) is int and 0<=op<len(PROBES) and op not in seen,'probe index');seen.add(op);cost+=1
    require(len(seen)<=3 and cost<=intent.budget,'budget');return cost

def run(plan,intent,observe,check):
    validate_plan(plan,intent)
    if not plan:return {'a':None,'b':None,'status':'unknown','cost':0,'trace':[]}
    b=observe(0);a=(observe(1)-b)&MASK;cost=2;trace=[];status='unknown'
    for op in plan:
        if op=='proof':
            cost+=intent.proof_cost;cert=bool(check(a,b));trace.append(['proof',cert]);status='certified' if cert else 'unknown';break
        x=PROBES[op];v=observe(x);cost+=1;trace.append(['probe',x,v])
        if v!=((a*x+b)&MASK):status='refuted';break
    return {'a':a,'b':b,'status':status,'cost':cost,'trace':trace}

def assess(rows,plan,intent,adapter=None):
    counts=Counter(cases=len(rows),eligible=sum(eligible(r) for r in rows));results=[]
    for r in rows:
        if adapter:observe,check=adapter(r['source'])
        else:
            lookup={0:r['b'],1:(r['a']+r['b'])&MASK,**dict(zip(PROBES,r['values']))}
            observe=lookup.__getitem__;check=lambda a,b:eligible(r)
        out=run(plan,intent,observe,check);assert out['a'] is None or (out['a'],out['b'])==(r['a'],r['b'])
        assert out['status']!='certified' or eligible(r)
        assert out['status']!='refuted' or not eligible(r)
        counts[out['status']]+=1;counts['cost']+=out['cost'];counts['probes']+=sum(x[0]=='probe' for x in out['trace']);counts['proofs']+=sum(x[0]=='proof' for x in out['trace']);counts['max_cost']=max(counts['max_cost'],out['cost'])
        results.append({'source':r['id'],**out})
    counts['utility']=intent.refute_reward*counts['refuted']+intent.certify_reward*counts['certified']-counts['cost']
    for k in ('refuted','certified','unknown','proofs','probes'):counts[k]+=0
    return dict(counts),results

def symbolic_inspect(m,p):
    """Direct source route: reconstruct bounded polynomial without execution probes."""
    polys={}
    for i in sorted(p.needed()):
        n=p.nodes[i]
        if n.op=='input':q=[0,1]
        elif n.op=='const':q=[n.value]
        elif n.op in ('add','mul'):
            u,v=(polys[j] for j in n.args);size=max(len(u),len(v)) if n.op=='add' else len(u)+len(v)-1
            if size>9:return {'status':'unknown','a':None,'b':None}
            q=[0]*size
            if n.op=='add':
                for z in (u,v):
                    for j,c in enumerate(z):q[j]=(q[j]+c)&MASK
            else:
                for j,c in enumerate(u):
                    for k,d in enumerate(v):q[j+k]=(q[j+k]+c*d)&MASK
        else:return {'status':'unknown','a':None,'b':None}
        while len(q)>1 and q[-1]==0:q.pop()
        polys[i]=q
    q=polys[p.output];b=q[0];a=(sum(q)-b)&MASK
    for x in range(2,max(1,len(q)-1)+1):
        value=0
        for c in reversed(q):value=(value*x+c)&MASK
        if value!=((a*x+b)&MASK):return {'status':'refuted','a':a,'b':b,'witness':[x,value]}
    return {'status':'certified','a':a,'b':b}

def inspect_assess(rows,fallback,intent,adapter,inspector):
    require(intent.proof_allowed and intent.proof_cost<=intent.budget,'source inspection authority')
    reduced=None
    if fallback:
        reduced=Intention(intent.name,intent.budget-intent.proof_cost,intent.proof_cost,False,intent.refute_reward,intent.certify_reward)
        validate_plan(fallback,reduced)
    counts=Counter(cases=len(rows),eligible=sum(eligible(r) for r in rows));results=[]
    for r in rows:
        initial=inspector(r['source']);status=initial['status'];cost=intent.proof_cost;trace=[['inspect',initial]];a,b=initial['a'],initial['b']
        if status=='unknown' and fallback:
            observe,check=adapter(r['source']);out=run(fallback,reduced,observe,check);status=out['status'];cost+=out['cost'];trace+=out['trace'];a,b=out['a'],out['b']
        assert a is None or (a,b)==(r['a'],r['b'])
        assert status!='certified' or eligible(r)
        assert status!='refuted' or not eligible(r)
        counts[status]+=1;counts['cost']+=cost;counts['inspections']+=1;counts['probes']+=sum(x[0]=='probe' for x in trace);counts['max_cost']=max(counts['max_cost'],cost)
        results.append({'source':r['id'],'a':a,'b':b,'status':status,'cost':cost,'trace':trace})
    counts['utility']=intent.refute_reward*counts['refuted']+intent.certify_reward*counts['certified']-counts['cost']
    for k in ('refuted','certified','unknown','proofs','probes'):counts[k]+=0
    return dict(counts),results

def external_plan(fixture,purpose,budget,read_allowed):
    """Metadata is a descriptive sensor, never a resident model capability."""
    require(purpose in ('describe','inspect-config','infer') and type(budget) is int and budget>=0 and type(read_allowed) is bool,'external intention')
    desc=projection(fixture['observed_fields'],fixture['model'],fixture['revision']);r=record(desc,'web-field-projection',fixture['source_url'])
    out={'descriptor_id':r['record_id'],'purpose':purpose,'byte_budget':budget,'authority':'descriptive-only'}
    if purpose=='describe':return out|{'status':'described','action':None,'missing':[]}
    if purpose=='infer':return out|{'status':'unqualified','action':None,'missing':['admitted-numerical-operator','execution-evidence']}
    if not r['next_observation']:return out|{'status':'unqualified','action':None,'missing':['declared-config']}
    if not read_allowed or budget<MAX:return out|{'status':'deferred','action':None,'missing':['read-permission' if not read_allowed else 'read-budget']}
    return out|{'status':'proposed','action':r['next_observation'],'missing':['configuration-response']}

def campaign(path,root):
    raw=Path(path).read_bytes();require(sha256(raw).hexdigest()==PARENT,'parent archive identity');cohorts=json.loads(raw)['cohorts'];m=portable();k=kernel(root)
    def source_adapter(s):
        p,o=s['program'],s['observer']
        def observe(x):
            seed=[0]*4;seed[o]=x;r=k.evaluate(seed,p,1,mode='reference');require(r['status']==0,'K1 refused');return r['registers'][o]
        return observe,lambda a,b:k1_law(p,o)==(a,b)
    def target_program(s):return m.Program(tuple(m.Node(op,tuple(args),v) for op,args,v in s['nodes']),s['output'])
    def target_adapter(s):
        p=target_program(s);return lambda x:m.reference(p,x),lambda a,b:polynomial_affine(m,p,a,b)
    def target_inspector(s):return symbolic_inspect(m,target_program(s))
    reports={};traces={}
    for intent in INTENTS:
        source=learn(cohorts['source_training'],intent);target=learn(cohorts['target_training'],intent)
        baseline=['proof'] if intent.proof_allowed and intent.budget>=2+intent.proof_cost else []
        options={'source':source,'target':target,'proof_only':baseline,'abstain':[]}
        val={name:assess(cohorts['target_validation'],p,intent)[0] for name,p in options.items()}
        inspect_options={}
        if intent.proof_allowed and intent.budget>=intent.proof_cost:
            inspect_options['inspect_only']=[]
            if intent.budget-intent.proof_cost>=2:
                reduced=Intention(intent.name,intent.budget-intent.proof_cost,intent.proof_cost,False,intent.refute_reward,intent.certify_reward)
                unknown=[r for r in cohorts['target_training'] if target_inspector(r['source'])['status']=='unknown']
                if unknown:inspect_options['inspect_then_probe']=learn(unknown,reduced)
            for name,p in inspect_options.items():val[name]=inspect_assess(cohorts['target_validation'],p,intent,target_adapter,target_inspector)[0]
        options.update({name:['inspect']+p for name,p in inspect_options.items()})
        winner=max(options,key=lambda name:(val[name]['utility'],-len(options[name])))
        report={'intention':asdict(intent),'plans':options,'validation':val,'selected':winner,'final':{}}
        for name,plan in options.items():
            if name in inspect_options:stats,records=inspect_assess(cohorts['target_final'],inspect_options[name],intent,target_adapter,target_inspector)
            else:
                stats,records=assess(cohorts['target_final'],plan,intent,target_adapter);assert stats==assess(cohorts['target_final'],plan,intent)[0]
            report['final'][name]=stats;traces[intent.name+'/'+name]=records
        stats,records=assess(cohorts['source_final'],source,intent,source_adapter);assert stats==assess(cohorts['source_final'],source,intent)[0];report['source_final']=stats;traces[intent.name+'/source_final']=records
        reports[intent.name]=report
    fixture=json.loads((Path(__file__).with_name('datasets')/'vlm015'/'hf-observation.json').read_bytes())
    external=[external_plan(fixture,goal,budget,allowed) for goal,budget,allowed in [('describe',0,False),('inspect-config',4096,True),('inspect-config',MAX,False),('inspect-config',MAX,True),('infer',MAX,True)]]
    return {'schema':'vlm-intention-acquisition-v1','parent_sha256':PARENT,'reports':reports,'external':external,'trace_sha256':digest(traces),'traces':traces}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--parent',required=True);p.add_argument('--root',default=os.environ.get('VLK_ROOT'));p.add_argument('--output',required=True);a=p.parse_args();r=campaign(a.parent,a.root);Path(a.output).write_bytes(canonical(r)+b'\n');print(json.dumps({k:v for k,v in r.items() if k!='traces'},indent=2))
