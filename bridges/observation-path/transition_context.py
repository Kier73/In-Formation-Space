"""Context-stratified analysis of repeated Trial 08 transition evidence.

Context values are caller-supplied observations bound to exact conformance
attempts. This module tests whether a declared partition reduces observed
within-stratum transition disagreement. It does not infer hidden-state
causation, stochasticity, probabilities, or model updates.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from math import comb
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Optional, Sequence

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_TRIAL_08 = _REPOSITORY_ROOT / "experiments" / "description-to-realization" / "trials" / "trial-08-intervention-aware-attention"
if str(_TRIAL_08) not in sys.path:
    sys.path.insert(0, str(_TRIAL_08))
from intervention_attention import validate_intervention_attention_document  # noqa: E402
from transition_conformance import validate_transition_conformance_record  # noqa: E402

_FORMAT = "in-formation.transition-context-analysis"
_SCHEMA = "in-formation.transition-context-analysis/0.1"
_ASSIGNMENT_FORMAT = "in-formation.transition-context-assignment"
_ASSIGNMENT_SCHEMA = "in-formation.transition-context-assignment/0.1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_DIMENSIONS = 32


class TransitionContextError(ValueError):
    """Invalid context assignment or unreconstructable transition evidence."""


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise TransitionContextError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise TransitionContextError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TransitionContextError(f"{label} must be non-empty text")
    return value


def _sha256(value: object, label: str) -> str:
    digest = _text(value, label)
    if _SHA256.fullmatch(digest) is None:
        raise TransitionContextError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _fraction(numerator: int, denominator: int) -> Optional[dict[str, int]]:
    if denominator <= 0:
        return None
    from fractions import Fraction
    value = Fraction(numerator, denominator)
    return {"numerator": value.numerator, "denominator": value.denominator}


def _transition_key(record: Mapping[str, Any]) -> str:
    transition = record["observed_transition"]
    return _canonical({
        "outcome": transition["outcome"],
        "next_state": transition["next_state"],
    })


def _is_full(record: Mapping[str, Any]) -> bool:
    return record["observed_transition"]["next_state"] is not None


def _histogram(records: Sequence[Mapping[str, Any]], *, full: bool) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        observed = record["observed_transition"]
        if full:
            key = _transition_key(record)
        else:
            key = _canonical(observed["outcome"])
        grouped[key].append(record)

    denominator = len(records)
    result = []
    for key in sorted(grouped):
        group = grouped[key]
        first = group[0]["observed_transition"]
        item = {
            "count": len(group),
            "empirical_frequency": _fraction(len(group), denominator),
            "source_attempt_ids": sorted(record["attempt_id"] for record in group),
        }
        if full:
            pair = json.loads(key)
            item["outcome"] = pair["outcome"]
            item["next_state"] = pair["next_state"]
        else:
            item["outcome"] = _copy_json(first["outcome"], "outcome-only histogram value")
        result.append(item)
    return result


def _disagreement_pairs(records: Sequence[Mapping[str, Any]]) -> int:
    total = comb(len(records), 2)
    same = Counter(_transition_key(record) for record in records)
    return total - sum(comb(count, 2) for count in same.values())


def _pairwise_comparison(
    full_records: Sequence[Mapping[str, Any]],
    full_groups: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Count exact pairwise disagreement before and after a context partition."""
    pooled_pairs = comb(len(full_records), 2)
    pooled_disagreements = _disagreement_pairs(full_records)
    within_pairs = sum(comb(len(group), 2) for group in full_groups.values())
    within_disagreements = sum(
        _disagreement_pairs(group) for group in full_groups.values()
    )
    between_pairs = pooled_pairs - within_pairs
    between_disagreements = pooled_disagreements - within_disagreements

    if not full_records:
        status = "no_full_transition_witnesses"
    elif len(full_groups) < 2:
        status = "insufficient_distinct_observed_context_values"
    elif pooled_disagreements == 0:
        status = "no_pooled_transition_diversity"
    elif within_pairs == 0:
        status = "no_within_stratum_pairs_to_test"
    elif within_disagreements == 0:
        status = "observed_partition_separates_supplied_sample"
    elif within_disagreements < pooled_disagreements:
        status = "observed_partition_reduces_within_stratum_disagreement"
    else:
        status = "no_observed_within_stratum_disagreement_reduction"

    return {
        "full_transition_sample_count": len(full_records),
        "pooled_pair_count": pooled_pairs,
        "pooled_disagreement_pair_count": pooled_disagreements,
        "pooled_disagreement_fraction": _fraction(pooled_disagreements, pooled_pairs),
        "within_stratum_pair_count": within_pairs,
        "within_stratum_disagreement_pair_count": within_disagreements,
        "within_stratum_disagreement_fraction": _fraction(
            within_disagreements, within_pairs
        ),
        "between_stratum_pair_count": between_pairs,
        "between_stratum_disagreement_pair_count": between_disagreements,
        "between_stratum_disagreement_fraction": _fraction(
            between_disagreements, between_pairs
        ),
        "separation_status": status,
    }


def _context_group(
    value: object,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    full = [record for record in records if _is_full(record)]
    outcome_only = [record for record in records if not _is_full(record)]
    return {
        "value": _copy_json(value, "context group value"),
        "sample_count": len(records),
        "full_transition_sample_count": len(full),
        "outcome_only_sample_count": len(outcome_only),
        "full_transition_histogram": _histogram(full, full=True),
        "outcome_only_histogram": _histogram(outcome_only, full=False),
        "source_attempt_ids": sorted(record["attempt_id"] for record in records),
    }


def _validate_dimensions(dimensions: object) -> dict[str, dict[str, Any]]:
    if not isinstance(dimensions, Mapping) or not dimensions:
        raise TransitionContextError("dimensions must be a non-empty object")
    if len(dimensions) > _MAX_DIMENSIONS:
        raise TransitionContextError(
            f"dimensions may contain at most {_MAX_DIMENSIONS} named fields"
        )
    normalized: dict[str, dict[str, Any]] = {}
    for raw_name, raw_value in dimensions.items():
        name = _text(raw_name, "dimension name")
        if not isinstance(raw_value, Mapping):
            raise TransitionContextError(f"dimension {name!r} must be an object")
        status = raw_value.get("status")
        if status == "observed":
            if set(raw_value) != {"status", "value"}:
                raise TransitionContextError(
                    f"observed dimension {name!r} must contain exactly status and value"
                )
            value = raw_value["value"]
            if type(value) not in (str, int, bool, type(None)):
                raise TransitionContextError(
                    f"observed dimension {name!r} must use a JSON scalar value"
                )
            normalized[name] = {"status": "observed", "value": value}
        elif status == "unknown":
            if set(raw_value) != {"status", "reason"}:
                raise TransitionContextError(
                    f"unknown dimension {name!r} must contain exactly status and reason"
                )
            normalized[name] = {
                "status": "unknown",
                "reason": _text(raw_value["reason"], f"dimension {name!r} unknown reason"),
            }
        else:
            raise TransitionContextError(
                f"dimension {name!r} status must be observed or unknown"
            )
    return {name: normalized[name] for name in sorted(normalized)}


def build_transition_context_assignment(
    *,
    attempt_id: str,
    conformance_record: Mapping[str, Any],
    dimensions: Mapping[str, Any],
    source_ref: Optional[str] = None,
) -> dict[str, Any]:
    """Bind caller-supplied context observations to one exact conformance attempt.

    A digest makes the assignment content-addressable; it does not authenticate
    the source or establish that a declared context value is true.
    """
    attempt = _text(attempt_id, "attempt_id")
    if not isinstance(conformance_record, Mapping):
        raise TypeError("conformance_record must be a mapping")
    if conformance_record.get("attempt_id") != attempt:
        raise TransitionContextError("attempt_id does not match conformance_record")
    conformance_digest = _sha256(
        conformance_record.get("conformance_digest"),
        "conformance_record.conformance_digest",
    )
    core: dict[str, Any] = {
        "format": _ASSIGNMENT_FORMAT,
        "schema": _ASSIGNMENT_SCHEMA,
        "attempt_id": attempt,
        "conformance_digest": conformance_digest,
        "dimensions": _validate_dimensions(dimensions),
    }
    if source_ref is not None:
        core["source_ref"] = _text(source_ref, "source_ref")
    return {**core, "assignment_digest": _digest(core)}


def _validate_assignment(raw: object) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise TypeError("context assignment must be an object")
    assignment = _copy_json(raw, "context assignment")
    required = {
        "format", "schema", "attempt_id", "conformance_digest",
        "dimensions", "assignment_digest",
    }
    allowed = required | {"source_ref"}
    if set(assignment) - allowed or required - set(assignment):
        raise TransitionContextError("context assignment has missing or unexpected fields")
    if assignment["format"] != _ASSIGNMENT_FORMAT or assignment["schema"] != _ASSIGNMENT_SCHEMA:
        raise TransitionContextError("unsupported context assignment format/schema")
    _text(assignment["attempt_id"], "context assignment attempt_id")
    _sha256(assignment["conformance_digest"], "context assignment conformance_digest")
    dimensions = _validate_dimensions(assignment["dimensions"])
    if dimensions != assignment["dimensions"]:
        raise TransitionContextError("context assignment dimensions are not canonical")
    if "source_ref" in assignment:
        _text(assignment["source_ref"], "context assignment source_ref")
    supplied_digest = _sha256(assignment["assignment_digest"], "assignment_digest")
    core = {key: value for key, value in assignment.items() if key != "assignment_digest"}
    if supplied_digest != _digest(core):
        raise TransitionContextError("context assignment digest does not match its contents")
    return assignment


def _dimension_analysis(
    *,
    dimension: str,
    records: Sequence[Mapping[str, Any]],
    assignments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    observed_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    observed_values: dict[str, Any] = {}
    unknown_ids = []
    not_supplied_ids = []
    unassigned_ids = []

    for record in records:
        attempt_id = record["attempt_id"]
        assignment = assignments.get(attempt_id)
        if assignment is None:
            unassigned_ids.append(attempt_id)
            continue
        descriptor = assignment["dimensions"].get(dimension)
        if descriptor is None:
            not_supplied_ids.append(attempt_id)
        elif descriptor["status"] == "unknown":
            unknown_ids.append(attempt_id)
        else:
            key = _canonical(descriptor["value"])
            observed_values[key] = descriptor["value"]
            observed_groups[key].append(record)

    full_groups = {
        key: full
        for key, group in observed_groups.items()
        if (full := [record for record in group if _is_full(record)])
    }
    full_records = [
        record
        for group in full_groups.values()
        for record in group
    ]
    groups = [
        _context_group(observed_values[key], observed_groups[key])
        for key in sorted(observed_groups)
    ]
    return {
        "dimension": dimension,
        "assigned_attempt_count": len(records) - len(unassigned_ids),
        "observed_attempt_count": sum(len(group) for group in observed_groups.values()),
        "unknown_attempt_ids": sorted(unknown_ids),
        "not_supplied_attempt_ids": sorted(not_supplied_ids),
        "unassigned_attempt_ids": sorted(unassigned_ids),
        "distinct_observed_value_count": len(observed_groups),
        "groups": groups,
        "pairwise_comparison": _pairwise_comparison(full_records, full_groups),
    }


def _joint_analysis(
    *,
    records: Sequence[Mapping[str, Any]],
    assignments: Mapping[str, Mapping[str, Any]],
    dimensions: Sequence[str],
) -> Optional[dict[str, Any]]:
    if not dimensions:
        return None
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    values: dict[str, dict[str, Any]] = {}
    incomplete_ids = []

    for record in records:
        assignment = assignments.get(record["attempt_id"])
        if assignment is None:
            incomplete_ids.append(record["attempt_id"])
            continue
        context: dict[str, Any] = {}
        complete = True
        for name in dimensions:
            descriptor = assignment["dimensions"].get(name)
            if descriptor is None or descriptor["status"] != "observed":
                complete = False
                break
            context[name] = descriptor["value"]
        if not complete:
            incomplete_ids.append(record["attempt_id"])
            continue
        key = _canonical(context)
        values[key] = context
        grouped[key].append(record)

    full_groups = {
        key: full
        for key, group in grouped.items()
        if (full := [record for record in group if _is_full(record)])
    }
    full_records = [
        record
        for group in full_groups.values()
        for record in group
    ]
    return {
        "dimension_names": list(dimensions),
        "complete_context_attempt_ids": sorted(
            record["attempt_id"]
            for group in grouped.values()
            for record in group
        ),
        "incomplete_context_attempt_ids": sorted(incomplete_ids),
        "distinct_joint_context_count": len(grouped),
        "groups": [
            _context_group(values[key], grouped[key])
            for key in sorted(grouped)
        ],
        "pairwise_comparison": _pairwise_comparison(full_records, full_groups),
    }


def _cell_analysis(
    records: Sequence[Mapping[str, Any]],
    assignments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    first = records[0]
    dimension_names = sorted({
        name
        for record in records
        for name in assignments.get(record["attempt_id"], {}).get("dimensions", {})
    })
    dimensions = [
        _dimension_analysis(
            dimension=name,
            records=records,
            assignments=assignments,
        )
        for name in dimension_names
    ]
    full_count = sum(1 for record in records if _is_full(record))
    outcome_only_count = len(records) - full_count
    assigned_count = sum(1 for record in records if record["attempt_id"] in assignments)
    return {
        "probe_id": first["probe_id"],
        "current_state": first["current_state"],
        "sample_count": len(records),
        "full_transition_sample_count": full_count,
        "outcome_only_sample_count": outcome_only_count,
        "context_assignment_count": assigned_count,
        "unassigned_attempt_ids": sorted(
            record["attempt_id"]
            for record in records
            if record["attempt_id"] not in assignments
        ),
        "dimensions": dimensions,
        "joint_context": _joint_analysis(
            records=records,
            assignments=assignments,
            dimensions=dimension_names,
        ),
    }


def build_transition_context_analysis(
    *,
    model_document: Mapping[str, Any],
    conformance_records: Sequence[Mapping[str, Any]],
    context_assignments: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Analyze observed transition disagreement under explicit context partitions."""
    try:
        model = validate_intervention_attention_document(model_document)
    except (TypeError, ValueError, KeyError) as error:
        raise TransitionContextError(f"invalid Trial 08 model document: {error}") from error
    if not isinstance(conformance_records, (list, tuple)) or not conformance_records:
        raise ValueError("conformance_records must be a non-empty sequence")
    if not isinstance(context_assignments, (list, tuple)):
        raise TypeError("context_assignments must be an array")

    records_by_attempt: dict[str, dict[str, Any]] = {}
    records_by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    conformance_digests = set()
    model_refs = set()
    for index, raw_record in enumerate(conformance_records):
        if not isinstance(raw_record, Mapping):
            raise TypeError(f"conformance_records[{index}] must be a mapping")
        record = _copy_json(raw_record, f"conformance_records[{index}]")
        try:
            validate_transition_conformance_record(record, model_document=model)
        except (TypeError, ValueError, KeyError) as error:
            raise TransitionContextError(
                f"conformance_records[{index}] failed independent reconstruction: {error}"
            ) from error
        attempt_id = record["attempt_id"]
        digest = record["conformance_digest"]
        if attempt_id in records_by_attempt:
            raise TransitionContextError(f"duplicate source attempt_id: {attempt_id}")
        if digest in conformance_digests:
            raise TransitionContextError(f"duplicate conformance digest: {digest}")
        records_by_attempt[attempt_id] = record
        records_by_cell[(record["probe_id"], record["current_state"])].append(record)
        conformance_digests.add(digest)
        model_refs.add(record["model_ref"])

    if len(model_refs) != 1:
        raise TransitionContextError("all conformance records must refer to the same model_ref")

    assignments_by_attempt: dict[str, dict[str, Any]] = {}
    assignment_digests = set()
    validated_assignments = []
    for index, raw_assignment in enumerate(context_assignments):
        assignment = _validate_assignment(raw_assignment)
        attempt_id = assignment["attempt_id"]
        record = records_by_attempt.get(attempt_id)
        if record is None:
            raise TransitionContextError(
                f"context assignment {index} refers to unknown attempt_id {attempt_id!r}"
            )
        if assignment["conformance_digest"] != record["conformance_digest"]:
            raise TransitionContextError(
                f"context assignment for {attempt_id!r} is bound to another conformance record"
            )
        if attempt_id in assignments_by_attempt:
            raise TransitionContextError(f"duplicate context assignment for attempt_id {attempt_id!r}")
        if assignment["assignment_digest"] in assignment_digests:
            raise TransitionContextError("duplicate context assignment digest")
        assignments_by_attempt[attempt_id] = assignment
        assignment_digests.add(assignment["assignment_digest"])
        validated_assignments.append(assignment)

    cells = [
        _cell_analysis(records, assignments_by_attempt)
        for _, records in sorted(records_by_cell.items())
    ]
    core = {
        "format": _FORMAT,
        "schema": _SCHEMA,
        "model_ref": next(iter(model_refs)),
        "model_digest": model["model_digest"],
        "source_conformance_digests": sorted(conformance_digests),
        "source_conformance_records": sorted(
            records_by_attempt.values(), key=lambda item: item["attempt_id"]
        ),
        "source_context_assignment_digests": sorted(assignment_digests),
        "source_context_assignments": sorted(
            validated_assignments, key=lambda item: item["attempt_id"]
        ),
        "cells": cells,
        "pairwise_semantics": "exact_descriptive_disagreement_counts_over_observed_full_transition_pairs",
        "frequency_semantics": "descriptive_empirical_sample_fraction_not_transition_probability",
        "policy_effect": "none",
        "model_effect": "none",
        "interpretation_limits": [
            "Every conformance record is reconstructed from the pinned Trial 08 model and its embedded ObservationPath snapshot before analysis.",
            "Context assignments are caller-supplied evidence claims bound to one exact attempt and conformance digest; their source artifacts are not fetched or authenticated here.",
            "A context value is an observed partition label, not proof that the context caused the transition.",
            "Unknown, not-supplied, and unassigned context are reported separately and are not collapsed into an observed context value.",
            "Pairwise disagreement counts compare supplied full transition witnesses only; outcome-only records never enter those denominators.",
            "A partition that separates the supplied sample does not establish hidden-state identity, causation, determinism, or generalization beyond the sample.",
            "The analysis does not infer transition probabilities, correct adaptive-policy selection bias, revise a model, change intervention costs, or alter attention policy.",
            "Repeated records may still differ because of unmeasured context, state drift, concurrency, observation error, or other omitted conditions.",
        ],
    }
    return {**core, "analysis_digest": _digest(core)}


def validate_transition_context_analysis(
    analysis: Mapping[str, Any],
    *,
    model_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild the result from its embedded conformance and context records."""
    if not isinstance(analysis, Mapping):
        raise TypeError("transition context analysis must be a mapping")
    supplied = dict(analysis)
    digest = supplied.pop("analysis_digest", None)
    if not isinstance(digest, str) or digest != _digest(supplied):
        raise TransitionContextError("analysis digest does not match its contents")
    if supplied.get("format") != _FORMAT or supplied.get("schema") != _SCHEMA:
        raise TransitionContextError("unsupported transition context analysis format/schema")
    source_records = supplied.get("source_conformance_records")
    source_assignments = supplied.get("source_context_assignments")
    if not isinstance(source_records, list) or not isinstance(source_assignments, list):
        raise TransitionContextError("embedded source records and assignments must be arrays")
    rebuilt = build_transition_context_analysis(
        model_document=model_document,
        conformance_records=source_records,
        context_assignments=source_assignments,
    )
    if rebuilt != dict(analysis):
        raise TransitionContextError(
            "analysis differs from independent reconstruction from embedded source records"
        )
    return dict(analysis)
