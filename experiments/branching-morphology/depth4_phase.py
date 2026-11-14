"""BMO-005: continuous, exact convex-hull certificate at grammar depth four.

Exact endpoint polynomials and interval positivity; rational, quadratic and
cubic algebraic endpoints. No floating-point calculation is used for proof.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from angle_transitions import endpoint_polynomials, oriented_cross, bernstein_homogenized, evaluate
from depth3_phase import ALPHA, REGIMES as PREVIOUS_REGIMES, endpoint_signatures as previous_signatures

F = Fraction
CUBIC = (11, -80, -48, 144)  # f(t) = 144t^3 -48t^2 -80t +11


def rational_poly_at(coeffs, x):
    y=F(0)
    for a in reversed(coeffs):y=y*x+a
    return y


def isolate_cubic(bits=100):
    """Rational isolating interval: unique root of f on (87/100,88/100).

    f' = 432t²-96t-80 is strictly positive on the input interval.
    """
    lo,hi=F(87,100),F(88,100)
    assert rational_poly_at(CUBIC,lo)<0<rational_poly_at(CUBIC,hi)
    assert 432*lo*lo-96*hi-80>0
    for _ in range(bits):
        mid=(lo+hi)/2
        val=rational_poly_at(CUBIC,mid)
        if val<0:lo=mid
        elif val>0:hi=mid
        else:raise AssertionError('unexpected rational root in irreducible cubic')
    return lo,hi


def interval_eval(coeffs,low,high):
    """An inclusive rational Horner interval for q(t) on [low,high]."""
    lo=hi=F(0)
    for value in reversed(coeffs):
        products=(lo*low,lo*high,hi*low,hi*high)
        lo,hi=min(products)+value,max(products)+value
    return lo,hi


@lru_cache(maxsize=32)
def fixed_bracket(bits):
    return isolate_cubic(bits)


def reduce_coeffs(coeffs):
    coeffs=list(map(F,coeffs))
    while len(coeffs)>3:
        degree=len(coeffs)-1
        top=coeffs.pop()
        # t^3 = (-11 +80t +48t^2)/144
        coeffs[degree-3]+=top*F(-11,144)
        coeffs[degree-2]+=top*F(80,144)
        coeffs[degree-1]+=top*F(48,144)
    return tuple(coeffs+[F(0)]*(3-len(coeffs)))


@dataclass(frozen=True)
class CubicRoot:
    """a+b*rho+c*rho² in Q[rho]; rho's cubic has no rational root."""
    coeffs: tuple[F, F, F]

    def __post_init__(self):
        object.__setattr__(self,'coeffs',reduce_coeffs(self.coeffs))

    @classmethod
    def coerce(cls, other):
        if isinstance(other,cls):return other
        return cls((F(other),))

    def __add__(self,other):
        other=self.coerce(other)
        return CubicRoot(tuple(a+b for a,b in zip(self.coeffs,other.coeffs)))
    __radd__=__add__

    def __neg__(self):return CubicRoot(tuple(-a for a in self.coeffs))
    def __sub__(self,other):return self+-self.coerce(other)
    def __rsub__(self,other):return self.coerce(other)-self

    def __mul__(self,other):
        other=self.coerce(other)
        result=[F(0)]*5
        for i,a in enumerate(self.coeffs):
            for j,b in enumerate(other.coeffs):result[i+j]+=a*b
        return CubicRoot(tuple(result))
    __rmul__=__mul__

    def __pow__(self,n):
        if not isinstance(n,int) or n<0:raise ValueError('nonnegative integer exponent required')
        answer=self.coerce(1);base=self
        while n:
            if n&1:answer=answer*base
            base=base*base;n>>=1
        return answer

    def sign(self):
        return field_sign(self.coeffs)

    def __eq__(self,other):
        try:return self.coeffs==self.coerce(other).coeffs
        except (TypeError,ValueError):return NotImplemented
    def __lt__(self,other):return (self-self.coerce(other)).sign()<0
    def __le__(self,other):return (self-self.coerce(other)).sign()<=0
    def __gt__(self,other):return (self-self.coerce(other)).sign()>0
    def __ge__(self,other):return (self-self.coerce(other)).sign()>=0

    def __str__(self):
        return '('+' + '.join(f'({v})*rho^{i}' for i,v in enumerate(self.coeffs) if v)+')' if any(self.coeffs) else '0'


@lru_cache(maxsize=50000)
def field_sign(coeffs):
    if coeffs[1:] == (F(0),F(0)):
        x=coeffs[0]
        return (x>0)-(x<0)
    for bits in (80,120,160,240,320):
        lo,hi=fixed_bracket(bits)
        lb,ub=interval_eval(coeffs,lo,hi)
        if lb>0:return 1
        if ub<0:return -1
    raise ArithmeticError('root sign did not separate; inspect field and interval')


RHO=CubicRoot((F(0),F(1)))
RATIONAL_BRIDGE=F(3,4)

# Order is counterclockwise, low cosine to high cosine. In range (alpha,rho)
# the added point 470 lies on the exposed edge; the false numerical vertex 94
# has IDENTICALLY zero area with 0,470 at every angle.
REGIMES=(
    ('broad', F(0),F(1,4),(500,625,250,0)),
    ('middle',F(1,4),F(1,2),(500,625,250,0,475)),
    ('narrow',F(1,2),ALPHA,(475,500,625,250,175,0)),
    ('new_7_left',ALPHA,RATIONAL_BRIDGE,(475,500,625,250,175,0,470)),
    ('new_7_right',RATIONAL_BRIDGE,RHO,(475,500,625,250,175,0,470)),
    ('new_8',RHO,F(1),(470,475,500,625,250,175,0,469)),
)


def signatures(depth=4):
    """Symbolic endpoints of the unchanged grammar, independent of visuals."""
    if isinstance(depth,bool) or not isinstance(depth,int) or not 0<=depth<=4:
        raise ValueError('depth must be integer 0..4')
    word='F'
    for _ in range(depth):word=''.join('F[+F]F[-F]F' if c=='F' else c for c in word)
    heading=0;counts={};stack=[];unique={():None}
    for c in word:
        if c=='F':
            counts[heading]=counts.get(heading,0)+1
            unique[tuple(sorted(counts.items()))]=None
        elif c=='+':heading+=1
        elif c=='-':heading-=1
        elif c=='[':stack.append((heading,counts.copy()))
        elif c==']':
            if not stack:raise ValueError('unbalanced brackets')
            heading,counts=stack.pop()
        else:raise ValueError('unknown token')
    assert not stack and heading==0
    return tuple(unique)


def transform_signature(signature, turn, trunk_steps):
    """Translate and rotate one smaller canopy by integer heading counts."""
    steps={heading+turn:count for heading,count in signature}
    if trunk_steps:
        steps[0]=steps.get(0,0)+trunk_steps
    return tuple(sorted((h,n) for h,n in steps.items() if n))


def recursive_candidate_indices(stage, current):
    """Five affine copies of previous-stage hull vertices, not all endpoints.

    This is valid because convex hull distributes over finite unions and
    invertible affine transformations. The 5 copies are each the entire
    depth-3 canopy, with two ±angle rotations and three trunk positions.
    """
    previous_hull=PREVIOUS_REGIMES[stage][3]
    old=previous_signatures(3)
    now={signature:i for i,signature in enumerate(current)}
    offsets=((0,0),(1,27),(0,27),(-1,54),(0,54))
    return tuple(sorted({now[transform_signature(old[i],turn,trunk)]
                         for i in previous_hull for turn,trunk in offsets}))


def exact_hull_at(points,cosine):
    """Independent monotone-chain hull, rational or a single algebraic field."""
    # Q46 and CubicRoot implement all necessary operations; fixed type
    # of cosine determines the algebraic field of the coordinates.
    c=cosine
    xy={}
    for i,(x,y) in enumerate(points):
        p=(evaluate(x,c),evaluate(y,c))
        xy.setdefault(p,i)
    ordered=sorted((xy,i) for xy,i in xy.items())
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
    return tuple(p[1] for p in lower[:-1]+upper[:-1])


def certify_interval(points,name,lo,hi,corners,candidate_ids):
    """Every candidate in every CCW hull half-plane over a WHOLE interval."""
    if not lo<hi:
        raise ValueError('interval endpoints out of order')
    checks=0
    for k in range(len(corners)):
        triple=[points[corners[(k+j)%len(corners)]] for j in range(3)]
        coeff=bernstein_homogenized(oriented_cross(*triple),lo,hi)
        if not (all(z>=0 for z in coeff) and any(z>0 for z in coeff)):
            raise AssertionError((name,'corner',k,coeff))
    for i,j in zip(corners,corners[1:]+corners[:1]):
        for k in candidate_ids:
            coeff=bernstein_homogenized(oriented_cross(points[i],points[j],points[k]),lo,hi)
            if not all(z>=0 for z in coeff):
                raise AssertionError((name,'containment',i,j,k,coeff))
            checks+=1
    return checks


def certificate():
    endpoint_labels=signatures(4)
    points=tuple(map(endpoint_polynomials,endpoint_labels))
    if len(points)!=626: raise AssertionError('wrong endpoint count')
    if oriented_cross(points[0],points[94],points[470])!=(0,):
        raise AssertionError('expected persistent collinearity')
    all_checks=0;poly_corners=0;regimes=[]
    for stage,(name,lo,hi,corners) in enumerate(REGIMES):
        # Stage three is split across a rational bridge to avoid mixing
        # quadratic and cubic algebraic extension fields.
        previous_stage=min(stage,3)
        reduced=recursive_candidate_indices(previous_stage,endpoint_labels)
        if not set(corners).issubset(reduced):
            raise AssertionError((name,'unrealizable hull corner'))
        checks=certify_interval(points,name,lo,hi,corners,reduced)
        all_checks+=checks;poly_corners+=len(corners)
        mid=(lo+hi)*F(1,2)
        if set(exact_hull_at(points,mid))!=set(corners):
            raise AssertionError((name,'midpoint'))
        regimes.append({'interval':name,'cosine_low':str(lo),'cosine_high':str(hi),
                        'extreme_point_ids':list(corners),'hull_vertices':len(corners),
                        'inequalities_checked':checks, 'recursive_candidates':len(reduced)})
    # Collinearity witnesses at exact roots of the polynomials, and exact
    # rational / algebraic hulls at boundaries, not only interior samples.
    witnesses=(
        ((0,475,500),(-243,972),F(1,4),4),
        ((0,175,250),(243,-486),F(1,2),5),
        ((0,470,475),(-189,-216,648),ALPHA,6),
        ((0,469,470),(33,-240,-144,432),RHO,7),
    )
    boundaries=[]
    for triple,poly,root,count in witnesses:
        observed=oriented_cross(*(points[i] for i in triple))
        if observed!=poly or evaluate(observed,root)!=0:
            raise AssertionError((triple,observed))
        hull=exact_hull_at(points,root)
        if len(hull)!=count: raise AssertionError((triple,hull))
        boundaries.append({'cosine':str(root),'cross_polynomial':list(poly),
                           'collinear_endpoints':list(triple),'hull_vertices':len(hull)})
    if all_checks!=1007: raise AssertionError('unexpected certificate count')
    return {'experiment':'BMO-005','depth':4,'segments':625,'symbolic_endpoints':626,
            'proof_domain':'0 < cos(theta) < 1','quadratic_root':'(2+sqrt(46))/12',
            'cubic_root_poly':list(CUBIC),'cubic_root_isolator':['87/100','88/100'],
            'split_at_rational':'3/4', 'regimes':regimes,'boundaries':boundaries,
            'exact_halfplane_constraints':all_checks,
            'full_endpoint_naive_constraints':626*(4+5+6+7+7+8),'exact_strict_convexity_checks':poly_corners,
            'numerical_hull_false_positive':'cross(0,94,470) == 0 identically',
            'scope':'outer convex hull only, not internal segment crossings or all depths'}


if __name__=='__main__':print(json.dumps(certificate(),indent=2))
