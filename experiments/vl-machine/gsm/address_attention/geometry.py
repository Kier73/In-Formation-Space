"""GSM-004: learned byte-address geometry, predictive diagnostics, exact residual admission."""
import hashlib,itertools,json,time
from pathlib import Path
import numpy as np

N=256; DK=8; DV=8; D=DK+DV

def digest(a):return hashlib.sha256(np.ascontiguousarray(a,dtype='<f8').tobytes()).hexdigest()

def partitions(bits=tuple(range(8))):
    if not bits:yield ();return
    a,*tail=bits
    for b in tail:
        for rest in partitions(tuple(x for x in tail if x!=b)):yield ((a,b),)+rest

GEOMS=tuple(partitions()); IDS=np.arange(N)

def digits(g):return np.stack([((IDS>>a)&1)+2*((IDS>>b)&1) for a,b in g],axis=1)

def design(g):
    x=digits(g);return np.column_stack([np.ones(N)]+[(x[:,j]==i).astype(float) for j in range(4) for i in range(1,4)])

DESIGNS={g:design(g) for g in GEOMS}

def fit(g,rows,y,integer=False):
    x=DESIGNS[g][rows];train=np.arange(len(rows))
    for _ in range(3):
        c=np.linalg.lstsq(x[train],y[train],rcond=None)[0]
        e=np.sum((x@c-y)**2,axis=1);train=np.argsort(e,kind='stable')[:max(13,int(.9*len(rows))) ]
    if integer:c=np.rint(c)
    return c

def softmax(q,k):
    l=q@k.T/np.sqrt(DK);w=np.exp(l-l.max(axis=1,keepdims=True));return w/w.sum(axis=1,keepdims=True)

def diagnostics(q,actual,approx):
    p=softmax(q,actual[:,:DK]);r=softmax(q,approx[:,:DK]);kl=float(np.mean(np.sum(p*(np.log(p)-np.log(r)),axis=1)))
    return {'attention_kl_nats':max(0.,kl),'excess_perplexity_ratio':float(np.exp(max(0.,kl))),'output_mse':float(np.mean((p@actual[:,DK:]-r@approx[:,DK:])**2))}

def select(src,train,val,integer,prior=None):
    """Only training/validation coordinates enter discovery. Compare all 105 groupings."""
    start=time.perf_counter_ns();candidates=[]
    for g in GEOMS:
        c=fit(g,train,src[train],integer);e=float(np.mean((DESIGNS[g][val]@c-src[val])**2));candidates.append((e,g,c))
    e,g,c=min(candidates,key=lambda x:(x[0],x[1]));old=next((a for a in candidates if a[1]==prior),None)
    return g,c,e,None if old is None else old[0],time.perf_counter_ns()-start

def qualify(src,g,c):
    """Full independently observed source: retain every nonidentical row or dense fallback."""
    base=DESIGNS[g]@c;bad=np.flatnonzero(np.any(base!=src,axis=1));cost=c.nbytes+8+len(bad)*(4+8*D)
    if cost>=src.nbytes:return {'mode':'dense','bytes':src.nbytes,'exceptions':len(bad),'source':digest(src)},src.copy()
    out=base.copy();out[bad]=src[bad]
    assert np.array_equal(out,src)
    return {'mode':'ground','bytes':cost,'exceptions':len(bad),'source':digest(src),'geometry':g,'coefficients':c.tolist(),'overrides':[[int(i),src[i].tolist()] for i in bad]},out

def reconstruct(r,expected):
    if r['mode']!='ground':raise ValueError('dense source required')
    g=tuple(tuple(x) for x in r['geometry']);c=np.asarray(r['coefficients'],dtype=float)
    if g not in DESIGNS or c.shape!=(13,D):raise ValueError('geometry')
    out=DESIGNS[g]@c;seen=set()
    for i,row in r['overrides']:
        if type(i) is not int or not 0<=i<N or i in seen or np.shape(row)!=(D,):raise ValueError('override')
        seen.add(i);out[i]=row
    if digest(out)!=expected or r['source']!=expected:raise ValueError('identity')
    return out

def compact_query(r,expected,q):
    """Full-population softmax via GSM-003 factor tables, without row expansion."""
    from address_attention import Ground
    if r['mode']!='ground' or r['source']!=expected:raise ValueError('unqualified ground')
    g=tuple(tuple(x) for x in r['geometry']);c=np.asarray(r['coefficients'],dtype=float)
    table=np.zeros((4,4,D));table[:,1:]=c[1:].reshape(4,3,D);table[0]+=c[0]
    ds=digits(g);mapping=ds@np.array([64,16,4,1]);patches={int(mapping[i]):(row[:DK],row[DK:]) for i,row in r['overrides']}
    ground=Ground(table[:,:,:DK],table[:,:,DK:],np.zeros((4,4,DV)),patches)
    return np.stack([ground.query(row,N)[0] for row in q])

def generated(g,seed,patches=0):
    rng=np.random.default_rng(seed);c=rng.integers(-3,4,size=(13,D)).astype(float);src=DESIGNS[g]@c
    ids=rng.choice(N,patches,replace=False);src[ids]+=rng.integers(1,5,size=(patches,D));return src

def campaign(neural=None):
    rng=np.random.default_rng(400);q=rng.normal(size=(64,DK));order=rng.permutation(N);train=order[:128];val=order[128:192];test=order[192:];prior=GEOMS[0];records=[]
    sources=[('structured-A',generated(GEOMS[27],401),True),('shifted-B',generated(GEOMS[82],402,8),True),('unstructured',rng.normal(size=(N,D)),False)]
    if neural is not None:sources.append(('trained-neural-projections',neural,False))
    for name,src,integer in sources:
        g,c,err,old,elapsed=select(src,train,val,integer,prior);approx=DESIGNS[g]@c
        fixed=DESIGNS[prior]@fit(prior,train,src[train],integer)
        record={'name':name,'source_sha256':digest(src),'geometry':g,'previous':prior,'validation_mse':err,'previous_validation_mse':old,'heldout_row_mse':float(np.mean((approx[test]-src[test])**2)),'heldout_fixed_mse':float(np.mean((fixed[test]-src[test])**2)),'predictive':diagnostics(q,src[test],approx[test]),'fixed_predictive':diagnostics(q,src[test],fixed[test]),'discovery_ns':elapsed}
        admitted,out=qualify(src,g,c);record['admission']=admitted;record['verified_output_error']=float(np.max(np.abs(softmax(q,src[:,:DK])@src[:,DK:]-softmax(q,out[:,:DK])@out[:,DK:])))
        if admitted['mode']=='ground':
            assert np.array_equal(reconstruct(admitted,digest(src)),src)
            prediction=compact_query(admitted,digest(src),q);record['compact_query_error']=float(np.max(np.abs(prediction-softmax(q,src[:,:DK])@src[:,DK:])))
            assert record['compact_query_error']<1e-10;prior=g
        records.append(record)
    return {'schema':'gsm-004-v1','candidate_geometries':len(GEOMS),'train':train.tolist(),'validation':val.tolist(),'heldout':test.tolist(),'query_count':len(q),'records':records}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--neural');p.add_argument('--output',required=True);a=p.parse_args();r=campaign(np.load(a.neural,allow_pickle=False) if a.neural else None);Path(a.output).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps([{k:v for k,v in x.items() if k!='admission'}|{'admission':{k:v for k,v in x['admission'].items() if k not in ('coefficients','overrides')}} for x in r['records']],indent=2))
