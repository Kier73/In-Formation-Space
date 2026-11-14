"""BMO-008: exact depth-six hull classification with inherited hull candidates.

The turning-angle domain is 0 < theta < 90 degrees, c=cos(theta).
Finite interval certificates use exact rational, quadratic, cubic, quartic,
and quintic arithmetic. Floating point never certifies an interval.
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction as F
from functools import lru_cache
import json
from angle_transitions import endpoint_polynomials, oriented_cross, bernstein_homogenized, evaluate
from depth3_phase import ALPHA
from depth4_phase import RHO, transform_signature, interval_eval, rational_poly_at
from depth5_phase import SIGMA, REGIMES as PREVIOUS, signatures as previous_signatures, poly_mod_remainder
from all_depth_law import new_corner_polynomial

QUINTIC = (-97, 1108, 1248, -5472, -1728, 5184)


def quintic_irreducible_mod_7():
    """A degree-five polynomial with no F7 linear or quadratic factor is irreducible."""
    if any(rational_poly_at(QUINTIC,a)%7==0 for a in range(7)):
        return False
    return all(poly_mod_remainder(QUINTIC,(a,b,1),7)
               for a in range(7) for b in range(7))


def isolate_quintic(bits=120):
    """Unique root lambda in [951/1000,952/1000] by a strict derivative bound."""
    if isinstance(bits,bool) or not isinstance(bits,int) or bits<=0:
        raise ValueError('bits must be a positive integer')
    lo,hi=F(951,1000),F(952,1000)
    assert rational_poly_at(QUINTIC,lo)<0<rational_poly_at(QUINTIC,hi)
    assert 1108+2496*lo-16416*hi**2-6912*hi**3+25920*lo**4>0
    for _ in range(bits):
        mid=(lo+hi)/2
        value=rational_poly_at(QUINTIC,mid)
        if value<0:lo=mid
        elif value>0:hi=mid
        else:raise ArithmeticError('unexpected rational quintic root')
    return lo,hi


@lru_cache(maxsize=24)
def quintic_bracket(bits):
    return isolate_quintic(bits)


def reduce_quintic(coeffs):
    result=list(map(F,coeffs))
    while len(result)>5:
        last=result.pop()
        k=len(result)-5
        for j,a in enumerate((97,-1108,-1248,5472,1728)):
            result[k+j]+=last*F(a,5184)
    return tuple(result+[F(0)]*(5-len(result)))


@lru_cache(maxsize=120000)
def quintic_sign(coefficients):
    if not any(coefficients):return 0
    if not any(coefficients[1:]):
        x=coefficients[0]
        return (x>0)-(x<0)
    # Mod-7 irreducibility ensures every nonzero reduced polynomial
    # is nonzero at lambda; rational isolation eventually separates its sign.
    for bits in (80,120,180,260,400):
        lo,hi=quintic_bracket(bits)
        a,b=interval_eval(coefficients,lo,hi)
        if a>0:return 1
        if b<0:return -1
    raise ArithmeticError('quintic sign undecidable at configured precision')


@dataclass(frozen=True)
class QuinticRoot:
    """Exact elements of Q(lambda), modulo the irreducible quintic."""
    coefficients: tuple[F,...]

    def __post_init__(self):
        object.__setattr__(self,'coefficients',reduce_quintic(self.coefficients))

    @classmethod
    def coerce(cls,other):
        return other if isinstance(other,cls) else cls((F(other),))

    def __add__(self,other):
        other=self.coerce(other)
        return QuinticRoot(tuple(a+b for a,b in zip(self.coefficients,other.coefficients)))
    __radd__=__add__
    def __neg__(self):return QuinticRoot(tuple(-x for x in self.coefficients))
    def __sub__(self,other):return self+-self.coerce(other)
    def __rsub__(self,other):return self.coerce(other)-self
    def __mul__(self,other):
        other=self.coerce(other)
        result=[F(0)]*9
        for i,a in enumerate(self.coefficients):
            for j,b in enumerate(other.coefficients):result[i+j]+=a*b
        return QuinticRoot(tuple(result))
    __rmul__=__mul__
    def __pow__(self,n):
        if isinstance(n,bool) or not isinstance(n,int) or n<0:
            raise ValueError('nonnegative integer exponent required')
        acc=self.coerce(1);base=self
        while n:
            if n&1:acc=acc*base
            base=base*base;n>>=1
        return acc
    def sign(self):return quintic_sign(self.coefficients)
    def __eq__(self,other):
        try:return self.coefficients==self.coerce(other).coefficients
        except (TypeError,ValueError):return NotImplemented
    def __lt__(self,other):return (self-self.coerce(other)).sign()<0
    def __le__(self,other):return (self-self.coerce(other)).sign()<=0
    def __gt__(self,other):return (self-self.coerce(other)).sign()>0
    def __ge__(self,other):return (self-self.coerce(other)).sign()>=0
    def __str__(self):
        return ' + '.join(f'({a})*lambda^{i}' for i,a in enumerate(self.coefficients) if a) or '0'


LAMBDA=QuinticRoot((F(0),F(1)))
BRIDGE=F(93,100) # Avoid mixing quartic sigma with quintic lambda.
# Exact CCW extreme point indices in the depth-six grammar.
REGIMES=(
    ('four',F(0),F(1,4),tuple(5*i for i in PREVIOUS[0][3]),0),
    ('five',F(1,4),F(1,2),tuple(5*i for i in PREVIOUS[1][3]),1),
    ('six',F(1,2),ALPHA,tuple(5*i for i in PREVIOUS[2][3]),2),
    ('seven_a',ALPHA,F(3,4),tuple(5*i for i in PREVIOUS[3][3]),3),
    ('seven_b',F(3,4),RHO,tuple(5*i for i in PREVIOUS[4][3]),4),
    ('eight_a',RHO,F(23,25),tuple(5*i for i in PREVIOUS[5][3]),5),
    ('eight_b',F(23,25),SIGMA,tuple(5*i for i in PREVIOUS[6][3]),6),
    ('nine_a',SIGMA,BRIDGE,tuple(5*i for i in PREVIOUS[7][3]),7),
    ('nine_b',BRIDGE,LAMBDA,tuple(5*i for i in PREVIOUS[7][3]),7),
    ('ten',LAMBDA,F(1),(11719,11720,11725,11750,11875,12500,15625,6250,4375,0),7),
)


def signatures(depth=6):
    if isinstance(depth,bool) or not isinstance(depth,int) or not 0<=depth<=6:
        raise ValueError('depth must be integer from 0 to 6')
    word='F'
    for _ in range(depth):word=''.join('F[+F]F[-F]F' if c=='F' else c for c in word)
    heading=0;counts={};stack=[];unique={():None}
    for char in word:
        if char=='F':
            counts[heading]=counts.get(heading,0)+1
            unique[tuple(sorted(counts.items()))]=None
        elif char=='+':heading+=1
        elif char=='-':heading-=1
        elif char=='[':stack.append((heading,counts.copy()))
        elif char==']':
            if not stack:raise ValueError('unbalanced bracket')
            heading,counts=stack.pop()
        else:raise ValueError('unknown token')
    assert not stack and heading==0
    return tuple(unique)


def inherited_candidates(stage,current):
    """Take five affine images of the preceding, certified hull vertices."""
    old=previous_signatures(5)
    lookup={signature:i for i,signature in enumerate(current)}
    offsets=((0,0),(1,243),(0,243),(-1,486),(0,486))
    return tuple(sorted({lookup[transform_signature(old[i],turn,vertical)]
                         for i in PREVIOUS[stage][3] for turn,vertical in offsets}))


def exact_hull(points,indices,cosine):
    """Independent exact rational/algebraic monotone-chain convex hull."""
    xy={}
    for i in indices:
        xp,yp=points[i]
        xy.setdefault((evaluate(xp,cosine),evaluate(yp,cosine)),i)
    ordered=sorted((p,i) for p,i in xy.items())
    def cross(a,b,p):
        (ax,ay),(bx,by),(px,py)=a[0],b[0],p[0]
        return (bx-ax)*(py-ay)-(by-ay)*(px-ax)
    lower=[];upper=[]
    for p in ordered:
        while len(lower)>1 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
        lower.append(p)
    for p in reversed(ordered):
        while len(upper)>1 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
        upper.append(p)
    return tuple(v[1] for v in lower[:-1]+upper[:-1])


def certify_interval(points,name,lo,hi,corners,candidates):
    assert lo<hi
    for j in range(len(corners)):
        triple=(points[corners[(j+k)%len(corners)]] for k in range(3))
        coeff=bernstein_homogenized(oriented_cross(*triple),lo,hi)
        if not all(v>=0 for v in coeff) or not any(v>0 for v in coeff):
            raise AssertionError(('not strictly convex',name,j,coeff))
    for a,b in zip(corners,corners[1:]+corners[:1]):
        for i in candidates:
            coeff=bernstein_homogenized(oriented_cross(points[a],points[b],points[i]),lo,hi)
            if not all(v>=0 for v in coeff):
                raise AssertionError(('not containing',name,a,b,i,coeff))
    return len(corners)*len(candidates)


def certificate(*,verify_previous=False):
    if verify_previous:
        from depth5_phase import certificate as prior
        prior()
    labels=signatures(6)
    assert len(labels)==15626
    points=tuple(map(endpoint_polynomials,labels))
    assert quintic_irreducible_mod_7()
    checks=0;record=[];corner_checks=0;inherited_identities=0
    for name,lo,hi,corners,stage in REGIMES:
        candidates=inherited_candidates(stage,labels)
        assert set(corners).issubset(candidates)
        if name != 'ten':
            old_corners=PREVIOUS[stage][3]
            assert corners==tuple(5*i for i in old_corners)
            for i in old_corners:
                old_point=endpoint_polynomials(previous_signatures(5)[i])
                new_point=points[5*i]
                assert new_point==tuple(tuple(3*a for a in p) for p in old_point)
                inherited_identities+=1
        n=certify_interval(points,name,lo,hi,corners,candidates)
        mid=(lo+hi)*F(1,2)
        assert set(exact_hull(points,candidates,mid))==set(corners),(name,'wrong midpoint hull')
        checks+=n;corner_checks+=len(corners)
        record.append({'regime':name,'cosine_low':str(lo),'cosine_high':str(hi),
                       'vertices':len(corners),'corner_ids':list(corners),
                       'inherited_candidates':len(candidates),'halfplane_checks':n})
    boundary_values=((F(1,4),0,4),(F(1,2),1,5),(ALPHA,2,6),
                     (RHO,4,7),(SIGMA,6,8),(LAMBDA,7,9))
    boundary=[]
    for c,stage,n in boundary_values:
        h=exact_hull(points,inherited_candidates(stage,labels),c)
        assert len(h)==n,(str(c),h,n)
        boundary.append({'cosine':str(c),'vertices':n,'corner_ids':list(h)})
    tip=(0,11719,11720)
    polynomial=oriented_cross(*(points[i] for i in tip))
    assert polynomial==tuple(3*x for x in QUINTIC)
    assert evaluate(polynomial,LAMBDA)==0
    # The new tip lies strictly outside the edge 0->11720 of 3*H5
    # whenever lambda<c<1. This witnesses persistent departure at later depths.
    witness=bernstein_homogenized(polynomial,LAMBDA,F(1))
    assert [v.sign() for v in witness]==[0,1,1,1,1,1]
    assert checks==2483 and corner_checks==73
    return {'experiment':'BMO-008','depth':6,'drawn_segments':15625,
            'symbolic_endpoints':len(labels),'angle_domain_degrees':'0 < theta < 90',
            'new_transition_cosine':'lambda; unique root of quintic in (951/1000,952/1000)',
            'minimal_quintic_coefficients_ascending':list(QUINTIC),
            'irreducibility_prime':7,'exact_tip_cross_polynomial':list(polynomial),
            'regimes':record,'boundaries':boundary,
            'exact_containment_checks':checks,'exact_corner_checks':corner_checks,
            'inherited_hull_regimes':9,
            'inherited_vertex_polynomial_identifications':inherited_identities,
            'outside_tip_witness_bernstein_signs':[v.sign() for v in witness],
            'all_future_depths':{
                'for_n_at_least_6':'H_n=3**(n-5)*H_5 for 0<c<=lambda',
                'for_c_greater_than_lambda':'H_n strictly contains 3**(n-5)*H_5'
            },
            'naive_full_endpoint_checks':len(labels)*corner_checks,
            'notes':'Outer convex hull at depth 6; no internal intersection or universal n-transition classification.'}


if __name__=='__main__':
    print(json.dumps(certificate(),indent=2))
