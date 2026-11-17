"""COG-005: provably distinct nonlinear capability coordinates and evidenced induction.

This is a mathematical reference, not pretrained intelligence. Reuses the
COG-001 affine compiler/address, COG-003 sourced EvidenceAtlas, and COG-004
nonlinear family for compatibility. No parallel E-CPU execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from capability_atlas import Affine, cardinality as affine_count, decode as affine_decode, encode as affine_encode, compile_regions
from structural_discovery import EvidenceAtlas, checked_point, digest, canonical, infer_affine

SCHEMA = 'in-formation.codonic-capability-atlas/005'
MAX_DEGREE = 32
MAX_PROBES = 10000
EXPERT_INDEX_CAP = 1 << 48


def _pmod(v: int, p: int) -> int:
    if type(v) is not int:
        raise ValueError('noninteger field coefficient')
    return v % p


@dataclass(frozen=True)
class PolynomialGround:
    """Exactly invertible (x,y)->A(x,y+P(x))+b, P has no degree 0/1 terms.

    Representation is canonical: A incorporates all affine terms; the trailing
    polynomial zeros are removed. Hence each coefficient tuple and affine map
    describes a distinct function on Fp² for degree < p.
    """
    affine: Affine
    coefficients: tuple[int, ...] = ()  # coefficients of x^2, x^3, ...

    def __post_init__(self) -> None:
        if not isinstance(self.affine, Affine):
            raise ValueError('missing existing affine Ground')
        if not isinstance(self.coefficients, tuple) or len(self.coefficients) > MAX_DEGREE - 1:
            raise ValueError('polynomial degree exceeds admitted grammar')
        if any(type(v) is not int or v < 0 or v >= self.p for v in self.coefficients):
            raise ValueError('noncanonical polynomial coefficient')
        if self.coefficients and self.coefficients[-1] == 0:
            raise ValueError('trailing-zero family aliases are refused')

    @property
    def p(self) -> int:
        return self.affine.p

    @property
    def degree(self) -> int:
        return len(self.coefficients) + 1 if self.coefficients else 1

    def shear(self, x: int) -> int:
        # Horner evaluation for c2*x^2 + ... + cd*x^d.
        value = 0
        for c in reversed(self.coefficients):
            value = (value * x + c) % self.p
        return value * x * x % self.p

    def apply(self, point: Sequence[int]) -> tuple[int, int]:
        x, y = checked_point(self.p, point)
        return self.affine.apply((x, (y + self.shear(x)) % self.p))

    def inverse(self, point: Sequence[int]) -> tuple[int, int]:
        """Exact inverse: A inverse followed by inverse triangular shear."""
        z, w = checked_point(self.p, point)
        (a, b), (c, d) = self.affine.mat
        delta = pow((a * d - b * c) % self.p, -1, self.p)
        z = (z - self.affine.bias[0]) % self.p
        w = (w - self.affine.bias[1]) % self.p
        x = (d * z - b * w) * delta % self.p
        y = (-c * z + a * w) * delta % self.p
        return x, (y - self.shear(x)) % self.p

    def to_dict(self) -> dict[str, Any]:
        return {'schema': SCHEMA+'.ground', 'affine': self.affine.dictionary(),
                'shear_coefficients_from_degree_two': list(self.coefficients), 'degree': self.degree}

    @property
    def fingerprint(self) -> str:
        return digest(self.to_dict())

    def plan(self) -> dict[str, Any]:
        parts = compile_regions(self.affine)
        body = {'schema': SCHEMA+'.plan', 'ground': self.fingerprint,
                'degree': self.degree, 'regions': ['polynomial-shear']+[q.region for q in parts.steps],
                'source': 'declared-exact-polynomial-law',
                'work': {'polynomial_horner_steps': len(self.coefficients),
                         'affine_region_steps': len(parts.steps)},
                'claims_no_remote_authority': True}
        return {**body, 'digest': digest(body)}


def count_family(p: int, degree: int) -> int:
    """Exact count of unique degree-<=D polynomial shear + affine functions.

    Independent P coefficients c2..cD: p**(D-1), and all AGL(2,p).
    Distinctness follows from partial difference in y recovering A[:,1],
    the x-linear term recovering A[:,0], and uniqueness of polynomial
    functions degree < p. No hashing-based uniqueness assumption.
    """
    if type(degree) is not int or not 2 <= degree <= MAX_DEGREE or degree >= p:
        raise ValueError('degree outside proved unique functional regime')
    return affine_count(p) * p ** (degree - 1)


def decode_capability(p: int, degree: int, address: int) -> PolynomialGround:
    size = count_family(p, degree)
    if type(address) is not int or not 0 <= address < size:
        raise ValueError('capability address out of range')
    base = affine_count(p)
    affine = affine_decode(p, address % base)
    rest = address // base
    coeff = []
    for _ in range(degree - 1):
        coeff.append(rest % p)
        rest //= p
    while coeff and coeff[-1] == 0:
        coeff.pop()
    return PolynomialGround(affine, tuple(coeff))


def encode_capability(ground: PolynomialGround, degree: int) -> int:
    if not isinstance(ground, PolynomialGround) or type(degree) is not int or degree < ground.degree:
        raise ValueError('ground outside declared family grammar')
    count_family(ground.p, degree)
    acc = 0
    for c in reversed(ground.coefficients + (0,) * (degree-1-len(ground.coefficients))):
        acc = acc * ground.p + c
    return acc * affine_count(ground.p) + affine_encode(ground.affine)


def _basis_row(p: int, point: Sequence[int], degree: int) -> tuple[int, ...]:
    x, y = checked_point(p, point)
    row = [1, x, y]
    power = x * x % p
    for _ in range(2, degree + 1):
        row.append(power)
        power = power * x % p
    return tuple(row)


def _row_add(basis: dict[int, tuple[int, ...]], row: Sequence[int], p: int) -> bool:
    """Incremental canonical echelon; O(D²), no repeated matrix ranks."""
    r = list(row)
    for pivot, old in sorted(basis.items()):
        if r[pivot]:
            f = r[pivot]
            r = [(a-f*b) % p for a,b in zip(r,old)]
    loc = next((i for i,z in enumerate(r) if z), None)
    if loc is None:
        return False
    inv = pow(r[loc], -1, p)
    basis[loc] = tuple(v * inv % p for v in r)
    return True


def select_probes(evidence: EvidenceAtlas, context: str, pool: Sequence[Sequence[int]], *,
                  degree: int, limit: int) -> tuple[tuple[int,int], ...]:
    """Choose unseen rank-increasing probes, then independent challenge probes.

    One pass and incremental echelon: O(pool*degree²). Selection never sees
    answers, unlike a label-oracle shortcut. Challengers are not used for fit.
    """
    if (not isinstance(evidence,EvidenceAtlas) or type(limit) is not int or not 1 <= limit <= 100 or
        not isinstance(pool,(tuple,list)) or not 1<=len(pool)<=4096):
        raise ValueError('invalid bounded acquisition request')
    count_family(evidence.base.p,degree)
    previous=evidence.for_context(context)
    seen={w.source for w in previous}
    basis: dict[int,tuple[int,...]]={}
    for w in previous:
        _row_add(basis, _basis_row(evidence.base.p,w.source,degree),evidence.base.p)
    candidates=[]
    for item in pool:
        point=checked_point(evidence.base.p,item)
        if point not in seen and point not in candidates:
            candidates.append(point)
    selected=[]
    # Deterministic rank-first, then caller-order challenges. No label access.
    for point in candidates:
        if len(selected)>=limit:break
        if len(basis)<degree+2 and _row_add(basis,_basis_row(evidence.base.p,point,degree),evidence.base.p):
            selected.append(point)
    for point in candidates:
        if len(selected)>=limit:break
        if point not in selected:
            selected.append(point)
    if len(selected) < limit:
        raise ValueError('probe budget cannot be fulfilled')
    return tuple(selected)


def _solve(features: Sequence[Sequence[int]], outputs: Sequence[int], p: int) -> tuple[int,...]:
    n = len(features)
    if not n or len(outputs)!=n or any(len(row)!=n for row in features):
        raise ValueError('square polynomial evidence basis missing')
    m = [[_pmod(x,p) for x in row]+[_pmod(y,p)] for row,y in zip(features,outputs)]
    for j in range(n):
        pivot=next((i for i in range(j,n) if m[i][j]),None)
        if pivot is None:raise ValueError('source probes do not span polynomial feature space')
        m[j],m[pivot]=m[pivot],m[j]
        inv=pow(m[j][j],-1,p)
        m[j]=[z*inv%p for z in m[j]]
        for i in range(n):
            if i!=j and m[i][j]:
                q=m[i][j];m[i]=[(a-q*b)%p for a,b in zip(m[i],m[j])]
    return tuple(row[-1] for row in m)


@dataclass(frozen=True)
class CapabilityClaim:
    context: str
    ground: PolynomialGround
    basis_indices: tuple[int, ...]
    challenge_indices: tuple[int, ...]
    source_root: str
    source_fingerprint: str
    max_degree: int

    def to_dict(self) -> dict[str,Any]:
        return {'schema':SCHEMA+'.claim','context':self.context,'ground':self.ground.to_dict(),
                'ground_digest':self.ground.fingerprint,'basis_indices':list(self.basis_indices),
                'challenge_indices':list(self.challenge_indices),
                'source_root':self.source_root,'source_fingerprint':self.source_fingerprint,
                'hypothesis_max_degree':self.max_degree,'admission':
                'uniquely_interpolated_within_declared_polynomial_shear_grammar;unseen_laws_may_differ'}

    @property
    def fingerprint(self) -> str:
        return digest(self.to_dict())


def infer_capability(state: EvidenceAtlas, context: str, *, max_degree: int,
                     min_challenges: int=2) -> CapabilityClaim:
    """Infer a fully unknown affine+polynomial family, not a prior degree label."""
    if not isinstance(state,EvidenceAtlas) or type(min_challenges) is not int or min_challenges < 1:
        raise ValueError('invalid evidence or challenge policy')
    p=state.base.p
    count_family(p,max_degree)
    obs=state.for_context(context)
    selected=[];basis:dict[int,tuple[int,...]]={}
    for i,w in enumerate(obs):
        if _row_add(basis,_basis_row(p,w.source,max_degree),p):
            selected.append(i)
            if len(selected)==max_degree+2:break
    if len(selected)!=max_degree+2:
        raise ValueError('underdetermined source geometry, cannot identify full family')
    challenges=tuple(i for i in range(len(obs)) if i not in selected)
    if len(challenges)<min_challenges:
        raise ValueError('insufficient independent withheld challenge observations')
    rows=[_basis_row(p,obs[i].source,max_degree) for i in selected]
    coeffs=tuple(_solve(rows,[obs[i].observed[k] for i in selected],p) for k in (0,1))
    y_column=(coeffs[0][2],coeffs[1][2])
    affine=Affine(p,((coeffs[0][1],coeffs[0][2]),(coeffs[1][1],coeffs[1][2])),
                  (coeffs[0][0],coeffs[1][0]))
    axis=0 if y_column[0] else 1
    scale=pow(y_column[axis],-1,p)
    coeff=[]
    for j in range(3,max_degree+2):
        c=coeffs[axis][j]*scale%p
        if any(coeffs[out][j]!=(y_column[out]*c)%p for out in range(2)):
            raise ValueError('unsupported polynomial family: sheared coefficients not collinear')
        coeff.append(c)
    while coeff and coeff[-1]==0:
        coeff.pop()
    ground=PolynomialGround(affine,tuple(coeff))
    if any(ground.apply(w.source)!=w.observed for w in obs):
        raise ValueError('source challenge contradicts identified algebraic family')
    if not ground.coefficients:
        old,_=infer_affine(p,obs)
        if old!=affine:raise ValueError('independent COG003 affine interpolation disagrees')
    if len(ground.coefficients)==1:
        from family_discovery import ShearGround, identify
        old=identify(state,context,min_challenges=1)
        if not isinstance(old.ground,ShearGround) or old.ground.q != ground.coefficients[0]:
            raise ValueError('independent COG004 quadratic family disagrees')
    return CapabilityClaim(context,ground,tuple(selected),challenges,state.head,state.fingerprint,max_degree)


def verify_claim(state:EvidenceAtlas, claim:Mapping[str,Any], *,
                 expected_head:str, expected_fingerprint:str) -> bool:
    if not isinstance(state,EvidenceAtlas) or state.head!=expected_head or state.fingerprint!=expected_fingerprint:
        raise ValueError('receiver-owned source high-water mismatch')
    if not isinstance(claim,Mapping) or type(claim.get('hypothesis_max_degree')) is not int:
        raise ValueError('malformed capability claim')
    expected=infer_capability(state,claim.get('context'),max_degree=claim['hypothesis_max_degree'])
    if canonical(dict(claim))!=canonical(expected.to_dict()):
        raise ValueError('claim not supported by exact source observations')
    return True


@dataclass(frozen=True)
class NavigableExpertAtlas:
    """N unique source-defined polynomial laws from one compact mathematical class.

    A fixed-size *index set* is injected into widely separated distinct function
    addresses, not into identical templates. It creates no learned semantics.
    """
    p: int=257
    degree: int=32
    logical_experts: int=1<<48
    namespace: str='cog005-default'

    def __post_init__(self)->None:
        total=count_family(self.p,self.degree)
        if (type(self.logical_experts) is not int or
            not 8<=self.logical_experts<=EXPERT_INDEX_CAP or
            self.logical_experts & (self.logical_experts-1) or
            total < 2*self.logical_experts or
            type(self.namespace) is not str or not 1<=len(self.namespace)<=50):
            raise ValueError('index set must be an admitted power-of-two inside the mathematical atlas')

    @property
    def fingerprint(self)->str:
        return digest({'schema':SCHEMA+'.index','p':self.p,'degree':self.degree,
                       'logical_experts':self.logical_experts,'namespace':self.namespace,
                       'addressing':'disjoint-strata-sha256-offset-v1'})

    def capability(self, index:int)->PolynomialGround:
        if type(index) is not int or not 0 <= index < self.logical_experts:
            raise ValueError('invalid capability expert address')
        cap=count_family(self.p,self.degree)
        stride=cap//self.logical_experts
        source=sha256((self.namespace+'|'+str(index)).encode()).digest()
        offset=int.from_bytes(source,'big')%stride
        return decode_capability(self.p,self.degree,index*stride+offset)

    def center(self, t:int, *,native:bool=False)->int:
        """O(log(t)) affine jump; native verifies E-CPU's existing jump law."""
        if type(t) is not int or not 0<=t<(1<<63):
            raise ValueError('invalid distant logical-time coordinate')
        n=self.logical_experts
        if native:
            from mailcpu.law_certifier import lcg_navigate
            native_center=lcg_navigate(5,1,n,7,t)
        mul,add=1,0
        a,b=5%n,1
        steps=t
        while steps:
            if steps&1:
                mul,add=mul*a%n,(a*add+b)%n
            a,b=a*a%n,(a*b+b)%n
            steps>>=1
        result=(mul*7+add)%n
        if native and native_center!=result:
            raise ValueError('E-CPU native temporal navigation differs from independent law')
        return result

    def route(self,t:int,k:int=8,*,native:bool=False)->dict[str,Any]:
        if type(k) is not int or not 1<=k<=16 or k>self.logical_experts:
            raise ValueError('invalid bounded expert demand')
        center=self.center(t,native=native)
        sequence=[center]
        for d in range(1,k):
            delta=(d+1)//2
            chosen=center-delta if d%2 else center+delta
            if chosen<0 or chosen>=self.logical_experts:
                chosen=(center+d) % self.logical_experts
            if chosen in sequence:
                chosen=next(i for i in range(self.logical_experts) if i not in sequence)
            sequence.append(chosen)
        body={'schema':SCHEMA+'.route','atlas':self.fingerprint,'tick':t,
              'center':center,'indices':sequence,'k':k,'selection':'bounded-neighbor-with-edge-wrap'}
        return {**body,'digest':digest(body)}

    def observe(self,point:Sequence[int],route:Mapping[str,Any])->dict[str,Any]:
        x=checked_point(self.p,point)
        if not isinstance(route,Mapping) or canonical(dict(route))!=canonical(self.route(route.get('tick'),route.get('k'))):
            raise ValueError('route is not grounded in the receiver-owned atlas')
        outputs=[self.capability(j).apply(x) for j in route['indices']]
        inv=pow(len(outputs),-1,self.p)
        out=tuple(sum(v[i] for v in outputs)*inv %self.p for i in range(2))
        body={'schema':SCHEMA+'.observation','atlas':self.fingerprint,'route':route['digest'],
              'input':list(x),'result':list(out),
              'materialized_experts':len(outputs),
              'per_expert_outputs':[list(row) for row in outputs],
              'source':'synthetic-injective-polynomial-not-trained'}
        return {**body,'digest':digest(body)}

    def verify_observation(self,route:Mapping[str,Any],observation:Mapping[str,Any])->bool:
        if not isinstance(observation,Mapping):
            raise ValueError('invalid observer result')
        if not isinstance(route,Mapping) or canonical(dict(route))!=canonical(self.route(route.get('tick'),route.get('k'))):
            raise ValueError('receiver route is ungrounded')
        x,y=checked_point(self.p,observation.get('input'))
        expected_per=[]
        # Deliberately independent direct power-series oracle, not the Horner
        # path in PolynomialGround.apply. This can be more expensive.
        for index in route['indices']:
            ground=self.capability(index)
            shear=sum(c*pow(x,j+2,self.p) for j,c in enumerate(ground.coefficients))%self.p
            a,b=ground.affine.mat[0];c,d=ground.affine.mat[1]
            yp=(y+shear)%self.p
            expected_per.append([(a*x+b*yp+ground.affine.bias[0])%self.p,
                                 (c*x+d*yp+ground.affine.bias[1])%self.p])
        k=len(expected_per)
        inverse=pow(k,-1,self.p)
        out=[sum(row[j] for row in expected_per)*inverse%self.p for j in range(2)]
        body={'schema':SCHEMA+'.observation','atlas':self.fingerprint,'route':route['digest'],
              'input':[x,y],'result':out,'materialized_experts':k,
              'per_expert_outputs':expected_per,
              'source':'synthetic-injective-polynomial-not-trained'}
        expected={**body,'digest':digest(body)}
        if canonical(dict(observation))!=canonical(expected):
            raise ValueError('observer result differs from independent polynomial arithmetic')
        return True
