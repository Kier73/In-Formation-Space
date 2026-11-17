"""COG-004: evidence-conditioned mathematical family discovery.

Reuses COG-003 EvidenceAtlas and its observation chain, COG-003's affine
solver, COG-001 compiler, and COG-002's existing VersionSpace. No new
Hypervisor, source authority, native VGI nonlinear operator, or host is claimed.
Only two explicitly admitted classes over Fp^2 are considered:
  affine:                  A(x,y)+b
  quadratic-shear-affine:  A(x,y+q*x*x)+b, q != 0, det(A) != 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from capability_atlas import Affine, compile_regions, encode
from structural_discovery import EvidenceAtlas, checked_point, infer_affine, digest, canonical, rank

SCHEMA = "in-formation.codonic-capability-atlas/004"
FAMILIES = ("affine", "quadratic-shear-before-affine")


def polynomial_row(p: int, xy: Sequence[int]) -> tuple[int,int,int,int]:
    x,y=checked_point(p,xy)
    return (1,x,y,(x*x)%p)


def matrix_rank(rows: Sequence[Sequence[int]],p:int,width:int)->int:
    """Finite-field Gaussian rank, never floating point or hashed distances."""
    if type(p) is not int or p not in (3,5,257) or type(width) is not int or not 1<=width<=4:
        raise ValueError("invalid field / feature width")
    matrix=[]
    for row in rows:
        row=tuple(row)
        if len(row)!=width or any(type(x) is not int for x in row):
            raise ValueError("invalid polynomial feature row")
        matrix.append([v%p for v in row])
    k=0
    for col in range(width):
        pivot=next((i for i in range(k,len(matrix)) if matrix[i][col]),None)
        if pivot is None:continue
        matrix[pivot],matrix[k]=matrix[k],matrix[pivot]
        inv=pow(matrix[k][col],-1,p)
        matrix[k]=[(z*inv)%p for z in matrix[k]]
        for i in range(k+1,len(matrix)):
            a=matrix[i][col]
            if a:matrix[i]=[(u-a*v)%p for u,v in zip(matrix[i],matrix[k])]
        k+=1
        if k==width:break
    return k


def feature_rank(points: Sequence[Sequence[int]],p:int)->int:
    return matrix_rank([polynomial_row(p,v) for v in points],p,4)


def _solve(rows:Sequence[Sequence[int]],out:Sequence[int],p:int)->tuple[int,int,int,int]:
    """Unique four-feature interpolation with full finite-field elimination."""
    if len(rows)!=4 or len(out)!=4:
        raise ValueError("four independent equations required")
    work=[]
    for row,y in zip(rows,out):
        if len(row)!=4 or any(type(v) is not int for v in row) or type(y) is not int:
            raise ValueError("invalid interpolation inputs")
        work.append([*(v%p for v in row),y%p])
    for col in range(4):
        pivot=next((r for r in range(col,4) if work[r][col]),None)
        if pivot is None:raise ValueError("underdetermined polynomial feature Ground")
        work[pivot],work[col]=work[col],work[pivot]
        inv=pow(work[col][col],-1,p)
        work[col]=[(v*inv)%p for v in work[col]]
        for r in range(4):
            if r!=col:
                a=work[r][col]
                if a:work[r]=[(u-a*v)%p for u,v in zip(work[r],work[col])]
    return tuple(row[4] for row in work)


@dataclass(frozen=True)
class ShearGround:
    """Invertible nonlinear law with one new shear before COG-001's affine plan."""
    affine:Affine
    q:int

    def __post_init__(self):
        if not isinstance(self.affine,Affine) or type(self.q) is not int or not 1<=self.q<self.affine.p:
            raise ValueError("nonzero canonical shear coefficient required")

    @property
    def p(self)->int:return self.affine.p

    def apply(self,v:Sequence[int])->tuple[int,int]:
        x,y=checked_point(self.p,v)
        return self.affine.apply((x,(y+self.q*x*x)%self.p))

    def inverse(self,v:Sequence[int])->tuple[int,int]:
        """Independent inverse using det(A), then subtracting the shear."""
        a,b=self.affine.mat[0];c,d=self.affine.mat[1];m=self.p
        inv=pow((a*d-b*c)%m,-1,m)
        z,w=checked_point(m,v)
        z=(z-self.affine.bias[0])%m
        w=(w-self.affine.bias[1])%m
        x=(d*z-b*w)*inv%m
        y=(-c*z+a*w)*inv%m
        return (x,(y-self.q*x*x)%m)

    def plan(self)->dict[str,Any]:
        old=compile_regions(self.affine)
        plan={"schema":SCHEMA+".plan","family":"quadratic-shear-before-affine",
              "p":self.p,"curvature":self.q,"affine_address":encode(self.affine),
              "regions":["quadratic-shear"]+[s.region for s in old.steps],
              "realization_order":"shear_then_existing_COG001_affine_compiler",
              "execution_authority":"local_mathematical_reference_only"}
        return {**plan,"digest":digest(plan)}


@dataclass(frozen=True)
class FamilyClaim:
    context:str
    family:str
    ground:Affine|ShearGround
    basis_indices:tuple[int,int,int,int]
    challenge_indices:tuple[int,...]
    root:str
    witness_count:int

    def __post_init__(self):
        if self.family not in FAMILIES or (self.family=="affine")!=isinstance(self.ground,Affine):
            raise ValueError("mismatched typed family")

    def apply(self,v:Sequence[int])->tuple[int,int]:return self.ground.apply(v)

    @property
    def fingerprint(self)->str:return digest(self.to_dict())

    def to_dict(self)->dict[str,Any]:
        if isinstance(self.ground,Affine):
            plan=compile_regions(self.ground)
            model={"type":"affine","map":self.ground.dictionary(),
                   "address":plan.address,"regions":[s.region for s in plan.steps]}
        else:
            model={"type":"quadratic-shear-before-affine",
                   "map":self.ground.affine.dictionary(),"q":self.ground.q,
                   "plan":self.ground.plan()}
        return {"schema":SCHEMA+".claim","context":self.context,"family":self.family,
                "ground":model,"basis_indices":list(self.basis_indices),
                "challenge_indices":list(self.challenge_indices),"source_root":self.root,
                "witness_count":self.witness_count,
                "epistemic_status":"unique_within_declared_two_family_class_only",
                "provenance_scope":"content_hash_not_host_authentication"}


def _basis(evidence,p)->tuple[int,int,int,int]:
    picked=[];rows=[]
    for i,w in enumerate(evidence):
        row=polynomial_row(p,w.source)
        if matrix_rank(rows+[row],p,4)>len(rows):
            picked.append(i);rows.append(row)
            if len(rows)==4:break
    if len(rows)!=4:
        raise ValueError("underdetermined family: four independent polynomial probes required")
    return tuple(picked)


def identify(state:EvidenceAtlas,context:str,*,min_challenges:int=1)->FamilyClaim:
    if not isinstance(state,EvidenceAtlas) or type(min_challenges) is not int or min_challenges<1:
        raise ValueError("invalid source state or challenge count")
    obs=state.for_context(context);p=state.base.p
    basis=_basis(obs,p)
    challenges=tuple(i for i in range(len(obs)) if i not in basis)
    if len(challenges)<min_challenges:
        raise ValueError("missing independent out-of-basis challenge observations")
    rows=[polynomial_row(p,obs[i].source) for i in basis]
    coeff=tuple(_solve(rows,[obs[i].observed[j] for i in basis],p) for j in range(2))
    w=(coeff[0][3],coeff[1][3])
    v=(coeff[0][2],coeff[1][2])
    affine=Affine(p,tuple((coeff[j][1],coeff[j][2]) for j in range(2)),
                  tuple(coeff[j][0] for j in range(2)))
    if w==(0,0):
        ground,_=infer_affine(p,obs)
        if ground!=affine:raise ValueError("COG003 affine reconstruction disagreement")
        family="affine"
    else:
        if v==(0,0):raise ValueError("unsupported quadratic class: shear direction absent")
        axis=0 if v[0] else 1
        q=w[axis]*pow(v[axis],-1,p)%p
        if not q or any(w[j]!=(q*v[j])%p for j in range(2)):
            raise ValueError("unsupported quadratic family: not a typed shear")
        ground=ShearGround(affine,q)
        family="quadratic-shear-before-affine"
    if any(ground.apply(o.source)!=o.observed for o in obs):
        raise ValueError("new observation contradicts proposed family Ground")
    return FamilyClaim(context,family,ground,basis,challenges,state.head,len(obs))


def choose_probe(state:EvidenceAtlas,context:str,pool:Sequence[Sequence[int]])->tuple[int,int]:
    """Maximize polynomial rank before observing any target output."""
    if not isinstance(state,EvidenceAtlas) or not isinstance(pool,(tuple,list)) or not 1<=len(pool)<=2048:
        raise ValueError("invalid Ground or candidate pool")
    current=[w.source for w in state.for_context(context)]
    seen=set(current);p=state.base.p
    old=feature_rank(current,p);old_affine=rank(current,p)
    best=None
    for raw in pool:
        x=checked_point(p,raw)
        if x in seen:continue
        now=feature_rank(current+[x],p)
        now_affine=rank(current+[x],p)
        dist=min((min(abs(x[0]-z[0]),p-abs(x[0]-z[0]))+
                  min(abs(x[1]-z[1]),p-abs(x[1]-z[1]))
                  for z in current),default=0)
        score=(now-old,now_affine-old_affine,dist,-x[0],-x[1])
        if best is None or score>best[0]:best=(score,x)
    if best is None:raise ValueError("no unobserved probe remains")
    return best[1]


def typed_catalogue(state:EvidenceAtlas,*,min_challenges:int=1)->dict[str,Any]:
    claims=[identify(state,c,min_challenges=min_challenges) for c in state.contexts]
    report={"schema":SCHEMA+".catalogue","source_atlas":state.base.fingerprint,
            "source_root":state.head,"source_fingerprint":state.fingerprint,
            "capabilities":[c.to_dict() for c in claims],
            "distinct_family_count":len(set(c.family for c in claims)),
            "admission":"unique_in_two_family_class; challenged; not_authenticated",
            "ecpu_admission":"not_attempted"}
    return {**report,"digest":digest(report)}


def verify_catalogue(state:EvidenceAtlas,doc:Mapping[str,Any],*,
                     receiver_expected_head:str,receiver_expected_fingerprint:str)->bool:
    if state.head!=receiver_expected_head or state.fingerprint!=receiver_expected_fingerprint:
        raise ValueError("receiver expected source pins do not match witness Ground")
    if not isinstance(doc,Mapping) or canonical(dict(doc))!=canonical(typed_catalogue(state)):
        raise ValueError("catalogue differs from reconstructed witnessed capabilities")
    return True


@dataclass(frozen=True)
class MixedFamilyAtlas:
    """Read-only adapter to COG002 VersionSpace; its affine-only certificate isn't used."""
    state:EvidenceAtlas
    claims:tuple[FamilyClaim,...]

    def __post_init__(self):
        if not isinstance(self.state,EvidenceAtlas) or len(self.claims)!=len(self.state.contexts):
            raise ValueError("typed catalogue missing source evidence")
        if self.claims!=tuple(identify(self.state,c) for c in self.state.contexts):
            raise ValueError("capability catalogue substitution")
        if len(self.claims)<2:raise ValueError("arbitration needs multiple capabilities")

    @classmethod
    def from_evidence(cls,state:EvidenceAtlas)->"MixedFamilyAtlas":
        return cls(state,tuple(identify(state,c) for c in state.contexts))

    @property
    def choices(self):
        return tuple(("learned_"+c.context,c.ground) for c in self.claims)

    @property
    def p(self)->int:return self.state.base.p

    @property
    def fingerprint(self)->str:
        return digest({"schema":SCHEMA+".mixed-arbitration-adapter",
                       "ground":self.state.base.fingerprint,"observation_root":self.state.head,
                       "claims":[c.fingerprint for c in self.claims],
                       "predicates_from":"COG002/adaptive_arbiter.PREDICATES"})

    def by_name(self,name:str):
        for key,ground in self.choices:
            if name==key:return ground
        raise ValueError("unknown source-ground capability")

    def point(self,v):return checked_point(self.p,v)

    def typed_certificate(self,policy,x)->dict[str,Any]:
        from adaptive_arbiter import Policy,predicate
        if not isinstance(policy,Policy):raise ValueError("invalid COG002 policy")
        src=self.point(x);branch=predicate(policy.feature,src,self.p)
        choice=policy.one if branch else policy.zero
        ground=self.by_name(choice)
        if isinstance(ground,Affine):
            old=compile_regions(ground)
            plan={"family":"affine","address":old.address,
                  "regions":[s.region for s in old.steps]}
        else:plan=ground.plan()
        report={"schema":SCHEMA+".typed-arbitration-certificate",
                "catalogue":self.fingerprint,"policy":{"feature":policy.feature,
                "zero":policy.zero,"one":policy.one},
                "input":list(src),"branch":branch,"selected":choice,
                "plan":plan,"output":list(ground.apply(src)),"source_root":self.state.head}
        return {**report,"digest":digest(report)}
