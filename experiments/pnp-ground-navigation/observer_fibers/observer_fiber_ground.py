"""OFG-001: exact observer-fiber coordinates for disjoint bounded-width CNF Grounds.

A certificate is a replayable description of fibers, not a claim of host authority.
Every clause and each observation table is source-bound. This model refuses
cross-block clauses rather than silently assuming a product decomposition.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import product
from json import dumps
from math import prod


class GroundRefusal(ValueError):
    """The description cannot be admitted by this bounded constructor."""


@dataclass(frozen=True)
class Source:
    n: int
    clauses: tuple[tuple[int, ...], ...]
    scopes: tuple[tuple[int, ...], ...]
    old_tables: tuple[tuple[int, ...], ...]
    new_tables: tuple[tuple[int, ...], ...]


def _source_payload(source: Source) -> dict:
    return {"n": source.n, "clauses": source.clauses, "scopes": source.scopes,
            "old_tables": source.old_tables, "new_tables": source.new_tables}


def _digest(source: Source) -> str:
    return sha256(dumps(_source_payload(source), sort_keys=True,
                        separators=(",", ":")).encode()).hexdigest()


def _admit(source: Source, max_width: int) -> tuple[tuple[tuple[int, ...], ...], ...]:
    if not isinstance(source.n, int) or isinstance(source.n, bool) or source.n < 1:
        raise GroundRefusal("invalid variable count")
    if not isinstance(max_width, int) or max_width < 1:
        raise GroundRefusal("invalid width budget")
    b = len(source.scopes)
    if b == 0 or len(source.old_tables) != b or len(source.new_tables) != b:
        raise GroundRefusal("incomplete observation description")
    if any(not scope or len(scope) > max_width for scope in source.scopes):
        raise GroundRefusal("scope exceeds declared width")
    variables = [v for scope in source.scopes for v in scope]
    if sorted(variables) != list(range(1, source.n + 1)):
        raise GroundRefusal("scopes must partition every source variable exactly once")
    for scope, old, new in zip(source.scopes, source.old_tables, source.new_tables):
        if len(old) != 1 << len(scope) or len(new) != 1 << len(scope):
            raise GroundRefusal("observation table has incorrect arity")
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (*old, *new)):
            raise GroundRefusal("observation values must be nonnegative integers")
    grouped = [[] for _ in source.scopes]
    membership = {v: i for i, scope in enumerate(source.scopes) for v in scope}
    for clause in source.clauses:
        if not clause:
            # Empty clause is an immediate local contradiction, assigned to block 0.
            grouped[0].append(clause)
            continue
        if any(not isinstance(lit, int) or isinstance(lit, bool) or
               lit == 0 or abs(lit) > source.n for lit in clause):
            raise GroundRefusal("noncanonical or out-of-domain literal")
        destinations = {membership[abs(lit)] for lit in clause}
        if len(destinations) != 1:
            raise GroundRefusal("cross-block clause requires another Ground constructor")
        grouped[next(iter(destinations))].append(clause)
    return tuple(tuple(g) for g in grouped)


def _satisfies_block(scope: tuple[int, ...], clauses: tuple[tuple[int, ...], ...], mask: int) -> bool:
    loc = {var: i for i, var in enumerate(scope)}
    for clause in clauses:
        if not any(bool(mask & (1 << loc[abs(lit)])) == (lit > 0) for lit in clause):
            return False
    return True


def _ceil_log2_positive(x: int) -> int:
    return (x - 1).bit_length() if x > 0 else 0


def compile_ground(source: Source, *, max_width: int = 8) -> dict:
    """Construct local observer fibers; the only exponential is in block width."""
    grouped = _admit(source, max_width)
    blocks = []
    local_checks = 0
    local_counts = []
    multiplicities = []
    for scope, clauses, old, new in zip(source.scopes, grouped, source.old_tables, source.new_tables):
        fibers: dict[int, dict[int, int]] = {}
        count = 0
        for mask in range(1 << len(scope)):
            local_checks += 1
            if _satisfies_block(scope, clauses, mask):
                count += 1
                by_new = fibers.setdefault(old[mask], {})
                by_new.setdefault(new[mask], mask)
        entries = [{"old": o, "new": sorted(f),
                    "representatives": [f[q] for q in sorted(f)]}
                   for o, f in sorted(fibers.items())]
        blocks.append({"fibers": entries, "models": count})
        local_counts.append(count)
        multiplicities.append(max((len(f) for f in fibers.values()), default=0))
    total_models = prod(local_counts)
    max_fiber = prod(multiplicities) if total_models else 0
    return {"schema": "ifs.ofg.observer-fiber.v1", "source_sha256": _digest(source),
            "max_width": max_width, "blocks": blocks,
            "models": total_models, "maximum_fiber_size": max_fiber,
            "minimum_aux_bits": _ceil_log2_positive(max_fiber),
            "local_states_checked": local_checks,
            "status": "UNSAT" if total_models == 0 else "SAT"}


def _independent_expected(source: Source, width: int) -> dict:
    """Reference construction: re-evaluate all local Boolean tuples directly."""
    grouped = _admit(source, width)
    result = []
    for scope, clauses, old, new in zip(source.scopes, grouped, source.old_tables, source.new_tables):
        seen = {}
        count = 0
        for bits in product((False, True), repeat=len(scope)):
            valuation = dict(zip(scope, bits))
            if not all(any(valuation[abs(l)] == (l > 0) for l in clause) for clause in clauses):
                continue
            count += 1
            mask = sum(int(v) << i for i, v in enumerate(bits))
            a = old[mask]
            b = new[mask]
            seen.setdefault(a, {}).setdefault(b, []).append(mask)
        result.append({"models": count, "fibers": [
            {"old": o, "new": sorted(bucket),
             "representatives": [min(bucket[q]) for q in sorted(bucket)]}
            for o, bucket in sorted(seen.items())]})
    return result


def verify_ground(source: Source, ground: dict) -> bool:
    """Independently replay the source-bound certificate and minimality bound."""
    if not isinstance(ground, dict) or ground.get("schema") != "ifs.ofg.observer-fiber.v1":
        raise GroundRefusal("invalid certificate schema")
    width = ground.get("max_width")
    if not isinstance(width, int) or isinstance(width, bool):
        raise GroundRefusal("invalid certified width")
    blocks = _independent_expected(source, width)
    counts = [b["models"] for b in blocks]
    total = prod(counts)
    multiplicity = prod((max((len(f["new"]) for f in b["fibers"]), default=0)
                         for b in blocks)) if total else 0
    expected = {"schema": "ifs.ofg.observer-fiber.v1",
                "source_sha256": _digest(source), "max_width": width,
                "blocks": blocks, "models": total,
                "maximum_fiber_size": multiplicity,
                "minimum_aux_bits": _ceil_log2_positive(multiplicity),
                "local_states_checked": sum(1 << len(scope) for scope in source.scopes),
                "status": "SAT" if total else "UNSAT"}
    if ground != expected:
        raise GroundRefusal("certificate disagrees with independent source reconstruction")
    return True


def source_accepts(source: Source, assignment: int) -> bool:
    """Independent original-clause check on a global Boolean assignment."""
    if not isinstance(assignment, int) or assignment < 0 or assignment >= (1 << source.n):
        return False
    return all(any(bool(assignment & (1 << (abs(lit) - 1))) == (lit > 0)
                   for lit in clause) for clause in source.clauses)


def old_coordinates(source: Source, assignment: int) -> tuple[int, ...]:
    return tuple(old[sum(bool(assignment & (1 << (v - 1))) << i for i, v in enumerate(scope))]
                 for scope, old in zip(source.scopes, source.old_tables))


def new_coordinates(source: Source, assignment: int) -> tuple[int, ...]:
    return tuple(new[sum(bool(assignment & (1 << (v - 1))) << i for i, v in enumerate(scope))]
                 for scope, new in zip(source.scopes, source.new_tables))


def _entry(ground: dict, i: int, old: int) -> dict:
    for f in ground["blocks"][i]["fibers"]:
        if f["old"] == old:
            return f
    raise GroundRefusal("old coordinate has no source-admitted realizations")


def encode_observation(source: Source, ground: dict, assignment: int) -> tuple[tuple[int, ...], int]:
    """Return old observation and minimum-width mixed-radix supplement."""
    if ground["source_sha256"] != _digest(source) or not source_accepts(source, assignment):
        raise GroundRefusal("source mismatch or non-witness")
    old, new = old_coordinates(source, assignment), new_coordinates(source, assignment)
    code = 0
    for i, (o, q) in enumerate(zip(old, new)):
        options = _entry(ground, i, o)["new"]
        code = code * len(options) + options.index(q)
    if code >= 1 << ground["minimum_aux_bits"]:
        raise GroundRefusal("invalid coordinate width")
    return old, code


def decode_observation(source: Source, ground: dict, old: tuple[int, ...], code: int) -> int:
    """Reconstruct a source-valid witness with the observer's desired new coordinate."""
    if ground["source_sha256"] != _digest(source) or ground["status"] != "SAT":
        raise GroundRefusal("unusable source or certificate")
    if len(old) != len(source.scopes) or not isinstance(code, int) or code < 0 or code >= (1 << ground["minimum_aux_bits"]):
        raise GroundRefusal("invalid supplement")
    choices = []
    for i, o in enumerate(old):
        choices.append(_entry(ground, i, o))
    remainder = code
    indices = [0] * len(choices)
    for i in range(len(choices) - 1, -1, -1):
        indices[i] = remainder % len(choices[i]["new"])
        remainder //= len(choices[i]["new"])
    if remainder:
        raise GroundRefusal("supplement lies outside this observer fiber")
    assignment = 0
    for scope, choice, j in zip(source.scopes, choices, indices):
        local = choice["representatives"][j]
        for i, var in enumerate(scope):
            if local & (1 << i):
                assignment |= 1 << (var - 1)
    if (not source_accepts(source, assignment) or old_coordinates(source, assignment) != old
            or new_coordinates(source, assignment) != tuple(choice["new"][j] for choice, j in zip(choices, indices))):
        raise GroundRefusal("decoded state fails source or intended observation")
    return assignment


def disjoint_three_state_source(blocks: int, *, old_mode: str = "constant") -> Source:
    """Each 2-variable block forbids 11, leaving three local models."""
    if blocks <= 0 or old_mode not in ("constant", "parity", "identity"):
        raise ValueError("invalid fixture")
    scopes = tuple((2 * i + 1, 2 * i + 2) for i in range(blocks))
    old_table = {"constant": (0, 0, 0, 0),
                 "parity": (0, 1, 1, 0),
                 "identity": (0, 1, 2, 3)}[old_mode]
    return Source(2 * blocks, tuple((-a, -b) for a, b in scopes), scopes,
                  (old_table,) * blocks, ((0, 1, 2, 3),) * blocks)
