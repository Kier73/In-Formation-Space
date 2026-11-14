"""SNC-001: construct a ReLU realization from a verified-format semantic atlas.

The compilation algorithm is a producer, not a verifier. Receivers must
independently validate the portable COE-002 certificate and source binding.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import re
import sys

COE = Path(__file__).resolve().parents[1] / "continuous-observation-equivalence"
sys.path.insert(0, str(COE))
from continuous_equivalence import Affine, Region, fingerprint, layer, token  # noqa: E402
from certificate_producer import produce  # noqa: E402

SCHEMA = "in-formation-space.snc001.semantic-to-neural/0.1"
_RAT = re.compile(r"(?:0|-?[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z", re.ASCII)


class AtlasRejected(ValueError):
    """The proposed description cannot be compiled safely."""


def require(ok: bool, why: str) -> None:
    if not ok:
        raise AtlasRejected(why)


def rational(value: object) -> Fraction:
    require(type(value) is str and len(value) <= 128 and _RAT.fullmatch(value) is not None,
            "noncanonical rational token")
    result = Fraction(value)
    require(str(result) == value, "unreduced rational token")
    return result


def parse_atlas(value: object, *, max_regions: int = 64, max_outputs: int = 16
                ) -> tuple[Region, ...]:
    """Admit canonical, continuous, full-line piecewise-affine output laws.

    This is input validation for the construction, not an independent proof.
    """
    require(type(max_regions) is int and 1 <= max_regions <= 126,
            "unsupported region budget")
    require(type(max_outputs) is int and 1 <= max_outputs <= 16,
            "unsupported output budget")
    require(type(value) is list and 0 < len(value) <= max_regions,
            "empty atlas or region budget exceeded")
    result: list[Region] = []
    arity: int | None = None
    for i, raw in enumerate(value):
        require(type(raw) is dict and set(raw) == {"left", "right", "affines"},
                "unexpected semantic cell fields")
        left_raw, right_raw = raw["left"], raw["right"]
        require(type(left_raw) is str and type(right_raw) is str,
                "non-string atlas endpoint")
        left = None if left_raw == "-inf" else rational(left_raw)
        right = None if right_raw == "+inf" else rational(right_raw)
        require((left is None) == (i == 0), "invalid left infinity")
        require((right is None) == (i == len(value) - 1), "invalid right infinity")
        require(left is None or right is None or left < right, "empty interval")
        pairs = raw["affines"]
        require(type(pairs) is list and 0 < len(pairs) <= max_outputs,
                "invalid output arity")
        if arity is None:
            arity = len(pairs)
        require(len(pairs) == arity, "inconsistent output arity")
        affine = []
        for pair in pairs:
            require(type(pair) is list and len(pair) == 2, "invalid affine pair")
            affine.append(Affine(rational(pair[0]), rational(pair[1])))
        region = Region(left, right, tuple(affine))
        if result:
            previous = result[-1]
            require(previous.right == left, "gap or overlap in atlas")
            require(previous.output != region.output,
                    "nonmaximal semantic atlas (redundant region)")
            require(all(a.at(left) == b.at(left) for a, b in
                        zip(previous.output, region.output)),
                    "discontinuous output at a breakpoint")
        result.append(region)
    return tuple(result)


def describe(regions: tuple[Region, ...]) -> list[dict[str, object]]:
    return [
        {"left": token(r.left, infinite="-inf"),
         "right": token(r.right, infinite="+inf"),
         "affines": [[token(a.slope), token(a.offset)] for a in r.output]}
        for r in regions
    ]


def construct(regions: tuple[Region, ...]):
    """Compile slopes and hinges into two exact rational affine/ReLU layers.

    x = ReLU(x) - ReLU(-x), so the initial slope is represented exactly.
    Every subsequent slope change is a ReLU(x - breakpoint) contribution.
    """
    require(len(regions) >= 1 and regions[0].left is None and
            regions[-1].right is None, "requires a full-line atlas")
    hinges = [r.left for r in regions[1:]]
    hidden = layer(
        [[1], [-1]] + [[1] for _ in hinges],
        [0, 0] + [-p for p in hinges],
        "relu",
    )
    out_rows: list[list[Fraction]] = []
    biases: list[Fraction] = []
    for channel in range(len(regions[0].output)):
        first = regions[0].output[channel]
        slopes = [r.output[channel].slope for r in regions]
        row = [first.slope, -first.slope]
        row.extend(current - previous for previous, current in
                   zip(slopes, slopes[1:]))
        out_rows.append(row)
        biases.append(first.offset)
    return (hidden, layer(out_rows, biases, "linear"))


def compile_semantics(source_atlas: object, *, max_regions: int = 64
                     ) -> dict[str, object]:
    regions = parse_atlas(source_atlas, max_regions=max_regions)
    network = construct(regions)
    semantic = describe(regions)
    certificate = produce(network, max_cells=max_regions * 4)
    source_sha = fingerprint(regions)
    # This producer-side check is a useful regression guard, not proof.
    require(certificate["semantic_atlas"] == semantic and
            certificate["semantic_sha256"] == source_sha,
            "constructed network did not reproduce requested atlas")
    return {
        "schema": SCHEMA,
        "source_semantic_atlas": semantic,
        "source_semantic_sha256": source_sha,
        "generated_certificate": certificate,
    }
