"""Stronger enumeration control: reuse axis logits, enumerate all addresses."""
import json,time
import numpy as np
from address_attention import fixture


def campaign():
    r=np.random.default_rng(1927);g=fixture(64);q=r.normal(size=g.dk);rows=[]
    for stop in (1,65537,12345678,16777216):
        t=time.perf_counter_ns();a,w=g.query(q,stop);ground_ns=time.perf_counter_ns()-t
        t=time.perf_counter_ns();logits=g.k@q/np.sqrt(g.dk);num=np.zeros(g.dv);mass=0.;m=-np.inf
        for start in range(0,stop,262144):
            end=min(start+262144,stop);ids=np.arange(start,end,dtype=np.int64);s=np.zeros(len(ids));v=np.zeros((len(ids),g.dv));p=np.ones_like(v)
            for j in range(g.depth):
                digit=(ids//g.radix**(g.depth-j-1))%g.radix
                s+=logits[j,digit];v+=g.v[j,digit];p*=g.p[j,digit]
            v+=p
            for addr,(key,val) in g.overrides.items():
                if start<=addr<end:s[addr-start]=key@q/np.sqrt(g.dk);v[addr-start]=val
            new=max(m,float(s.max()));weights=np.exp(s-new);scale=np.exp(m-new);num=num*scale+weights@v;mass=mass*scale+weights.sum();m=new
        b=num/mass;ns=time.perf_counter_ns()-t;err=float(abs(a-b).max());assert err<1e-10
        rows.append(dict(stop=stop,ground_ns=ground_ns,enumerated_axis_ns=ns,error=err,work=w))
    return rows

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();open(a.output,'w').write(json.dumps(campaign(),indent=2)+'\n')
