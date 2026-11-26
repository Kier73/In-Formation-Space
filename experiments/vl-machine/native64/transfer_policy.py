"""VLM-015: learn counterexample probes on one substrate, transfer to another."""
import argparse
from hashlib import sha1,sha256
import json,os,random,sys
from pathlib import Path
from collections import Counter,defaultdict
from experience_contract import kernel,k1_law,digest,COHORT_PINS

MASK=(1<<32)-1
PROBES=(2,3,65536,0x55555555,0xaaaaaaaa,0xffffffff,0x80000000,0x12345678)
MACHINE_BLOB='97eedd6529b58e0592f9bdaa5bf2d1ea324234ed'

def portable():
    path=Path(__file__).resolve().parent.parent/'machine.py'
    if not path.is_file():path=Path(__file__).with_name('machine.py')
    raw=path.read_bytes();assert sha1(('blob %d\0'%len(raw)).encode()+raw).hexdigest()==MACHINE_BLOB
    import importlib.util
    spec=importlib.util.spec_from_file_location('pinned_vlm',path);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def inspect(identity,source,observe,check):
    b=observe(0);a=(observe(1)-b)&MASK
    values=[observe(x) for x in PROBES];bad=[int(y!=((a*x+b)&MASK)) for x,y in zip(PROBES,values)]
    eligible=bool(check(a,b));assert not eligible or not any(bad)
    return {'id':identity,'source':source,'a':a,'b':b,'values':values,'bad':bad,'eligible':eligible}

def source_rows(k,archive,cohort):
    rows=archive[cohort];name='train' if cohort=='training' else cohort
    assert digest(rows)==COHORT_PINS[name]
    for row in rows:
        p,o=row['program'],row['observer'];assert digest([p,o])==row['source_sha256']
        def observe(x):
            v=[0]*4;v[o]=x;r=k.evaluate(v,p,1,mode='reference');assert r['status']==0;return r['registers'][o]
        yield inspect(row['source_sha256'],{'program':p,'observer':o},observe,lambda a,b:k1_law(p,o)==(a,b))

def context(row):
    a,b=row['a'],row['b'];return str((int(a==0),a&1,b&1))

def best(rows):return max(range(len(PROBES)),key=lambda i:(sum(r['bad'][i] for r in rows),-i))

def fit(rows):
    groups=defaultdict(list)
    for r in rows:groups[context(r)].append(r)
    return {'default':best(rows),'contexts':{k:best(v) for k,v in sorted(groups.items()) if len(v)>=16}}

def assess(rows,policy):
    s=Counter(cases=len(rows),eligible=sum(r['eligible'] for r in rows),basis_calls=2*len(rows))
    for r in rows:
        i=policy['contexts'].get(context(r),policy['default'])
        rejected=i is not None and r['bad'][i]
        s['extra_probes']+=i is not None;s['counterexamples']+=bool(rejected);s['verifier_calls']+=not rejected;s['admitted']+=r['eligible'] and not rejected
        if rejected and r['eligible']:raise RuntimeError('false refutation')
    assert s['admitted']==s['eligible'];return dict(s)

def policy_for(rows,validation):
    adaptive=fit(rows);global_only={'default':adaptive['default'],'contexts':{}}
    # Freeze on validation, prefer simpler policy on ties; no target data enters this choice.
    chosen=max((global_only,adaptive),key=lambda p:(assess(validation,p)['counterexamples'],-len(p['contexts'])))
    return chosen,adaptive,global_only

def polynomial_affine(m,p,a,b,max_degree=8):
    """Degree-bounded exact Newton-difference certificate over the word ring."""
    if type(max_degree) is not int or not 1<=max_degree<=8 or any(type(v) is not int or not 0<=v<=MASK for v in (a,b)):return False
    polys={}
    for i in sorted(p.needed()):
        n=p.nodes[i]
        if n.op=='input':q=[0,1]
        elif n.op=='const':q=[n.value]
        elif n.op in ('add','mul'):
            u,v=(polys[j] for j in n.args)
            size=max(len(u),len(v)) if n.op=='add' else len(u)+len(v)-1
            if size>max_degree+1:return False
            q=[0]*size
            if n.op=='add':
                for vec in (u,v):
                    for j,x in enumerate(vec):q[j]=(q[j]+x)&MASK
            else:
                for j,x in enumerate(u):
                    for k,y in enumerate(v):q[j+k]=(q[j+k]+x*y)&MASK
        else:return False
        while len(q)>1 and q[-1]==0:q.pop()
        polys[i]=q
    q=polys[p.output];d=max(1,len(q)-1)
    def value(x):
        y=0
        for c in reversed(q):y=(y*x+c)&MASK
        return y
    differences=[(value(i)-a*i-b)&MASK for i in range(d+1)]
    # Integer-valued Newton expansion of the degree-bounded difference;
    # all coefficients must vanish modulo 2^32. Not unrestricted sampling.
    return all(x==0 for x in differences)

def target_rows(m,seed,n):
    r=random.Random(seed)
    for i in range(n):
        family=i%6;a,b=r.getrandbits(32),r.getrandbits(32);depth=r.randrange(1,12)
        if family==0:p=m.layered_affine(a,b,depth)
        else:
            nodes=[m.Node('input'),m.Node('const',value=a),m.Node('const',value=b)]
            if family==1:nodes += [m.Node('mul',(0,0)),m.Node('add',(3,2))]
            elif family==2:nodes += [m.Node('xor',(0,1)),m.Node('add',(3,2))]
            elif family==3:nodes += [m.Node('lt',(0,1)),m.Node('select',(3,0,2))]
            elif family==4:nodes += [m.Node('and',(0,1)),m.Node('add',(3,2))]
            else:nodes += [m.Node('mul',(0,0)),m.Node('const',value=1<<31),m.Node('mul',(3,4)),m.Node('add',(5,2))]
            p=m.Program(tuple(nodes),len(nodes)-1)
        source={'family':family,'nodes':[[v.op,list(v.args),v.value] for v in p.nodes],'output':p.output}
        def check(a,b):return m.verify(p,m.Ground(p.identity,a,b))
        row=inspect(p.identity,source,lambda x:m.reference(p,x),check)
        row['polynomial_eligible']=polynomial_affine(m,p,row['a'],row['b']);assert not row['polynomial_eligible'] or not any(row['bad'])
        # Cross-check the two actual VLM evaluation paths, including new seeds.
        for _ in range(4):
            x=r.getrandbits(32);y=m.reference(p,x);assert m.demand(p,x)[0]==y
            if row['polynomial_eligible']:assert ((row['a']*x+row['b'])&MASK)==y
            if row['eligible']:
                vm=m.Machine();vm.admit(p,m.Ground(p.identity,row['a'],row['b']));assert vm.observe(p,x)['output']==y
        yield row

def live_assess(rows,policy,adapter):
    """Actually invoke only the chosen probes and, if needed, the exact checker."""
    s=Counter(cases=len(rows),eligible=sum(r['eligible'] for r in rows))
    for row in rows:
        observe,check=adapter(row['source'])
        b=observe(0);a=(observe(1)-b)&MASK;s['basis_calls']+=2
        assert (a,b)==(row['a'],row['b'])
        i=policy['contexts'].get(context({'a':a,'b':b}),policy['default']);rejected=False
        if i is not None:
            x=PROBES[i];s['extra_probes']+=1;rejected=observe(x)!=((a*x+b)&MASK)
        s['counterexamples']+=rejected;s['verifier_calls']+=not rejected
        admitted=not rejected and check(a,b);s['admitted']+=admitted
        assert admitted==row['eligible']
    return dict(s)

def campaign(archive,root):
    k=kernel(root);m=portable();train=list(source_rows(k,archive,'training'));val=list(source_rows(k,archive,'validation'));held=list(source_rows(k,archive,'heldout'));stress=list(source_rows(k,archive,'stress'))
    source_ids=set();
    for rows in (train,val,held,stress):
        ids={r['id'] for r in rows};assert len(ids)==len(rows) and not ids&source_ids;source_ids|=ids
    chosen,adaptive,global_only=policy_for(train,val)
    target=list(target_rows(m,220,240));target_validation=list(target_rows(m,221,120));target_final=list(target_rows(m,222,240));ids=set()
    for rows in (target,target_validation,target_final):
        assert len({r['id'] for r in rows})==len(rows) and not ids&{r['id'] for r in rows};ids|={r['id'] for r in rows}
    adapted,_,_=policy_for(target,target_validation)
    policies={'no_extra':{'default':None,'contexts':{}},'fixed_two':{'default':0,'contexts':{}},'source_global':global_only,'source_context':adaptive,'transferred':chosen,'target_adapted':adapted}
    cohorts={'source_validation':val,'source_final':held,'source_stress':stress,'target_final':target_final}
    reports={name:{p:assess(rows,policy) for p,policy in policies.items() if p!='target_adapted' or name=='target_final'} for name,rows in cohorts.items()}
    def source_adapter(source):
        p,o=source['program'],source['observer']
        def observe(x):
            v=[0]*4;v[o]=x;r=k.evaluate(v,p,1,mode='reference');assert r['status']==0;return r['registers'][o]
        return observe,lambda a,b:k1_law(p,o)==(a,b)
    def target_adapter(source):
        p=m.Program(tuple(m.Node(op,tuple(args),v) for op,args,v in source['nodes']),source['output'])
        return lambda x:m.reference(p,x),lambda a,b:m.verify(p,m.Ground(p.identity,a,b))
    live={'source_final':live_assess(held,chosen,source_adapter),'target_transferred':live_assess(target_final,chosen,target_adapter),'target_adapted':live_assess(target_final,adapted,target_adapter)}
    assert live['source_final']==reports['source_final']['transferred'] and live['target_transferred']==reports['target_final']['transferred'] and live['target_adapted']==reports['target_final']['target_adapted']
    extra={'original' :sum(r['eligible'] for r in target_final),'polynomial':sum(r['polynomial_eligible'] for r in target_final),'newly_verified':sum(r['polynomial_eligible'] and not r['eligible'] for r in target_final)}
    return {'schema':'vlm-transfer-probe-v1','polynomial_extension':extra,'live_paths':live,'probes':list(PROBES),'policies':policies,'reports':reports,'cohorts':{'source_training':train,'source_validation':val,'source_final':held,'source_stress':stress,'target_training':target,'target_validation':target_validation,'target_final':target_final},'offline_probe_calls':(len(train)+len(val)+len(held)+len(stress)+len(target)+len(target_validation)+len(target_final))*(2+len(PROBES))}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--root',default=os.environ.get('VLK_ROOT'));p.add_argument('--output',required=True);a=p.parse_args();report=campaign(json.loads(Path(a.archive).read_bytes()),a.root);Path(a.output).write_text(json.dumps(report,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps({k:v for k,v in report.items() if k!='cohorts'},indent=2))
