"""COE-001: exact all-real equivalence for scalar-input rational ReLU MLPs.

Pure standard-library implementation. Every returned equivalence decision comes
from a complete rational piecewise-affine decomposition, not sample testing.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import re
from typing import Iterable

_Q = re.compile(r"-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z")


class InvalidNetwork(ValueError):
    pass


class RegionBudgetExceeded(RuntimeError):
    pass


def q(value: str | int | Fraction) -> Fraction:
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, Fraction):
        return value
    if not isinstance(value, str) or not _Q.fullmatch(value):
        raise InvalidNetwork(f"expected exact rational token, got {value!r}")
    return Fraction(value)


def token(value: Fraction | None, *, infinite: str = "") -> str:
    if value is None:
        return infinite
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


@dataclass(frozen=True)
class Affine:
    slope: Fraction
    offset: Fraction

    def at(self, x: Fraction) -> Fraction:
        return self.slope * x + self.offset


ZERO = Affine(Fraction(0), Fraction(0))


@dataclass(frozen=True)
class Layer:
    weights: tuple[tuple[Fraction, ...], ...]
    bias: tuple[Fraction, ...]
    activation: str


def layer(weights: Iterable[Iterable[str | int | Fraction]],
          bias: Iterable[str | int | Fraction], activation: str) -> Layer:
    if activation not in ("linear", "relu"):
        raise InvalidNetwork("activation must be 'linear' or 'relu'")
    w = tuple(tuple(q(x) for x in row) for row in weights)
    b = tuple(q(x) for x in bias)
    if not w or len(w) != len(b) or not w[0] or any(len(row) != len(w[0]) for row in w):
        raise InvalidNetwork("weights must be a nonempty rectangular matrix matching biases")
    return Layer(w, b, activation)


def validate(layers: tuple[Layer, ...]) -> None:
    if not layers or len(layers) > 128:
        raise InvalidNetwork("network requires 1..128 layers")
    width = 1
    for index, current in enumerate(layers):
        if current.activation not in ("linear", "relu"):
            raise InvalidNetwork(f"unsupported activation at layer {index}")
        if not current.weights or len(current.weights) != len(current.bias) or len(current.weights) > 256:
            raise InvalidNetwork(f"invalid layer {index} height")
        if any(len(row) != width for row in current.weights):
            raise InvalidNetwork(f"layer {index} input width mismatch")
        if any(not isinstance(v, Fraction) for row in current.weights for v in row + ()) or any(not isinstance(v, Fraction) for v in current.bias):
            raise InvalidNetwork("network parameters must be exact Fractions")
        width = len(current.weights)


def evaluate(layers: tuple[Layer, ...], x: Fraction) -> tuple[Fraction, ...]:
    """Independent direct rational evaluator (also used to confirm witnesses)."""
    validate(layers)
    values = (q(x),)
    for current in layers:
        values = tuple(sum((weight * val for weight, val in zip(row, values)), bias)
                       for row, bias in zip(current.weights, current.bias))
        if current.activation == "relu":
            values = tuple(max(Fraction(0), value) for value in values)
    return values


@dataclass(frozen=True)
class Region:
    left: Fraction | None    # None = -infinity
    right: Fraction | None   # None = +infinity
    output: tuple[Affine, ...]


def interior(left: Fraction | None, right: Fraction | None) -> Fraction:
    if left is None and right is None:
        return Fraction(0)
    if left is None:
        return right - 1
    if right is None:
        return left + 1
    return (left + right) / 2


def inside(x: Fraction, left: Fraction | None, right: Fraction | None) -> bool:
    return (left is None or left < x) and (right is None or x < right)


def compact(regions: list[Region]) -> list[Region]:
    merged: list[Region] = []
    for region in regions:
        if merged and merged[-1].right == region.left and merged[-1].output == region.output:
            merged[-1] = Region(merged[-1].left, region.right, region.output)
        else:
            merged.append(region)
    return merged


def atlas(layers: tuple[Layer, ...], *, max_regions: int = 4096,
          retain_activation_cells: bool = False) -> tuple[Region, ...]:
    """Propagate exact affine output laws across every reachable real interval.

    A ReLU split is made at each interior zero of a preactivation affine
    expression. The functions are continuous, so endpoint values agree with
    the limits of their neighboring open intervals. When retaining activation
    cells, preserve intermediate ReLU split points even if later layers cancel.
    """
    validate(layers)
    if max_regions < 1:
        raise ValueError("max_regions must be positive")
    regions = [Region(None, None, (Affine(Fraction(1), Fraction(0)),))]
    for current in layers:
        result: list[Region] = []
        for region in regions:
            pre = tuple(Affine(
                sum((weight * expr.slope for weight, expr in zip(row, region.output)), Fraction(0)),
                sum((weight * expr.offset for weight, expr in zip(row, region.output)), bias))
                for row, bias in zip(current.weights, current.bias))
            if current.activation == "linear":
                result.append(Region(region.left, region.right, pre))
                continue
            roots = sorted({-expr.offset / expr.slope for expr in pre if expr.slope != 0
                            and inside(-expr.offset / expr.slope, region.left, region.right)})
            ends = [region.left, *roots, region.right]
            for left, right in zip(ends, ends[1:]):
                at = interior(left, right)
                result.append(Region(left, right, tuple(expr if expr.at(at) > 0 else ZERO for expr in pre)))
                if len(result) > max_regions:
                    raise RegionBudgetExceeded(f"exceeded {max_regions} intermediate regions")
        regions = result if retain_activation_cells else compact(result)
        if len(regions) > max_regions:
            raise RegionBudgetExceeded(f"exceeded {max_regions} intermediate regions")
    return tuple(regions)


def fingerprint(regions: tuple[Region, ...]) -> str:
    """Digest of normalized semantic function, not of model parameters."""
    payload = [{"left": token(p.left, infinite="-inf"),
                "right": token(p.right, infinite="+inf"),
                "affines": [[token(f.slope), token(f.offset)] for f in p.output]}
               for p in regions]
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def _two_points(left: Fraction | None, right: Fraction | None) -> tuple[Fraction, Fraction]:
    if left is None and right is None:
        return Fraction(0), Fraction(1)
    if left is None:
        return right - 1, right - 2
    if right is None:
        return left + 1, left + 2
    return (2 * left + right) / 3, (left + 2 * right) / 3


def _output_at(regions: tuple[Region, ...], x: Fraction) -> tuple[Affine, ...]:
    for region in regions:
        if inside(x, region.left, region.right):
            return region.output
    raise AssertionError("symbolic partition has a gap")


def compare(left: tuple[Layer, ...], right: tuple[Layer, ...],
            *, max_regions: int = 4096) -> dict[str, object]:
    """Exact semantic equivalence, counterexample, or budget-limited unknown.

    Universal result applies to *ideal real arithmetic* and rational weights
    for scalar-input feedforward affine/ReLU networks; no float inference.
    """
    try:
        l_atlas = atlas(left, max_regions=max_regions)
        r_atlas = atlas(right, max_regions=max_regions)
    except RegionBudgetExceeded as exc:
        return {"status": "unresolved", "reason": str(exc), "max_regions": max_regions}
    if len(l_atlas[0].output) != len(r_atlas[0].output):
        raise InvalidNetwork("output arities differ; specify an observation projection first")
    l_digest, r_digest = fingerprint(l_atlas), fingerprint(r_atlas)
    if l_atlas == r_atlas:
        return {"status": "equivalent", "semantic_digest": l_digest,
                "left_regions": len(l_atlas), "right_regions": len(r_atlas),
                "domain": "all-real-scalar-input"}
    cutpoints = sorted({edge for p in (*l_atlas, *r_atlas) for edge in (p.left, p.right)
                        if edge is not None})
    endpoints = [None, *cutpoints, None]
    for start, stop in zip(endpoints, endpoints[1:]):
        sample = interior(start, stop)
        a, b = _output_at(l_atlas, sample), _output_at(r_atlas, sample)
        if a != b:
            for witness in _two_points(start, stop):
                l_out = evaluate(left, witness)
                r_out = evaluate(right, witness)
                if l_out != r_out:
                    return {"status": "different", "witness": token(witness),
                            "left_output": [token(x) for x in l_out],
                            "right_output": [token(x) for x in r_out],
                            "left_digest": l_digest, "right_digest": r_digest,
                            "left_regions": len(l_atlas), "right_regions": len(r_atlas),
                            "domain": "all-real-scalar-input"}
            raise AssertionError("distinct affines did not yield witness at either point")
    raise AssertionError("differing canonical atlases were indistinguishable")
