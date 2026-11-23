"""OFG-002: exact observer fibers over separator-conditioned CNF Grounds.

Private bags share a small Boolean separator. Clauses may cross bags only
through separator variables. Hidden-separator mode uses exact inclusion-exclusion
of overlapping output rectangles, never global state enumeration.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations, product
from json import dumps
from math import prod


class GroundRefusal(ValueError):
    """Source, evidence, or resource budget is not admitted."""


@dataclass(frozen=True)
class SeparatorSource:
    n: int
    separator: tuple[int, ...]
    bags: tuple[tuple[int, ...], ...]
    clauses: tuple[tuple[int, ...], ...]
    old_tables: tuple[tuple[int, ...], ...]
    new_tables: tuple[tuple[int, ...], ...]
    separator_visible: bool = True


def _digest(s: SeparatorSource) -> str:
    return sha256(dumps({"n": s.n, "separator": s.separator, "bags": s.bags,
                         "clauses": s.clauses, "old_tables": s.old_tables,
                         "new_tables": s.new_tables, "separator_visible": s.separator_visible},
                        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _admit(s: SeparatorSource, bag_width: int, sep_width: int, max_states: int):
    if type(s.n) is not int or s.n < 2 or type(s.separator_visible) is not bool:
        raise GroundRefusal("invalid source domain")
    if any(type(v) is not int or v < 1 or v > s.n for v in s.separator):
        raise GroundRefusal("invalid separator")
    if not s.separator or tuple(sorted(set(s.separator))) != s.separator:
        raise GroundRefusal("separator must be strictly ordered")
    if not (type(bag_width) is int and type(sep_width) is int and
            type(max_states) is int and bag_width >= 2 and sep_width >= 1 and max_states >= 1):
        raise GroundRefusal("invalid construction budget")
    if len(s.separator) > sep_width or (not s.separator_visible and len(s.separator) > 3):
        raise GroundRefusal("separator exceeds allowed budget")
    if not s.bags or len(s.old_tables) != len(s.bags) or len(s.new_tables) != len(s.bags):
        raise GroundRefusal("incomplete bag/observation description")
    all_vars = list(s.separator)
    for bag, old, new in zip(s.bags, s.old_tables, s.new_tables):
        if (not bag or any(type(v) is not int or v < 1 or v > s.n for v in bag)
                or tuple(sorted(set(bag))) != bag or len(bag) + len(s.separator) > bag_width):
            raise GroundRefusal("bag is unordered, empty, or too wide")
        all_vars.extend(bag)
        needed = 1 << (len(s.separator) + len(bag))
        if len(old) != needed or len(new) != needed:
            raise GroundRefusal("observation table has wrong arity")
        if any(type(v) is not int or v < 0 for v in (*old, *new)):
            raise GroundRefusal("observation labels must be nonnegative integers")
        if not s.separator_visible and len(set(old)) != 1:
            raise GroundRefusal("hidden separator mode requires constant old observation per bag")
    if sorted(all_vars) != list(range(1, s.n + 1)):
        raise GroundRefusal("separator and private bags must partition the source")
    states = (1 << len(s.separator)) * sum(1 << len(bag) for bag in s.bags)
    if states > max_states:
        raise GroundRefusal("local enumeration budget exceeded")
    belongs = {v: i for i, bag in enumerate(s.bags) for v in bag}
    sep = set(s.separator)
    grouped = [[] for _ in s.bags]
    global_clauses = []
    for clause in s.clauses:
        if any(type(l) is not int or l == 0 or abs(l) > s.n for l in clause):
            raise GroundRefusal("invalid original source clause")
        affected = {belongs[abs(l)] for l in clause if abs(l) not in sep}
        if len(affected) > 1:
            raise GroundRefusal("private-to-private clause crosses the separator decomposition")
        if affected:
            grouped[next(iter(affected))].append(clause)
        else:
            global_clauses.append(clause)
    return tuple(tuple(c) for c in grouped), tuple(global_clauses), states


def _clause_true(clause, values):
    return any(values[abs(l)] == (l > 0) for l in clause)


def _row(s, sep_mask, grouped, global_clauses, reference=False):
    fixed = {v: bool(sep_mask & (1 << i)) for i, v in enumerate(s.separator)}
    allowed = all(_clause_true(c, fixed) for c in global_clauses)
    blocks = []
    for bag, clauses, old, new in zip(s.bags, grouped, s.old_tables, s.new_tables):
        fibers = {}
        count = 0
        if reference:
            assignments = (sum(int(bit) << j for j, bit in enumerate(bits))
                           for bits in product((False, True), repeat=len(bag)))
        else:
            assignments = range(1 << len(bag))
        for mask in assignments:
            values = {**fixed, **{v: bool(mask & (1 << i)) for i, v in enumerate(bag)}}
            if not all(_clause_true(c, values) for c in clauses):
                continue
            count += 1
            index = (sep_mask << len(bag)) | mask
            a, b = old[index], new[index]
            fibers.setdefault(a, {}).setdefault(b, []).append(mask)
        entries = [{"old": a, "new": sorted(choices),
                    "representatives": [min(choices[b]) for b in sorted(choices)]}
                   for a, choices in sorted(fibers.items())]
        blocks.append({"models": count, "fibers": entries})
    return {"separator": sep_mask, "allowed": allowed, "blocks": blocks,
            "models": prod(b["models"] for b in blocks) if allowed else 0}


def _rectangles(rows):
    """Set of distinct allowed output coordinates per bag, for each active separator."""
    rectangles = []
    for row in rows:
        if not row["models"]:
            continue
        rectangle = tuple(frozenset(v for f in b["fibers"] for v in f["new"])
                          for b in row["blocks"])
        if all(rectangle) and rectangle not in rectangles:
            rectangles.append(rectangle)
    return tuple(rectangles)


def _union_count(rectangles, prefix=()):
    """Exact cardinality of a union of products using inclusion-exclusion.

    For t active separator configurations the cost is O((2^t-1) * bags).
    A supplied prefix restricts the first coordinates and enables rank/unrank.
    """
    result = 0
    for size in range(1, len(rectangles) + 1):
        for choice in combinations(rectangles, size):
            cardinality = 1
            for i in range(len(choice[0])):
                common = set(choice[0][i])
                for other in choice[1:]:
                    common.intersection_update(other[i])
                if i < len(prefix):
                    cardinality *= int(prefix[i] in common)
                else:
                    cardinality *= len(common)
                if not cardinality:
                    break
            result += cardinality if size % 2 else -cardinality
    return result


def _summary(s, rows):
    models = sum(row["models"] for row in rows)
    if not models:
        maximum = 0
    elif not s.separator_visible:
        maximum = _union_count(_rectangles(rows))
    else:
        maximum = max((prod(max((len(f["new"]) for f in b["fibers"]), default=0)
                             for b in row["blocks"]) if row["models"] else 0)
                      for row in rows)
    return {"models": models, "maximum_fiber_size": maximum,
            "minimum_aux_bits": (maximum - 1).bit_length() if maximum else 0,
            "status": "SAT" if models else "UNSAT"}


def compile_ground(s: SeparatorSource, *, max_bag_width=8, max_separator_width=4,
                   max_local_states=200_000):
    """Compile a source-anchored, separator-conditioned observer certificate."""
    grouped, global_clauses, states = _admit(s, max_bag_width, max_separator_width, max_local_states)
    rows = [_row(s, t, grouped, global_clauses) for t in range(1 << len(s.separator))]
    return {"schema": "ifs.ofg.separator-fiber.v2", "source_sha256": _digest(s),
            "separator_visible": s.separator_visible, "max_bag_width": max_bag_width,
            "max_separator_width": max_separator_width, "max_local_states": max_local_states,
            "local_states_checked": states, "separator_configurations": len(rows),
            "rows": rows, **_summary(s, rows)}


def verify_ground(s: SeparatorSource, certificate: dict) -> bool:
    """Re-evaluate original clauses through independent local Boolean tuples."""
    if type(certificate) is not dict or certificate.get("schema") != "ifs.ofg.separator-fiber.v2":
        raise GroundRefusal("invalid certificate schema")
    args = [certificate.get(k) for k in ("max_bag_width", "max_separator_width", "max_local_states")]
    grouped, global_clauses, states = _admit(s, *args)
    rows = [_row(s, t, grouped, global_clauses, reference=True)
            for t in range(1 << len(s.separator))]
    expected = {"schema": "ifs.ofg.separator-fiber.v2", "source_sha256": _digest(s),
                "separator_visible": s.separator_visible, "max_bag_width": args[0],
                "max_separator_width": args[1], "max_local_states": args[2],
                "local_states_checked": states, "separator_configurations": len(rows),
                "rows": rows, **_summary(s, rows)}
    # Canonical JSON comparison also distinguishes booleans from integer evidence.
    try:
        identical = dumps(certificate, sort_keys=True, separators=(",", ":"), allow_nan=False) == dumps(
            expected, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError):
        identical = False
    if not identical:
        raise GroundRefusal("certificate conflicts with independent original-source replay")
    return True


def source_accepts(s: SeparatorSource, assignment: int) -> bool:
    if type(assignment) is not int or assignment < 0 or assignment >= (1 << s.n):
        return False
    return all(any(bool(assignment & (1 << (abs(l) - 1))) == (l > 0) for l in c)
               for c in s.clauses)


def _local_masks(s, assignment):
    sep_mask = sum(bool(assignment & (1 << (v - 1))) << i for i, v in enumerate(s.separator))
    local_masks = [sum(bool(assignment & (1 << (v - 1))) << i for i, v in enumerate(bag))
                   for bag in s.bags]
    return sep_mask, local_masks


def old_coordinates(s: SeparatorSource, assignment: int) -> tuple[int, ...]:
    t, masks = _local_masks(s, assignment)
    result = tuple(old[(t << len(bag)) | mask]
                   for bag, mask, old in zip(s.bags, masks, s.old_tables))
    return ((t,) + result) if s.separator_visible else result


def new_coordinates(s: SeparatorSource, assignment: int) -> tuple[int, ...]:
    t, masks = _local_masks(s, assignment)
    return tuple(new[(t << len(bag)) | mask]
                 for bag, mask, new in zip(s.bags, masks, s.new_tables))


def _entry(row, bag_index, old):
    for fiber in row["blocks"][bag_index]["fibers"]:
        if fiber["old"] == old:
            return fiber
    raise GroundRefusal("observation is not a source-admitted fiber")


def _hidden_domains(rectangles):
    if not rectangles:
        return ()
    return tuple(tuple(sorted(set().union(*(r[i] for r in rectangles))))
                 for i in range(len(rectangles[0])))


def _rank(rectangles, coordinate):
    domains = _hidden_domains(rectangles)
    prefix, rank = [], 0
    for i, value in enumerate(coordinate):
        if value not in domains[i]:
            raise GroundRefusal("new coordinate not in Ground")
        for prior in domains[i]:
            if prior >= value:
                break
            rank += _union_count(rectangles, tuple(prefix) + (prior,))
        prefix.append(value)
    if _union_count(rectangles, coordinate) != 1:
        raise GroundRefusal("new coordinate absent from union")
    return rank


def _unrank(rectangles, index):
    if index < 0 or index >= _union_count(rectangles):
        raise GroundRefusal("supplement outside exact observer fiber")
    prefix = []
    for domain in _hidden_domains(rectangles):
        for value in domain:
            amount = _union_count(rectangles, tuple(prefix) + (value,))
            if index < amount:
                prefix.append(value)
                break
            index -= amount
        else:
            raise GroundRefusal("invalid symbolic rank")
    return tuple(prefix)


def _assemble(s, row, masks):
    result = 0
    for i, v in enumerate(s.separator):
        if row["separator"] & (1 << i):
            result |= 1 << (v - 1)
    for bag, mask in zip(s.bags, masks):
        for i, v in enumerate(bag):
            if mask & (1 << i):
                result |= 1 << (v - 1)
    return result


def _witness_for_new(s, rows, old, desired):
    for row in rows:
        if not row["models"]:
            continue
        masks = []
        try:
            for i, value in enumerate(desired):
                entry = _entry(row, i, old[i])
                masks.append(entry["representatives"][entry["new"].index(value)])
        except (GroundRefusal, ValueError):
            continue
        candidate = _assemble(s, row, masks)
        if source_accepts(s, candidate):
            return candidate
    raise GroundRefusal("no verified witness for decoded coordinate")


def encode_observation(s: SeparatorSource, ground: dict, assignment: int):
    """Encode new observation into minimal worst-case-width auxiliary bits."""
    if ground.get("source_sha256") != _digest(s) or not source_accepts(s, assignment):
        raise GroundRefusal("source mismatch or invalid witness")
    old, new = old_coordinates(s, assignment), new_coordinates(s, assignment)
    if s.separator_visible:
        row = ground["rows"][old[0]]
        code = 0
        for i, q in enumerate(new):
            options = _entry(row, i, old[i + 1])["new"]
            code = code * len(options) + options.index(q)
    else:
        code = _rank(_rectangles(ground["rows"]), new)
    if code >= 1 << ground["minimum_aux_bits"]:
        raise GroundRefusal("supplement exceeds source-bound width")
    return old, code


def decode_observation(s: SeparatorSource, ground: dict, old: tuple[int, ...], code: int) -> int:
    """Decode a source-valid witness with the requested observable, or refuse."""
    if ground.get("source_sha256") != _digest(s) or ground.get("status") != "SAT":
        raise GroundRefusal("unadmitted source or UNSAT")
    if (type(old) is not tuple or type(code) is not int or code < 0 or
            code >= (1 << ground["minimum_aux_bits"])):
        raise GroundRefusal("malformed old observation or code")
    if s.separator_visible:
        if len(old) != len(s.bags) + 1 or type(old[0]) is not int or old[0] not in range(len(ground["rows"])):
            raise GroundRefusal("invalid separator observation")
        row = ground["rows"][old[0]]
        if not row["models"]:
            raise GroundRefusal("separator observation is UNSAT")
        entries = [_entry(row, i, old[i + 1]) for i in range(len(s.bags))]
        indices = [0] * len(entries)
        for i in range(len(entries) - 1, -1, -1):
            indices[i] = code % len(entries[i]["new"])
            code //= len(entries[i]["new"])
        if code:
            raise GroundRefusal("supplement outside conditional fiber")
        new = tuple(entries[i]["new"][j] for i, j in enumerate(indices))
        assignment = _assemble(s, row, [entries[i]["representatives"][j] for i, j in enumerate(indices)])
    else:
        if len(old) != len(s.bags) or old != tuple(table[0] for table in s.old_tables):
            raise GroundRefusal("hidden observation cannot identify this fiber")
        new = _unrank(_rectangles(ground["rows"]), code)
        assignment = _witness_for_new(s, ground["rows"], old, new)
    if (not source_accepts(s, assignment) or old_coordinates(s, assignment) != old or
            new_coordinates(s, assignment) != new):
        raise GroundRefusal("decoded witness conflicts with original source")
    return assignment


def shared_switch_source(blocks: int, *, separator_visible=True) -> SeparatorSource:
    """Separator selects which of two private coordinates is forced to zero."""
    if type(blocks) is not int or blocks < 2:
        raise ValueError("at least two independent private variables required")
    # When s=0, x1 must be zero. When s=1, x2 must be zero.
    clauses = ((1, -2), (-1, -3))
    bags = tuple((i + 2,) for i in range(blocks))
    return SeparatorSource(blocks + 1, (1,), bags, clauses,
                           ((0, 0, 0, 0),) * blocks,
                           ((0, 1, 0, 1),) * blocks, separator_visible)
