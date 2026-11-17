"""RCG-004: source-pinned distant-time connectome Ground over an exact prime field.

This does not model physiological dynamics. It compiles a normalized
connectivity operator and a source/target observable to a certified scalar
linear recurrence, then uses quotient-polynomial navigation to jump to
an arbitrary logical tick. A finite-dimensional Cayley-Hamilton invariant
makes n consecutive recurrence checks a proof, not merely a test.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from connectome_ground import ConnectomeGround

SCHEMA = "ifs.real-connectome-temporal-ground.v1"
MODULUS = 1000000007
MAX_TICK = (1 << 63) - 1
MAX_NODES = 1024


class TemporalGroundRefused(ValueError):
    """Ground, recurrence, intention, or evidence is not admitted."""


def canonical(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False).encode("utf-8")


def hash_object(v: Any) -> str:
    return sha256(canonical(v)).hexdigest()


def ensure(cond: bool, why: str):
    if not cond:
        raise TemporalGroundRefused(why)


@dataclass(frozen=True)
class SparseTransfer:
    source: str
    target: str
    kind: str
    ground: str
    blob: str
    field: int
    n: int
    names: tuple[str, ...]
    column_edges: tuple[tuple[tuple[int, int], ...], ...]

    @classmethod
    def from_ground(cls, ground: ConnectomeGround, source: str, target: str,
                    *, kind: str = "chemical", modulus: int = MODULUS):
        ensure(isinstance(ground, ConnectomeGround) and source in ground.nodes and
               target in ground.nodes and kind in ("chemical", "electrical"),
               "source, target, type must exist in an admitted connectome Ground")
        ensure(modulus == MODULUS, "prime field is part of the Ground contract")
        names = tuple(sorted(ground.nodes))
        ensure(len(names) <= MAX_NODES, "bounded operator preparation")
        ids = {v: i for i, v in enumerate(names)}
        strengths = [0] * len(names)
        for edge in ground.edges:
            if edge.kind == kind:
                strengths[ids[edge.source]] += edge.count
        ensure(all(mass % modulus for mass in strengths if mass),
               "out-strength has no field inverse")
        edges: list[list[tuple[int, int]]] = [[] for _ in names]
        for edge in ground.edges:
            if edge.kind != kind:
                continue
            a = ids[edge.source]
            weight = (edge.count * pow(strengths[a], -1, modulus)) % modulus
            edges[a].append((ids[edge.target], weight))
        return cls(source, target, kind, ground.fingerprint, ground.source_blob,
                   modulus, len(names), names,
                   tuple(tuple(sorted(x)) for x in edges))

    def step(self, x: list[int]) -> list[int]:
        ensure(len(x) == self.n and
               all(type(z) is int and 0 <= z < self.field for z in x),
               "malformed finite-field state")
        y = [0] * self.n
        p = self.field
        for i, mass in enumerate(x):
            if mass:
                for j, w in self.column_edges[i]:
                    y[j] = (y[j] + mass * w) % p
        return y

    def samples(self, count: int) -> list[int]:
        ensure(type(count) is int and 0 <= count <= 2*self.n + 128,
               "unbounded source sample request")
        x = [0] * self.n
        x[self.names.index(self.source)] = 1
        target_id = self.names.index(self.target)
        answer = []
        for _ in range(count):
            answer.append(x[target_id])
            x = self.step(x)
        return answer

    @property
    def sparse_edge_count(self) -> int:
        return sum(len(v) for v in self.column_edges)


def berlekamp_massey(observed: list[int], field: int) -> tuple[int, ...]:
    """Independent reference; native execution reuses mailcpu.law_certifier."""
    c = [1]
    b = [1]
    degree = 0
    shift = 1
    last = 1
    for index, value in enumerate(observed):
        d = (value + sum(c[i]*observed[index-i]
                         for i in range(1, degree+1))) % field
        if d == 0:
            shift += 1
            continue
        prev = c[:]
        factor = d*pow(last, -1, field) % field
        target_size = len(b)+shift
        if len(c) < target_size:
            c.extend([0]*(target_size-len(c)))
        for j, item in enumerate(b):
            c[j+shift] = (c[j+shift]-factor*item) % field
        if 2*degree <= index:
            degree = index+1-degree
            b, last, shift = prev, d, 1
        else:
            shift += 1
    return tuple((-c[i]) % field for i in range(1, degree+1))


def check_global_annihilation(op: SparseTransfer, samples: list[int],
                              coefficients: tuple[int, ...]) -> None:
    """Cayley-Hamilton proof of all-time scalar recurrence.

    q(M)=M^r - sum(c_i M^(r-1-i)), and residual
    g_t=e_target^T M^t q(M)e_source.
    g_t obeys an order-at-most-n recurrence for any n-dimensional M.
    Checking g_0..g_(n-1)=0 therefore proves g_t=0 for all t.
    """
    r = len(coefficients)
    ensure(r <= op.n and len(samples) >= op.n + r,
           "insufficient finite-dimensional annihilator evidence")
    p = op.field
    for t in range(op.n):
        residual = (samples[t+r] - sum(coefficients[i]*samples[t+r-1-i]
                                      for i in range(r))) % p
        ensure(residual == 0,
               "source operator does not admit claimed temporal recurrence")


def prepare(op: SparseTransfer, *, native_ecpu: bool = False) -> dict[str, Any]:
    """Prepare from 2n source observations, never from a distant requested tick."""
    samples = op.samples(2*op.n)
    if native_ecpu:
        from mailcpu.law_certifier import berlekamp_massey as ecpu_bm
        connection, degree = ecpu_bm(samples, q=op.field)
        coefficients = tuple(-connection[i] % op.field
                             for i in range(1, degree+1))
        ensure(coefficients == berlekamp_massey(samples, op.field),
               "native E-CPU and independent recurrence derivations disagree")
    else:
        coefficients = berlekamp_massey(samples, op.field)
    check_global_annihilation(op, samples, coefficients)
    r = len(coefficients)
    body = {"schema": SCHEMA, "ground": op.ground, "source_blob": op.blob,
            "source": op.source, "target": op.target, "edge_kind": op.kind,
            "field": op.field, "dimension": op.n,
            "edge_count": op.sparse_edge_count,
            "recurrence_degree": r, "coefficients": list(coefficients),
            "initial_terms": samples[:r], "preparation_terms": 2*op.n,
            "sequence_digest": hash_object(samples),
            "assurance": "n-consecutive-residuals-plus-cayley-hamilton"}
    return {**body, "digest": hash_object(body)}


def verify_preparation(op: SparseTransfer, receipt: dict[str, Any]) -> None:
    ensure(type(receipt) is dict and receipt.get("schema") == SCHEMA and
           receipt.get("ground") == op.ground and
           receipt.get("source_blob") == op.blob and
           receipt.get("source") == op.source and
           receipt.get("target") == op.target and
           receipt.get("edge_kind") == op.kind and
           receipt.get("dimension") == op.n and
           receipt.get("edge_count") == op.sparse_edge_count and
           receipt.get("field") == op.field and receipt.get("assurance") ==
           "n-consecutive-residuals-plus-cayley-hamilton",
           "unrecognized or source-mismatched preparation")
    ensure(set(receipt) == {"schema","ground","source_blob","source","target",
           "edge_kind","field","dimension","edge_count","recurrence_degree",
           "coefficients","initial_terms","preparation_terms",
           "sequence_digest","assurance","digest"} and
           type(receipt.get("recurrence_degree")) is int and
           0 <= receipt["recurrence_degree"] <= op.n and
           type(receipt.get("coefficients")) is list and
           len(receipt["coefficients"]) == receipt["recurrence_degree"] and
           all(type(x) is int and 0<=x<op.field
               for x in receipt["coefficients"]) and
           type(receipt.get("initial_terms")) is list and
           len(receipt["initial_terms"]) == receipt["recurrence_degree"] and
           all(type(x) is int and 0<=x<op.field
               for x in receipt["initial_terms"]) and
           receipt.get("preparation_terms") == 2*op.n and
           receipt["digest"] == hash_object(
               {k:v for k,v in receipt.items() if k!="digest"}),
           "invalid or altered claimed recurrence")
    # Reconstruct from receiver-owned original Ground, not caller's trace.
    samples = op.samples(2*op.n)
    ensure(samples[:len(receipt["coefficients"])] ==
           receipt["initial_terms"] and
           hash_object(samples) == receipt["sequence_digest"],
           "original source samples differ from preparation")
    check_global_annihilation(op, samples, tuple(receipt["coefficients"]))


def _multiply_mod(left: list[int], right: list[int],
                  coefficients: tuple[int, ...], p: int) -> list[int]:
    r = len(coefficients)
    c = [0]*(2*r-1)
    for i,a in enumerate(left):
        if a:
            for j,b in enumerate(right):
                c[i+j] = (c[i+j] + a*b) % p
    for k in range(2*r-2,r-1,-1):
        v = c[k]
        if v:
            for i,z in enumerate(coefficients):
                c[k-1-i] = (c[k-1-i]+v*z) % p
    return c[:r]


def navigate_verified(receipt: dict[str, Any], tick: int) -> dict[str, Any]:
    """After source verification, jump in O(r² log tick), no token iteration."""
    ensure(type(tick) is int and 0<=tick<=MAX_TICK,
           "logical time outside admitted horizon")
    c = tuple(receipt["coefficients"])
    r = len(c)
    p = receipt["field"]
    if r == 0:
        value = 0
        products = 0
    elif tick < r:
        value = receipt["initial_terms"][tick]
        products = 0
    else:
        result = [1]+[0]*(r-1)
        base = ([c[0]] if r==1 else [0,1]+[0]*(r-2))
        remain = tick
        products = 0
        while remain:
            if remain&1:
                result = _multiply_mod(result, base, c, p)
                products += 1
            remain >>= 1
            if remain:
                base = _multiply_mod(base, base, c, p)
                products += 1
        value = sum((a*b for a,b in
                     zip(result,receipt["initial_terms"])))%p
    body = {"schema": SCHEMA+".navigation.v1",
            "ground":receipt["ground"],
            "preparation_digest":receipt["digest"],
            "tick":tick,"value_mod_p":value,
            "recurrence_degree":r,"polynomial_products":products,
            "strategy":"exact-quotient-polynomial-not-token-iteration"}
    return {**body,"digest":hash_object(body)}


def validate_navigation(op: SparseTransfer, certificate: dict[str, Any],
                        result: dict[str, Any], *,
                        verify_source: bool = True) -> None:
    if verify_source:
        verify_preparation(op, certificate)
    ensure(type(result) is dict and
           type(result.get("tick")) is int, "invalid tick")
    ensure(result == navigate_verified(certificate,result["tick"]),
           "navigation does not match pinned recurrence")
    if result["tick"]+1 <= 2*op.n+128:
        expected = op.samples(result["tick"]+1)[-1]
        ensure(result["value_mod_p"] == expected,
               "direct source iteration disagrees")


def navigation_request(op: SparseTransfer, certificate: dict[str, Any],
                       tick: int) -> dict[str, Any]:
    verify_preparation(op,certificate)
    return navigate_verified(certificate,tick)
