"""24-bit address-factorized softmax: explicitly structured K/V, not arbitrary KV."""
import numpy as np
import hashlib, json, time
from statistics import median


def rectangles(lo, hi, radix=64, depth=4):
    """Disjoint Cartesian boxes covering exactly the half-open address interval."""
    if type(lo) is not int or type(hi) is not int or not 0 <= lo <= hi <= radix**depth:
        raise ValueError('address interval')
    def walk(start, level, fixed):
        size=radix**(depth-level)
        if hi<=start or lo>=start+size:return
        if lo<=start and start+size<=hi:
            yield fixed+((0,radix),)*(depth-level);return
        step=size//radix
        first=max(0,(lo-start)//step);last=min(radix,(hi-start+step-1)//step)
        a=max(first,(lo-start+step-1)//step);b=min(last,(hi-start)//step)
        if first<a:
            yield from walk(start+first*step,level+1,fixed+((first,first+1),))
        if a<b:yield fixed+((a,b),)+((0,radix),)*(depth-level-1)
        if b<last and last-1>=a:
            yield from walk(start+(last-1)*step,level+1,fixed+((last-1,last),))
    if lo<hi:yield from walk(0,0,())


class Ground:
    """K(a)=sum K_j[a_j]; V(a)=sum V_j[a_j]+prod P_j[a_j] (componentwise)."""
    def __init__(self,k,v,p,overrides=None):
        self.k,self.v,self.p=(np.array(x,dtype='<f8',copy=True) for x in (k,v,p))
        if self.k.ndim!=3 or self.v.ndim!=3 or self.p.shape!=self.v.shape or self.k.shape[:2]!=self.v.shape[:2]:raise ValueError('shape')
        self.depth,self.radix,self.dk=self.k.shape;self.dv=self.v.shape[2];self.n=self.radix**self.depth
        if min(self.depth,self.radix,self.dk,self.dv)<1 or self.radix<2 or self.n>2**24:raise ValueError('extent')
        self.overrides={}
        for a,(key,value) in (overrides or {}).items():
            if type(a) is not int or not 0<=a<self.n:raise ValueError('override address')
            key,value=np.array(key,dtype='<f8',copy=True),np.array(value,dtype='<f8',copy=True)
            if key.shape!=(self.dk,) or value.shape!=(self.dv,):raise ValueError('override shape')
            self.overrides[a]=(key,value)
        arrays=[self.k,self.v,self.p]+[x for a in sorted(self.overrides) for x in self.overrides[a]]
        if not all(np.isfinite(x).all() for x in arrays):raise ValueError('nonfinite')
        for x in arrays:x.flags.writeable=False
        h=hashlib.sha256(json.dumps(['address-softmax-v1',list(self.k.shape),list(self.v.shape),sorted(self.overrides)]).encode())
        for x in arrays:h.update(x.tobytes())
        self.identity=h.hexdigest()
        self.payload_bytes=sum(x.nbytes for x in arrays)+4*len(self.overrides)

    def query(self,q,stop):
        q=np.asarray(q,dtype=np.float64)
        if q.shape!=(self.dk,) or not np.isfinite(q).all() or type(stop) is not int or not 1<=stop<=self.n:raise ValueError('query')
        logits=self.k@q/np.sqrt(self.dk);terms=[];cache={};boxes=0
        def axis(j,a,b):
            tag=j,a,b
            if tag not in cache:
                s=logits[j,a:b];m=s.max();w=np.exp(s-m);z=w.sum();w/=z
                cache[tag]=(float(m+np.log(z)),w@self.v[j,a:b],w@self.p[j,a:b])
            return cache[tag]
        def interval(lo,hi):
            nonlocal boxes
            for box in rectangles(lo,hi,self.radix,self.depth):
                fields=[axis(j,a,b) for j,(a,b) in enumerate(box)];boxes+=1
                terms.append((sum(t[0] for t in fields),np.sum([t[1] for t in fields],axis=0)+np.prod([t[2] for t in fields],axis=0)))
        lo=0;patched=0
        for addr,(key,value) in sorted(self.overrides.items()):
            if addr>=stop:break
            interval(lo,addr);terms.append((float(key@q/np.sqrt(self.dk)),value));lo=addr+1;patched+=1
        interval(lo,stop)
        masses=np.array([t[0] for t in terms]);w=np.exp(masses-masses.max());w/=w.sum()
        return w@np.stack([t[1] for t in terms]),{'boxes':boxes,'overrides':patched,'axis_summaries':len(cache),'base_key_scores':self.depth*self.radix,'logical_addresses':stop}

    def dense(self,q,stop,chunk=262144):
        """Independent address-by-address reconstruction, stable streaming softmax."""
        m=-np.inf;z=0.;num=np.zeros(self.dv);q=np.asarray(q)
        for start in range(0,stop,chunk):
            end=min(start+chunk,stop);ids=np.arange(start,end,dtype=np.int64)
            k=np.zeros((len(ids),self.dk));v=np.zeros((len(ids),self.dv));p=np.ones_like(v)
            for j in range(self.depth):
                digit=(ids//self.radix**(self.depth-j-1))%self.radix
                k+=self.k[j,digit];v+=self.v[j,digit];p*=self.p[j,digit]
            v+=p
            for a,(key,val) in self.overrides.items():
                if start<=a<end:k[a-start]=key;v[a-start]=val
            s=k@q/np.sqrt(self.dk);new=max(m,float(s.max()));w=np.exp(s-new);scale=np.exp(m-new);num=num*scale+w@v;z=z*scale+w.sum();m=new
        return num/z


def fixture(radix=64,depth=4,seed=127,patches=16):
    r=np.random.default_rng(seed);k=r.normal(size=(depth,radix,8));v=r.normal(size=(depth,radix,4));p=r.uniform(-1,1,size=v.shape)
    addresses=r.choice(radix**depth,size=min(patches,radix**depth),replace=False)
    return Ground(k,v,p,{int(a):(r.normal(size=8),r.normal(size=4)) for a in addresses})


def campaign():
    rows=[];r=np.random.default_rng(128)
    for radix in (8,16,32,64):
        g=fixture(radix);q=r.normal(size=8);stop=g.n
        samples=[]
        for _ in range(11):
            t=time.perf_counter_ns();a,work=g.query(q,stop);samples.append(time.perf_counter_ns()-t)
        t=time.perf_counter_ns();b=g.dense(q,stop);elapsed=time.perf_counter_ns()-t
        error=float(np.max(np.abs(a-b)));assert error<1e-10
        rows.append({'radix':radix,'n':stop,'dense_ns':elapsed,'ground_median_ns':int(median(samples)),'ground_samples_ns':samples,'error':error,'dense_kv_bytes':stop*(g.dk+g.dv)*8,'ground_payload_bytes':g.payload_bytes,'work':work,'identity':g.identity})
        print(rows[-1],flush=True)
    return rows

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();open(a.output,'w').write(json.dumps(campaign(),indent=2)+'\n')
