"""RCG-005: source-pinned, nonlinearly conjugated sparse neural orbit.

The body is E-CPU observer-host execution, not an animal body. The mind is a
procedurally realized, exact finite-field polynomial automorphism around the
RCG-004 sparse connectome Ground. A source-owned *vector* annihilator witnesses
all requested readouts; one quotient-polynomial jump serves them together.

This is a constructed, reversible nonlinear model, NOT a learned connectome
brain or a general fast-forwarding method for arbitrary neural dynamics.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from temporal_ground import (
    SparseTransfer, TemporalGroundRefused, MODULUS, MAX_TICK,
    berlekamp_massey, _multiply_mod, hash_object,
)

SCHEMA = 'ifs.rcg005.nonlin-conjugate-vector-ground.v1'
MAX_DEPTH = 6


def require(ok: bool, what: str) -> None:
    if not ok:
        raise TemporalGroundRefused(what)


def _alpha(ground: str, coordinates: tuple[str, ...], seed: str, i: int, p: int) -> int:
    material = f'{SCHEMA}:{ground}:{seed}:{i}:{coordinates[i]}:{coordinates[i+1]}'.encode()
    return int.from_bytes(sha256(material).digest(), 'big') % (p - 1) + 1


@dataclass(frozen=True)
class ConjugatedGround:
    """E and D=E^-1 are a sequence of triangular polynomial coupling cells.

    E: for i from 0 to d-1, add alpha_i * x[i+1]**2 to x[i]; all other
    coordinates unchanged. D executes these inverse cells in reverse order.
    F(x) = D(M E(x)) is a polynomial recurrent neural map over GF(p).
    No invertibility of M is needed; all E_i are invertible by construction.
    """
    operator: SparseTransfer
    coordinates: tuple[str, ...]
    seed: str = 'rcg005-procedural-neural-v1'

    def __post_init__(self) -> None:
        op = self.operator
        require(isinstance(op, SparseTransfer) and op.field == MODULUS,
                'expected source-pinned finite-field sparse operator')
        require(isinstance(self.coordinates, tuple) and 2 <= len(self.coordinates) <= MAX_DEPTH+1 and
                len(set(self.coordinates)) == len(self.coordinates) and
                all(isinstance(x, str) and x in op.names for x in self.coordinates) and
                self.coordinates[0] == op.source, 'unadmitted nonlinear coordinate chain')
        require(type(self.seed) is str and 1 <= len(self.seed) <= 96 and
                all(32 <= ord(c) < 127 for c in self.seed), 'noncanonical procedural seed')

    @property
    def dimension(self) -> int:
        return len(self.coordinates)

    @property
    def positions(self) -> tuple[int, ...]:
        return tuple(self.operator.names.index(name) for name in self.coordinates)

    @property
    def alphas(self) -> tuple[int, ...]:
        return tuple(_alpha(self.operator.ground, self.coordinates, self.seed, i,
                            self.operator.field) for i in range(self.dimension-1))

    @property
    def description(self) -> dict[str, Any]:
        return {'schema': SCHEMA+'.model.v1', 'ground': self.operator.ground,
                'source_blob': self.operator.blob, 'source': self.operator.source,
                'edge_kind': self.operator.kind, 'dimension': self.operator.n,
                'edge_count': self.operator.sparse_edge_count,
                'field': self.operator.field, 'coordinates': list(self.coordinates),
                'seed': self.seed, 'alphas': list(self.alphas),
                'encoder': 'triangular-shear-squares-in-ascending-coordinate-order',
                'decoder': 'inverse-triangular-shear-squares-in-descending-order',
                'transition': 'decode(linear_sparse_step(encode(state)))',
                'initial': 'unit-vector-at-coordinate-0'}

    @property
    def fingerprint(self) -> str:
        return hash_object(self.description)

    def initial(self) -> list[int]:
        x = [0] * self.operator.n
        x[self.positions[0]] = 1
        return x

    def _valid(self, x: list[int]) -> None:
        require(type(x) is list and len(x) == self.operator.n and
                all(type(v) is int and 0 <= v < self.operator.field for v in x),
                'invalid finite-field vector')

    def encode(self, x: list[int]) -> list[int]:
        self._valid(x)
        y = x.copy()
        p = self.operator.field
        positions, coefficients = self.positions, self.alphas
        for i, c in enumerate(coefficients):
            a,b = positions[i], positions[i+1]
            y[a] = (y[a] + c * y[b] * y[b]) % p
        return y

    def decode(self, y: list[int]) -> list[int]:
        self._valid(y)
        x = y.copy()
        p = self.operator.field
        positions, coefficients = self.positions, self.alphas
        for i in reversed(range(len(coefficients))):
            a,b = positions[i], positions[i+1]
            x[a] = (x[a] - coefficients[i] * x[b] * x[b]) % p
        return x

    def step(self, x: list[int]) -> list[int]:
        return self.decode(self.operator.step(self.encode(x)))

    def direct_at(self, tick: int) -> int:
        require(type(tick) is int and 0 <= tick <= 2048,
                'direct nonlinear iteration is bounded: distant ticks require navigation')
        x = self.initial()
        for _ in range(tick):
            x = self.step(x)
        return x[self.positions[0]]

    def readout_decode(self, coordinates: dict[str, int]) -> int:
        """Reconstruct one observable without decoding or materializing n state slots."""
        require(type(coordinates) is dict and set(coordinates) == set(self.coordinates) and
                all(type(x) is int and 0 <= x < self.operator.field for x in coordinates.values()),
                'missing or malformed coupled latent readout')
        values = [coordinates[name] for name in self.coordinates]
        for i in reversed(range(len(self.alphas))):
            values[i] = (values[i] - self.alphas[i]*values[i+1]**2) % self.operator.field
        return values[0]


def _probe(op: SparseTransfer, number: int) -> tuple[int, ...]:
    """Deterministic challenge projection; randomness selects a candidate, not proof."""
    require(type(number) is int and 0 <= number <= 7, 'projection count budget')
    p = op.field
    return tuple(1 + int.from_bytes(sha256(
        f'{SCHEMA}:projection:{op.ground}:{op.source}:{op.kind}:{number}:{i}'.encode()
    ).digest(), 'big') % (p-1) for i in range(op.n))


def _state_annihilator(states: list[list[int]], coefficients: tuple[int, ...], p: int) -> bool:
    r=len(coefficients)
    if r<1 or len(states)<r+1:
        return False
    for j in range(len(states[0])):
        if (states[r][j] - sum(coefficients[i]*states[r-1-i][j]
                               for i in range(r))) % p:
            return False
    return True


def prepare_shared(ground: ConjugatedGround, *, attempts: int = 4) -> dict[str, Any]:
    """Train BM candidate on source orbit; certify full-vector annihilation.

    A vector equality q(M) e_source=0 guarantees M^t q(M)e_source=0 for every
    t, i.e. the same recurrence controls *every* target coordinate. This
    fails closed if up to four deterministic projections miss the order.
    """
    require(isinstance(ground, ConjugatedGround) and
            type(attempts) is int and 1 <= attempts <= 8, 'unadmitted preparation')
    op=ground.operator
    seed=ground.encode(ground.initial())
    require(seed == ground.initial(), 'initial chart does not preserve source basis')
    p,n=op.field,op.n
    out=[]
    basis=[]
    projections=[_probe(op,i) for i in range(attempts)]
    for index in range(2*n):
        if index<=n:
            basis.append(seed.copy())
        out.append(tuple(sum(a*b for a,b in zip(pr,seed))%p for pr in projections))
        seed=op.step(seed)
    accepted=None
    for index in range(attempts):
        coefficients=berlekamp_massey([row[index] for row in out],p)
        if len(coefficients)<=n and _state_annihilator(basis,coefficients,p):
            accepted=(index,coefficients)
            break
    require(accepted is not None,'no globally certified vector annihilator; insufficient projections')
    probe_index,coefficients=accepted
    r=len(coefficients)
    positions=ground.positions
    terms={name:[basis[k][pos] for k in range(r)]
           for name,pos in zip(ground.coordinates,positions)}
    body={'schema':SCHEMA+'.certificate.v1','model':ground.description,
          'model_digest':ground.fingerprint,'recurrence_degree':r,
          'coefficients':list(coefficients),'initial_terms':terms,
          'projection_index':probe_index,'training_terms':2*n,
          'assurance':'receiver-owned-global-vector-annihilator-q(M)e0=0',
          'navigation':'shared-quotient-polynomial-for-all-requested-coordinates'}
    return {**body,'digest':hash_object(body)}


def verify_shared(ground: ConjugatedGround, certificate: dict[str, Any]) -> None:
    """Independent of producer BM/probe; rederive q(M)e0 and readout inputs."""
    require(isinstance(ground,ConjugatedGround) and
            type(certificate) is dict and set(certificate) == {
                'schema','model','model_digest','recurrence_degree','coefficients',
                'initial_terms','projection_index','training_terms','assurance',
                'navigation','digest'}, 'malformed shared neural certificate')
    op=ground.operator
    r=certificate['recurrence_degree']
    coeff=certificate['coefficients']
    require(certificate['schema']==SCHEMA+'.certificate.v1' and
            certificate['model']==ground.description and
            certificate['model_digest']==ground.fingerprint and
            type(r) is int and 1<=r<=op.n and
            type(coeff) is list and len(coeff)==r and
            all(type(v) is int and 0<=v<op.field for v in coeff) and
            type(certificate['projection_index']) is int and
            0<=certificate['projection_index']<8 and
            certificate['training_terms']==2*op.n and
            certificate['assurance']=='receiver-owned-global-vector-annihilator-q(M)e0=0' and
            certificate['navigation']=='shared-quotient-polynomial-for-all-requested-coordinates' and
            type(certificate['initial_terms']) is dict and
            set(certificate['initial_terms'])==set(ground.coordinates) and
            all(type(vals) is list and len(vals)==r and
                all(type(v) is int and 0<=v<op.field for v in vals)
                for vals in certificate['initial_terms'].values()) and
            certificate['digest']==hash_object({k:v for k,v in certificate.items() if k!='digest'}),
            'source or certificate field identity refused')
    state=ground.encode(ground.initial())
    basis=[]
    for _ in range(r+1):
        basis.append(state)
        state=op.step(state)
    require(_state_annihilator(basis,tuple(coeff),op.field),
            'full-vector source Krylov annihilator mismatch')
    for name,pos in zip(ground.coordinates,ground.positions):
        expected=[basis[k][pos] for k in range(r)]
        require(certificate['initial_terms'][name]==expected,
                'source-pinned initial terms disagree')


def quotient_power(c: tuple[int, ...], p: int, tick: int) -> tuple[list[int],int]:
    """Single polynomial power shared by every linear readout of a Ground."""
    require(type(tick) is int and 0<=tick<=MAX_TICK, 'unadmitted distant tick')
    require(type(c) is tuple and 1<=len(c)<=1024 and
            all(type(z) is int and 0<=z<p for z in c), 'invalid recurrence')
    r=len(c)
    if tick<r:
        return [int(i==tick) for i in range(r)],0
    poly=[1]+[0]*(r-1)
    base=([c[0]] if r==1 else [0,1]+[0]*(r-2))
    muls=0
    while tick:
        if tick&1:
            poly=_multiply_mod(poly,base,c,p)
            muls+=1
        tick>>=1
        if tick:
            base=_multiply_mod(base,base,c,p)
            muls+=1
    return poly,muls


def navigate(ground: ConjugatedGround,certificate:dict[str,Any],tick:int,
             *,trusted_certificate:bool=False)->dict[str,Any]:
    """Trust flag means *verified in this receiver policy*; caller owns it."""
    if not trusted_certificate:
        verify_shared(ground,certificate)
    require(type(tick) is int and 0<=tick<=MAX_TICK,'unadmitted nonlinear temporal coordinate')
    c=tuple(certificate['coefficients'])
    polynomial,products=quotient_power(c,ground.operator.field,tick)
    latent={name:sum(a*b for a,b in zip(polynomial,certificate['initial_terms'][name]))%ground.operator.field
            for name in ground.coordinates}
    output=ground.readout_decode(latent)
    body={'schema':SCHEMA+'.navigation.v1','model_digest':ground.fingerprint,
          'certificate_digest':certificate['digest'],'tick':tick,'field':ground.operator.field,
          'latent_readouts':latent,'nonlinear_readout':output,'polynomial_products':products,
          'requested_coordinate_count':ground.dimension,
          'intermediate_logical_steps_materialized':0,
          'method':'source-vector-annihilator-one-quotient-power-plus-procedural-decoder'}
    return {**body,'digest':hash_object(body)}


def verify_result(ground: ConjugatedGround,certificate:dict[str,Any],receipt:dict[str,Any]) -> None:
    verify_shared(ground,certificate)
    require(type(receipt) is dict and type(receipt.get('tick')) is int and
            receipt == navigate(ground,certificate,receipt['tick'],trusted_certificate=True),
            'recomputed source-owned nonlinear result differs')
    if receipt['tick']<=16:
        require(receipt['nonlinear_readout']==ground.direct_at(receipt['tick']),
                'independent iterative nonlinear reference disagrees')
