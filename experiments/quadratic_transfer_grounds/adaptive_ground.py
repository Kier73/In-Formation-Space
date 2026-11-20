"""TCN-005: intention-scoped choice of an orthogonal sparse Ground or phase carrier.

This is a compiler for a declared polynomial/harmonic gate followed by a
known quadratic schedule, not an inference engine for unknown physical laws.
The carrier describes an exact mathematical phase function, while rendering
complex amplitudes remains numerical. Charge discovery, powering and readout
costs separately.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import numpy as np
from branch import StructuredState, fit_frame, gate_phases
from cocycle import ExactOperator, ExactSchedule


def _valid_budget(value, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError(f'{name} must be finite and nonnegative')


def _phase(p, cubic, harmonic, indices):
    x = np.asarray(indices, dtype=np.int64) % p
    residues = (int(cubic) % p) * ((x*x % p)*x % p) % p
    return np.exp(2j*np.pi*residues/p + 1j*harmonic*np.cos(2*np.pi*x/p))


@dataclass(frozen=True)
class PhaseCarrier:
    """A phase gauge on one input frame, followed by a full-phase TCN-003 operator.

    Cubic and harmonic phase gates in the same frame commute, and so can be
    combined without increasing description size. Noncommuting operations
    at a later frame must be reanchored explicitly.
    """
    base: StructuredState
    cubic: int = 0
    harmonic: float = 0.0
    outer: ExactOperator | None = None
    interventions: int = 0

    def __post_init__(self):
        if not isinstance(self.base, StructuredState):
            raise ValueError('StructuredState required')
        if (type(self.cubic) is not int or
                not isinstance(self.harmonic, (int, float)) or not math.isfinite(self.harmonic)):
            raise ValueError('integer cubic and finite harmonic required')
        if type(self.interventions) is not int or self.interventions < 0:
            raise ValueError('nonnegative intervention count required')
        if self.outer is None:
            object.__setattr__(self, 'outer', ExactOperator.identity(self.base.p))
        if not isinstance(self.outer, ExactOperator) or self.outer.p != self.base.p:
            raise ValueError('operator field mismatch')
        object.__setattr__(self, 'cubic', self.cubic % self.base.p)

    @classmethod
    def start(cls, base):
        return cls(base)

    def apply_gate(self, kind, strength):
        if self.outer != ExactOperator.identity(self.base.p):
            raise ValueError('a new gate after quadratic transport requires explicit re-anchoring')
        if kind == 'cubic' and type(strength) is int:
            return PhaseCarrier(self.base, (self.cubic+strength)%self.base.p,
                                self.harmonic, self.outer, self.interventions+1)
        if kind == 'harmonic' and isinstance(strength, (int,float)) and math.isfinite(strength):
            total = self.harmonic+strength
            if not math.isfinite(total):
                raise ValueError('nonfinite combined harmonic strength')
            return PhaseCarrier(self.base,self.cubic,total,self.outer,self.interventions+1)
        raise ValueError('unsupported phase gate')

    def after_operator(self, op):
        if not isinstance(op, ExactOperator) or op.p != self.base.p:
            raise ValueError('operator field mismatch')
        return PhaseCarrier(self.base,self.cubic,self.harmonic,
                            op.compose(self.outer),self.interventions)

    def after_schedule(self, pattern, steps):
        op, products = ExactSchedule(self.base.p, tuple(pattern)).navigate(steps)
        return self.after_operator(op), products

    def _source_value(self, x):
        return self.base.value(x)*complex(_phase(self.base.p,self.cubic,self.harmonic,[x])[0])

    def _input_vector(self):
        # Temporary O(p) rendering at the query boundary, never retained in Ground.
        return self.base.dense()*_phase(self.base.p,self.cubic,self.harmonic,
                                        np.arange(self.base.p))

    def estimated_query_work(self, targets):
        return len(targets)*len(self.base.terms)*(1 if self.outer.m[0][1]==0 else self.base.p)

    def amplitude(self, coordinate):
        if type(coordinate) is not int:
            raise ValueError('integer coordinate required')
        p,y=self.base.p,coordinate%self.base.p
        a,b=self.outer.m[0]
        if b==0:
            x=pow(a,-1,p)*y%p
            return self.outer.basis_amplitude(x,y).complex_value()*self._source_value(x)
        return self.outer.apply_coordinate(self._input_vector(),y)

    def dense(self):
        # Diagnostic; O(p^2) materialization, not a claimed cheap shortcut.
        return np.array([self.amplitude(y) for y in range(self.base.p)])

    def reanchor(self, *, max_terms, budget, search_frames=True):
        """An explicit expensive exit into a chirp basis; no mutation on failure."""
        _valid_budget(budget, 'budget')
        fit=fit_frame(self.dense(),p=self.base.p,max_terms=max_terms,
                      max_relative_omission=min(0.999999,budget),
                      search_frames=search_frames)
        bound=self.base.error_l2_ideal+fit.omitted_l2
        if bound>budget+1e-10:
            return None, {'decision':'refused',
                          'minimum_rank_in_scanned_frames':fit.globally_min_required_rank,
                          'candidate_frames':fit.candidates,'proposed_error':bound}
        state=StructuredState(self.base.p,'flat',fit.a,fit.terms,
                              bound,self.base.steps_logged)
        return state, {'decision':'admitted','candidate_frames':fit.candidates,
                       'curvature':fit.a,'error_bound_ideal':bound}


@dataclass(frozen=True)
class GroundChoice:
    decision: str
    representation: str
    state: StructuredState | PhaseCarrier | None
    estimated_query_work: int
    products: int
    approximation_error_bound: float | None
    rationale: str
    sparse_probe: dict
    requested_coordinates: tuple[int, ...]

    def amplitudes(self):
        if self.state is None:
            raise ValueError('no admissible representation under budget')
        return tuple(self.state.value(y) if isinstance(self.state,StructuredState)
                     else self.state.amplitude(y) for y in self.requested_coordinates)


def choose_ground(base, kind, strength, pattern, steps, coordinates, *,
                  max_terms=7, error_budget=.01, max_query_work=100000,
                  exact_gate=False, cubic_frame_scan=False, taylor_order=12):
    """Select per observable; refuse when no candidate meets work/error budget.

    Numerical terms count as an ideal-arithmetic approximation bound only.
    Discovery cost (especially exhaustive curvature scans) is separately
    identified and is not included in estimated query work.
    """
    if not isinstance(base,StructuredState):
        raise ValueError('base must be a StructuredState')
    if type(max_terms) is not int or not 1<=max_terms<=base.p:
        raise ValueError('rank budget must be in [1,p]')
    _valid_budget(error_budget,'error_budget')
    if type(max_query_work) is not int or max_query_work<0:
        raise ValueError('max_query_work must be nonnegative integer')
    if type(exact_gate) is not bool or type(cubic_frame_scan) is not bool:
        raise ValueError('exact_gate and cubic_frame_scan must be booleans')
    try:
        targets=tuple(coordinates)
    except TypeError as exc:
        raise ValueError('coordinates must be iterable') from exc
    if (not targets or len(targets)>base.p or
            any(type(x) is not int or x<0 or x>=base.p for x in targets) or
            len(set(targets))!=len(targets)):
        raise ValueError('distinct coordinates in [0,p) required')
    if type(steps) is not int or steps<0:
        raise ValueError('nonnegative step count required')
    op,products=ExactSchedule(base.p,tuple(pattern)).navigate(steps)
    carrier=PhaseCarrier.start(base).apply_gate(kind,strength).after_operator(op)
    sparse=None
    probe={'status':'not_attempted','cost_note':'no frame search performed'}
    if kind=='harmonic' and not exact_gate:
        if type(taylor_order) is not int or not 0<=taylor_order<=40:
            raise ValueError('Taylor order must be in [0,40]')
        if abs(float(strength))<=4:
            sparse,receipt=base.after_harmonic(strength,taylor_order=taylor_order,
                                               max_terms=max_terms,
                                               absolute_error_budget=error_budget)
            probe={'status':receipt['status'],
                   'projected_error':receipt['cumulative_error_bound_ideal'],
                   'taylor_order':taylor_order,
                   'generated_modes':receipt['generated_taylor_modes'],
                   'cost_note':'procedural Fourier-Taylor; no full frame scan'}
    elif kind=='cubic' and cubic_frame_scan and not exact_gate:
        dense_input=base.dense()*gate_phases(base.p,'cubic',strength)
        fit=fit_frame(dense_input,p=base.p,max_terms=max_terms,
                      max_relative_omission=min(.999999,error_budget),
                      search_frames=True)
        bound=base.error_l2_ideal+fit.omitted_l2
        if bound<=error_budget+1e-10:
            sparse=StructuredState(base.p,'flat',fit.a,fit.terms,bound,base.steps_logged)
        probe={'status':'admitted' if sparse is not None else 'refused',
               'projected_error':bound,'minimum_rank':fit.globally_min_required_rank,
               'cost_note':'p chirp frames; O(p^2 log p) discovery'}
    if sparse is not None:
        carried=sparse.after_operator(op)
        work=len(carried.terms)*len(targets)
        if work<=max_query_work:
            return GroundChoice('admitted','sparse',carried,work,products,
                                carried.error_l2_ideal,
                                'orthogonal approximation within ideal-arithmetic bound',
                                probe,targets)
    work=carrier.estimated_query_work(targets)
    if work<=max_query_work and carrier.base.error_l2_ideal<=error_budget+1e-12:
        return GroundChoice('admitted','carrier',carrier,work,products,
                            carrier.base.error_l2_ideal,
                            'preserve declared phase; charge cost at readout',
                            probe,targets)
    return GroundChoice('refused','none',None,min(work,max_query_work+1),
                        products,None,'no candidate meets work and error budgets',
                        probe,targets)


def choice_receipt(base,kind,strength,pattern,steps,coordinates,**options):
    """Replayable computational witness; SHA-256 is integrity, not trust."""
    from witness import state_record
    choice=choose_ground(base,kind,strength,pattern,steps,coordinates,**options)
    values=choice.amplitudes() if choice.state is not None else ()
    rec={'schema':'ifs.adaptive-ground.v1','base':state_record(base),
         'gate':{'kind':kind,'strength':float(strength).hex() if kind=='harmonic' else strength},
         'pattern':list(pattern),'steps_decimal':str(steps),
         'coordinates':list(coordinates),
         'options':{'max_terms':options.get('max_terms',7),
                    'error_budget':float(options.get('error_budget',.01)).hex(),
                    'max_query_work':options.get('max_query_work',100000),
                    'exact_gate':options.get('exact_gate',False),
                    'cubic_frame_scan':options.get('cubic_frame_scan',False),
                    'taylor_order':options.get('taylor_order',12)},
         'choice':{'decision':choice.decision,'representation':choice.representation,
                   'work':choice.estimated_query_work,'products':choice.products,
                   'error_bound':choice.approximation_error_bound,
                   'sparse_probe':choice.sparse_probe,'rationale':choice.rationale},
         'predictions':[[float(z.real).hex(),float(z.imag).hex()] for z in values],
         'scope':'conditional mathematical description, not external-system observation'}
    rec['sha256']=sha256(json.dumps(rec,sort_keys=True,separators=(',',':'),
                                  allow_nan=False).encode()).hexdigest()
    return rec


def verify_choice_receipt(rec, *, dense_check_limit=40):
    """Recompute the Ground, and check against direct FFT for short schedules."""
    from witness import restore_state
    from branch import dense_quadratic_reference
    try:
        expected_keys={'schema','base','gate','pattern','steps_decimal','coordinates',
                       'options','choice','predictions','scope','sha256'}
        if not isinstance(rec,dict) or set(rec)!=expected_keys or rec['schema']!='ifs.adaptive-ground.v1':
            return False
        digest=sha256(json.dumps({k:v for k,v in rec.items() if k!='sha256'},
                                  sort_keys=True,separators=(',',':'),
                                  allow_nan=False).encode()).hexdigest()
        if digest!=rec['sha256']:
            return False
        base=restore_state(rec['base'])
        g,opts=rec['gate'],rec['options']
        if (set(g)!={'kind','strength'} or set(opts)!={'max_terms','error_budget',
                'max_query_work','exact_gate','cubic_frame_scan','taylor_order'}):
            return False
        strength=float.fromhex(g['strength']) if g['kind']=='harmonic' else g['strength']
        n=rec['steps_decimal']
        if (type(n) is not str or not n.isascii() or not n.isdigit() or
                len(n)>120 or (len(n)>1 and n[0]=='0')):
            return False
        steps=int(n)
        params={'max_terms':opts['max_terms'],
                'error_budget':float.fromhex(opts['error_budget']),
                'max_query_work':opts['max_query_work'],
                'exact_gate':opts['exact_gate'],
                'cubic_frame_scan':opts['cubic_frame_scan'],
                'taylor_order':opts['taylor_order']}
        expected=choice_receipt(base,g['kind'],strength,tuple(rec['pattern']),
                                steps,tuple(rec['coordinates']),**params)
        if expected!=rec:
            return False
        if rec['choice']['decision']=='refused':
            return rec['predictions']==[]
        v=gate_phases(base.p,g['kind'],strength)*base.dense()
        pattern=tuple(rec['pattern'])
        if steps<=dense_check_limit:
            reference=dense_quadratic_reference(base.p,pattern,steps,v)
        else:
            op,_=ExactSchedule(base.p,pattern).navigate(steps)
            reference=op.apply_full(v)
        predicted=[complex(float.fromhex(a),float.fromhex(b)) for a,b in rec['predictions']]
        error=max(abs(z-reference[i]) for z,i in zip(predicted,rec['coordinates']))
        return bool(error<=rec['choice']['error_bound']+1e-8)
    except (ValueError,TypeError,KeyError,OverflowError,ArithmeticError,
            AttributeError,IndexError):
        return False
