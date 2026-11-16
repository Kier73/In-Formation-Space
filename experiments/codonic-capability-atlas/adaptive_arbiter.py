"""COG-002: evidence-conditional arbitration over COG-001's exact algebraic atlas.

Learns which *already admitted* affine Ground to compose for a task. It does
not invent an affine law, infer unsupported semantics, or authenticate a host.
The finite version space is explicit so that its evidence can be independently
replayed and every held-out result is falsifiable.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from capability_atlas import Affine, compile_regions, encode, point_label

SCHEMA = 'in-formation.codonic-capability-atlas/002'
PREDICATES = ('constant', 'parity-x', 'parity-y', 'parity-sum', 'half-x')


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def hash_object(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def exact_int(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'invalid {name}')
    return value


def predicate(name: str, x: tuple[int, int], p: int) -> int:
    if name == 'constant': return 0
    if name == 'parity-x': return x[0] % 2
    if name == 'parity-y': return x[1] % 2
    if name == 'parity-sum': return (x[0] + x[1]) % 2
    if name == 'half-x': return int(x[0] >= p // 2)
    raise ValueError('unregistered contextual observation')


@dataclass(frozen=True)
class Atlas:
    """The computational Ground is source-pinned by its algebra, not a hash metric."""
    choices: tuple[tuple[str, Affine], ...]

    def __post_init__(self) -> None:
        if not (2 <= len(self.choices) <= 5) or any(
            type(name) is not str or not name.isidentifier() or not isinstance(map_, Affine)
            for name, map_ in self.choices
        ) or len({n for n, _ in self.choices}) != len(self.choices):
            raise ValueError('require 2..5 named typed affine capability Grounds')
        if any(transform.p != self.choices[0][1].p for _, transform in self.choices):
            raise ValueError('incompatible geometry/Ground field')
        if len({encode(t) for _, t in self.choices}) != len(self.choices):
            raise ValueError('duplicate equivalent capability Grounds')
        if tuple(sorted(n for n, _ in self.choices)) != tuple(n for n, _ in self.choices):
            raise ValueError('capability identities must be sorted for canonical evidence')
        for _, transform in self.choices:
            if compile_regions(transform).realization != transform:
                raise ValueError('capability Ground did not compile exactly')

    @property
    def p(self) -> int:
        return self.choices[0][1].p

    @property
    def fingerprint(self) -> str:
        return hash_object({'schema': SCHEMA, 'capabilities': [
            {'name': name, 'address': encode(transform), 'map': transform.dictionary()}
            for name, transform in self.choices], 'predicates': PREDICATES})

    def by_name(self, name: str) -> Affine:
        for candidate, transformation in self.choices:
            if name == candidate:
                return transformation
        raise ValueError('unknown capability or unsupported Ground')

    def point(self, value: Sequence[int]) -> tuple[int, int]:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError('requires typed 2D state')
        return (exact_int(value[0], 'x', 0, self.p-1),
                exact_int(value[1], 'y', 0, self.p-1))


@dataclass(frozen=True, order=True)
class Policy:
    """Depth-one conditional program; pure constant policy uses one Ground."""
    feature: str
    zero: str
    one: str

    def output(self, atlas: Atlas, x: tuple[int, int]) -> tuple[int, int]:
        name = self.one if predicate(self.feature, x, atlas.p) else self.zero
        return atlas.by_name(name).apply(x)

    def certificate(self, atlas: Atlas, x: tuple[int, int]) -> dict[str, Any]:
        """A verifiable composed Ground plan for the one selected region."""
        name = self.one if predicate(self.feature, x, atlas.p) else self.zero
        plan = compile_regions(atlas.by_name(name))
        return {'feature': self.feature, 'branch': predicate(self.feature, x, atlas.p),
                'capability': name, 'address': plan.address,
                'regions': [s.region for s in plan.steps],
                'compiled_steps': len(plan.steps)}


def policies(atlas: Atlas) -> tuple[Policy, ...]:
    names = tuple(n for n, _ in atlas.choices)
    return tuple([Policy('constant', n, n) for n in names] + [
        Policy(feature, a, b) for feature in PREDICATES[1:]
        for a in names for b in names if a != b])


def genesis(atlas: Atlas) -> str:
    return hash_object({'schema': SCHEMA, 'genesis': atlas.fingerprint})


@dataclass(frozen=True)
class Witness:
    """One task feedback event. Its hash binds content, not observer authenticity."""
    index: int
    previous: str
    x: tuple[int, int]
    y: tuple[int, int]
    digest: str

    @classmethod
    def create(cls, atlas: Atlas, index: int, previous: str, x: Sequence[int],
               y: Sequence[int]) -> 'Witness':
        exact_int(index, 'event index', 0, 10_000)
        if type(previous) is not str or len(previous) != 64:
            raise ValueError('invalid previous evidence root')
        a, b = atlas.point(x), atlas.point(y)
        return cls(index, previous, a, b, hash_object({
            'schema': SCHEMA, 'ground': atlas.fingerprint, 'index': index,
            'previous': previous, 'input': a, 'observed_output': b}))

    def to_dict(self) -> dict[str, Any]:
        return {'index': self.index, 'previous': self.previous, 'x': list(self.x),
                'y': list(self.y), 'digest': self.digest}


@dataclass(frozen=True)
class VersionSpace:
    atlas: Atlas
    witnesses: tuple[Witness, ...]
    viable: tuple[Policy, ...]

    @classmethod
    def empty(cls, atlas: Atlas) -> 'VersionSpace':
        return cls(atlas, (), policies(atlas))

    @property
    def head(self) -> str:
        return self.witnesses[-1].digest if self.witnesses else genesis(self.atlas)

    @property
    def fingerprint(self) -> str:
        return hash_object({'schema': SCHEMA, 'atlas': self.atlas.fingerprint,
                            'head': self.head, 'count': len(self.witnesses),
                            'viable': [policy.__dict__ for policy in self.viable]})

    def admit(self, witness: Witness) -> 'VersionSpace':
        if not isinstance(witness, Witness) or witness != Witness.create(
            self.atlas, len(self.witnesses), self.head, witness.x, witness.y):
            raise ValueError('witness does not extend the current sourced Ground')
        if witness.x in {w.x for w in self.witnesses}:
            raise ValueError('duplicate training observation')
        retained = tuple(h for h in self.viable if h.output(self.atlas, witness.x) == witness.y)
        if not retained:
            raise ValueError('observed task result not explained by admitted capacity class')
        return VersionSpace(self.atlas, self.witnesses + (witness,), retained)

    def best_policy(self) -> Policy:
        # Prefer simpler constant policies on a tie, then canonical region identity.
        return min(self.viable, key=lambda h: (h.feature != 'constant', h.feature, h.zero, h.one))

    def acquisition(self, candidates: Sequence[tuple[int, int]]) -> tuple[int, int]:
        """Choose input with greatest exact version-space prediction disagreement."""
        if not candidates or len(candidates) > 1024:
            raise ValueError('candidate observation pool must have 1..1024 coordinates')
        observed = {w.x for w in self.witnesses}
        best = None
        for raw in candidates:
            x = self.atlas.point(raw)
            if x in observed:
                continue
            votes: dict[tuple[int,int], int] = {}
            for h in self.viable:
                out = h.output(self.atlas, x)
                votes[out] = votes.get(out, 0) + 1
            n = len(self.viable)
            disagreement = (n*n - sum(size*size for size in votes.values()))//2
            # Largest disagreement, stable tie-break by state coordinate.
            ranking = (disagreement, -x[0], -x[1])
            if best is None or ranking > best[0]:
                best = (ranking, x)
        if best is None:
            raise ValueError('no unobserved target state available')
        return best[1]

    def trace(self) -> dict[str, Any]:
        return {'schema': SCHEMA, 'atlas': self.atlas.fingerprint,
                'witnesses': [w.to_dict() for w in self.witnesses],
                'head': self.head, 'fingerprint': self.fingerprint,
                'remaining': len(self.viable), 'selected': self.best_policy().__dict__}


def restore(atlas: Atlas, document: Mapping[str, Any], *,
            receiver_expected_head: str, receiver_expected_fingerprint: str) -> VersionSpace:
    if not isinstance(document, Mapping) or set(document) != {
        'schema', 'atlas', 'witnesses', 'head', 'fingerprint', 'remaining', 'selected'
    } or document['schema'] != SCHEMA or document['atlas'] != atlas.fingerprint:
        raise ValueError('unrecognized or substituted typed atlas')
    if not isinstance(document['witnesses'], list) or len(document['witnesses']) > 10_000:
        raise ValueError('invalid persisted witness stream')
    state = VersionSpace.empty(atlas)
    for item in document['witnesses']:
        if not isinstance(item, Mapping) or set(item) != {'index','previous','x','y','digest'}:
            raise ValueError('malformed source witness')
        if item['index'] != len(state.witnesses) or item['previous'] != state.head:
            raise ValueError('witness index/predecessor changed')
        w = Witness.create(atlas, item['index'], item['previous'], item['x'], item['y'])
        if w.digest != item['digest']:
            raise ValueError('witness content digest changed')
        state = state.admit(w)
    if (state.head != document['head'] or state.fingerprint != document['fingerprint']
        or len(state.viable) != document['remaining']
        or state.best_policy().__dict__ != document['selected']
        or state.head != receiver_expected_head
        or state.fingerprint != receiver_expected_fingerprint):
        raise ValueError('persisted atlas disagrees with externally pinned evidence')
    return state


def fixture_atlas() -> Atlas:
    p = 257
    return Atlas((
        ('balance', Affine(p, ((2,1),(0,3)),(5,7))),
        ('couple', Affine(p, ((1,2),(1,1)),(7,9))),
        ('rotate', Affine(p, ((0,1),(1,1)),(13,21))),
    ))


def fixture_oracle(atlas: Atlas, feature: str, x: tuple[int,int]) -> tuple[int,int]:
    if feature not in PREDICATES[1:]:
        raise ValueError('invalid experiment target')
    return atlas.by_name('couple' if predicate(feature, x, atlas.p) else 'balance').apply(x)


def accuracy(atlas: Atlas, policy: Policy, observations: Sequence[tuple[tuple[int,int],tuple[int,int]]]) -> tuple[int,int]:
    return sum(policy.output(atlas,x)==y for x,y in observations), len(observations)


def static_baseline(atlas: Atlas, witnesses: Sequence[Witness]) -> Policy:
    best = None
    for name,_ in atlas.choices:
        candidate = Policy('constant',name,name)
        hits = sum(candidate.output(atlas,w.x)==w.y for w in witnesses)
        ranking = (hits,-tuple(n for n,_ in atlas.choices).index(name))
        if best is None or ranking > best[0]:
            best = (ranking,candidate)
    assert best is not None
    return best[1]