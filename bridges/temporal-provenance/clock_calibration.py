"""Bounded affine clock calibration from explicit, uncertainty-bearing anchors.

This module does not infer anchors from similarity and does not assign
probabilities. It constructs the feasible set of positive affine clock maps
that satisfy every supplied target interval, then derives conservative mapped
intervals for source-clock observations within the calibration's declared
validity range.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.clock-calibration/0.1"
ANALYSIS_FORMAT = "in-formation.clock-calibration-analysis/0.1"
MODEL = "positive-affine-feasible-set-v1"
BASIS_VALUES = {
    "shared_trigger",
    "hardware_capture",
    "common_capture",
    "controlled_intervention",
}
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_CALIBRATION_FIELDS = {
    "format",
    "model",
    "calibration_id",
    "source_clock_id",
    "target_clock_id",
    "source_unit",
    "target_unit",
    "validity_source_min",
    "validity_source_max",
    "minimum_scale",
    "anchors",
    "feasible_region",
    "scale_bounds",
    "offset_bounds",
    "calibration_digest",
}
_ANCHOR_FIELDS = {
    "anchor_id",
    "source_coordinate",
    "target_lower",
    "target_upper",
    "correlation_basis",
    "witness_ref",
    "witness_sha256",
}
_REGION_VERTEX_FIELDS = {"scale", "offset"}


class ClockCalibrationError(ValueError):
    """A clock calibration or requested cross-clock comparison is invalid."""


class InfeasibleCalibrationError(ClockCalibrationError):
    """The supplied anchor intervals admit no positive affine clock mapping."""


class CalibrationRangeError(ClockCalibrationError):
    """A requested source coordinate lies outside the calibration validity range."""


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ClockCalibrationError(f"value is not canonical finite JSON: {exc}") from exc


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ClockCalibrationError(f"{label} must be non-empty text without NUL")
    return value.strip()


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ClockCalibrationError(f"{label} must be an integer >= {minimum}")
    return value


def _finite(value: object, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ClockCalibrationError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ClockCalibrationError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise ClockCalibrationError(f"{label} must be >= {minimum}")
    return result


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise ClockCalibrationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _normalize_anchors(anchors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(anchors, (list, tuple)) or len(anchors) < 2:
        raise ClockCalibrationError("at least two clock-correlation anchors are required")
    normalized = []
    anchor_ids: set[str] = set()
    witness_refs: set[str] = set()
    for index, anchor in enumerate(anchors):
        if not isinstance(anchor, Mapping) or set(anchor) != _ANCHOR_FIELDS:
            raise ClockCalibrationError(
                f"anchors[{index}] must contain exactly {sorted(_ANCHOR_FIELDS)}"
            )
        anchor_id = _text(anchor["anchor_id"], f"anchors[{index}].anchor_id")
        source_coordinate = _integer(
            anchor["source_coordinate"], f"anchors[{index}].source_coordinate"
        )
        target_lower = _finite(anchor["target_lower"], f"anchors[{index}].target_lower")
        target_upper = _finite(anchor["target_upper"], f"anchors[{index}].target_upper")
        if target_lower > target_upper:
            raise ClockCalibrationError(
                f"anchors[{index}].target_lower must not exceed target_upper"
            )
        basis = _text(anchor["correlation_basis"], f"anchors[{index}].correlation_basis")
        if basis not in BASIS_VALUES:
            raise ClockCalibrationError(
                f"anchors[{index}].correlation_basis must be one of {sorted(BASIS_VALUES)}"
            )
        witness_ref = _text(anchor["witness_ref"], f"anchors[{index}].witness_ref")
        witness_sha256 = _sha256(
            anchor["witness_sha256"], f"anchors[{index}].witness_sha256"
        )
        if anchor_id in anchor_ids:
            raise ClockCalibrationError("anchor IDs must be unique")
        if witness_ref in witness_refs:
            raise ClockCalibrationError("anchor witness references must be unique")
        anchor_ids.add(anchor_id)
        witness_refs.add(witness_ref)
        normalized.append({
            "anchor_id": anchor_id,
            "source_coordinate": source_coordinate,
            "target_lower": target_lower,
            "target_upper": target_upper,
            "correlation_basis": basis,
            "witness_ref": witness_ref,
            "witness_sha256": witness_sha256,
        })
    normalized.sort(key=lambda item: item["anchor_id"])
    distinct_source_coordinates = {
        item["source_coordinate"] for item in normalized
    }
    if len(distinct_source_coordinates) < 2:
        raise ClockCalibrationError(
            "anchors must span at least two distinct source-clock coordinates"
        )
    return normalized


def _constraints(
    anchors: Sequence[Mapping[str, Any]],
    minimum_scale: float,
) -> list[tuple[float, float, float]]:
    """Return A*scale + B*offset <= C half-planes."""
    constraints: list[tuple[float, float, float]] = [(-1.0, 0.0, -minimum_scale)]
    for anchor in anchors:
        x = float(anchor["source_coordinate"])
        constraints.append((x, 1.0, float(anchor["target_upper"])))
        constraints.append((-x, -1.0, -float(anchor["target_lower"])))
    return constraints


def _satisfies(
    scale: float,
    offset: float,
    constraints: Sequence[tuple[float, float, float]],
) -> bool:
    for a, b, c in constraints:
        lhs = a * scale + b * offset
        tolerance = 1e-10 * max(1.0, abs(lhs), abs(c))
        if lhs > c + tolerance:
            return False
    return True


def _feasible_vertices(
    constraints: Sequence[tuple[float, float, float]],
) -> list[dict[str, float]]:
    candidates: list[tuple[float, float]] = []
    for (a1, b1, c1), (a2, b2, c2) in combinations(constraints, 2):
        determinant = a1 * b2 - a2 * b1
        determinant_scale = max(1.0, abs(a1 * b2), abs(a2 * b1))
        if abs(determinant) <= 1e-14 * determinant_scale:
            continue
        scale = (c1 * b2 - c2 * b1) / determinant
        offset = (a1 * c2 - a2 * c1) / determinant
        if not math.isfinite(scale) or not math.isfinite(offset):
            continue
        if _satisfies(scale, offset, constraints):
            candidates.append((scale, offset))

    candidates.sort()
    unique: list[tuple[float, float]] = []
    for scale, offset in candidates:
        if not any(
            math.isclose(scale, prior_scale, rel_tol=1e-10, abs_tol=1e-10)
            and math.isclose(offset, prior_offset, rel_tol=1e-10, abs_tol=1e-10)
            for prior_scale, prior_offset in unique
        ):
            unique.append((scale, offset))
    if not unique:
        raise InfeasibleCalibrationError(
            "anchor intervals admit no positive affine clock mapping"
        )
    return [
        {"scale": scale, "offset": offset}
        for scale, offset in unique
    ]


def build_affine_calibration(
    *,
    calibration_id: str,
    source_clock_id: str,
    target_clock_id: str,
    source_unit: str,
    target_unit: str,
    anchors: Sequence[Mapping[str, Any]],
    validity_source_min: int | None = None,
    validity_source_max: int | None = None,
    minimum_scale: float = 1e-12,
) -> dict[str, Any]:
    """Build a bounded positive-affine calibration from interval-valued anchors.

    Every anchor asserts that one explicitly correlated physical event was
    observed at source_coordinate on the source clock and lies in
    [target_lower, target_upper] on the target clock. This function does not
    authenticate that assertion or fetch its witness artifact.
    """
    calibration_id = _text(calibration_id, "calibration_id")
    source_id = _text(source_clock_id, "source_clock_id")
    target_id = _text(target_clock_id, "target_clock_id")
    if source_id == target_id:
        raise ClockCalibrationError("source_clock_id and target_clock_id must differ")
    source_unit = _text(source_unit, "source_unit")
    target_unit = _text(target_unit, "target_unit")
    minimum_scale_value = _finite(minimum_scale, "minimum_scale", minimum=0.0)
    if minimum_scale_value <= 0:
        raise ClockCalibrationError("minimum_scale must be strictly positive")

    normalized_anchors = _normalize_anchors(anchors)
    anchor_min = min(item["source_coordinate"] for item in normalized_anchors)
    anchor_max = max(item["source_coordinate"] for item in normalized_anchors)
    validity_min = (
        anchor_min if validity_source_min is None
        else _integer(validity_source_min, "validity_source_min")
    )
    validity_max = (
        anchor_max if validity_source_max is None
        else _integer(validity_source_max, "validity_source_max")
    )
    if validity_min > validity_max:
        raise ClockCalibrationError("calibration validity range is reversed")
    if validity_min < anchor_min or validity_max > anchor_max:
        raise ClockCalibrationError(
            "calibration validity range must remain within the anchor span; extrapolation is not allowed"
        )

    constraints = _constraints(normalized_anchors, minimum_scale_value)
    region = _feasible_vertices(constraints)
    scales = [item["scale"] for item in region]
    offsets = [item["offset"] for item in region]
    core = {
        "format": FORMAT,
        "model": MODEL,
        "calibration_id": calibration_id,
        "source_clock_id": source_id,
        "target_clock_id": target_id,
        "source_unit": source_unit,
        "target_unit": target_unit,
        "validity_source_min": validity_min,
        "validity_source_max": validity_max,
        "minimum_scale": minimum_scale_value,
        "anchors": normalized_anchors,
        "feasible_region": region,
        "scale_bounds": {"lower": min(scales), "upper": max(scales)},
        "offset_bounds": {"lower": min(offsets), "upper": max(offsets)},
    }
    return {**core, "calibration_digest": digest(core)}


def validate_calibration(calibration: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild feasibility and all derived bounds; reject any changed certificate field."""
    if not isinstance(calibration, Mapping) or set(calibration) != _CALIBRATION_FIELDS:
        raise ClockCalibrationError(
            f"calibration must contain exactly {sorted(_CALIBRATION_FIELDS)}"
        )
    if calibration["format"] != FORMAT or calibration["model"] != MODEL:
        raise ClockCalibrationError("unsupported clock calibration format or model")
    rebuilt = build_affine_calibration(
        calibration_id=calibration["calibration_id"],
        source_clock_id=calibration["source_clock_id"],
        target_clock_id=calibration["target_clock_id"],
        source_unit=calibration["source_unit"],
        target_unit=calibration["target_unit"],
        anchors=calibration["anchors"],
        validity_source_min=calibration["validity_source_min"],
        validity_source_max=calibration["validity_source_max"],
        minimum_scale=calibration["minimum_scale"],
    )
    if rebuilt != dict(calibration):
        raise ClockCalibrationError(
            "calibration differs from independently reconstructed feasible set or digest"
        )
    return rebuilt


def map_source_interval(
    calibration: Mapping[str, Any],
    source_coordinate: int,
) -> dict[str, Any]:
    """Return the target-coordinate envelope across every feasible affine mapping."""
    calibration = validate_calibration(calibration)
    source = _integer(source_coordinate, "source_coordinate", minimum=-(2**63))
    if not (
        calibration["validity_source_min"]
        <= source
        <= calibration["validity_source_max"]
    ):
        raise CalibrationRangeError(
            "source coordinate is outside the calibrated validity range; extrapolation is refused"
        )
    mapped = [
        vertex["scale"] * source + vertex["offset"]
        for vertex in calibration["feasible_region"]
    ]
    lower, upper = min(mapped), max(mapped)
    return {
        "calibration_id": calibration["calibration_id"],
        "calibration_digest": calibration["calibration_digest"],
        "source_clock_id": calibration["source_clock_id"],
        "source_coordinate": source,
        "source_unit": calibration["source_unit"],
        "target_clock_id": calibration["target_clock_id"],
        "target_lower": lower,
        "target_upper": upper,
        "target_unit": calibration["target_unit"],
        "interpretation": "feasible_set_envelope_not_probability_or_confidence_interval",
    }


def compare_cross_clock_intervals(
    calibration: Mapping[str, Any],
    *,
    source_event_id: str,
    source_coordinate: int,
    target_event_id: str,
    target_lower: float,
    target_upper: float,
) -> dict[str, Any]:
    """Compare mapped source-event bounds to a target event's explicit interval.

    The result is strict only when the intervals are disjoint. Touching or
    overlapping intervals remain unresolved.
    """
    source_id = _text(source_event_id, "source_event_id")
    target_id = _text(target_event_id, "target_event_id")
    if source_id == target_id:
        raise ClockCalibrationError("cross-clock comparison requires distinct event IDs")
    target_low = _finite(target_lower, "target_lower")
    target_high = _finite(target_upper, "target_upper")
    if target_low > target_high:
        raise ClockCalibrationError("target_lower must not exceed target_upper")
    mapped = map_source_interval(calibration, source_coordinate)

    if mapped["target_upper"] < target_low:
        relation = "before"
        explanation = "every admissible mapped source coordinate precedes the target interval"
    elif mapped["target_lower"] > target_high:
        relation = "after"
        explanation = "every admissible mapped source coordinate follows the target interval"
    else:
        relation = "overlap_unresolved"
        explanation = "the mapped source envelope overlaps or touches the target interval"

    return {
        "source_event_id": source_id,
        "target_event_id": target_id,
        "relation": relation,
        "mapped_source_interval": {
            "lower": mapped["target_lower"],
            "upper": mapped["target_upper"],
            "unit": mapped["target_unit"],
        },
        "target_event_interval": {
            "lower": target_low,
            "upper": target_high,
            "unit": mapped["target_unit"],
        },
        "calibration_digest": mapped["calibration_digest"],
        "explanation": explanation,
    }


def _example_anchors() -> list[dict[str, Any]]:
    return [
        {
            "anchor_id": "pulse-001",
            "source_coordinate": 0,
            "target_lower": 100.0,
            "target_upper": 100.4,
            "correlation_basis": "shared_trigger",
            "witness_ref": "capture://shared-pulse-001",
            "witness_sha256": "1" * 64,
        },
        {
            "anchor_id": "pulse-002",
            "source_coordinate": 100,
            "target_lower": 300.0,
            "target_upper": 300.6,
            "correlation_basis": "shared_trigger",
            "witness_ref": "capture://shared-pulse-002",
            "witness_sha256": "2" * 64,
        },
        {
            "anchor_id": "pulse-003",
            "source_coordinate": 200,
            "target_lower": 500.0,
            "target_upper": 500.5,
            "correlation_basis": "shared_trigger",
            "witness_ref": "capture://shared-pulse-003",
            "witness_sha256": "3" * 64,
        },
    ]


def build_demonstration() -> dict[str, Any]:
    calibration = build_affine_calibration(
        calibration_id="controller-to-sensor-demo",
        source_clock_id="controller:C",
        target_clock_id="sensor:S",
        source_unit="tick",
        target_unit="tick",
        anchors=_example_anchors(),
    )
    certain_before = compare_cross_clock_intervals(
        calibration,
        source_event_id="controller-event-050",
        source_coordinate=50,
        target_event_id="sensor-event-400",
        target_lower=400.0,
        target_upper=400.2,
    )
    ambiguous_overlap = compare_cross_clock_intervals(
        calibration,
        source_event_id="controller-event-100",
        source_coordinate=100,
        target_event_id="sensor-event-300",
        target_lower=300.1,
        target_upper=300.3,
    )
    return {
        "format": ANALYSIS_FORMAT,
        "schema": ANALYSIS_FORMAT,
        "provenance": "synthetic calibration anchors with explicit shared-trigger declarations",
        "calibration": calibration,
        "comparisons": {
            "strictly_ordered": certain_before,
            "overlapping_uncertainty": ambiguous_overlap,
        },
        "interpretation": (
            "The anchor intervals constrain a set of positive affine mappings. "
            "The first comparison is before because every admissible mapping puts "
            "the source event before the target interval. The second remains "
            "unresolved because the mapped envelope overlaps the target interval."
        ),
        "boundaries": [
            "Correlation anchors are supplied declarations and are not authenticated here.",
            "Witness hashes are not proof that a witness is truthful or available.",
            "The affine clock model is an assumption tested for interval consistency, not guaranteed by feasibility.",
            "The mapping is only used within the source anchor span; no extrapolation occurs.",
            "The feasible envelope is not a probability distribution or calibrated confidence interval.",
            "A consistent calibration does not establish physical causation between the events.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or demonstrate bounded affine clock calibration."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build_demonstration()
    serialized = json.dumps(
        report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
