"""AKS-001: exact affine-kernel attention Ground with sufficient prefix state.

This is an observation algebra over a finite prime field, not an approximation
of Transformer softmax and not an execution/authorization subsystem.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any, Sequence


class GroundRefused(ValueError):
    """A proposed Ground, token, lineage, or observation is inadmissible."""


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _int(value: Any, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise GroundRefused(f"{name} must be a strict integer in [{lo}, {hi}]")
    return value


def _vector(value: Any, length: int, modulus: int, name: str) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise GroundRefused(f"{name} dimension mismatch")
    return tuple(_int(v, name, 0, modulus - 1) for v in value)


@dataclass(frozen=True)
class AttentionGround:
    """Exact kernel K(q,k)=1+q.k in F_p; no softmax semantics."""

    modulus: int
    key_dim: int
    value_dim: int

    def __post_init__(self) -> None:
        p = _int(self.modulus, "modulus", 2, 65521)
        if any(p % d == 0 for d in range(2, math.isqrt(p) + 1)):
            raise GroundRefused("modulus must be prime for normalized observations")
        _int(self.key_dim, "key_dim", 1, 64)
        _int(self.value_dim, "value_dim", 1, 64)

    @property
    def fingerprint(self) -> str:
        return _digest({"schema": "ifs.attention-kernel-ground.v1", "p": self.modulus,
                        "key_dim": self.key_dim, "value_dim": self.value_dim,
                        "kernel": "affine-dot-v1"})


@dataclass(frozen=True)
class TokenEvidence:
    """Unsigned integrity-bound observation of one admitted token pair."""

    ground: str
    index: int
    previous: str
    key: tuple[int, ...]
    value: tuple[int, ...]
    digest: str

    @classmethod
    def form(cls, ground: AttentionGround, index: int, previous: str,
             key: Sequence[int], value: Sequence[int]) -> "TokenEvidence":
        _int(index, "index", 0, 1_000_000)
        if not isinstance(previous, str) or len(previous) != 64 or any(c not in "0123456789abcdef" for c in previous):
            raise GroundRefused("invalid predecessor digest")
        k = _vector(key, ground.key_dim, ground.modulus, "key")
        v = _vector(value, ground.value_dim, ground.modulus, "value")
        payload = {"ground": ground.fingerprint, "index": index,
                   "previous": previous, "key": k, "value": v}
        return cls(ground.fingerprint, index, previous, k, v, _digest(payload))


def _origin(ground: AttentionGround) -> str:
    return _digest({"origin": ground.fingerprint, "schema": "ifs.aks001.origin.v1"})


@dataclass(frozen=True)
class PrefixGround:
    """Fixed-size exact sufficient state for all affine-kernel query coordinates."""

    ground: AttentionGround
    count: int
    matrix: tuple[tuple[int, ...], ...]
    mass: tuple[int, ...]
    history_head: str

    def __post_init__(self) -> None:
        if not isinstance(self.ground, AttentionGround):
            raise GroundRefused("prefix requires a declared AttentionGround")
        _int(self.count, "count", 0, 1_000_001)
        p = self.ground.modulus
        d = self.ground.key_dim + 1
        if not isinstance(self.matrix, tuple) or len(self.matrix) != d:
            raise GroundRefused("invalid prefix matrix shape")
        for row in self.matrix:
            _vector(row, self.ground.value_dim, p, "prefix matrix row")
        _vector(self.mass, d, p, "prefix mass")
        if not isinstance(self.history_head, str) or len(self.history_head) != 64 or any(
                c not in "0123456789abcdef" for c in self.history_head):
            raise GroundRefused("invalid prefix history digest")

    @classmethod
    def empty(cls, ground: AttentionGround) -> "PrefixGround":
        return cls(ground, 0, tuple((0,) * ground.value_dim for _ in range(ground.key_dim + 1)),
                   (0,) * (ground.key_dim + 1), _origin(ground))

    @property
    def fingerprint(self) -> str:
        return _digest({"schema": "ifs.aks001.prefix.v1", "ground": self.ground.fingerprint,
                        "count": self.count, "matrix": self.matrix, "mass": self.mass,
                        "history_head": self.history_head})

    def admit(self, token: TokenEvidence) -> "PrefixGround":
        """Add one witnessed (key,value) to the Ground without replaying history."""
        if not isinstance(token, TokenEvidence):
            raise GroundRefused("expected typed token evidence")
        if token.ground != self.ground.fingerprint or token.index != self.count or token.previous != self.history_head:
            raise GroundRefused("token does not extend this exact Ground prefix")
        fresh = TokenEvidence.form(self.ground, token.index, token.previous, token.key, token.value)
        if token != fresh:
            raise GroundRefused("token digest or shape disagrees with its content")
        p = self.ground.modulus
        k = (1,) + token.key
        m = tuple(tuple((x + a * v) % p for x, v in zip(row, token.value))
                  for row, a in zip(self.matrix, k))
        z = tuple((x + a) % p for x, a in zip(self.mass, k))
        return PrefixGround(self.ground, self.count + 1, m, z, token.digest)

    def query(self, query: Sequence[int], *, normalized: bool) -> "Observation":
        """Navigate one observation in O(key_dim*value_dim), independent of prefix length."""
        q = _vector(query, self.ground.key_dim, self.ground.modulus, "query")
        features = (1,) + q
        p = self.ground.modulus
        numerator = tuple(sum(a * row[j] for a, row in zip(features, self.matrix)) % p
                          for j in range(self.ground.value_dim))
        denominator = sum(a * b for a, b in zip(features, self.mass)) % p
        if normalized and denominator == 0:
            raise GroundRefused("normalization denominator is zero in the admitted field")
        values = tuple((v * pow(denominator, -1, p)) % p for v in numerator) if normalized else numerator
        return Observation(self.fingerprint, q, normalized, numerator, denominator, values)


@dataclass(frozen=True)
class Observation:
    """A result scoped to one exact prefix and declared observer contract."""
    prefix_fingerprint: str
    query: tuple[int, ...]
    normalized: bool
    numerator: tuple[int, ...]
    denominator: int
    result: tuple[int, ...]


def reconstruct(ground: AttentionGround, tokens: Sequence[TokenEvidence]) -> PrefixGround:
    """Independently rebuild the claimed prefix from all supplied source observations."""
    state = PrefixGround.empty(ground)
    for token in tokens:
        state = state.admit(token)
    return state


def direct_observe(ground: AttentionGround, tokens: Sequence[TokenEvidence],
                   query: Sequence[int], *, normalized: bool) -> tuple[int, ...]:
    """Independent O(T*d_k*d_v) history oracle, without using summary moments."""
    q = _vector(query, ground.key_dim, ground.modulus, "query")
    p = ground.modulus
    numerator = [0] * ground.value_dim
    denominator = 0
    for token in tokens:
        if token.ground != ground.fingerprint:
            raise GroundRefused("history Ground mismatch")
        weight = (1 + sum(a * b for a, b in zip(q, token.key))) % p
        denominator = (denominator + weight) % p
        for j, value in enumerate(token.value):
            numerator[j] = (numerator[j] + weight * value) % p
    if normalized and denominator == 0:
        raise GroundRefused("normalization denominator is zero in the admitted field")
    return tuple((v * pow(denominator, -1, p)) % p for v in numerator) if normalized else tuple(numerator)


def verify_observation(ground: AttentionGround, tokens: Sequence[TokenEvidence],
                       receipt: Observation, *, expected_head: str) -> bool:
    """Check source lineage and query by separate direct per-token arithmetic.

    The expected head must come from receiver-owned policy, not the receipt.
    SHA-256 is an integrity check, not authentication of the observing host.
    """
    if not isinstance(receipt, Observation) or type(receipt.normalized) is not bool:
        raise GroundRefused("invalid observation contract")
    state = reconstruct(ground, tokens)
    if state.history_head != expected_head:
        raise GroundRefused("source history disagrees with receiver-owned pin")
    expected = state.query(receipt.query, normalized=receipt.normalized)
    independent = direct_observe(ground, tokens, receipt.query, normalized=receipt.normalized)
    if expected != receipt or independent != receipt.result:
        raise GroundRefused("observation disagrees with exact Ground or independent source replay")
    return True
