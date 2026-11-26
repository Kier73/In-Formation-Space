"""VLM-018: observational rule discovery, bitwise certificates and compositional replay."""
import argparse,json,random,time
from collections import Counter,defaultdict
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from itertools import product
from transfer_policy import portable,MASK
from intention_acquisition import symbolic_inspect
from experience_contract import canonical,digest,require

PARENT='a29df00a178dcd512802bbaf2507b7196c365a96d6647e2e0d63ea055ad3d4eb'
STRESS_PIN='2456a0fe89f847c0ef70092d0783f89d2f13959734f813f5f2c2bf74997531ac'
OPS=('xor','and')
LEAVES=(('v',0),('v',1),('v',2),('c',0),('c',MASK))

@lru_cache(None)
def size(t):return 0 if t[0] in ('v','c') else 1+size(t[1])+size(t[2])
def variables(t):return {t[1]} if t[0]=='v' else set() if t[0]=='c' else variables(t[1])|variables(t[2])
def evaluate(t,values):
    if t[0]=='v':return values[t[1]]
    if t[0]=='c':return t[1]
    a,b=evaluate(t[1],values),evaluate(t[2],values)
    return a^b if t[0]=='xor' else a&b

def valid(t,depth=0):
    if type(t) is not tuple or not t or depth>4:return False
    if t[0]=='v':return len(t)==2 and type(t[1]) is int and 0<=t[1]<3
    if t[0]=='c':return len(t)==2 and type(t[1]) is int and t[1] in (0,MASK)
    return t[0] in OPS and len(t)==3 and valid(t[1],depth+1) and valid(t[2],depth+1)

def certify(lhs,rhs):
    """Independent universal per-bit checker, not a word-sampling test."""
    if not valid(lhs) or not valid(rhs) or size(lhs)>4 or size(rhs)>=size(lhs) or not variables(rhs)<=variables(lhs):return False
    def bit(t,v):
        if t[0]=='v':return v[t[1]]
        if t[0]=='c':return bool(t[1])
        a,b=bit(t[1],v),bit(t[2],v)
        return a!=b if t[0]=='xor' else a and b
    return all(bit(lhs,v)==bit(rhs,v) for v in product((False,True),repeat=3))

def grammar(max_ops):
    levels=[LEAVES]
    for n in range(1,max_ops+1):
        levels.append(tuple((op,a,b) for k in range(n) for a in levels[k] for b in levels[n-1-k] for op in OPS))
    return levels

def discover(terms,max_ops=2,samples=None):
    """Candidate search from observed equivalences; exact admission is separate."""
    if samples is None:
        r=random.Random(1801);samples=[tuple(r.getrandbits(32) for _ in range(3)) for _ in range(4)]
    def signature(t):return tuple(evaluate(t,v) for v in samples)
    index=defaultdict(list)
    for level in grammar(max_ops):
        for t in level:index[signature(t)].append(t)
    rules=set();attempts=rejected=0
    for lhs in sorted(set(terms)):
        if not valid(lhs) or size(lhs)>4:continue
        for rhs in index[signature(lhs)]:
            if size(rhs)>=size(lhs):break
            attempts+=1
            if certify(lhs,rhs):rules.add((lhs,rhs));break
            rejected+=1
    return tuple(sorted(rules,key=lambda r:(size(r[0]),r))),{'terms':len(set(terms)),'candidate_checks':attempts,'rejected':rejected,'admitted':len(rules)}

def source_terms(p):
    """Extract bounded islands; treat non-bitwise nodes as opaque words."""
    for i in sorted(p.needed()):
        if p.nodes[i].op not in OPS:continue
        slots={};count=0
        def lift(j,depth=0):
            nonlocal count
            n=p.nodes[j]
            if n.op in OPS:
                count+=1
                if count>4 or depth>4:raise ValueError('island extent')
                return (n.op,*(lift(k,depth+1) for k in n.args))
            if n.op=='const' and n.value in (0,MASK):return ('c',n.value)
            if j not in slots:slots[j]=len(slots)
            if slots[j]>=3:raise ValueError('island variables')
            return ('v',slots[j])
        try:yield lift(i)
        except ValueError:continue

class Rewriter:
    def __init__(self,m,rules):
        require(len(rules)<=512 and all(certify(*r) for r in rules),'uncertified rule catalogue');self.m=m;self.rules=tuple(rules);self.by=defaultdict(list)
        for i,(l,r) in enumerate(rules):self.by[l[0]].append((i,l,r))
    def rewrite(self,p):
        m=self.m;require(len(p.nodes)<=1024,'graph bound');nodes=[];ids={};mapping={};hits=Counter();checks=0
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
        for i in sorted(p.needed()):
            n=p.nodes[i];j=intern(m.Node(n.op,tuple(mapping[k] for k in n.args),n.value))
            # Bounded local composition; every admitted rule is an exact substitution.
            for _ in range(8):
                changed=False
                for k,l,r in self.by[nodes[j].op]:
                    checks+=1;env={}
                    if match(l,j,env):j=build(r,env);hits[k]+=1;changed=True;break
                if not changed:break
            mapping[i]=j
        out=m.Program(tuple(nodes),mapping[p.output]);return out,{'hits':dict(hits),'checks':checks,'before':sum(bool(p.nodes[i].args) for i in p.needed()),'after':sum(bool(out.nodes[i].args) for i in out.needed())}

class DirectBits:
    """Exact direct baseline: constant/identity of a bounded bitwise island."""
    def __init__(self,m):self.m=m
    def rewrite(self,p):
        m=self.m;require(len(p.nodes)<=65536,'graph bound');nodes=[];mapping={};ids={};checks=hits=0
        def intern(n):
            if n not in ids:ids[n]=len(nodes);nodes.append(n)
            return ids[n]
        for i in sorted(p.needed()):
            n=p.nodes[i];j=intern(m.Node(n.op,tuple(mapping[k] for k in n.args),n.value))
            if n.op in OPS:
                opaque=set();island=set()
                stack=[j]
                while stack and len(island)<=64 and len(opaque)<=3:
                    k=stack.pop()
                    if k in island:continue
                    v=nodes[k]
                    if v.op in OPS:island.add(k);stack.extend(v.args)
                    elif v.op!='const':opaque.add(k)
                if not stack and len(opaque)<=3 and len(island)<=64:
                    leaves=sorted(opaque);outputs=[];assignments=list(product((0,MASK),repeat=len(leaves)))
                    for values in assignments:
                        env=dict(zip(leaves,values))
                        for k in sorted(island):
                            def read(a):return nodes[a].value if nodes[a].op=='const' else env[a]
                            v=nodes[k];a,b=map(read,v.args);env[k]=a^b if v.op=='xor' else a&b
                        outputs.append(env[j]);checks+=1
                    if len(set(outputs))==1:j=intern(m.Node('const',value=outputs[0]));hits+=1
                    else:
                        for k,leaf in enumerate(leaves):
                            if outputs==[v[k] for v in assignments]:j=leaf;hits+=1;break
            mapping[i]=j
        out=m.Program(tuple(nodes),mapping[p.output]);return out,{'hits':{0:hits} if hits else {},'checks':checks,'before':sum(bool(p.nodes[i].args) for i in p.needed()),'after':sum(bool(out.nodes[i].args) for i in out.needed())}

class Hybrid:
    def __init__(self,m,rules):self.first=Rewriter(m,rules);self.second=DirectBits(m)
    def rewrite(self,p):
        q,a=self.first.rewrite(p);r,b=self.second.rewrite(q)
        return r,{'hits':a['hits']|{len(self.first.rules):sum(b['hits'].values())},'checks':a['checks']+b['checks'],'before':a['before'],'after':b['after']}

def from_source(m,s):return m.Program(tuple(m.Node(op,tuple(args),v) for op,args,v in s['nodes']),s['output'])

def generated(m,seed,n,depth):
    """New task shapes from the same bitwise grammar, with opaque affine leaves."""
    r=random.Random(seed)
    for i in range(n):
        nodes=[m.Node('input'),m.Node('const',value=r.getrandbits(32)),m.Node('const',value=r.getrandbits(32)),m.Node('const',value=0),m.Node('const',value=MASK)]
        def op(name,a,b):nodes.append(m.Node(name,(a,b)));return len(nodes)-1
        x=0
        for _ in range(depth):
            k=r.choice((1,2));kind=r.randrange(6)
            if kind==0:x=op('xor',op('xor',x,k),k)
            elif kind==1:x=op('xor',x,3)
            elif kind==2:x=op('and',x,4)
            elif kind==3:x=op('and',x,x)
            elif kind==4:x=op('xor',op('xor',x,k),x) # constant result k
            else:x=op('and',x,k) # not generally affine
        x=op('add',x,2)
        yield m.Program(tuple(nodes),x)

def self_generated(m,rules,seed,n):
    """Existing rules define new task structure; mutate a random leaf occurrence."""
    rng=random.Random(seed)
    for i in range(n):
        nodes=[m.Node('input'),m.Node('const',value=rng.getrandbits(32)),m.Node('const',value=rng.getrandbits(32))]
        def put(op,a,b):nodes.append(m.Node(op,(a,b)));return len(nodes)-1
        def emit(t,env,mutate):
            if t[0]=='v':return env[t[1]] if not mutate or rng.randrange(4) else rng.randrange(3)
            if t[0]=='c':nodes.append(m.Node('const',value=t[1]));return len(nodes)-1
            return put(t[0],emit(t[1],env,mutate),emit(t[2],env,mutate))
        x=0
        for _ in range(8):
            lhs,rhs=rng.choice(rules);env=[rng.randrange(3) for _ in range(3)];env[0]=x
            x=emit(lhs,env,i%2==1)
            # Cross algebraic boundary; rules must preserve the whole opaque subexpression.
            x=put('add',x,2)
        yield m.Program(tuple(nodes),x)

def qualify(m,candidates,training):
    """Keep rules actually used; repeat with the resulting catalogue to remove dead rules."""
    rw=Rewriter(m,candidates);used=Counter()
    for p in training:used.update(rw.rewrite(p)[1]['hits'])
    return tuple(candidates[i] for i in sorted(used))

def audit(m,ps,rules):
    rw=DirectBits(m) if rules is None else Hybrid(m,rules[1]) if rules and rules[0]=='hybrid' else Rewriter(m,rules);r=random.Random(1805);stats=Counter();evidence=[];start=time.perf_counter_ns();rewrite_ns=0
    for p in ps:
        before=symbolic_inspect(m,p);t=time.perf_counter_ns();q,work=rw.rewrite(p);after=symbolic_inspect(m,q);rewrite_ns+=time.perf_counter_ns()-t
        for x in (0,1,2,MASK,*[r.getrandbits(32) for _ in range(8)]):
            require(m.reference(p,x)==m.reference(q,x),'rewrite parity');stats['queries']+=1
            if after['status']=='certified':require(m.reference(p,x)==(after['a']*x+after['b'])&MASK,'certificate parity')
        stats['before_'+before['status']]+=1;stats['after_'+after['status']]+=1;stats['ops_before']+=work['before'];stats['ops_after']+=work['after'];stats['rule_hits']+=sum(work['hits'].values());stats['rule_checks']+=work['checks'];stats['multi_rule_programs']+=sum(work['hits'].values())>1
        evidence.append({'source':p.identity,'rewritten':q.identity,'before':before,'after':after,'work':work})
    return {'stats':dict(stats),'evidence':evidence,'elapsed_ns':time.perf_counter_ns()-start,'rewrite_and_inspect_ns':rewrite_ns}

def campaign(parent=None):
    m=portable()
    if parent is not None:
        raw=Path(parent).read_bytes();require(sha256(raw).hexdigest()==PARENT,'parent identity');rows=json.loads(raw)['cohorts']['stress']
    else:
        from measured_acquisition import stress
        rows=list(stress(m,1704,120))
    require(digest(rows)==STRESS_PIN,'stress cohort identity')
    prior=[from_source(m,r['source']) for r in rows];unknown=[p for p in prior if symbolic_inspect(m,p)['status']=='unknown']
    start=time.perf_counter_ns();first,first_stats=discover([t for p in unknown for t in source_terms(p)]);first=qualify(m,first,unknown);first_ns=time.perf_counter_ns()-start
    train=list(generated(m,1802,120,2));valid_set=list(generated(m,1803,120,3));final=list(generated(m,1804,240,6));seen=set()
    for ps in (prior,train,valid_set,final):
        ix={p.identity for p in ps};require(len(ix)==len(ps) and not ix&seen,'cohort overlap');seen|=ix
    start=time.perf_counter_ns();second,second_stats=discover([t for p in train for t in source_terms(p)]);combined=tuple(sorted(set(first)|set(second),key=lambda r:(size(r[0]),r)));combined=qualify(m,combined,train+unknown);second_ns=time.perf_counter_ns()-start
    # Deliberately impoverished observation sensor: exact verifier rejects aliases.
    _,collision=discover(grammar(1)[1],samples=[(0,0,0)])
    reports={}
    options=[('baseline',()),('first',first),('combined',combined),('direct',None)]
    for name,ps in [('prior',prior),('validation',valid_set)]:
        reports[name]={label:audit(m,ps,rules) for label,rules in options}
    require(reports['validation']['combined']['stats'].get('after_certified',0)>=reports['validation']['first']['stats'].get('after_certified',0),'validation regression')
    reports['final']={label:audit(m,final,rules) for label,rules in options}
    # A second, rule-generated environment. Keep validation and final separate.
    recursive_val=list(self_generated(m,combined,1806,120));recursive_final=list(self_generated(m,combined,1807,240))
    for ps in (recursive_val,recursive_final):
        ix={p.identity for p in ps};require(len(ix)==len(ps) and not ix&seen,'recursive cohort overlap');seen|=ix
    recursive_options=options+[('hybrid',('hybrid',combined))]
    reports['recursive_validation']={label:audit(m,recursive_val,rules) for label,rules in recursive_options}
    selected=max(recursive_options,key=lambda x:(reports['recursive_validation'][x[0]]['stats'].get('after_certified',0),-reports['recursive_validation'][x[0]]['stats']['ops_after']))[0]
    reports['recursive_final']={label:audit(m,recursive_final,rules) for label,rules in recursive_options}
    # Refine vocabulary from residual structures of a separate generated training stream.
    epoch_train=list(self_generated(m,combined,1808,120));epoch_val=list(self_generated(m,combined,1809,120));epoch_final=list(self_generated(m,combined,1810,240))
    for ps in (epoch_train,epoch_val,epoch_final):
        ix={p.identity for p in ps};require(len(ix)==len(ps) and not ix&seen,'epoch cohort overlap');seen|=ix
    start=time.perf_counter_ns();rw=Rewriter(m,combined);residual=[rw.rewrite(p)[0] for p in epoch_train]
    third,third_stats=discover([t for p in epoch_train+residual for t in source_terms(p)])
    pool=tuple(sorted(set(combined)|set(third),key=lambda r:(size(r[0]),r)))
    refined=tuple(sorted(set(combined)|set(qualify(m,pool,epoch_train)),key=lambda r:(size(r[0]),r)));third_ns=time.perf_counter_ns()-start
    epoch_options=[('combined',combined),('refined',refined),('direct',None),('old_hybrid',('hybrid',combined)),('refined_hybrid',('hybrid',refined))]
    reports['epoch_validation']={label:audit(m,epoch_val,rules) for label,rules in epoch_options}
    epoch_selected=max(epoch_options,key=lambda x:(reports['epoch_validation'][x[0]]['stats'].get('after_certified',0),-reports['epoch_validation'][x[0]]['stats']['ops_after']))[0]
    reports['epoch_final']={label:audit(m,epoch_final,rules) for label,rules in epoch_options}
    allcohorts=[('prior',prior),('training',train),('validation',valid_set),('final',final),('recursive_validation',recursive_val),('recursive_final',recursive_final),('epoch_training',epoch_train),('epoch_validation',epoch_val),('epoch_final',epoch_final)]
    sources={k:[{'id':p.identity,'nodes':[[n.op,list(n.args),n.value] for n in p.nodes],'output':p.output} for p in ps] for k,ps in allcohorts}
    return {'schema':'vlm-rewrite-discovery-v1','parent_sha256':PARENT,'first_discovery':first_stats,'second_discovery':second_stats,'collision_control':collision,'first_rules':first,'combined_rules':combined,'discovery_ns':[first_ns,second_ns,third_ns],'recursive_selected':selected,'third_discovery':third_stats,'refined_rules':refined,'epoch_selected':epoch_selected,'cohorts':sources,'reports':reports}

def semantic(r):
    return digest({k:({c:{n:{x:y for x,y in v.items() if x not in ('elapsed_ns','rewrite_and_inspect_ns')} for n,v in a.items()} for c,a in z.items()} if k=='reports' else z) for k,z in r.items() if k!='discovery_ns'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent');p.add_argument('--output',required=True);a=p.parse_args();r=campaign(a.parent);Path(a.output).write_bytes(canonical(r)+b'\n');print('semantic',semantic(r));print(json.dumps({k:v for k,v in r.items() if k not in ('reports','cohorts','combined_rules')}));print(json.dumps({k:{n:v['stats'] for n,v in s.items()} for k,s in r['reports'].items()},indent=2))
