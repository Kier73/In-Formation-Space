"""GSM-005: witness-directed pair interactions and exact softmax contraction."""
import itertools,json,time
from pathlib import Path
import numpy as np
from address_attention import rectangles

EDGES=tuple(itertools.combinations(range(4),2))
MODELS=((),)+tuple((e,) for e in EDGES)

def features(radix,edges):
    x=np.indices((radix,)*4).reshape(4,-1).T
    cols=[np.ones(len(x))]+[(x[:,j]==a) for j in range(4) for a in range(1,radix)]
    cols += [(x[:,i]==a)&(x[:,j]==b) for i,j in edges for a in range(1,radix) for b in range(1,radix)]
    return np.stack(cols,1).astype(float)

DESIGNS={e:features(4,e) for e in MODELS}

def candidates(observed):
    ids=np.array(sorted(observed));y=np.stack([observed[i] for i in ids]);out=[]
    for edges,x in DESIGNS.items():
        a=x[ids];u,s,v=np.linalg.svd(a,full_matrices=True);rank=int((s>1e-9).sum())
        c=np.linalg.lstsq(a,y,rcond=1e-10)[0];err=float(np.max(abs(a@c-y)))
        out.append((edges,c,err,rank,np.sum((x@v[rank:].T)**2,axis=1)))
    return out

def learn(read,pool,initial,budget,mode,seed):
    """Only read() can reveal source rows; candidates are fitted on acquired coordinates."""
    rng=np.random.default_rng(seed);obs={int(i):read(int(i)) for i in initial};trace=[]
    while len(obs)<budget:
        cs=candidates(obs);best=min(c[2] for c in cs);live=[c for c in cs if c[2]<=best+1e-8]
        remaining=np.array(sorted(set(pool)-obs.keys()))
        if mode=='active':
            pred=np.stack([DESIGNS[e][remaining]@c for e,c,_,_,_ in live]);disagreement=np.mean(np.var(pred,axis=0),axis=1)
            uncertainty=np.mean([v[remaining] for *_,v in live],axis=0)
            score=disagreement/(1+disagreement)+uncertainty
            i=int(remaining[np.argmax(score)])
        elif mode=='rank':
            # Source-independent experimental design: all candidate nullspaces, no values.
            i=int(remaining[np.argmax(np.mean([v[remaining] for *_,v in cs],axis=0))])
        elif mode=='random':i=int(rng.choice(remaining))
        else:raise ValueError('mode')
        trace.append([i,len(live)]);obs[i]=read(i)
    cs=candidates(obs);best=min(c[2] for c in cs);live=[c for c in cs if c[2]<=best+1e-8]
    e,c,err,rank,_=min(live,key=lambda c:(len(c[0]),-c[3],c[0]));return e,c,{'observations':sorted(obs),'trace':trace,'rank':rank,'fit_error':err,'remaining_candidates':len(live)}

def order_for(edges,radix):
    """Enumerate 24 elimination schedules; count combined factor cells, not FLOPs."""
    def cost(order):
        scopes=[{j} for j in range(4)]+[set(e) for e in edges];sizes=[]
        for j in order:
            hit=[s for s in scopes if j in s];union=set.union(*hit);sizes.append(radix**len(union));scopes=[s for s in scopes if j not in s]+[union-{j}]
        return sum(sizes),max(sizes)
    order=min(itertools.permutations(range(4)),key=lambda o:(cost(o),o));return order,cost(order)

def contract(unary,pairs,q,stop=None,order=None):
    """Factor semiring: mass and weighted additive value. Ordinary softmax, real algebra."""
    radix,dk,dv=unary.shape[1],len(q),unary.shape[-1]-len(q);n=radix**4
    if stop is None:stop=n
    if type(stop) is not int or not 1<=stop<=n:raise ValueError('prefix')
    if order is None:order=order_for(pairs,radix)[0]
    if sorted(order)!=list(range(4)):raise ValueError('order')
    terms=[];cells=0
    for box in rectangles(0,stop,radix,4):
        sizes=[b-a for a,b in box];factors=[];shift=0.
        for scope,t in [( (j,),unary[j]) for j in range(4)]+list(pairs.items()):
            data=t[tuple(slice(*box[j]) for j in scope)];s=data[...,:dk]@q/np.sqrt(dk);m=float(s.max());shift+=m;z=np.exp(s-m)
            factors.append((scope,z,z[...,None]*data[...,dk:]))
        for j in order:
            hit=[f for f in factors if j in f[0]];factors=[f for f in factors if j not in f[0]];scope=tuple(sorted(set().union(*(f[0] for f in hit))));z=1.;v=np.zeros(dv);cells+=int(np.prod([sizes[k] for k in scope]))
            for axes,a,b in hit:
                shape=tuple(sizes[k] if k in axes else 1 for k in scope);a=a.reshape(shape);b=b.reshape(shape+(dv,));v=v*a[...,None]+z[...,None]*b if isinstance(z,np.ndarray) else v*a[...,None]+z*b;z=z*a
            axis=scope.index(j);factors.append((tuple(k for k in scope if k!=j),z.sum(axis),v.sum(axis)))
        # Disconnected components leave independent scalar factors.
        z=1.;v=np.zeros(dv)
        for _,a,b in factors:v=v*a+z*b;z=z*a
        if z<=0 or not np.isfinite(z) or not np.isfinite(v).all():raise ValueError('numerical extent')
        terms.append((shift+np.log(z),v/z))
    logs=np.array([x[0] for x in terms]);w=np.exp(logs-logs.max());return (w@np.stack([x[1] for x in terms]))/w.sum(),cells

def tables(e,c):
    d=c.shape[1];u=np.zeros((4,4,d));u[:,1:]=c[1:13].reshape(4,3,d);u[0]+=c[0];p={}
    for j,edge in enumerate(e):
        a=np.zeros((4,4,d));a[1:,1:]=c[13+9*j:22+9*j].reshape(3,3,d);p[edge]=a
    return u,p

def enumerate_softmax(unary,pairs,q,stop,chunk=262144):
    radix=unary.shape[1];dk=len(q);dv=unary.shape[-1]-dk;m=-np.inf;z=0.;v=np.zeros(dv)
    # Independent streaming address evaluation with cached local scores.
    ulog=unary[...,:dk]@q/np.sqrt(dk);plog={e:a[...,:dk]@q/np.sqrt(dk) for e,a in pairs.items()}
    for lo in range(0,stop,chunk):
        ids=np.arange(lo,min(lo+chunk,stop));ds=[ids//radix**(3-j)%radix for j in range(4)];s=sum(ulog[j,d] for j,d in enumerate(ds));val=sum(unary[j,d,dk:] for j,d in enumerate(ds))
        for (i,j),p in pairs.items():s+=plog[i,j][ds[i],ds[j]];val+=p[ds[i],ds[j],dk:]
        new=max(m,float(s.max()));w=np.exp(s-new);scale=np.exp(m-new);z=z*scale+w.sum();v=v*scale+w@val;m=new
    return v/z

def campaign():
    rows=[];r=np.random.default_rng(501)
    for i in range(28):
        edge=MODELS[i%7];src=DESIGNS[edge]@r.integers(-4,5,(DESIGNS[edge].shape[1],8)) if i<21 else r.normal(size=(256,8));perm=r.permutation(256);pool=perm[:192];initial=pool[:12];held=perm[192:];row={'case':i,'family':'structured' if i<21 else 'random','edge':edge,'routes':{}}
        for mode in ('active','rank','random'):
            t=time.perf_counter_ns();e,c,trace=learn(lambda j:src[j].copy(),pool,initial,32,mode,i+700);ns=time.perf_counter_ns()-t
            if i<21:c=np.rint(c)
            pred=DESIGNS[e]@c;err=float(np.mean((pred[held]-src[held])**2));admitted=bool(np.array_equal(pred,src));out={'edge':e,'heldout_mse':err,'exact':admitted,'search_ns':ns,**trace}
            if admitted:
                u,p=tables(e,c);q=np.random.default_rng(900+i).normal(size=4);a,_=contract(u,p,q);b=enumerate_softmax(u,p,q,256);out['attention_error']=float(abs(a-b).max());assert out['attention_error']<1e-10
            row['routes'][mode]=out
        rows.append(row)
    scale=[]
    for edge in (((0,1),(1,2),(2,3)),((0,1),(1,2),(2,3),(0,3))):
        u=r.normal(size=(4,64,8))*.2;p={e:r.normal(size=(64,64,8))*.2 for e in edge};q=r.normal(size=4);order,cost=order_for(edge,64)
        for stop in (12345678,2**24):
            t=time.perf_counter_ns();a,cells=contract(u,p,q,stop,order);ns=time.perf_counter_ns()-t;t=time.perf_counter_ns();b=enumerate_softmax(u,p,q,stop);dense=time.perf_counter_ns()-t;err=float(abs(a-b).max());assert err<1e-10
            scale.append({'edges':edge,'stop':stop,'order':order,'full_order_cost':cost,'cells':cells,'contract_ns':ns,'enumeration_ns':dense,'error':err})
    return {'schema':'gsm-005-v1','rows':rows,'scale':scale}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();r=campaign();Path(a.output).write_text(json.dumps(r,indent=2)+'\n');print({m:sum(x['routes'][m]['exact'] for x in r['rows']) for m in ('active','rank','random')});print(r['scale'])
