"""VLM-019: context-sensitive rule scheduling and independently replayed certificates."""
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import json, random
from rewrite_ground import portable, certify, self_generated, DirectBits
from intention_acquisition import symbolic_inspect
from experience_contract import canonical, digest, require

PARENT='c984a379474f433fbe5fdeab7780def2d1df934c3d7233ab4c1a3f2126078e97'
RULES=(
    (('and',('v',0),('c',4294967295)),('v',0)),
    (('and',('v',0),('v',0)),('v',0)),
    (('xor',('v',0),('c',0)),('v',0)),
    (('and',('and',('v',0),('v',1)),('v',1)),('and',('v',0),('v',1))),
    (('xor',('xor',('v',0),('v',1)),('v',0)),('v',1)),
    (('xor',('xor',('v',0),('v',1)),('v',1)),('v',0)),
)

def context(nodes,j):
    n=nodes[j]
    if not n.args:return (n.op,)
    return (n.op,tuple(nodes[k].op for k in n.args),len(set(n.args))==1)

def schedule(m,p,mode='static',policy=None):
    """All routes retain the same qualified vocabulary; a policy only reorders checks."""
    require(mode in ('static','index','learned'),'scheduler mode')
    require(len(p.nodes)<=1024,'source limit')
    nodes=[];ids={};mapping={};events=[];work=Counter();observations=Counter()
    by=defaultdict(list)
    for k,(lhs,rhs) in enumerate(RULES):by[lhs[0]].append(k)
    def intern(n):
        if n not in ids:ids[n]=len(nodes);nodes.append(n)
        return ids[n]
    def match(t,j,env):
        if t[0]=='v':
            if t[1] in env:return env[t[1]]==j
            env[t[1]]=j;return True
        n=nodes[j]
        if t[0]=='c':return n.op=='const' and n.value==t[1]
        return n.op==t[0] and match(t[1],n.args[0],env) and match(t[2],n.args[1],env)
    def build(t,env):
        if t[0]=='v':return env[t[1]]
        if t[0]=='c':return intern(m.Node('const',value=t[1]))
        return intern(m.Node(t[0],(build(t[1],env),build(t[2],env))))
    def compatible(lhs,j):
        n=nodes[j]
        for t,k in zip(lhs[1:],n.args):
            v=nodes[k]
            if t[0]=='c' and (v.op!='const' or v.value!=t[1]):return False
            if t[0] not in ('c','v') and v.op!=t[0]:return False
        return not (lhs[1]==lhs[2] and n.args[0]!=n.args[1])
    for i in sorted(p.needed()):
        n=p.nodes[i];j=intern(m.Node(n.op,tuple(mapping[k] for k in n.args),n.value));used=[]
        for _ in range(8):
            opts=by[nodes[j].op];ctx=str(context(nodes,j))
            if mode!='static':
                work['index_checks']+=len(opts);opts=[k for k in opts if compatible(RULES[k][0],j)]
            if mode=='learned':opts=sorted(opts,key=lambda k:(-(policy or {}).get(ctx,{}).get(str(k),0),k))
            for k in opts:
                work['matches']+=1;env={}
                if match(RULES[k][0],j,env):
                    j=build(RULES[k][1],env);used.append(k);observations[(ctx,k)]+=1;work['hits']+=1;break
            else:break
        if used:events.append([i,used])
        mapping[i]=j
    q=m.Program(tuple(nodes),mapping[p.output]);proof={'schema':'vlm-rewrite-proof-v1','source':p.identity,'target':q.identity,'rules':digest(RULES),'events':events}
    return q,proof,dict(work),observations

def replay(m,p,proof):
    """Independent traversal, matching and substitution; no scheduling policy trusted."""
    require(type(proof) is dict and set(proof)=={'schema','source','target','rules','events'},'proof fields')
    require(proof['schema']=='vlm-rewrite-proof-v1' and proof['source']==p.identity and proof['rules']==digest(RULES),'proof identity')
    require(all(certify(*r) for r in RULES),'rule certificate')
    require(len(p.nodes)<=1024 and type(proof['events']) is list and len(proof['events'])<=len(p.nodes),'proof extent')
    event={};last=-1
    for e in proof['events']:
        require(type(e) is list and len(e)==2 and type(e[0]) is int and e[0]>last and e[0] in p.needed(),'event position');last=e[0]
        require(type(e[1]) is list and 1<=len(e[1])<=8 and all(type(k) is int and 0<=k<len(RULES) for k in e[1]),'rule sequence');event[e[0]]=e[1]
    nodes=[];mapping={};table={}
    def add(op,args=(),value=0):
        key=(op,args,value)
        if key not in table:table[key]=len(nodes);nodes.append(m.Node(op,args,value))
        return table[key]
    for i in sorted(p.needed()):
        n=p.nodes[i];j=add(n.op,tuple(mapping[k] for k in n.args),n.value)
        for k in event.get(i,[]):
            lhs,rhs=RULES[k];bindings={};stack=[(lhs,j)]
            while stack:
                t,v=stack.pop();actual=nodes[v]
                if t[0]=='v':require(bindings.setdefault(t[1],v)==v,'inconsistent substitution')
                elif t[0]=='c':require(actual.op=='const' and actual.value==t[1],'constant substitution')
                else:
                    require(actual.op==t[0] and len(actual.args)==2,'operator substitution');stack.extend(zip(t[1:],actual.args))
            def substitute(t):
                if t[0]=='v':return bindings[t[1]]
                if t[0]=='c':return add('const',value=t[1])
                return add(t[0],tuple(substitute(x) for x in t[1:]))
            j=substitute(rhs)
        mapping[i]=j
    q=m.Program(tuple(nodes),mapping[p.output]);require(q.identity==proof['target'],'target identity');return q

def learn(m,rows):
    counts=defaultdict(Counter)
    for p in rows:
        _,_,_,obs=schedule(m,p)
        for (ctx,k),n in obs.items():counts[ctx][str(k)]+=n
    return {ctx:dict(v) for ctx,v in sorted(counts.items())}

def measure(m,rows,policy,mode,repeats=5):
    samples=[];evidence=[]
    for _ in range(repeats):
        work=Counter();records=[];start=perf_counter_ns()
        compiled=[schedule(m,p,mode,policy)[:3] for p in rows];compile_ns=perf_counter_ns()-start
        start=perf_counter_ns()
        for p,(q,proof,c) in zip(rows,compiled):
            z=replay(m,p,proof);require(z==q,'certificate replay');law=symbolic_inspect(m,z);work.update(c);work['certified']+=law['status']=='certified';work['live_ops']+=sum(bool(z.nodes[i].args) for i in z.needed());work['proof_bytes']+=len(canonical(proof));records.append({'proof':proof,'law':law,'work':c})
        verify_ns=perf_counter_ns()-start
        if evidence:require(evidence==records,'determinism')
        evidence=records;samples.append({'compile_ns':compile_ns,'verify_ns':verify_ns})
    r=random.Random(1905);queries=[[r.getrandbits(32) for _ in range(32)] for p in rows];baseline=[[m.reference(p,x) for x in xs] for p,xs in zip(rows,queries)]
    for rep,sample in enumerate(samples):
        routes=[('original_query_ns',rows),('rewritten_query_ns',[q for q,_,_ in compiled])]
        if rep%2:routes.reverse()
        for name,ps in routes:
            start=perf_counter_ns();actual=[[m.demand(p,x)[0] for x in xs] for p,xs in zip(ps,queries)];sample[name]=perf_counter_ns()-start;require(actual==baseline,'query parity')
    return {'work':dict(work),'samples':samples,**{k+'_median':int(median(s[k] for s in samples)) for k in samples[0]},'queries':32*len(rows),'records':evidence}

def campaign(parent=None):
    if parent is not None:
        raw=Path(parent).read_bytes();require(sha256(raw).hexdigest()==PARENT,'parent identity');require(canonical(json.loads(raw)['combined_rules'])==canonical(RULES),'parent catalogue')
    m=portable();require(all(certify(*r) for r in RULES),'catalogue qualification')
    cohorts={k:list(self_generated(m,RULES,s,n)) for k,s,n in [('train',1901,120),('validation',1902,120),('final',1903,240)]}
    identities=[p.identity for ps in cohorts.values() for p in ps];require(len(set(identities))==len(identities),'cohort overlap')
    policy=learn(m,cohorts['train']);modes=('static','index','learned')
    val={mode:measure(m,cohorts['validation'],policy,mode) for mode in modes}
    # Choose by exact certification coverage, then live work, then costly full matches;
    # cheap index checks separately retained rather than equated to full matches.
    selected=min(modes,key=lambda n:(-val[n]['work']['certified'],val[n]['work']['live_ops'],val[n]['work'].get('matches',0),val[n]['work'].get('index_checks',0),n))
    measured_selected=min(modes,key=lambda n:(-val[n]['work']['certified'],val[n]['work']['live_ops'],val[n]['compile_ns_median']+val[n]['verify_ns_median'],n))
    final={mode:measure(m,cohorts['final'],policy,mode) for mode in modes}
    # Strong independent direct-bit baseline; does not produce the same proof format.
    direct=Counter();d=DirectBits(m)
    for p in cohorts['final']:
        q,w=d.rewrite(p);direct['certified']+=symbolic_inspect(m,q)['status']=='certified';direct['live_ops']+=w['after']
        for x in (0,1,2,4294967295):require(m.reference(p,x)==m.reference(q,x),'direct parity')
    return {'schema':'vlm-rewrite-schedule-v1','rules':RULES,'policy':policy,'selected':selected,'measured_selected':measured_selected,'cohorts':{k:[{'id':p.identity,'nodes':[[n.op,list(n.args),n.value] for n in p.nodes],'output':p.output} for p in ps] for k,ps in cohorts.items()},'validation':val,'final':final,'direct':dict(direct)}

def semantic(report):
    return digest({k:({n:{x:y for x,y in r.items() if x!='samples' and not x.endswith('_median')} for n,r in v.items()} if k in ('validation','final') else v) for k,v in report.items() if k!='measured_selected'})

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--parent');args=a.parse_args();r=campaign(args.parent);Path(args.output).write_bytes(canonical(r)+b'\n');print(json.dumps({'semantic':semantic(r),'selected':r['selected'],'measured_selected':r['measured_selected'],'policy_contexts':len(r['policy']),'direct':r['direct'],'validation':{n:v['work'] for n,v in r['validation'].items()},'final':{n:{k:v for k,v in a.items() if k not in ('records','samples')} for n,a in r['final'].items()}},indent=2))
