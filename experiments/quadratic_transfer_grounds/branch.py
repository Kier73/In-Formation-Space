"""TCN-004: phase-aware sparse branches of exact quadratic Gauss operators.

Quadratic operations are exact algebraic hypotheses encoded by TCN-003.
Nonquadratic diagonal phase gates require materializing the p-coordinate
state and attempting a bounded re-projection in an orthonormal chirp frame.
Never equate in-sample projection with evidence about a physical process.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math

import numpy as np

from cocycle import ExactOperator, ExactSchedule
from transfer import _prime


@dataclass(frozen=True)
class FrameFit:
    p: int
    a: int
    terms: tuple[tuple[int, complex], ...]
    total_energy: float
    retained_energy: float
    omitted_l2: float
    rank: int
    required_rank: int
    globally_min_required_rank: int
    candidates: int

    def relative_energy(self) -> float:
        return self.retained_energy / self.total_energy

    def summary(self) -> dict:
        return {'curvature': self.a, 'rank': self.rank,
                'required_rank_in_selected_frame': self.required_rank,
                'globally_min_required_rank': self.globally_min_required_rank,
                'retained_energy': self.retained_energy,
                'relative_energy': self.relative_energy(),
                'omitted_l2': self.omitted_l2,
                'candidate_frames': self.candidates,
                'scope': 'in-sample orthonormal projection; numerical arithmetic'}


def fit_frame(vector, *, p: int, max_terms: int, max_relative_omission: float = 0.1,
              search_frames: bool = True) -> FrameFit:
    """Best top-k orthogonal projection across p quadratic Fourier frames.

    For a fixed a, the states T_a|b> (b=0..p-1) are an orthonormal
    basis. Greedy top-k selection is the *optimal* rank-k approximation
    within that frame; the global search covers only this set of p bases.
    Cost: O(p^2 log p) if all curvatures searched, not logarithmic.
    """
    if not _prime(p) or type(max_terms) is not int or not 1 <= max_terms <= p:
        raise ValueError('prime p and a positive rank budget <=p required')
    if not isinstance(max_relative_omission, (int, float)) or not 0 <= max_relative_omission < 1:
        raise ValueError('max relative omitted norm must be in [0,1)')
    v = np.asarray(vector, dtype=np.complex128)
    if v.shape != (p,) or not np.isfinite(v).all():
        raise ValueError('finite complex p-vector required')
    total = float(np.vdot(v, v).real)
    if total <= 1e-28:
        raise ValueError('cannot frame-fit zero vector')
    x = np.arange(p, dtype=np.int64)
    xx = x*x % p
    candidates = range(p) if search_frames else (0,)
    best = None
    min_required = p
    for a in candidates:
        demodulated = v * np.exp(-2j*np.pi*(a*xx % p)/p)
        coeffs = np.fft.fft(demodulated) / math.sqrt(p)
        energies = np.abs(coeffs)**2
        ranked = np.argsort(-energies, kind='stable')
        top = ranked[:max_terms]
        kept = float(np.sum(energies[top]))
        # Parseval exact mathematically; avoid small floating negative residuals.
        omitted = math.sqrt(max(0.0, total-kept))
        cumulative = np.cumsum(energies[ranked])
        needed = min(p, int(np.searchsorted(cumulative,
                          total*(1-max_relative_omission**2)-1e-12)+1))
        min_required = min(min_required, needed)
        key = (omitted, -float(energies[ranked[0]]), a)
        if best is None or key < best[0]:
            best = (key, a, tuple((int(b), complex(coeffs[b])) for b in top),
                    kept, omitted, needed)
    assert best is not None
    _, a, terms, kept, omitted, needed = best
    return FrameFit(p,a,terms,total,kept,omitted,len(terms),needed,min_required,
                    p if search_frames else 1)


def gate_phases(p: int, kind: str, strength) -> np.ndarray:
    """Nonquadratic deterministic *unit-modulus* diagonal gates.

    cubic: omega^(strength*x^3) with integer strength mod p.
    harmonic: exp(i*strength*cos(2*pi*x/p)) with finite real strength.
    """
    if not _prime(p):
        raise ValueError('odd prime required')
    x = np.arange(p, dtype=np.int64)
    if kind == 'cubic' and type(strength) is int:
        return np.exp(2j*np.pi*((strength%p) * ((x*x%p)*x%p) %p)/p)
    if kind == 'harmonic' and isinstance(strength, (int, float)) and math.isfinite(strength):
        return np.exp(1j*strength*np.cos(2*np.pi*x/p))
    raise ValueError('unsupported gate or non-finite/incorrect strength')


@dataclass(frozen=True)
class SparseGround:
    """Vector approximately equal to U sum_b coefficient[b] T_a |b>.

    T_a comes from cocycle.ExactOperator.transfer(p,a). U has its *full*
    global phase and must be composed in the same order as dense execution.
    'error_l2_ideal' is a triangle-inequality bound in exact complex
    arithmetic using computed projection coefficients, NOT a directed-
    rounding machine certificate or a verified external-system guarantee.
    """
    p: int
    frame_a: int
    terms: tuple[tuple[int, complex], ...]
    outer: ExactOperator
    error_l2_ideal: float=0.0
    truncations: int=0
    provenance: tuple[str,...]=()

    @classmethod
    def quadratic(cls, p: int, frame_a: int, source_b: int, coefficient: complex=1+0j):
        if not _prime(p) or type(frame_a) is not int or type(source_b) is not int:
            raise ValueError('prime field and integer quadratic coordinates required')
        if not np.isfinite(coefficient) or abs(coefficient) < 1e-15:
            raise ValueError('finite nonzero coefficient required')
        return cls(p, frame_a%p, ((source_b%p,complex(coefficient)),),
                   ExactOperator.identity(p))

    @classmethod
    def from_vector(cls, v, p: int, *, max_terms: int, max_omission: float):
        fit = fit_frame(v, p=p, max_terms=max_terms, max_relative_omission=max_omission)
        if fit.omitted_l2 > max_omission*math.sqrt(fit.total_energy)+1e-10:
            raise ValueError('rank budget cannot represent initial state to requested tolerance')
        return cls(p,fit.a,fit.terms,ExactOperator.identity(p),fit.omitted_l2,1)

    def after_operator(self, op: ExactOperator):
        if not isinstance(op, ExactOperator) or op.p != self.p:
            raise ValueError('operator field mismatch')
        return SparseGround(self.p,self.frame_a,self.terms,op.compose(self.outer),
                            self.error_l2_ideal,self.truncations,self.provenance)

    def after_schedule(self, pattern: tuple[int,...], steps: int):
        sch = ExactSchedule(self.p, pattern)
        op, products = sch.navigate(steps)
        return self.after_operator(op),products

    def amplitude(self, target: int) -> complex:
        if type(target) is not int:
            raise ValueError('target coordinate must be an integer')
        kernel = self.outer.compose(ExactOperator.transfer(self.p,self.frame_a))
        return sum(coeff*kernel.basis_amplitude(b,target).complex_value()
                   for b,coeff in self.terms)

    def dense(self) -> np.ndarray:
        return np.array([self.amplitude(y) for y in range(self.p)],dtype=complex)

    def after_gate(self, kind: str, strength, *, max_terms: int,
                   max_omission: float, search_frames: bool=True):
        """Transactional: no mutation; refuse if rank/error budget not met.

        Error bound holds by unitarity: ||D v - D approx|| = old error;
        project approximate new vector with error delta -> total <= old+delta.
        For exact mathematically computed coefficients; machine precision is
        separately checked through dense comparisons.
        """
        if not isinstance(max_omission, (float,int)) or not 0 <= max_omission < 1:
            raise ValueError('max_omission must be in [0,1)')
        phase = gate_phases(self.p,kind,strength)
        materialized = phase*self.dense()
        fit = fit_frame(materialized,p=self.p,max_terms=max_terms,
                        max_relative_omission=max_omission,search_frames=search_frames)
        proposed_bound = self.error_l2_ideal + fit.omitted_l2
        allowed = proposed_bound <= max_omission + 1e-10
        receipt = {'schema':'ifs.phase-branch-admission.v1','gate':kind,
                   'strength':strength,'p':self.p,
                   'incoming_rank':len(self.terms),'selected_frame':fit.a,
                   'candidate_frames':fit.candidates,'kept_rank':fit.rank,
                   'rank_required_for_single_step':fit.required_rank,
                   'minimum_rank_over_scanned_frames':fit.globally_min_required_rank,
                   'omitted_l2':fit.omitted_l2,
                   'prior_error_l2_ideal':self.error_l2_ideal,
                   'projected_total_error_l2_ideal':proposed_bound,
                   'budget_l2':max_omission,
                   'status':'admitted' if allowed else 'refused',
                   'scope':'in-sample mathematical projection, no external observation'}
        digest = sha256(json.dumps(receipt,sort_keys=True,separators=(',',':'),
                                   allow_nan=False).encode()).hexdigest()
        receipt['sha256']=digest
        if not allowed:
            return None,receipt
        return SparseGround(self.p,fit.a,fit.terms,ExactOperator.identity(self.p),
                            proposed_bound,self.truncations+1,
                            self.provenance+(digest,)),receipt


def dense_quadratic_reference(p: int, pattern: tuple[int,...], steps: int, vector):
    """Independent per-step FFT baseline for small step counts ONLY."""
    v=np.asarray(vector,dtype=np.complex128).copy()
    if v.shape!=(p,) or not np.isfinite(v).all():
        raise ValueError('finite p-vector required')
    x=np.arange(p)
    for i in range(steps):
        # np.ifft uses + sign, normalized by p. Multiplying by sqrt(p)
        # reproduces F_{y,x}=omega^(xy)/sqrt(p).
        v=np.sqrt(p)*np.fft.ifft(v)*np.exp(2j*np.pi*((pattern[i%len(pattern)]*(x*x%p))%p)/p)
    return v


def harmonic_taylor_modes(strength: float, order: int):
    """Truncated Fourier modes for exp(i*g*cos(theta)), independent of p.

    cos(theta)^r = 2^-r sum_j C(r,j) exp(i*(r-2j)*theta).
    The uniform pointwise Taylor remainder is at most
      exp(abs(g))*abs(g)**(order+1)/(order+1)!
    for real g, in exact arithmetic. Caller carries this extra error.
    """
    if not isinstance(strength,(int,float)) or not math.isfinite(strength) or abs(strength)>4:
        raise ValueError('finite real harmonic strength with abs<=4 required')
    if type(order) is not int or not 0<=order<=40:
        raise ValueError('Taylor order must be integer in [0,40]')
    coeffs={}
    for r in range(order+1):
        scale=(1j*strength/2)**r/math.factorial(r)
        for j in range(r+1):
            k=r-2*j
            coeffs[k]=coeffs.get(k,0j)+scale*math.comb(r,j)
    remainder=(math.exp(abs(strength))*abs(strength)**(order+1)/math.factorial(order+1))
    return coeffs,remainder


@dataclass(frozen=True)
class StructuredState:
    """Sparse sum in either a delta basis or one quadratic Fourier basis.

    Modes are mutually orthonormal, enabling explicit l2 bounds. Unlike a
    projective stabilizer ray, complex coefficients retain relative phase.
    """
    p: int
    kind: str # 'delta' or 'flat'
    a: int | None
    terms: tuple[tuple[int,complex],...]
    error_l2_ideal: float=0.0
    steps_logged: int=0

    def __post_init__(self):
        if not _prime(self.p) or self.kind not in ('delta','flat'):
            raise ValueError('prime field with flat/delta basis required')
        if self.kind=='flat' and type(self.a) is not int:
            raise ValueError('flat frame requires integer a')
        if self.kind=='delta' and self.a is not None:
            raise ValueError('delta frame has no curvature')
        if any(type(b) is not int or not np.isfinite(v) for b,v in self.terms):
            raise ValueError('finite coefficient and integer coordinate required')
        if len({b%self.p for b,_ in self.terms}) != len(self.terms) or len(self.terms)>self.p:
            raise ValueError('no duplicate modes or >p terms')
        if not math.isfinite(self.error_l2_ideal) or self.error_l2_ideal<0:
            raise ValueError('finite nonnegative l2 error bound required')
        if type(self.steps_logged) is not int or self.steps_logged<0:
            raise ValueError('nonnegative procedural step count required')

    @classmethod
    def flat(cls,p,a,b,coefficient=1+0j):
        return cls(p,'flat',a%p,((b%p,complex(coefficient)),))

    @classmethod
    def delta(cls,p,b,coefficient=1+0j):
        return cls(p,'delta',None,((b%p,complex(coefficient)),))

    def norm(self):
        return math.sqrt(sum(abs(v)**2 for _,v in self.terms))

    def value(self,y):
        y=int(y)%self.p
        if self.kind=='delta':
            return sum(v for b,v in self.terms if b%self.p==y)
        return sum(v*np.exp(2j*np.pi*((self.a*y*y+b*y)%self.p)/self.p)
                   for b,v in self.terms)/math.sqrt(self.p)

    def dense(self):
        return np.array([self.value(y) for y in range(self.p)],dtype=complex)

    def after_operator(self,op: ExactOperator):
        """Map each branch through TCN-003 without materializing p amplitudes.

        For nonzero B=(M)[0,1], K_M|x> is a flat quadratic with a'=D/(2B),
        b'=-x/B and scalar phase K_M(y=0,x)*sqrt(p).
        Otherwise it is a phase-weighted delta at y=A*x.
        """
        if not isinstance(op,ExactOperator) or op.p!=self.p:
            raise ValueError('matched exact quadratic operator required')
        kernel=op.compose(ExactOperator.transfer(self.p,self.a)) if self.kind=='flat' else op
        A,B=kernel.m[0]
        C,D=kernel.m[1]
        terms=[]
        if B:
            new_a=D*pow(2*B,-1,self.p)%self.p
            for b,v in self.terms:
                new_b=-b*pow(B,-1,self.p)%self.p
                scale=kernel.basis_amplitude(b,0).complex_value()*math.sqrt(self.p)
                terms.append((new_b, v*scale))
            return StructuredState(self.p,'flat',new_a,tuple(terms),
                                   self.error_l2_ideal,self.steps_logged)
        for b,v in self.terms:
            y=A*b%self.p
            scale=kernel.basis_amplitude(b,y).complex_value()
            terms.append((y,v*scale))
        return StructuredState(self.p,'delta',None,tuple(terms),
                               self.error_l2_ideal,self.steps_logged)

    def after_schedule(self,pattern,steps):
        op,products=ExactSchedule(self.p,tuple(pattern)).navigate(steps)
        state=self.after_operator(op)
        return StructuredState(self.p,state.kind,state.a,state.terms,
                               state.error_l2_ideal,self.steps_logged+steps),products

    def after_harmonic(self,strength,*,taylor_order=10,max_terms=7,
                       absolute_error_budget=0.1):
        """Procedural nonquadratic lift with no p-point state reconstruction.

        On flat frames, Fourier characters convolve with truncated Taylor
        coefficients. On delta frames, the gate simply adjusts each scalar.
        A rejected rank/error budget returns None, never a new active state.
        """
        if type(max_terms) is not int or not 1<=max_terms<=self.p:
            raise ValueError('max_terms in [1,p] required')
        if not isinstance(absolute_error_budget,(int,float)) or not 0<=absolute_error_budget<math.inf:
            raise ValueError('finite nonnegative absolute error budget required')
        coefficients,remainder=harmonic_taylor_modes(strength,taylor_order)
        if self.kind=='delta':
            if len(self.terms)>max_terms:
                raise ValueError('delta state exceeds requested rank budget')
            new=tuple((b,v*np.exp(1j*strength*np.cos(2*np.pi*b/self.p)))
                      for b,v in self.terms)
            added=0.0
            exact=True
        else:
            combined={}
            for b,v in self.terms:
                for shift,h in coefficients.items():
                    j=(b+shift)%self.p
                    combined[j]=combined.get(j,0j)+v*h
            ranked=sorted(combined.items(),key=lambda item:(-abs(item[1]),item[0]))
            new=tuple(ranked[:max_terms])
            # Exact projection residual of the *Taylor approximation* in a
            # common orthonormal basis. Errors sum by triangle inequality.
            added=math.sqrt(sum(abs(v)**2 for _,v in ranked[max_terms:]))
            added+=remainder*self.norm()
            exact=False
        new_bound=self.error_l2_ideal+added
        accepted=new_bound<=absolute_error_budget+1e-12
        record={'schema':'ifs.procedural-nonquadratic-ground.v1','gate':'harmonic',
                'p':self.p,'input_kind':self.kind,'input_modes':len(self.terms),
                'generated_taylor_modes':len(coefficients),'taylor_order':taylor_order,
                'maximum_uniform_taylor_remainder':remainder,
                'kept_modes':len(new),'l2_truncation_plus_taylor_bound':added,
                'cumulative_error_bound_ideal':new_bound,
                'budget':absolute_error_budget,
                'status':'admitted' if accepted else 'refused',
                'procedural_without_full_state':True,
                'note':'finite numerical precision not enclosed; gate and schedule are premises'}
        record['sha256']=sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if not accepted:
            return None,record
        return StructuredState(self.p,self.kind,self.a,new,new_bound,self.steps_logged),record
