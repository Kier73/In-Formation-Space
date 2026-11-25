from mmg002_fusion import *
from sympy import Matrix,eye
from sympy.matrices.normalforms import hermite_normal_form

def integral_cutoff(E,G):
    pairs=[(A,B) for A in wedges(E) for B in wedges(G)];d=len(pairs);HNF=Matrix.zeros(d,0);rows=0
    for H in range((E-G)%2,cutoff_bound(E,G)+1,2):
        vs=[[coeff(L,B,A) for A,B in pairs] for L in wedges(H)];rows+=len(vs)
        if vs:HNF=hermite_normal_form(HNF.row_join(Matrix(vs).T))
        if HNF==eye(d):return dict(E=E,G=G,dim=d,integral_cutoff=H,bound=cutoff_bound(E,G),rows=rows)
    return dict(E=E,G=G,dim=d,integral_cutoff=None,bound=cutoff_bound(E,G),rows=rows)
if __name__=='__main__':
    start=time.perf_counter();r=[]
    for E,G in [(10,10),(12,12),(12,11),(14,14)]:
        x=integral_cutoff(E,G);r.append(x);print(x,flush=True)
    path=Path(__file__).with_name('mmg002_fusion_results.json');data=json.loads(path.read_text());data['integral_cases']=r;data['integral_seconds']=time.perf_counter()-start;path.write_text(json.dumps(data,indent=2))
