"""Optional check of the user-supplied matching Seed (not distributed here).
No numerical fitting is used. Pass the exact external Python source path.
"""
import argparse,json,random
from importlib.util import spec_from_file_location,module_from_spec

def run(path):
    spec=spec_from_file_location('external_seed',path);m=module_from_spec(spec);spec.loader.exec_module(m)
    rng=random.Random(3232);out=[]
    for n in (6,8,10):
        c=m.Ctx(n);pool=m.crossing_pairs(n);checks=0
        for k in (1,3,5,10):
            for _ in range(3):
                F=rng.sample(pool,min(k,len(pool)));co=m.defect_expansion(c,F)
                for M in c.P:
                    M=frozenset(M);expect=(-1)**sum(e in M and f in M for e,f in F)
                    assert sum(v for U,v in co.items() if U<=M)==expect;checks+=1
        out.append(dict(n=n,matching_coefficient_checks=checks))
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--output',default='CIG-032A-external-check.json');a=p.parse_args();out=run(a.source);open(a.output,'w').write(json.dumps(out,indent=2)+'\n');print(out)
