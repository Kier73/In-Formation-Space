"""Exact finite-field probes of the Nov 24 manuscript's fusion-width lemma.
Energy indices are doubled. Matrix columns are all ordered basis pairs (A,B).
No floating point used in span verification or cutoff comparison.
"""
from functools import lru_cache
from math import comb,isqrt
import json,time
from pathlib import Path

@lru_cache(None)
def wedges(E,m=0):
    if E==0:return ((),)
    if E<2*m+1:return ()
    return wedges(E,m+1)+tuple((m,)+x for x in wedges(E-2*m-1,m+1))

@lru_cache(maxsize=300000)
def coeff(L,R,A):
    # first left fermion either survives as an output creation or contracts
    if not L:
        if len(R)!=len(A):return 0
        if not R:return 1
        b=R[0]
        return sum((-1)**i*comb(a,b)*coeff((),R[1:],A[:i]+A[i+1:]) for i,a in enumerate(A) if a>=b)
    if len(A)>len(L)+len(R) or (len(L)+len(R)-len(A))%2:return 0
    m=L[0]; z=0
    if m in A:
        i=A.index(m);z+=(-1)**i*coeff(L[1:],R,A[:i]+A[i+1:])
    for j,b in enumerate(R):
        z+=(-1)**(len(L)-1+j+b)*comb(m+b,m)*coeff(L[1:],R[:j]+R[j+1:],A)
    return z

def add_row(row,basis,p):
    for k,x in enumerate(row):
        if not x:continue
        if k not in basis:
            z=pow(x,-1,p);basis[k]=[(v*z)%p for v in row];return True
        a=basis[k]
        for i in range(k,len(row)):row[i]=(row[i]-x*a[i])%p
    return False

def cutoff_bound(E,G):
    # 2H=E+G+2sqrt(EG)+sqrt(E)+sqrt(G), conservative integer exact
    # integer sqrt via rational fixed point upper and lower; only use floor in easy cases
    from decimal import Decimal,localcontext
    with localcontext() as c:
        c.prec=70
        return int(Decimal(E+G)+2*Decimal(E*G).sqrt()+Decimal(E).sqrt()+Decimal(G).sqrt()+Decimal('1e-60'))

def run(max_energy=15,primes=(2,3,5,7,11)):
    start=time.perf_counter();rows=[]; evaluations=0; rowcount=0
    for E in range(max_energy+1):
        if not wedges(E):continue
        for G in range(max_energy+1):
            if not wedges(G):continue
            pairs=[(A,B) for A in wedges(E) for B in wedges(G)];d=len(pairs);limit=cutoff_bound(E,G)
            basis={p:{} for p in primes};finish={};used=0
            for H in range((E-G)%2,limit+1,2):
                for L in wedges(H):
                    vals=[coeff(L,B,A) for A,B in pairs];evaluations+=d;rowcount+=1;used+=1
                    for p in primes:
                        if p in finish:continue
                        if add_row([v%p for v in vals],basis[p],p) and len(basis[p])==d:finish[p]=H
                    if len(finish)==len(primes):break
                if len(finish)==len(primes):break
            rows.append(dict(E=E,G=G,dim=d,bound=limit,cutoffs={str(p):finish.get(p) for p in primes},ranks={str(p):len(basis[p]) for p in primes},rows=used))
    result=dict(max_doubled_energy=max_energy,primes=primes,cases=len(rows),coefficient_evaluations=evaluations,rows=rowcount,seconds=time.perf_counter()-start,results=rows)
    return result

if __name__=='__main__':
    import sys
    r=run(int(sys.argv[1]) if len(sys.argv)>1 else 15)
    out=Path(__file__).with_name('mmg002_fusion_results.json');out.write_text(json.dumps(r,indent=2))
    rs=r['results'];print({k:v for k,v in r.items() if k!='results'})
    print('failed',[(x['E'],x['G'],x['cutoffs']) for x in rs if None in x['cutoffs'].values()]);print('characteristic discrepancies',[(x['E'],x['G'],x['cutoffs']) for x in rs if len(set(x['cutoffs'].values()))>1][:30]);print('max dimension',max(x['dim'] for x in rs)); print('max gap',sorted(rs,key=lambda x:x['bound']-max(v or 0 for v in x['cutoffs'].values()),reverse=True)[:5]);print('min gap',sorted(rs,key=lambda x:x['bound']-max(v or 0 for v in x['cutoffs'].values()))[:5])
