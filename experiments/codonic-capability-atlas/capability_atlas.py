"""COG-001: independently typed algebraic capability regions and arbitrated composition.

A small, fully explainable, non-trained experiment. It distinguishes:
(1) independent affine transformations; (2) finite generative region schemas;
(3) a context-dependent arbiter; (4) logical-time jump via exact composition.

No remote-host admission, pretrained intelligence, or source attestation is implied.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from typing import Any


def fail(condition: bool, why: str) -> None:
    if condition:
        raise ValueError(why)


def inv(x: int, p: int) -> int:
    fail(x % p == 0, "noninvertible element")
    return pow(x, -1, p)


@dataclass(frozen=True)
class Affine:
    p: int
    mat: tuple[tuple[int, int], tuple[int, int]]
    bias: tuple[int, int]

    def __post_init__(self) -> None:
        fail(self.p not in (3, 5, 257), "only the explicitly tested prime fields are admitted")
        fail(len(self.mat) != 2 or any(len(r) != 2 for r in self.mat) or len(self.bias) != 2, "incorrect shape")
        fail(any(type(v) is not int or v < 0 or v >= self.p
                 for r in self.mat for v in r) or any(type(v) is not int or v < 0 or v >= self.p for v in self.bias),
             "noncanonical field coordinate")
        fail(self.det() == 0, "only invertible affine transformations are admitted")

    @staticmethod
    def identity(p: int) -> 'Affine':
        return Affine(p, ((1, 0), (0, 1)), (0, 0))

    def det(self) -> int:
        a, b = self.mat[0]; c, d = self.mat[1]
        return (a * d - b * c) % self.p

    def apply(self, v: tuple[int, int]) -> tuple[int, int]:
        fail(len(v) != 2, "input shape")
        x, y = v
        fail(type(x) is not int or type(y) is not int, "input type")
        p = self.p
        return ((self.mat[0][0]*x + self.mat[0][1]*y + self.bias[0]) % p,
                (self.mat[1][0]*x + self.mat[1][1]*y + self.bias[1]) % p)

    def after(self, preceding: 'Affine') -> 'Affine':
        """The exact composition self ∘ preceding."""
        fail(self.p != preceding.p, "unmatched coordinate frames")
        p=self.p; m=self.mat; n=preceding.mat
        z=tuple(tuple(sum(m[i][k]*n[k][j] for k in range(2))%p for j in range(2)) for i in range(2))
        off=self.apply(preceding.bias)
        return Affine(p, z, off)

    def jump(self, logical_time: int) -> 'Affine':
        """O(log t) binary-power composition, not t repeated state steps."""
        fail(type(logical_time) is not int or not 0 <= logical_time < (1<<128), "invalid logical time")
        result=Affine.identity(self.p); base=self; steps=logical_time
        while steps:
            if steps & 1: result=base.after(result)
            base=base.after(base)
            steps >>= 1
        return result

    def dictionary(self) -> dict[str, Any]:
        return {"p":self.p,"mat":[list(r) for r in self.mat],"bias":list(self.bias)}


def translation(p:int,u:int,v:int) -> Affine:
    return Affine(p, ((1,0),(0,1)), (u%p,v%p))


def diagonal(p:int, a:int,d:int) -> Affine:
    return Affine(p, ((a%p,0),(0,d%p)), (0,0))


def upper(p:int, u:int) -> Affine:
    return Affine(p, ((1,u%p),(0,1)),(0,0))


def lower(p:int, l:int) -> Affine:
    return Affine(p, ((1,0),(l%p,1)),(0,0))


def swap(p:int) -> Affine:
    return Affine(p, ((0,1),(1,0)),(0,0))


@dataclass(frozen=True)
class RegionStep:
    region: str
    parameters: tuple[int, ...]
    transform: Affine


@dataclass(frozen=True)
class Plan:
    address: int
    steps: tuple[RegionStep, ...]
    realization: Affine


def compile_regions(target: Affine) -> Plan:
    """Factor exact intent into independently generated regions, no search.

    Pivots, shears, diagonal map and translations form all AGL(2,Fp).
    Composition occurs in declared application order.
    """
    p=target.p
    (a,b),(c,d)=target.mat
    # P*M swaps target's rows if top-left cannot pivot.
    pivot=(a==0)
    if pivot: a,b,c,d=c,d,a,b
    u=b*inv(a,p)%p
    l=c*inv(a,p)%p
    s=(d-c*u)%p
    operations=[
        RegionStep('coupling-upper', (u,), upper(p,u)),
        RegionStep('gain-diagonal', (a,s), diagonal(p,a,s)),
        RegionStep('coupling-lower', (l,), lower(p,l)),
    ]
    if pivot: operations.append(RegionStep('frame-swap',(),swap(p)))
    operations.append(RegionStep('translation',target.bias,translation(p,*target.bias)))
    total=Affine.identity(p)
    for operation in operations: total=operation.transform.after(total)
    fail(total!=target,'compiled operations do not implement the admitted target')
    return Plan(address=encode(target),steps=tuple(operations),realization=total)


def cardinality(p:int) -> int:
    # |AGL(2,p)| = p^2 (p^2 - 1)(p^2 - p).
    fail(p not in (3,5,257),'field not admitted')
    return p*p*(p*p-1)*(p*p-p)


def decode(p:int,address:int) -> Affine:
    """O(1) exact unranking of *every* invertible affine map; no model-wide scan."""
    fail(type(address) is not int or not 0<=address<cardinality(p), 'invalid algebraic address')
    bias_y=address%p; address//=p
    bias_x=address%p; address//=p
    q=p*(p-1)
    second_idx=address%q; first_idx=address//q
    v=first_idx+1 # nonzero first column, as a+p*c
    a=v%p; c=v//p
    if a!=0:
        b=second_idx%p
        delta=second_idx//p+1
        d=(c*inv(a,p)*b+delta)%p
    else:
        b=second_idx//p+1
        d=second_idx%p
    return Affine(p,((a,b),(c,d)),(bias_x,bias_y))


def encode(target:Affine) -> int:
    p=target.p
    (a,b),(c,d)=target.mat
    first_idx=a+p*c-1
    if a!=0:
        delta=(d-c*inv(a,p)*b)%p
        fail(delta==0,'noninvertible map')
        second_idx=(delta-1)*p+b
    else:
        fail(b==0,'noninvertible pivot')
        second_idx=(b-1)*p+d
    return (((first_idx*(p*(p-1))+second_idx)*p+target.bias[0])*p+target.bias[1])


def point_label(seed:str,address:int) -> str:
    """Opaque identity only: hash is NOT the relationship/distance metric."""
    fail(type(seed) is not str or not 1<=len(seed)<=64, 'invalid label seed')
    return hashlib.sha256(f'{seed}|{address}'.encode()).hexdigest()


@dataclass(frozen=True)
class ContextualArbiter:
    """A two-context controller; this is conditional composition, not a global affine law."""
    even:Affine
    odd:Affine

    def __post_init__(self) -> None:
        fail(self.even.p!=self.odd.p,'incompatible contextual Grounds')

    def select(self, context:tuple[int,int]) ->Plan:
        return compile_regions(self.odd if context[0]%2 else self.even)

    def realize(self, context:tuple[int,int])->tuple[int,int]:
        return self.select(context).realization.apply(context)


def run_audit() ->dict[str,Any]:
    p=257
    even=Affine(p,((2,1),(0,3)),(5,7))
    odd=Affine(p,((1,2),(1,1)),(7,9))
    arbiter=ContextualArbiter(even,odd)
    # A single affine map must satisfy parallelogram identity, this arbiter does not.
    f=lambda x:arbiter.realize(x)
    f00,f10,f01,f11=map(f,((0,0),(1,0),(0,1),(1,1)))
    witness=tuple((f11[k]-f10[k]-f01[k]+f00[k])%p for k in range(2))
    fail(witness==(0,0),'context gate unexpectedly affine')
    all_distinct=cardinality(p)
    # Compare representations for independently seeded address labels.
    target=decode(p,(all_distinct//3)*2+41)
    compiled=compile_regions(target)
    far=target.jump((1<<63)+73)
    return {'field':p,'algebraic_transformations':all_distinct,
            'bits_to_address':(all_distinct-1).bit_length(),
            'sample_address':encode(target),'sample_plan_steps':len(compiled.steps),
            'families':list(dict.fromkeys(x.region for x in compiled.steps)),
            'seed_A_name':point_label('seed-A',encode(target)),
            'seed_B_name':point_label('seed-B',encode(target)),
            'same_shape_despite_labels':compiled.realization==target,
            'logical_time':(1<<63)+73,'jump_target_on_probe':list(far.apply((11,17))),
            'arbiter_parallelogram_violation':list(witness),
            'contextual_behaviour_not_single_affine':witness!=(0,0),
            'note':'exact finite-ring procedural functional capacity, no training or open-ended intelligence'}


if __name__=='__main__':
    print(json.dumps(run_audit(),sort_keys=True,indent=2))