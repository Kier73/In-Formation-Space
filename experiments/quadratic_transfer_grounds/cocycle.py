"""TCN-003: exact Gauss-cocycle lift of finite-field quadratic transfers.

The TCN-002 symplectic matrix discards an overall phase. This module restores
it as i**quadrant using the quadratic Gauss sum. Exact scalar amplitudes are
stored as a fourth-root phase, a pth-root phase, and 1 or 1/sqrt(p) magnitude.
A complex number is rendered only at the observation boundary.

T_a = D_a F, (Fv)[y] = p^-1/2 sum_x omega^(xy) v[x],
D_a[y,y]=omega^(a*y^2), omega=e^(2*pi*i/p).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import cmath
import hashlib
import json
import math

import numpy as np

from transfer import _I, _mm, _inverse, _matrix_order, _prime


def _matrix(x, p):
    try:
        rows=tuple(tuple(row) for row in x)
        if len(rows)!=2 or any(len(row)!=2 for row in rows):
            raise ValueError
        if any(type(z) is not int for row in rows for z in row):
            raise ValueError
        rows=tuple(tuple(z%p for z in row) for row in rows)
        if (rows[0][0]*rows[1][1]-rows[0][1]*rows[1][0])%p != 1:
            raise ValueError
        return rows
    except (TypeError,ValueError) as exc:
        raise ValueError('2x2 determinant-one integer matrix required') from exc


def _gauss_cocycle(m,n,p):
    """Quadratic Gauss multiplier: K_m K_n = i^q K_(mn), q in Z4.

    Only when b=m[0][1], f=n[0][1], B=(mn)[0][1] are all nonzero:
    sum_z omega^((B/(2*b*f))*z*z) = chi(B/(2bf))*epsilon_p*sqrt(p).
    In all degenerate cases the canonical zero/zero kernel has multiplier 1.
    epsilon_p=1 if p=1 mod4, i if p=3 mod4.
    """
    b,f=m[0][1],n[0][1]
    if b==0 or f==0:
        return 0
    B=_mm(m,n,p)[0][1]
    if B==0:
        return 0
    quadratic=B*pow(2*b*f,-1,p)%p
    chi=pow(quadratic,(p-1)//2,p)
    if chi not in (1,p-1):
        raise ArithmeticError('quadratic character must be ±1')
    return (int(p%4==3)+2*int(chi==p-1))%4


@dataclass(frozen=True)
class ExactAmplitude:
    """Exact symbolic phase; magnitude either 0, 1, or 1/sqrt(p)."""
    p: int
    nonzero: bool
    quadrant: int=0
    residue: int=0
    flat: bool=False

    def __post_init__(self):
        if not _prime(self.p) or type(self.nonzero) is not bool or type(self.flat) is not bool:
            raise ValueError('odd prime, boolean support and flatness required')
        if type(self.quadrant) is not int or type(self.residue) is not int:
            raise ValueError('integer phase residues required')
        object.__setattr__(self,'quadrant',self.quadrant%4)
        object.__setattr__(self,'residue',self.residue%self.p)
        if not self.nonzero and (self.quadrant or self.residue or self.flat):
            raise ValueError('zero has canonical phase 0 and no normalization')

    def probability(self):
        return Fraction(0 if not self.nonzero else 1,
                        self.p if self.nonzero and self.flat else 1)

    def complex_value(self):
        if not self.nonzero:
            return 0j
        return (1j)**self.quadrant*cmath.exp(2j*math.pi*self.residue/self.p) / (
            math.sqrt(self.p) if self.flat else 1.0)

    def description(self):
        return {'nonzero':self.nonzero,'quadrant_mod4':self.quadrant,
                'residue_mod_p':self.residue,'magnitude':
                ('zero' if not self.nonzero else '1/sqrt(p)' if self.flat else '1')}


@dataclass(frozen=True)
class ExactOperator:
    """U = i^quadrant K_M, with a fixed canonical quadratic kernel K_M.

    The central phase is part of the operator, unlike the TCN-002 ray.
    No arbitrary matrix/quantum evolution can be encoded into this family.
    """
    p: int
    m: tuple[tuple[int,int],tuple[int,int]]
    quadrant: int=0

    def __post_init__(self):
        if not _prime(self.p) or type(self.quadrant) is not int:
            raise ValueError('odd prime field and integer quadrant required')
        object.__setattr__(self,'m',_matrix(self.m,self.p))
        object.__setattr__(self,'quadrant',self.quadrant%4)

    @classmethod
    def identity(cls,p):
        return cls(p,_I,0)

    @classmethod
    def transfer(cls,p,a):
        if type(a) is not int:
            raise ValueError('integer quadratic chirp required')
        return cls(p,((0,p-1),(1,(-2*a)%p)))

    def compose(self,other):
        """U_self ∘ U_other: order matters; exact central multiplier."""
        if not isinstance(other,ExactOperator) or other.p!=self.p:
            raise ValueError('matched exact operators over the same field required')
        extra=_gauss_cocycle(self.m,other.m,self.p)
        return ExactOperator(self.p,_mm(self.m,other.m,self.p),
                             (self.quadrant+other.quadrant+extra)%4)

    def inverse(self):
        inverted=_inverse(self.m,self.p)
        extra=_gauss_cocycle(self.m,inverted,self.p)
        return ExactOperator(self.p,inverted,(-self.quadrant-extra)%4)

    def power(self,n):
        if type(n) is not int or n<0:
            raise ValueError('nonnegative integer exponent required')
        result=ExactOperator.identity(self.p)
        term=self
        multiplications=0
        while n:
            if n&1:
                result=result.compose(term)
                multiplications+=1
            n>>=1
            if n:
                term=term.compose(term)
                multiplications+=1
        return result,multiplications

    def basis_amplitude(self,source,target):
        """An exact symbolic amplitude <target|U|source>."""
        if type(source) is not int or type(target) is not int:
            raise ValueError('integer basis coordinates required')
        p=self.p
        x,y=source%p,target%p
        a,b=self.m[0]
        c,d=self.m[1]
        if b:
            residue=(d*y*y-2*y*x+a*x*x)*pow(2*b,-1,p)%p
            return ExactAmplitude(p,True,self.quadrant,residue,True)
        if y!=a*x%p:
            return ExactAmplitude(p,False)
        residue=c*y*y*pow(2*a,-1,p)%p
        return ExactAmplitude(p,True,self.quadrant,residue,False)

    def apply_coordinate(self,vector,target):
        """Full complex target amplitude from arbitrary length-p complex input.

        O(p) data work in dense-kernel case (O(1) for permutation case)
        plus the already O(log n) operator description. Source input is
        *supplied*, not compressed or discovered by this function.
        """
        v=np.asarray(vector,dtype=np.complex128)
        if v.shape!=(self.p,) or not np.isfinite(v).all():
            raise ValueError('finite complex vector with p entries required')
        if type(target) is not int:
            raise ValueError('integer target required')
        p,y=self.p,target%self.p
        a,b=self.m[0]
        c,d=self.m[1]
        if b==0:
            source=pow(a,-1,p)*y%p
            return self.basis_amplitude(source,y).complex_value()*v[source]
        x=np.arange(p,dtype=np.int64)
        residues=((d*y*y-2*y*x+a*x*x)*pow(2*b,-1,p))%p
        weights=np.exp(2j*np.pi*residues/p)
        return complex((1j)**self.quadrant*np.dot(weights,v)/np.sqrt(p))

    def apply_full(self,vector):
        """All p amplitudes; O(p²) work in general, unlike a single query."""
        return np.array([self.apply_coordinate(vector,y) for y in range(self.p)])

    def signature(self):
        return {'matrix':[list(self.m[0]),list(self.m[1])],
                'global_quadrant_mod4':self.quadrant}


class ExactSchedule:
    """Periodic quadratic schedule with exact Gauss phase and group inverses."""
    def __init__(self,p:int,pattern:tuple[int,...]):
        if not _prime(p) or not isinstance(pattern,tuple) or not pattern or len(pattern)>256:
            raise ValueError('odd prime and nonempty <=256 periodic chirp tuple required')
        if any(type(a) is not int for a in pattern):
            raise ValueError('chirp coefficients must be integers')
        self.p=p
        self.pattern=tuple(a%p for a in pattern)
        cycle=ExactOperator.identity(p)
        for a in self.pattern:
            cycle=ExactOperator.transfer(p,a).compose(cycle)
        self.cycle=cycle

    def navigate(self,n):
        if type(n) is not int or n<0:
            raise ValueError('nonnegative step count required')
        q,r=divmod(n,len(self.pattern))
        power,products=self.cycle.power(q)
        for a in self.pattern[:r]:
            power=ExactOperator.transfer(self.p,a).compose(power)
            products+=1
        # Include L construction products for q>0 (not part of the power cost).
        return power,products+(len(self.pattern) if q>0 else 0)

    def full_period_bound(self):
        """Exact central extension order of cycle, times schedule length."""
        projective_order=_matrix_order(self.cycle.m,self.p)
        residual,_=self.cycle.power(projective_order)
        if residual.m!=_I:
            raise ArithmeticError('lost symplectic order')
        extra=4//math.gcd(4,residual.quadrant)
        return len(self.pattern)*projective_order*extra

    def find_exact_operator_coordinate(self,target):
        """Earliest full *unitary* operator step, including global phase.

        Baby-step giant-step on the central extension. The inversion cost
        depends on sqrt(group order), not logarithmically on requested n.
        """
        if not isinstance(target,ExactOperator) or target.p!=self.p:
            raise ValueError('matched exact unitary target required')
        cycle=self.cycle
        order=self.full_period_bound()//len(self.pattern)
        width=math.isqrt(order)+1
        babies={}
        t=ExactOperator.identity(self.p)
        for j in range(width):
            babies.setdefault(t,j)
            t=cycle.compose(t)
        backward,_=cycle.inverse().power(width)
        prefix=ExactOperator.identity(self.p)
        minimum=None
        for r in range(len(self.pattern)):
            wanted=prefix.inverse().compose(target)
            giant=wanted
            for i in range(width+1):
                j=babies.get(giant)
                if j is not None and i*width+j<order:
                    step=len(self.pattern)*(i*width+j)+r
                    if minimum is None or step<minimum:
                        minimum=step
                    break
                giant=backward.compose(giant)
            prefix=ExactOperator.transfer(self.p,self.pattern[r]).compose(prefix)
        return minimum

    def receipt(self,n,source=0,target=0):
        if type(n) is not int or n<0:
            raise ValueError('nonnegative integer step required')
        op,products=self.navigate(n)
        amplitude=op.basis_amplitude(source,target)
        record={'schema':'ifs.exact-gauss-cocycle.v1','p':self.p,
                'pattern':list(self.pattern),'steps_decimal':str(n),
                'source':source%self.p,'target':target%self.p,
                'operator':op.signature(),'amplitude':amplitude.description(),
                'operator_products':products,
                'scope':'known quadratic Fourier schedule and computational basis; exact finite-field amplitude',
                'outside_observation':False}
        record['sha256']=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return record


def verify_receipt(record):
    """Independent mathematical recomputation, not authentication of observer."""
    if not isinstance(record,dict) or set(record)!={
        'schema','p','pattern','steps_decimal','source','target','operator',
        'amplitude','operator_products','scope','outside_observation','sha256'}:
        return False
    try:
        steps=record['steps_decimal']
        if (type(steps) is not str or not steps.isascii() or not steps.isdigit()
                or len(steps)>1000 or (len(steps)>1 and steps.startswith('0'))):
            return False
        sch=ExactSchedule(record['p'],tuple(record['pattern']))
        return record==sch.receipt(int(steps),record['source'],record['target'])
    except (ValueError,TypeError,KeyError,ArithmeticError,OverflowError):
        return False
