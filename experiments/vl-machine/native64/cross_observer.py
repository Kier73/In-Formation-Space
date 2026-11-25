"""VLM-013: learn an observer-specific Ground from a pinned VL-K K1 substrate."""
import ctypes as c
from hashlib import sha256,sha1
import importlib.util
import json,os,random
from pathlib import Path
from time import perf_counter_ns
from test_core import L,U,MASK,load,affine,call
from test_neural import I,install,forward

PIN='ad6dd45d06b9f349526783d45d0e5706a49ade79'
BLOBS={'vlk1.c':'cd9568e3246ec3eda10ecb7f6e6f5452a695935a','vlk.py':'e14e8fe8f372ecb707d53df29d2dcb53e75161d4'}

def gitblob(p):
    b=p.read_bytes();return sha1(('blob %d\0'%len(b)).encode()+b).hexdigest()

def kernel():
    root=Path(os.environ['VLK_ROOT']);cfile=root/'src/vlk1.c';pyfile=root/'python/vlk.py'
    for p in (cfile,pyfile):
        if gitblob(p)!=BLOBS[p.name]:raise ValueError('VL-K source pin')
    spec=importlib.util.spec_from_file_location('pinned_vlk',pyfile);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.Kernel(root/'dist/libvlk.so')

def digest(x):return sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def programs(seed,n,stress=False):
    r=random.Random(seed)
    for _ in range(n):
        o=r.randrange(4);other=[i for i in range(4) if i!=o];r.shuffle(other);family=r.randrange(5);p=[]
        group=[o]+other[:min(family,3)] if family<3 else list(range(4))
        for _ in range(r.randrange(4,20)):
            d=r.randrange(4);allowed=group if d in group else list(range(4));op=r.choice(('set','copy','add','mul','addr'))
            # Keep a dependency cone small in some families; other registers remain active.
            x=r.choice(allowed) if op in ('copy','addr') else r.getrandbits(32)
            p.append((op,d,x))
        if family==3:p.append(('set',o,r.getrandbits(32))) # removes earlier dependencies
        if family==4:p.append(('mulr',r.randrange(4),r.randrange(4)))
        if stress and family<4:
            # Force a persistent cycle after arbitrary earlier instructions, with no resets.
            p=[('add',i,r.getrandbits(32)) for i in range(4)]
            ring=[o]+other[:family]
            p.extend(('addr',d,ring[(i+1)%len(ring)]) for i,d in enumerate(ring))
        yield p,o

def symbolic(p):
    """Independent source replay over Z/(2^32), rejecting all variable products."""
    m=[[int(i==j) for j in range(5)] for i in range(5)]
    for op,d,x in p:
        if op=='mulr':return None
        if op=='set':m[d]=[0,0,0,0,x]
        elif op=='copy':m[d]=m[x][:]
        elif op=='add':m[d][4]=(m[d][4]+x)&MASK
        elif op=='mul':m[d]=[(x*v)&MASK for v in m[d]]
        elif op=='addr':m[d]=[(a+b)&MASK for a,b in zip(m[d],m[x])]
        else:raise ValueError('opcode')
    return m

def discover(k,p,o):
    """Learn a candidate law exclusively from five executed source observations."""
    values=[];work=0
    for i in range(5):
        seed=[int(j==i-1) for j in range(4)] if i else [0]*4
        result=k.evaluate(seed,p,1,mode='reference');assert result['status']==0
        values.append(result['registers']);work+=result['work']
    m=[[(values[j+1][i]-values[0][i])&MASK for j in range(4)]+[values[0][i]] for i in range(4)]+[[0,0,0,0,1]]
    return project(m,o),values,work

def project(m,o):
    keep={o}
    while True:
        nxt=keep|{j for i in keep for j in range(4) if m[i][j]}
        if nxt==keep:break
        keep=nxt
    ids=sorted(keep);indices=ids+[4]
    return {'ids':ids,'matrix':[[m[i][j] for j in indices] for i in indices]}

def verify(p,o,g):
    m=symbolic(p)
    return m is not None and g==project(m,o)

def navigate(g,seed,o,t):
    ids=g['ids'];m=g['matrix'];d=len(m)
    if len(ids)==1:
        a,b=m[0];nodes,output=affine(a,b,1);load(nodes,output);assert L.admit(a,b)
        return call(L.navigate,seed[o],t)[0]
    v=[seed[i] for i in ids]+[1]
    while t:
        if t&1:v=[sum(a*b for a,b in zip(row,v))&MASK for row in m]
        t>>=1
        if t:m=[[sum(m[i][k]*m[k][j] for k in range(d))&MASK for j in range(d)] for i in range(d)]
    return v[ids.index(o)]

def features(p,o):
    n=len(p);cross=('copy','addr','mulr')
    return [round(16*sum(d==o for op,d,x in p)/n),round(16*sum(d==o and op in cross and x!=o for op,d,x in p)/n),round(16*sum(op in cross for op,d,x in p)/n),16*int(any(op=='set' and d==o for op,d,x in p)),16*int(any(op=='mulr' for op,d,x in p)),min(16,n)]

def observations(k,seed,n,stress=False):
    for p,o in programs(seed,n,stress):
        g,v,work=discover(k,p,o);admitted=verify(p,o,g);label=len(g['ids']) if admitted and len(g['ids'])<=2 else 0
        yield {'program':p,'observer':o,'source_sha256':digest([p,o]),'features':features(p,o),'basis':v,'basis_work':work,'candidate':g,'verified':admitted,'label':label}

def train(rows):
    import numpy as np
    x=np.array([r['features'] for r in rows])/16;y=np.eye(3)[[r['label'] for r in rows]]
    rng=np.random.default_rng(45);a=rng.normal(0,.4,(6,8));b=np.zeros(8);c0=rng.normal(0,.4,(8,3));d=np.zeros(3)
    for _ in range(600):
        z=x@a+b;h=np.clip(z,0,7.9375);p=h@c0+d;p=np.exp(p-p.max(axis=1,keepdims=True));p/=p.sum(axis=1,keepdims=True)
        e=(p-y)/len(x);dh=(e@c0.T)*((z>0)&(z<7.9375));da=x.T@dh;db=dh.sum(axis=0);dc=h.T@e;dd=e.sum(axis=0)
        a-=.3*da;b-=.3*db;c0-=.3*dc;d-=.3*dd
    return np.clip(np.rint(16*np.concatenate([a.T.ravel(),np.zeros(64),b,c0.T.ravel(),d])),-127,127).astype(int).tolist()

def infer(w,x):
    h=L.nn_open();assert h;out=(I*3)()
    try:assert L.nn_step(h,(I*6)(*x),out)
    finally:assert L.nn_close(h)
    assert list(out)==forward(w,x,[0]*8)[1]
    return max(range(3),key=lambda i:out[i])

def iterative(p,seed,t):
    v=seed[:]
    for _ in range(t):
        for op,d,x in p:
            if op=='set':v[d]=x
            elif op=='copy':v[d]=v[x]
            elif op=='add':v[d]=(v[d]+x)&MASK
            elif op=='mul':v[d]=(v[d]*x)&MASK
            elif op=='addr':v[d]=(v[d]+v[x])&MASK
            elif op=='mulr':v[d]=(v[d]*v[x])&MASK
    return v

def campaign(k,weights,rows):
    install(weights);r=random.Random(191);stats={'cases':len(rows),'proposal_correct':0,'eligible':0,'projected':0,'missed':0,'rejected_probe':0,'basis_work_all':0,'basis_work_selected':0,'basis_calls_selected':0,'basis_calls_all':5*len(rows),'symbolic_baseline_eligible':0,'scalar_native_queries':0,'pair_python_queries':0,'full_queries':0,'queries':0,'nonaffine':0,'nonaffine_probe_rejected':0,'reference_work':0,'affine_guard_calls':0,'affine_guard_work':0,'affine_guard_eligible':0};results=[]
    for row in rows:
        p,o=row['program'],row['observer'];label=row['label'];proposal=infer(weights,row['features']);m=symbolic(p)
        baseline=project(m,o) if m is not None else None
        stats['symbolic_baseline_eligible']+=baseline is not None and len(baseline['ids'])<=2
        stats['nonaffine']+=m is None;stats['affine_guard_calls']+=5*(m is not None);stats['affine_guard_work']+=row['basis_work']*(m is not None);stats['affine_guard_eligible']+=bool(label);stats['proposal_correct']+=proposal==label;stats['eligible']+=bool(label);stats['basis_work_all']+=row['basis_work'];g=None
        if proposal:
            g0,v,work=discover(k,p,o);stats['basis_calls_selected']+=5;stats['basis_work_selected']+=work
            if verify(p,o,g0) and len(g0['ids'])<=2:g=g0;stats['projected']+=1
            else:stats['rejected_probe']+=1;stats['nonaffine_probe_rejected']+=m is None
        stats['missed']+=bool(label and g is None)
        assert (not label or baseline==row['candidate']) and (g is None or g==baseline)
        queries=[]
        for _ in range(4):
            seed=[r.getrandbits(32) for j in range(4)];t=r.randrange(64) if m is None else (1<<40)+r.getrandbits(32)
            source=k.evaluate(seed,p,t,mode='auto');assert source['status']==0;expected=source['registers'][o];stats['reference_work']+=source['work']
            if m is not None:assert navigate(project(m,o),seed,o,t)==expected
            else:assert iterative(p,seed,t)==source['registers']
            if g is None:actual=expected;stats['full_queries']+=1
            else:
                actual=navigate(g,seed,o,t);stats['scalar_native_queries' if len(g['ids'])==1 else 'pair_python_queries']+=1
            assert actual==expected;stats['queries']+=1;queries.append({'seed':seed,'time':t,'value':actual})
        results.append({'source_sha256':row['source_sha256'],'proposal':proposal,'admitted':g is not None,'queries':queries})
    return stats,results

def main():
    k=kernel();train_rows=list(observations(k,190,600));validation=list(observations(k,192,240));held=list(observations(k,193,240));stress=list(observations(k,194,120,True))
    seen=set()
    for cohort in (train_rows,validation,held,stress):
        ids={r['source_sha256'] for r in cohort};assert not seen&ids;seen|=ids
    start=perf_counter_ns();w=train(train_rows);training_ns=perf_counter_ns()-start
    val,vr=campaign(k,w,validation)
    # Admit only a strictly cheaper policy at unchanged eligible coverage, compared to the affine guard.
    qualified=val['missed']==0 and val['basis_work_selected']<val['affine_guard_work']
    stats,results=campaign(k,w,held);ss,sr=campaign(k,w,stress)
    report={'schema':'vlm-cross-observer-v1','vlk_commit':PIN,'vlk_blobs':BLOBS,'train_cases':len(train_rows),'validation_cases':len(validation),'heldout_cases':len(held),'stress_cases':len(stress),'weights':w,'train_digest':digest(train_rows),'validation_digest':digest(validation),'heldout_digest':digest(held),'stress_digest':digest(stress),'result_digest':digest(results),'stress_result_digest':digest(sr),'policy_qualified':qualified,'validation':val,'stats':stats,'stress':ss}
    Path('cross-observer-data.json').write_text(json.dumps({'report':report,'training':train_rows,'validation':validation,'heldout':held,'stress':stress,'validation_queries':vr,'queries':results,'stress_queries':sr},sort_keys=True,separators=(',',':'))+'\n')
    print(json.dumps(report,indent=2));print('training_ns',training_ns)

if __name__=='__main__':main()
