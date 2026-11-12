"""Exact empirical summaries of repeated Trial 08 transition observations.

This module counts completed conformance records for the same model/probe/state
cell. Full before/after witnesses and outcome-only returns are kept in
separate populations. Frequencies are descriptive sample fractions, not
inferred transition probabilities.

The output intentionally does not rewrite a Trial 08 model, infer a stochastic
process, or update intervention cost. It is a review artifact for deciding
what further experiments are needed.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from transition_conformance import (
    TransitionConformanceError,
    validate_transition_conformance_record,
)

_TRIAL_08 = Path(__file__).resolve().parents[2] / "experiments" / "description-to-realization" / "trials" / "trial-08-intervention-aware-attention"
if str(_TRIAL_08) not in sys.path:
    sys.path.insert(0, str(_TRIAL_08))
from intervention_attention import validate_intervention_attention_document  # noqa: E402

_FORMAT = "in-formation.transition-evidence-summary"
_SCHEMA = "in-formation.transition-evidence-summary/0.1"


class TransitionEvidenceError(ValueError):
    """Invalid, mixed, or duplicated transition evidence."""


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise TransitionEvidenceError(f"value must be finite canonical JSON: {error}") from error


def _copy(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise TransitionEvidenceError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _fraction(count: int, denominator: int) -> dict[str, int]:
    if denominator <= 0:
        raise TransitionEvidenceError("frequency denominator must be positive")
    from fractions import Fraction
    value = Fraction(count, denominator)
    return {"numerator": value.numerator, "denominator": value.denominator}


def _transition_cell(model: Mapping[str, Any], probe_id: str, current_state: str) -> Mapping[str, Any]:
    matches = [probe for probe in model["model"]["probes"] if probe["probe_id"] == probe_id]
    if len(matches) != 1:
        raise TransitionEvidenceError(f"model has no unique probe: {probe_id}")
    transition = matches[0]["transitions"].get(current_state)
    if transition is None:
        raise TransitionEvidenceError(f"model has no transition for {probe_id!r} at {current_state!r}")
    return transition


def _count_records(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(record["conformance_status"] for record in records)
    return {status: counts[status] for status in sorted(counts)}


def _cell_summary(
    *,
    model: Mapping[str, Any],
    probe_id: str,
    current_state: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    predicted = _transition_cell(model, probe_id, current_state)
    full = [record for record in records if record["observed_transition"]["next_state"] is not None]
    outcome_only = [record for record in records if record["observed_transition"]["next_state"] is None]

    full_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    outcome_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in full:
        value = record["observed_transition"]
        full_groups[_canonical({
            "outcome": value["outcome"],
            "next_state": value["next_state"],
        })].append(record)
    for record in outcome_only:
        value = record["observed_transition"]["outcome"]
        outcome_groups[_canonical(value)].append(record)

    full_histogram = []
    for key in sorted(full_groups):
        group = full_groups[key]
        pair = json.loads(key)
        full_histogram.append({
            "outcome": pair["outcome"],
            "next_state": pair["next_state"],
            "count": len(group),
            "empirical_frequency": _fraction(len(group), len(full)),
            "source_attempt_ids": sorted(record["attempt_id"] for record in group),
        })

    outcome_histogram = []
    for key in sorted(outcome_groups):
        group = outcome_groups[key]
        outcome_histogram.append({
            "outcome": json.loads(key),
            "count": len(group),
            "empirical_frequency": _fraction(len(group), len(outcome_only)),
            "source_attempt_ids": sorted(record["attempt_id"] for record in group),
        })

    if not full:
        diversity = "no_full_transition_witnesses"
        prediction_status = "outcome_only_evidence_not_sufficient_for_transition_comparison"
    elif len(full_groups) == 1:
        diversity = "one_distinct_full_transition_observed"
        prediction_status = (
            "all_full_samples_match_prediction"
            if all(record["conformance_status"] == "matched" for record in full)
            else "at_least_one_full_sample_mismatches_prediction"
        )
    else:
        diversity = "multiple_distinct_full_transitions_observed"
        prediction_status = (
            "all_full_samples_match_prediction"
            if all(record["conformance_status"] == "matched" for record in full)
            else "at_least_one_full_sample_mismatches_prediction"
        )

    all_records = sorted(records, key=lambda item: item["attempt_id"])
    return {
        "probe_id": probe_id,
        "current_state": current_state,
        "predicted_transition": {
            "outcome": _copy(predicted["outcome"], "predicted outcome"),
            "next_state": predicted["next_state"],
            "intervention_cost": _copy(predicted["intervention_cost"], "predicted intervention cost"),
        },
        "sample_count": len(all_records),
        "full_transition_sample_count": len(full),
        "outcome_only_sample_count": len(outcome_only),
        "conformance_status_counts": _count_records(all_records),
        "transition_diversity": diversity,
        "prediction_status": prediction_status,
        "full_transition_histogram": full_histogram,
        "outcome_only_histogram": outcome_histogram,
        "source_samples": [
            {
                "attempt_id": record["attempt_id"],
                "conformance_id": record["conformance_id"],
                "conformance_digest": record["conformance_digest"],
                "conformance_status": record["conformance_status"],
                "returned_ref": record["source_evidence"]["returned_ref"],
                "encounter_id": record["source_evidence"]["encounter_id"],
                "payload_digest": record["source_evidence"]["payload_digest"],
                "before_state_evidence": _copy(record["state_evidence"]["before"], "before state evidence"),
                "after_state_evidence": _copy(record["state_evidence"]["after"], "after state evidence"),
            }
            for record in all_records
        ],
        "interpretation": (
            "Observed frequencies describe only the supplied, policy-selected sample. "
            "One distinct observed value does not establish a deterministic transition; "
            "multiple values do not by themselves establish a stochastic transition."
        ),
    }


def build_transition_evidence_summary(
    *,
    model_document: Mapping[str, Any],
    conformance_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a digest-bound, self-contained summary grouped by probe/state cell."""
    try:
        model = validate_intervention_attention_document(model_document)
    except (TypeError, ValueError, KeyError) as error:
        raise TransitionEvidenceError(f"invalid Trial 08 model document: {error}") from error
    if not isinstance(conformance_records, (list, tuple)) or not conformance_records:
        raise ValueError("conformance_records must be a non-empty sequence")

    validated_records = []
    attempt_ids = set()
    conformance_digests = set()
    model_refs = set()
    cell_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for index, raw_record in enumerate(conformance_records):
        if not isinstance(raw_record, Mapping):
            raise TypeError(f"conformance_records[{index}] must be a mapping")
        record = _copy(raw_record, f"conformance_records[{index}]")
        try:
            validate_transition_conformance_record(record, model_document=model)
        except (TypeError, ValueError, KeyError) as error:
            raise TransitionEvidenceError(
                f"conformance_records[{index}] failed independent reconstruction: {error}"
            ) from error
        attempt_id = record["attempt_id"]
        digest = record["conformance_digest"]
        if attempt_id in attempt_ids:
            raise TransitionEvidenceError(f"duplicate source attempt_id: {attempt_id}")
        if digest in conformance_digests:
            raise TransitionEvidenceError(f"duplicate conformance digest: {digest}")
        attempt_ids.add(attempt_id)
        conformance_digests.add(digest)
        model_refs.add(record["model_ref"])
        cell_groups[(record["probe_id"], record["current_state"])].append(record)
        validated_records.append(record)

    if len(model_refs) != 1:
        raise TransitionEvidenceError("all records must refer to the same model_ref")
    cells = [
        _cell_summary(
            model=model,
            probe_id=probe_id,
            current_state=current_state,
            records=records,
        )
        for (probe_id, current_state), records in sorted(cell_groups.items())
    ]
    core = {
        "format": _FORMAT,
        "schema": _SCHEMA,
        "model_ref": next(iter(model_refs)),
        "model_digest": model["model_digest"],
        "source_conformance_digests": sorted(conformance_digests),
        "source_conformance_records": sorted(validated_records, key=lambda item: item["attempt_id"]),
        "cells": cells,
        "frequency_semantics": "descriptive_empirical_sample_fraction_not_transition_probability",
        "policy_effect": "none",
        "interpretation_limits": [
            "Every source conformance record is reconstructed from the pinned Trial 08 model and its embedded ObservationPath snapshot before aggregation.",
            "Encounter Envelope and state-witness references remain external claims; this module does not fetch or authenticate their contents.",
            "The provided records may be selected by an adaptive policy; reported empirical frequencies are not corrected for selection bias.",
            "Outcome-only observations are counted separately and never enter full-transition denominators.",
            "A single distinct observed transition does not prove deterministic system dynamics.",
            "Multiple distinct observed transitions do not by themselves prove a stochastic process; unmodelled context, state drift, concurrency, or measurement error may explain them.",
            "No candidate transition, probability model, intervention cost, or Trial 08 planner revision is automatically created or activated.",
            "Intervention-cost semantics remain those of the pinned model and are not inferred from operation timing.",
        ],
    }
    return {**core, "summary_digest": _digest(core)}


def validate_transition_evidence_summary(
    summary: Mapping[str, Any],
    *,
    model_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild the aggregation from its embedded source conformance records."""
    if not isinstance(summary, Mapping):
        raise TypeError("transition evidence summary must be a mapping")
    supplied = dict(summary)
    digest = supplied.pop("summary_digest", None)
    if not isinstance(digest, str) or digest != _digest(supplied):
        raise TransitionEvidenceError("transition evidence summary digest does not match its contents")
    if supplied.get("format") != _FORMAT or supplied.get("schema") != _SCHEMA:
        raise TransitionEvidenceError("unsupported transition evidence summary format/schema")
    source_records = supplied.get("source_conformance_records")
    if not isinstance(source_records, list):
        raise TransitionEvidenceError("source_conformance_records must be an array")
    rebuilt = build_transition_evidence_summary(
        model_document=model_document,
        conformance_records=source_records,
    )
    if rebuilt != dict(summary):
        raise TransitionEvidenceError("summary differs from independent reconstruction from source records")
    return dict(summary)
