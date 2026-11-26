from mmg002_fusion import *
import random

def pfaffian(M,p):
    n=len(M);M=[list(r) for r in M];z=1
    if n%2:return 0
    for i in range(0,n,2):
        j=next((j for j in range(i+1,n) if M[i][j]%p),None)
        if j is None:return 0
        if j!=i+1:
            M[j],M[i+1]=M[i+1],M[j]
            for r in M:r[j],r[i+1]=r[i+1],r[j]
            z=-z
        a=M[i][i+1]%p;z=z*a%p;inv=pow(a,-1,p)
        for j in range(i+2,n):
            for k in range(j+1,n):
                M[j][k]=(M[j][k]-(M[i][j]*M[i+1][k]-M[i][k]*M[i+1][j])*inv)%p
                M[k][j]=-M[j][k]
    return z%p

def direct(L,R,A,p):
    xs=[(0,m) for m in L]+[(1,m) for m in R]+[(2,m) for m in reversed(A)]
    n=len(xs);M=[[0]*n for _ in xs]
    for i,(s,m) in enumerate(xs):
        for j in range(i+1,n):
            t,b=xs[j];v=0
            if (s,t)==(0,1):v=(-1)**b*comb(m+b,m)
            elif (s,t)==(0,2):v=int(m==b)
            elif (s,t)==(1,2) and b>=m:v=comb(b,m)
            M[i][j]=v%p;M[j][i]=-v%p
    return pfaffian(M,p)

if __name__=='__main__':
    rng=random.Random(20261124); pool=[x for E in range(41) for x in wedges(E)]
    n=0;nonzero=0
    for i in range(20000):
        L,R,A=(rng.choice(pool) for _ in range(3));p=rng.choice((2,3,5,7,11));a=direct(L,R,A,p);b=coeff(L,R,A)%p
        assert a==b,(L,R,A,p,a,b)
        n+=1;nonzero+=bool(a)
    path=Path(__file__).with_name('mmg002_fusion_results.json');r=json.loads(path.read_text());r['independent_pfaffian_checks']=n;r['independent_nonzero_checks']=nonzero
    path.write_text(json.dumps(r,indent=2));print(n,nonzero)
    rows=r['results'];print('varying characteristic',sum(len(set(x['cutoffs'].values()))>1 for x in rows));print('max dimension cases', [x for x in rows if x['dim']==max(t['dim'] for t in rows)]);print('diagonal',[(x['E'],x['bound'],x['cutoffs']) for x in rows if x['E']==x['G'] and x['E']>=10]);print('strictly lower in all fields',sum(max(x['cutoffs'].values())<x['bound'] for x in rows));print('max cutoff',max(max(x['cutoffs'].values()) for x in rows))
