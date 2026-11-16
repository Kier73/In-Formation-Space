"""COG-003: discover unregistered affine capability Grounds from geometric evidence.

Reuse COG-001's algebraic factorizer, COG-002's Atlas, and (in native CI)
the VGI typed operator verifier. Three independent probes identify an
affine hypothesis; a fourth tests consistency. Observations do not prove
the model family globally or authenticate their external source.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence
from capability_atlas import Affine, compile_regions, encode
from adaptive_arbiter import Atlas

SCHEMA = 'in-formation.codonic-capability-atlas/003'


def canonical(x: Any) -> bytes:
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(x: Any) -> str:
    return hashlib.sha256(canonical(x)).hexdigest()


def label(v: str) -> str:
    if type(v) is not str or not 1 <= len(v) <= 40 or not v.isidentifier():
        raise ValueError('context must be a stable typed identifier')
    return v


def checked_point(p: int, x: Sequence[int]) -> tuple[int, int]:
    if not isinstance(x, (tuple, list)) or len(x) != 2 or any(type(t) is not int or t < 0 or t >= p for t in x):
        raise ValueError('point is not a canonical Fp2 coordinate')
    return (x[0], x[1])


def rank(points: Sequence[tuple[int,int]], p: int) -> int:
    """Rank of augmented (x,y,1) coordinates over Fp, bounded by 3."""
    rows = [list((x, y, 1)) for x, y in points]
    k = 0
    for col in range(3):
        pivot = next((i for i in range(k, len(rows)) if rows[i][col] % p), None)
        if pivot is None:
            continue
        rows[pivot], rows[k] = rows[k], rows[pivot]
        inv = pow(rows[k][col], -1, p)
        rows[k] = [t * inv % p for t in rows[k]]
        for i in range(k + 1, len(rows)):
            factor = rows[i][col]
            rows[i] = [(a - factor * b) % p for a, b in zip(rows[i], rows[k])]
        k += 1
        if k == 3:
            break
    return k


@dataclass(frozen=True)
class Observation:
    index: int
    previous: str
    context: str
    source: tuple[int,int]
    observed: tuple[int,int]
    digest: str

    @classmethod
    def form(cls, root: str, index: int, context: str, source: Sequence[int],
             observed: Sequence[int], p: int) -> 'Observation':
        if type(index) is not int or not 0 <= index <= 10000:
            raise ValueError('invalid evidence index')
        if type(root) is not str or len(root) != 64 or any(c not in '0123456789abcdef' for c in root):
            raise ValueError('invalid prior evidence root')
        key = label(context)
        x, y = checked_point(p, source), checked_point(p, observed)
        body = {'schema': SCHEMA, 'index': index, 'previous': root, 'context': key,
                'source': list(x), 'observed': list(y), 'field': p}
        return cls(index, root, key, x, y, digest(body))

    def to_dict(self) -> dict[str, Any]:
        return {'index': self.index, 'previous': self.previous, 'context': self.context,
                'source': list(self.source), 'observed': list(self.observed), 'digest': self.digest}


def infer_affine(p: int, observations: Sequence[Observation]) -> tuple[Affine, tuple[int,int,int]]:
    """Infer one bijective affine hypothesis from a rank-three observation basis.

    Online basis selection is linear in the witness count. Additional points
    must agree with the proposed map, not merely a rehashed receipt.
    """
    if len(observations) < 3:
        raise ValueError('three independent observations are required')
    basis_indices, basis_points = [], []
    for index, observation in enumerate(observations):
        candidate = basis_points + [observation.source]
        if rank(candidate, p) > len(basis_points):
            basis_indices.append(index)
            basis_points.append(observation.source)
            if len(basis_indices) == 3:
                break
    if len(basis_indices) < 3:
        raise ValueError('underdetermined geometry: no affine basis observed')
    chosen = tuple(basis_indices)
    x0, x1, x2 = [observations[t].source for t in chosen]
    y0, y1, y2 = [observations[t].observed for t in chosen]
    ux, uy = (x1[0]-x0[0]) % p, (x1[1]-x0[1]) % p
    vx, vy = (x2[0]-x0[0]) % p, (x2[1]-x0[1]) % p
    determinant = (ux * vy - vx * uy) % p
    if not determinant:
        raise ValueError('singular observation basis')
    inverse = pow(determinant, -1, p)
    matrix = []
    for d in range(2):
        dy1, dy2 = (y1[d]-y0[d]) % p, (y2[d]-y0[d]) % p
        a = (dy1 * vy - dy2 * uy) * inverse % p
        b = (ux * dy2 - vx * dy1) * inverse % p
        matrix.append((a, b))
    bias = tuple((y0[d] - sum(matrix[d][c] * x0[c] for c in range(2))) % p for d in range(2))
    candidate = Affine(p, tuple(matrix), bias)
    if any(candidate.apply(o.source) != o.observed for o in observations):
        raise ValueError('new evidence contradicts inferred affine Ground')
    return candidate, chosen


@dataclass(frozen=True)
class Discovery:
    context: str
    candidate: Affine
    basis_indices: tuple[int,int,int]
    challenge_indices: tuple[int, ...]
    source_root: str
    source_count: int

    def to_dict(self) -> dict[str, Any]:
        return {'context': self.context, 'candidate': self.candidate.dictionary(),
                'address': encode(self.candidate), 'basis_indices': list(self.basis_indices),
                'challenge_indices': list(self.challenge_indices),
                'source_root': self.source_root, 'source_count': self.source_count,
                'admission': 'sample_consistent_affine_hypothesis_not_global_law_proof'}


@dataclass(frozen=True)
class EvidenceAtlas:
    """Evidence-qualified candidate registry; authority pins come from receiver."""
    base: Atlas
    contexts: tuple[str, ...]
    observations: tuple[Observation, ...] = ()

    def __post_init__(self):
        if not isinstance(self.base, Atlas) or not (1 <= len(self.contexts) <= 5-len(self.base.choices)):
            raise ValueError('invalid source atlas or contexts')
        if tuple(sorted(set(map(label, self.contexts)))) != self.contexts:
            raise ValueError('context identities must be sorted and unique')

    @property
    def seed(self) -> str:
        return digest({'schema': SCHEMA, 'ground': self.base.fingerprint,
                       'contexts': list(self.contexts)})

    @property
    def head(self) -> str:
        return self.observations[-1].digest if self.observations else self.seed

    @property
    def fingerprint(self) -> str:
        return digest({'schema': SCHEMA, 'ground': self.base.fingerprint,
                       'contexts': list(self.contexts), 'head': self.head,
                       'count': len(self.observations)})

    def for_context(self, context: str) -> tuple[Observation, ...]:
        if label(context) not in self.contexts:
            raise ValueError('unknown context')
        return tuple(o for o in self.observations if o.context == context)

    def admit(self, context: str, source: Sequence[int],
              observed: Sequence[int]) -> 'EvidenceAtlas':
        if context not in self.contexts:
            raise ValueError('unknown context not admitted')
        x = checked_point(self.base.p, source)
        if x in {o.source for o in self.for_context(context)}:
            raise ValueError('duplicate source observation')
        witness = Observation.form(self.head, len(self.observations), context, x, observed, self.base.p)
        return EvidenceAtlas(self.base, self.contexts, self.observations+(witness,))

    def select_probe(self, context: str, pool: Sequence[tuple[int,int]]) -> tuple[int,int]:
        """Prefer geometry-informative probes, then independent distant checks."""
        if not 1 <= len(pool) <= 2048:
            raise ValueError('candidate pool must have 1..2048 points')
        observations = self.for_context(context)
        seen = {o.source for o in observations}
        current = [o.source for o in observations]
        base_rank = rank(current, self.base.p)
        best = None
        for point in pool:
            x = checked_point(self.base.p, point)
            if x in seen:
                continue
            new_rank = rank(current + [x], self.base.p)
            min_distance = min((
                min(abs(x[0]-z[0]), self.base.p-abs(x[0]-z[0])) +
                min(abs(x[1]-z[1]), self.base.p-abs(x[1]-z[1]))
                for z in current
            ), default=0)
            score = (new_rank-base_rank, min_distance, -x[0], -x[1])
            if best is None or score > best[0]:
                best = (score, x)
        if best is None:
            raise ValueError('no unused observation coordinate')
        return best[1]

    def discover(self, context: str, *, min_challenges: int = 1) -> Discovery:
        if type(min_challenges) is not int or min_challenges < 1:
            raise ValueError('at least one independent challenge is required')
        evidence = self.for_context(context)
        model, basis = infer_affine(self.base.p, evidence)
        challenges = tuple(i for i in range(len(evidence)) if i not in basis)
        if len(challenges) < min_challenges:
            raise ValueError('insufficient independent observed challenges')
        if compile_regions(model).realization != model:
            raise ValueError('candidate not realized by original atlas')
        return Discovery(context, model, basis, challenges, self.head, len(self.observations))

    def discovered_atlas(self) -> Atlas:
        discovered = []
        for context in self.contexts:
            record = self.discover(context)
            discovered.append((f'learned_{context}', record.candidate))
        known = {encode(t) for _, t in self.base.choices}
        if any(encode(t) in known for _, t in discovered) or len({encode(t) for _, t in discovered}) != len(discovered):
            raise ValueError('discovered capability duplicates registered mathematical Ground')
        return Atlas(tuple(sorted(self.base.choices+tuple(discovered))))

    def trace(self) -> dict[str, Any]:
        return {'schema': SCHEMA, 'base': self.base.fingerprint,
                'contexts': list(self.contexts), 'observations': [o.to_dict() for o in self.observations],
                'head': self.head, 'fingerprint': self.fingerprint}


def restore(base: Atlas, document: Mapping[str, Any], *, expected_head: str,
            expected_fingerprint: str) -> EvidenceAtlas:
    if not isinstance(document, Mapping) or set(document) != {
        'schema','base','contexts','observations','head','fingerprint'
    } or document['schema'] != SCHEMA or document['base'] != base.fingerprint:
        raise ValueError('unknown research Ground or schema')
    if not isinstance(document['contexts'], list) or not isinstance(document['observations'], list) or len(document['observations']) > 10000:
        raise ValueError('malformed persistent evidence')
    state = EvidenceAtlas(base, tuple(document['contexts']))
    for raw in document['observations']:
        if not isinstance(raw, Mapping) or set(raw) != {'index','previous','context','source','observed','digest'}:
            raise ValueError('malformed observation')
        if raw['previous'] != state.head or raw['index'] != len(state.observations):
            raise ValueError('stale/reordered evidence')
        next_ = state.admit(raw['context'], raw['source'], raw['observed'])
        if next_.observations[-1].to_dict() != raw:
            raise ValueError('changed observation digest')
        state = next_
    if (state.head != document['head'] or state.fingerprint != document['fingerprint'] or
        state.head != expected_head or state.fingerprint != expected_fingerprint):
        raise ValueError('reconstructed research state differs from independent receiver pins')
    return state
