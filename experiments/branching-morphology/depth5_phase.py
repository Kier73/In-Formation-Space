"""BMO-006: exact depth-five canopy hull certificate via inherited hulls.

All claims about the continuum 0<cos(theta)<1 use integer polynomials,
exact algebraic arithmetic and Bernstein half-plane inequalities.
Floating point is not used in the certificate. Standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from functools import lru_cache
import json

from angle_transitions import (endpoint_polynomials, oriented_cross,
                                bernstein_homogenized, evaluate)
from depth3_phase import ALPHA
from depth4_phase import (RHO, REGIMES as PREVIOUS, signatures as previous_signatures,
                          transform_signature, rational_poly_at, interval_eval)

QUARTIC = (65, 136, -696, -288, 864)


def poly_mod_remainder(dividend, divisor, prime=17):
    """Polynomial remainder over F_p, low-degree coefficient first."""
    dividend=[int(c)%prime for c in dividend]
    divisor=[int(c)%prime for c in divisor]
    while dividend and dividend[-1]==0:dividend.pop()
    while divisor and divisor[-1]==0:divisor.pop()
    if not divisor: raise ZeroDivisionError('zero divisor')
    inv=pow(divisor[-1],-1,prime)
    while len(dividend)>=len(divisor):
        factor=dividend[-1]*inv%prime
        shift=len(dividend)-len(divisor)
        for i,c in enumerate(divisor):
            dividend[i+shift]=(dividend[i+shift]-factor*c)%prime
        while dividend and dividend[-1]==0:dividend.pop()
    return tuple(dividend)


def quartic_irreducible_mod_17():
    """Quartic with no F17 factors of degrees 1 or 2 is irreducible."""
    for a in range(17):
        if rational_poly_at(QUARTIC,a)%17==0:return False
    for a in range(17):
        for b in range(17):
            if not poly_mod_remainder(QUARTIC,(a,b,1)):return False
    return True


def isolate_quartic(bits=100):
    """Unique real root of 864c^4-288c^3-696c^2+136c+65 on [.92,.93].

    Derivative P' = 3456c^3 - 864c^2 - 1392c + 136 has positive
    interval lower bound on [23/25,93/100] by simple term monotonicity.
    """
    lo,hi=F(23,25),F(93,100)
    assert rational_poly_at(QUARTIC,lo)<0<rational_poly_at(QUARTIC,hi)
    assert 3456*lo**3-864*hi**2-1392*hi+136>0
    for _ in range(bits):
        mid=(lo+hi)/2
        v=rational_poly_at(QUARTIC,mid)
        if v<0:lo=mid
        elif v>0:hi=mid
        else:raise ArithmeticError('unexpected rational root')
    return lo,hi


@lru_cache(maxsize=16)
def quartic_bracket(bits):
    return isolate_quartic(bits)


def reduce_quartic(coefficients):
    out=list(map(F,coefficients))
    while len(out)>4:
        top=out.pop()
        i=len(out)-4
        # c^4 = (-65 -136c +696c^2 +288c^3)/864.
        for j,value in enumerate((-65,-136,696,288)):
            out[i+j]+=top*F(value,864)
    return tuple(out+[F(0)]*(4-len(out)))


@lru_cache(maxsize=200000)
def quartic_sign(coefficients):
    if not any(coefficients):return 0
    if not any(coefficients[1:]):
        x=coefficients[0];return (x>0)-(x<0)
    # The minimal polynomial is irreducible over Q (irreducible mod 17).
    # Therefore any reduced nonzero polynomial has nonzero evaluation.
    for bits in (80,120,180,260,360):
        lo,hi=quartic_bracket(bits)
        lb,ub=interval_eval(coefficients,lo,hi)
        if lb>0:return 1
        if ub<0:return -1
    raise ArithmeticError('quartic root sign could not be separated')


@dataclass(frozen=True)
class QuarticRoot:
    """Exact element of Q(sigma), with sigma the isolated quartic root."""
    coefficients: tuple[F,...]

    def __post_init__(self):
        object.__setattr__(self,'coefficients',reduce_quartic(self.coefficients))

    @classmethod
    def coerce(cls,value):
        return value if isinstance(value,cls) else cls((F(value),))

    def __add__(self,value):
        other=self.coerce(value)
        return QuarticRoot(tuple(a+b for a,b in zip(self.coefficients,other.coefficients)))
    __radd__=__add__
    def __neg__(self):return QuarticRoot(tuple(-v for v in self.coefficients))
    def __sub__(self,value):return self+-self.coerce(value)
    def __rsub__(self,value):return self.coerce(value)-self
    def __mul__(self,value):
        other=self.coerce(value)
        product=[F(0)]*7
        for i,a in enumerate(self.coefficients):
            for j,b in enumerate(other.coefficients):product[i+j]+=a*b
        return QuarticRoot(tuple(product))
    __rmul__=__mul__
    def __pow__(self,n):
        if not isinstance(n,int) or n<0:raise ValueError('nonnegative integer exponent required')
        acc=self.coerce(1);base=self
        while n:
            if n&1:acc=acc*base
            base=base*base;n>>=1
        return acc
    def sign(self):return quartic_sign(self.coefficients)
    def __eq__(self,value):
        try:return self.coefficients==self.coerce(value).coefficients
        except (TypeError,ValueError):return NotImplemented
    def __lt__(self,value):return (self-self.coerce(value)).sign()<0
    def __le__(self,value):return (self-self.coerce(value)).sign()<=0
    def __gt__(self,value):return (self-self.coerce(value)).sign()>0
    def __ge__(self,value):return (self-self.coerce(value)).sign()>=0
    def __str__(self):
        return ' + '.join(f'({a})*sigma^{i}' for i,a in enumerate(self.coefficients) if a) or '0'

SIGMA=QuarticRoot((F(0),F(1)))
BRIDGE=F(23,25)

# Convex hull regimes ordered by increasing cosine / decreasing turn angle.
# A rational break at 23/25 separates prior cubic and new quartic fields;
# it is not a geometric transition.
REGIMES=(
    ('broad',F(0),F(1,4),(2500,3125,1250,0),0),
    ('middle',F(1,4),F(1,2),(2500,3125,1250,0,2375),1),
    ('narrow',F(1,2),ALPHA,(2375,2500,3125,1250,875,0),2),
    ('seven_left',ALPHA,F(3,4),(2375,2500,3125,1250,875,0,2350),3),
    ('seven_right',F(3,4),RHO,(2375,2500,3125,1250,875,0,2350),4),
    ('eight_left',RHO,BRIDGE,(2350,2375,2500,3125,1250,875,0,2345),5),
    ('eight_right',BRIDGE,SIGMA,(2350,2375,2500,3125,1250,875,0,2345),5),
    ('nine',SIGMA,F(1),(2345,2350,2375,2500,3125,1250,875,0,2344),5),
)


def signatures(depth=5):
    if isinstance(depth,bool) or not isinstance(depth,int) or not 0<=depth<=5:
        raise ValueError('depth must be integer between 0 and 5')
    word='F'
    for _ in range(depth):word=''.join('F[+F]F[-F]F' if c=='F' else c for c in word)
    heading=0;counts={};stack=[];observed={():None}
    for c in word:
        if c=='F':
            counts[heading]=counts.get(heading,0)+1
            observed[tuple(sorted(counts.items()))]=None
        elif c=='+':heading+=1
        elif c=='-':heading-=1
        elif c=='[':stack.append((heading,counts.copy()))
        elif c==']':
            if not stack:raise ValueError('unmatched bracket')
            heading,counts=stack.pop()
        else:raise ValueError('invalid grammar token')
    assert not stack and heading==0
    return tuple(observed)


def recursive_candidates(stage,current):
    """Five transformed images of PREVIOUS *certified* hull corners."""
    old=previous_signatures(4)
    lookup={signature:i for i,signature in enumerate(current)}
    corners=PREVIOUS[stage][3]
    copies=((0,0),(1,81),(0,81),(-1,162),(0,162))
    return tuple(sorted({lookup[transform_signature(old[i],turn,up)]
                         for i in corners for turn,up in copies}))


def hull(points,indices,cosine):
    """Independent exact convex hull of selected symbolic endpoints."""
    coordinates={}
    for i in indices:
        xp,yp=points[i]
        coordinates.setdefault((evaluate(xp,cosine),evaluate(yp,cosine)),i)
    ordered=sorted((coord,i) for coord,i in coordinates.items())
    def cross(a,b,p):
        (ax,ay),(bx,by),(px,py)=a[0],b[0],p[0]
        return (bx-ax)*(py-ay)-(by-ay)*(px-ax)
    lower=[];upper=[]
    for vertex in ordered:
        while len(lower)>1 and cross(lower[-2],lower[-1],vertex)<=0:lower.pop()
        lower.append(vertex)
    for vertex in reversed(ordered):
        while len(upper)>1 and cross(upper[-2],upper[-1],vertex)<=0:upper.pop()
        upper.append(vertex)
    return tuple(v[1] for v in lower[:-1]+upper[:-1])


def interval_certificate(points,name,lo,hi,corners,candidates):
    """Exact polynomial half-plane containment throughout [lo,hi]."""
    assert lo<hi
    for j in range(len(corners)):
        triple=(points[corners[(j+k)%len(corners)]] for k in range(3))
        coeff=bernstein_homogenized(oriented_cross(*triple),lo,hi)
        if not (all(x>=0 for x in coeff) and any(x>0 for x in coeff)):
            raise AssertionError((name,'convexity',j,coeff))
    for i,j in zip(corners,corners[1:]+corners[:1]):
        for k in candidates:
            coeff=bernstein_homogenized(oriented_cross(points[i],points[j],points[k]),lo,hi)
            if not all(x>=0 for x in coeff):
                raise AssertionError((name,'containment',i,j,k,coeff))
    return len(corners)*len(candidates)


def certificate():
    labels=signatures(5)
    assert len(labels)==3126
    points=tuple(map(endpoint_polynomials,labels))
    assert quartic_irreducible_mod_17()
    result=[];checks=0
    for name,lo,hi,corners,stage in REGIMES:
        candidates=recursive_candidates(stage,labels)
        assert set(corners).issubset(candidates),(name,'missing predicted corner')
        n=interval_certificate(points,name,lo,hi,corners,candidates)
        checks+=n
        mid=(lo+hi)*F(1,2)
        observed=hull(points,candidates,mid)
        assert set(observed)==set(corners),(name,observed,corners)
        result.append({'regime':name,'cosine_low':str(lo),'cosine_high':str(hi),
                       'hull_vertices':len(corners),'corner_ids_ccw':list(corners),
                       'recursion_candidates':len(candidates),'checked_halfplanes':n})

    # Boundary points are certified by the closed-interval containment
    # and exact collinearity, not by a floating-point hull approximation.
    # Independently compute exact hulls of the recursively sufficient set.
    boundaries=((F(1,4),0,4),(F(1,2),1,5),(ALPHA,2,6),
                (RHO,4,7),(SIGMA,5,8))
    records=[]
    for c,stage,expected_count in boundaries:
        candidates=recursive_candidates(stage,labels)
        observed=hull(points,candidates,c)
        assert len(observed)==expected_count,(str(c),observed,expected_count)
        records.append({'cosine':str(c),'hull_vertices':len(observed),
                        'hull_corners':list(observed)})
    new_cross=oriented_cross(points[0],points[2344],points[2345])
    assert new_cross==tuple(3*x for x in QUARTIC)
    assert evaluate(new_cross,SIGMA)==0
    assert checks==1659,checks
    return {'experiment':'BMO-006','depth':5,'drawn_segments':3125,
            'symbolic_endpoints':3126,'angle_domain':'0 < theta < 90 degrees',
            'new_transition_cosine':'sigma in (23/25, 93/100), root of quartic',
            'quartic_polynomial':list(QUARTIC),
            'irreducible_mod_prime':17,
            'new_transition_orientation_polynomial':list(new_cross),
            'continuous_regimes':result,'exact_boundaries':records,
            'certified_halfplane_checks':checks,
            'strict_convexity_checks':sum(len(r[3]) for r in REGIMES),
            'naive_all_endpoints_checks':3126*sum(len(r[3]) for r in REGIMES),
            'scope':'convex hull only; no claim about internal crossings or all depths'}

if __name__=='__main__':print(json.dumps(certificate(),indent=2))
