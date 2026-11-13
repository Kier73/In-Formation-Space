"""One-reference-step lookahead for calibration acquisition and evidence gating.

RIV-010 values a known-standard measurement by its expected effect on the
*subsequent target decision*. This differs from RIV-008's immediate myopic
EVSI: a calibration reference can improve C without changing the current
marginal decision about an as-yet-unobserved target H.

After planning, a selected reference can be admitted only through an
ObservationPath with dispatch, admission, return, AUTHORIZED evidence, and
interpretation. The resulting reference row is passed to RIV-009, which owns
the exact shared-calibration update and target filtering.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from observation_path import ObservationIntent, ObservationPath

FORMAT = "in-formation.reference-acquisition-lookahead/0.1"
RIV007_FORMAT = "in-formation.calibration-aware-evidence/0.1"
RIV009_FORMAT = "in-formation.reference-calibrated-evidence/0.1"
RIV008_FORMAT = "in-formation.decision-value-context-acquisition/0.1"
_INTERPRETATION_METHOD = "exact-calibration-reference-outcome-v1"
_REQUIRED_STAGES = (
    "planned",
    "dispatched",
    "admitted",
    "returned",
    "evidence_authorized",
    "interpreted",
)
_REFERENCE_CANDIDATE_FIELDS = {
    "candidate_id",
    "sensor_id",
    "known_hypothesis",
    "reference_standard_ref",
    "reference_standard_sha256",
    "cost",
}
_RETURN_FIELDS = {
    "encounter_id",
    "payload_digest",
    "canonicalization",
    "candidate_id",
    "sensor_id",
    "dimension",
    "known_hypothesis",
    "reference_standard_ref",
    "reference_standard_sha256",
    "reference_acquisition_report_digest",
    "observed_outcome",
}
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")


class ReferenceAcquisitionError(ValueError):
    """Invalid reference-acquisition model, report, or execution evidence."""


class ReferenceAcquisitionMismatch(ReferenceAcquisitionError):
    """A returned reference outcome is impossible or mismatched to its plan."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load required module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[2]
_RIV007 = _load_module(
    "riv010_riv007",
    _ROOT / "experiments" / "calibration-aware-joint-evidence" / "calibration_aware_evidence.py",
)
_RIV008 = _load_module(
    "riv010_riv008",
    _ROOT / "experiments" / "decision-value-context-acquisition" / "decision_value_acquisition.py",
)
_RIV009 = _load_module(
    "riv010_riv009",
    Path(__file__).resolve().with_name("reference_calibrated_evidence.py"),
)
if _RIV007.FORMAT != RIV007_FORMAT:
    raise RuntimeError("RIV-010 requires the declared RIV-007 report contract")
if _RIV009.FORMAT != RIV009_FORMAT:
    raise RuntimeError("RIV-010 requires the declared RIV-009 report contract")
if _RIV008.FORMAT != RIV008_FORMAT:
    raise RuntimeError("RIV-010 requires the declared RIV-008 report contract")


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ReferenceAcquisitionError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise ReferenceAcquisitionError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ReferenceAcquisitionError(f"{label} must be non-empty text without NUL")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise ReferenceAcquisitionError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _rational(
    value: object,
    label: str,
    *,
    nonnegative: bool = False,
    positive: bool = False,
    unit_interval: bool = False,
) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise ReferenceAcquisitionError(
            f"{label} must be exact; floats and booleans are rejected"
        )
    try:
        if isinstance(value, Mapping) and set(value) == {"numerator", "denominator"}:
            numerator, denominator = value["numerator"], value["denominator"]
            if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
                raise ValueError
            result = Fraction(numerator, denominator)
        else:
            result = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise ReferenceAcquisitionError(f"{label} must be an exact rational") from error
    if nonnegative and result < 0:
        raise ReferenceAcquisitionError(f"{label} must be non-negative")
    if positive and result <= 0:
        raise ReferenceAcquisitionError(f"{label} must be positive")
    if unit_interval and not 0 <= result <= 1:
        raise ReferenceAcquisitionError(f"{label} must be in [0, 1]")
    return result


def _fraction_doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _fraction_value(value: object, label: str) -> Fraction:
    if not isinstance(value, Mapping) or set(value) != {"numerator", "denominator"}:
        raise ReferenceAcquisitionError(f"{label} must be an exact rational document")
    return _rational(value, label)


def _base_target_report(
    *,
    prior_hypothesis_a: object,
    calibrations: Sequence[Mapping[str, Any]],
    target_sensor_schedule: Sequence[str],
    max_histories: int,
) -> dict[str, Any]:
    try:
        report = _RIV007.build_report(
            prior_hypothesis_a=prior_hypothesis_a,
            calibrations=calibrations,
            sensor_schedule=target_sensor_schedule,
            max_histories=max_histories,
        )
        _RIV007.validate_report(report)
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        raise ReferenceAcquisitionError(
            f"RIV-007 could not construct the current target filter: {error}"
        ) from error
    return report


def _normalize_reference_candidates(
    raw: object,
    sensor_schedule: Sequence[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw, (tuple, list)) or not raw:
        raise ReferenceAcquisitionError("reference_candidates must be a non-empty sequence")
    if len(raw) > 64:
        raise ReferenceAcquisitionError("at most 64 reference candidates are supported")
    allowed_sensors = set(sensor_schedule)
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, candidate in enumerate(raw):
        if not isinstance(candidate, Mapping) or set(candidate) != _REFERENCE_CANDIDATE_FIELDS:
            raise ReferenceAcquisitionError(
                f"reference_candidates[{index}] must contain exactly {sorted(_REFERENCE_CANDIDATE_FIELDS)}"
            )
        candidate_id = _text(candidate["candidate_id"], "candidate_id")
        if candidate_id in seen:
            raise ReferenceAcquisitionError(f"duplicate candidate_id: {candidate_id}")
        seen.add(candidate_id)
        sensor_id = _text(candidate["sensor_id"], f"{candidate_id}.sensor_id")
        if sensor_id not in allowed_sensors:
            raise ReferenceAcquisitionError(
                f"{candidate_id}.sensor_id must appear in the target sensor schedule"
            )
        known_hypothesis = candidate["known_hypothesis"]
        if known_hypothesis not in ("A", "B"):
            raise ReferenceAcquisitionError(
                f"{candidate_id}.known_hypothesis must be A or B"
            )
        normalized.append({
            "candidate_id": candidate_id,
            "sensor_id": sensor_id,
            "known_hypothesis": known_hypothesis,
            "reference_standard_ref": _text(
                candidate["reference_standard_ref"],
                f"{candidate_id}.reference_standard_ref",
            ),
            "reference_standard_sha256": _sha256(
                candidate["reference_standard_sha256"],
                f"{candidate_id}.reference_standard_sha256",
            ),
            "cost": _fraction_doc(_rational(
                candidate["cost"], f"{candidate_id}.cost", positive=True
            )),
            "outcomes": ["A", "B"],
        })
    return sorted(normalized, key=lambda item: item["candidate_id"])


def _reference_likelihood(
    calibration: Mapping[str, Any],
    sensor_id: str,
    known_hypothesis: str,
    signal: str,
) -> Fraction:
    model = calibration["sensor_models"][sensor_id]
    field = (
        "p_signal_a_given_hypothesis_a"
        if known_hypothesis == "A"
        else "p_signal_a_given_hypothesis_b"
    )
    p_signal_a = Fraction(**model[field])
    return p_signal_a if signal == "A" else 1 - p_signal_a


def _posterior_calibration(
    prior: Mapping[str, Fraction],
    calibrations: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    signal: str,
) -> tuple[dict[str, Fraction], Fraction]:
    likelihoods = {
        item["calibration_id"]: _reference_likelihood(
            item, candidate["sensor_id"], candidate["known_hypothesis"], signal
        )
        for item in calibrations
    }
    weighted = {
        key: prior[key] * likelihoods[key]
        for key in prior
    }
    predictive = sum(weighted.values(), Fraction(0))
    if predictive == 0:
        return {}, Fraction(0)
    posterior = {
        key: weighted[key] / predictive
        for key in weighted
    }
    return posterior, predictive


def _target_accuracy(
    prior_hypothesis_a: object,
    calibrations: Sequence[Mapping[str, Any]],
    sensor_schedule: Sequence[str],
    max_histories: int,
) -> tuple[Fraction, dict[str, Any]]:
    report = _base_target_report(
        prior_hypothesis_a=prior_hypothesis_a,
        calibrations=calibrations,
        target_sensor_schedule=sensor_schedule,
        max_histories=max_histories,
    )
    return Fraction(**report["summary"]["shared_calibration_map_accuracy"]), report


def _myopic_riv008_comparator(
    *,
    prior_hypothesis_a: Fraction,
    calibrations: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    upstream_report_digest: str,
) -> dict[str, Any]:
    """Show what current-target RIV-008 EVSI assigns this reference reading."""
    rows = []
    for hypothesis, prior_h in (
        ("A", prior_hypothesis_a),
        ("B", 1 - prior_hypothesis_a),
    ):
        for calibration in calibrations:
            rows.append({
                "hypothesis": hypothesis,
                "context_state": calibration["calibration_id"],
                "probability": _fraction_doc(
                    prior_h * Fraction(**calibration["prior_probability"])
                ),
            })
    belief = _RIV008.build_joint_belief_document(
        joint_posterior=rows,
        source_ref=f"urn:sha256:{upstream_report_digest}",
        source_report_digest=upstream_report_digest,
    )
    outcome_rows = []
    for signal in ("A", "B"):
        likelihoods = []
        for hypothesis in ("A", "B"):
            for calibration in calibrations:
                # A known reference standard makes the reference likelihood
                # depend on C and the known standard, not on the unknown target H.
                probability = _reference_likelihood(
                    calibration,
                    candidate["sensor_id"],
                    candidate["known_hypothesis"],
                    signal,
                )
                likelihoods.append({
                    "hypothesis": hypothesis,
                    "context_state": calibration["calibration_id"],
                    "probability": _fraction_doc(probability),
                })
        outcome_rows.append({"outcome": signal, "likelihoods": likelihoods})
    candidate_model = {
        "sensor_id": candidate["candidate_id"],
        "dimension": f"known-reference:{candidate['known_hypothesis']}",
        "cost": candidate["cost"],
        "outcomes": outcome_rows,
    }
    report = _RIV008.build_report(
        joint_belief=belief,
        candidate_sensors=(candidate_model,),
    )
    _RIV008.validate_report(report)
    score = report["candidate_evaluations"][0]
    return {
        "objective": "immediate_target_hypothesis_decision_loss",
        "expected_bayes_risk_reduction": score["expected_bayes_risk_reduction"],
        "expected_value_per_cost": score["expected_value_per_cost"],
        "selection_status": report["selection"]["status"],
        "reason": (
            "the reference likelihood depends on calibration but is independent of the unknown target hypothesis; "
            "with an independent H x C prior, the current target decision is unchanged"
        ),
        "report_digest": report["report_digest"],
    }


def _pareto_frontier(candidate_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    frontier: list[str] = []
    for candidate in candidate_rows:
        cost = Fraction(**candidate["cost"])
        risk = 1 - Fraction(**candidate["expected_target_map_accuracy"])
        dominated = False
        for other in candidate_rows:
            if other["candidate_id"] == candidate["candidate_id"]:
                continue
            other_cost = Fraction(**other["cost"])
            other_risk = 1 - Fraction(**other["expected_target_map_accuracy"])
            if (
                other_cost <= cost
                and other_risk <= risk
                and (other_cost < cost or other_risk < risk)
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate["candidate_id"])
    return sorted(frontier)


def build_report(
    *,
    prior_hypothesis_a: object,
    calibrations: Sequence[Mapping[str, Any]],
    target_sensor_schedule: Sequence[str],
    reference_candidates: Sequence[Mapping[str, Any]],
    cost_budget: Optional[object] = None,
    source_reference_report_digest: Optional[str] = None,
    max_histories: int = 1_000_000,
) -> dict[str, Any]:
    """Choose one known-standard reading by its expected downstream target value.

    This is a one-reference-step lookahead to a fixed downstream target
    observation schedule. It is not a multi-reference dynamic programme.
    """
    if isinstance(max_histories, bool) or not isinstance(max_histories, int) or max_histories < 1:
        raise ReferenceAcquisitionError("max_histories must be a positive integer")
    source_ref_digest = (
        None if source_reference_report_digest is None
        else _sha256(source_reference_report_digest, "source_reference_report_digest")
    )
    baseline = _base_target_report(
        prior_hypothesis_a=prior_hypothesis_a,
        calibrations=calibrations,
        target_sensor_schedule=target_sensor_schedule,
        max_histories=max_histories,
    )
    prior_a = Fraction(**baseline["model"]["prior_A"])
    normalized_calibrations = baseline["model"]["calibrations"]
    schedule = baseline["model"]["sensor_schedule"]
    candidates = _normalize_reference_candidates(reference_candidates, schedule)
    budget = (
        None if cost_budget is None
        else _fraction_doc(_rational(cost_budget, "cost_budget", nonnegative=True))
    )
    prior_c = {
        item["calibration_id"]: Fraction(**item["prior_probability"])
        for item in normalized_calibrations
    }
    baseline_accuracy = Fraction(**baseline["summary"]["shared_calibration_map_accuracy"])
    evaluated: list[dict[str, Any]] = []
    for candidate in candidates:
        branches = []
        expected_accuracy = Fraction(0)
        for signal in ("A", "B"):
            posterior_c, predictive = _posterior_calibration(
                prior_c, normalized_calibrations, candidate, signal
            )
            if predictive == 0:
                branches.append({
                    "signal": signal,
                    "predictive_probability": _fraction_doc(Fraction(0)),
                    "reachable": False,
                    "posterior_calibration_probabilities": None,
                    "target_map_accuracy": None,
                    "target_filter_report": None,
                })
                continue
            updated_calibrations = [
                {
                    **item,
                    "prior_probability": _fraction_doc(posterior_c[item["calibration_id"]]),
                }
                for item in normalized_calibrations
            ]
            target_accuracy, target_report = _target_accuracy(
                prior_a,
                updated_calibrations,
                schedule,
                max_histories,
            )
            expected_accuracy += predictive * target_accuracy
            branches.append({
                "signal": signal,
                "predictive_probability": _fraction_doc(predictive),
                "reachable": True,
                "posterior_calibration_probabilities": [
                    {
                        "calibration_id": key,
                        "probability": _fraction_doc(posterior_c[key]),
                    }
                    for key in sorted(posterior_c)
                ],
                "target_map_accuracy": _fraction_doc(target_accuracy),
                "target_filter_report": target_report,
            })
        value = expected_accuracy - baseline_accuracy
        if value < 0:
            raise AssertionError(
                "expected downstream Bayes decision accuracy cannot decrease after optional reference information"
            )
        cost = Fraction(**candidate["cost"])
        comparator = _myopic_riv008_comparator(
            prior_hypothesis_a=prior_a,
            calibrations=normalized_calibrations,
            candidate=candidate,
            upstream_report_digest=baseline["content_digest"],
        )
        if Fraction(**comparator["expected_bayes_risk_reduction"]) != 0:
            raise AssertionError(
                "known-reference measurement should not change current H decision under independent H x C prior"
            )
        evaluated.append({
            **candidate,
            "branches": branches,
            "baseline_target_map_accuracy": _fraction_doc(baseline_accuracy),
            "expected_target_map_accuracy": _fraction_doc(expected_accuracy),
            "expected_downstream_decision_value": _fraction_doc(value),
            "expected_downstream_decision_value_per_cost": _fraction_doc(value / cost),
            "myopic_riv008_comparator": comparator,
        })
    eligible = [
        item for item in evaluated
        if budget is None or Fraction(**item["cost"]) <= Fraction(**budget)
    ]
    positive = [
        item for item in eligible
        if Fraction(**item["expected_downstream_decision_value"]) > 0
    ]
    if positive:
        selected = min(
            positive,
            key=lambda item: (
                -Fraction(**item["expected_downstream_decision_value_per_cost"]),
                -Fraction(**item["expected_downstream_decision_value"]),
                Fraction(**item["cost"]),
                item["candidate_id"],
            ),
        )
        selection = {
            "status": "selected",
            "objective": (
                "maximize one-reference-step expected downstream target MAP accuracy gain per cost; "
                "then maximize gain; then minimize cost; then lexical candidate_id"
            ),
            "cost_budget": budget,
            "eligible_candidate_ids": sorted(item["candidate_id"] for item in eligible),
            "selected_candidate_id": selected["candidate_id"],
        }
    else:
        selection = {
            "status": (
                "no_positive_value_candidate_within_cost_budget"
                if eligible else "no_candidate_within_cost_budget"
            ),
            "objective": (
                "maximize one-reference-step expected downstream target MAP accuracy gain per cost"
            ),
            "cost_budget": budget,
            "eligible_candidate_ids": sorted(item["candidate_id"] for item in eligible),
            "selected_candidate_id": None,
        }
    core = {
        "format": FORMAT,
        "model": {
            "target_prior_hypothesis_a": baseline["model"]["prior_A"],
            "calibrations_with_current_prior": normalized_calibrations,
            "target_sensor_schedule": schedule,
            "source_reference_report_digest": source_ref_digest,
            "max_histories": max_histories,
            "calibration_scope": "one fixed discrete calibration profile shared by reference and future target observations",
            "reference_observation_model": "P(reference signal | known standard hypothesis, calibration profile, sensor type)",
            "target_hypothesis_prior_independent_of_current_calibration_profile": True,
        },
        "baseline_target_filter_report": baseline,
        "baseline_target_map_accuracy": _fraction_doc(baseline_accuracy),
        "candidate_evaluations": evaluated,
        "pareto_frontier_candidate_ids": _pareto_frontier(evaluated),
        "selection": selection,
        "objective_boundary": {
            "current_target_myopic_evsi": "RIV-008 assigns zero immediate decision value to a known-reference reading when its likelihood is independent of the unknown target hypothesis and H is initially independent of C.",
            "lookahead_value": "RIV-010 values the reference outcome by recomputing the later target MAP accuracy under the updated calibration posterior.",
            "horizon": "one candidate reference observation followed by the complete fixed target sensor schedule",
            "not_claimed": "not a multi-reference dynamic programme and not a universally optimal acquisition policy",
        },
        "interpretation_limits": [
            "Reference standard identity and known hypothesis are supplied inputs; their truth, custody, and authorization are not authenticated by this planner.",
            "Candidate outcome probabilities are derived from the supplied sensor likelihoods and fixed calibration profiles; they are not measurements of physical sensor performance.",
            "The calibration profile is discrete and fixed across the reference and target phases; drift, continuous uncertainty, and residual dependence are not modeled.",
            "The target hypothesis prior is assumed independent of the current calibration profile and known reference standard.",
            "The value is one-step lookahead to a fixed target schedule. Selecting multiple references jointly or adaptively requires a longer-horizon policy.",
            "Costs are exact caller-declared values in one common unit, not measured dispatch, transport, admission, authority, latency, or energy costs.",
            "RIV-008 immediate EVSI and RIV-010 downstream lookahead value optimize different horizons and are not interchangeable.",
            "SHA-256 digests bind supplied content but do not authenticate sources, standards, actors, sensor readings, or authority artifacts.",
        ],
    }
    return {**core, "report_digest": _digest(core)}


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild all reference branches, RIV-007 target filters, and scores."""
    if not isinstance(document, Mapping):
        raise TypeError("reference-acquisition report must be an object")
    supplied = _copy_json(document, "reference-acquisition report")
    digest = supplied.pop("report_digest", None)
    if not isinstance(digest, str) or not _HEX_256.fullmatch(digest) or digest != _digest(supplied):
        raise ReferenceAcquisitionError("report_digest does not match contents")
    if supplied.get("format") != FORMAT:
        raise ReferenceAcquisitionError("unsupported reference-acquisition report format")
    model = supplied.get("model")
    selection = supplied.get("selection")
    if not isinstance(model, Mapping) or not isinstance(selection, Mapping):
        raise ReferenceAcquisitionError("reference-acquisition report model/selection is missing")
    candidates = [
        {
            key: item[key]
            for key in (
                "candidate_id", "sensor_id", "known_hypothesis",
                "reference_standard_ref", "reference_standard_sha256", "cost",
            )
        }
        for item in supplied.get("candidate_evaluations", [])
    ]
    rebuilt = build_report(
        prior_hypothesis_a=model.get("target_prior_hypothesis_a"),
        calibrations=model.get("calibrations_with_current_prior"),
        target_sensor_schedule=model.get("target_sensor_schedule"),
        reference_candidates=candidates,
        cost_budget=selection.get("cost_budget"),
        source_reference_report_digest=model.get("source_reference_report_digest"),
        max_histories=model.get("max_histories"),
    )
    if rebuilt != dict(document):
        raise ReferenceAcquisitionError(
            "report differs from independent reconstruction from retained models and candidate references"
        )
    return dict(document)


def _selected_candidate(report: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        validated = validate_report(report)
    except (TypeError, ValueError, KeyError) as error:
        raise ReferenceAcquisitionError(
            f"reference-acquisition report failed reconstruction: {error}"
        ) from error
    selection = validated["selection"]
    candidate_id = selection["selected_candidate_id"]
    if selection["status"] != "selected" or candidate_id is None:
        raise ReferenceAcquisitionError("reference-acquisition report has no selected candidate")
    matches = [
        item for item in validated["candidate_evaluations"]
        if item["candidate_id"] == candidate_id
    ]
    if len(matches) != 1:
        raise ReferenceAcquisitionError("selected reference candidate is not unique")
    return validated, dict(matches[0])


def new_reference_acquisition_observation_path(
    *,
    reference_acquisition_report: Mapping[str, Any],
    attempt_id: str,
) -> ObservationPath:
    """Create a planned-only authority-gated path for the selected reference."""
    report, candidate = _selected_candidate(reference_acquisition_report)
    attempt = _text(attempt_id, "attempt_id")
    cost = Fraction(**candidate["cost"])
    try:
        estimated_cost = float(cost)
    except (OverflowError, ValueError) as error:
        raise ReferenceAcquisitionError("reference cost cannot be represented by ObservationIntent") from error
    if estimated_cost <= 0 or estimated_cost == float("inf"):
        raise ReferenceAcquisitionError("reference cost is outside finite positive ObservationIntent range")
    report_digest = report["report_digest"]
    intent = ObservationIntent(
        attempt_id=attempt,
        candidate_name=f"reference-calibration:{candidate['candidate_id']}",
        query=(
            f"Observe sensor {candidate['sensor_id']!r} against known standard "
            f"{candidate['known_hypothesis']!r} from {candidate['reference_standard_ref']!r}"
        ),
        hypothesis_set_digest=report_digest,
        estimated_cost=estimated_cost,
        plan_ref=f"urn:sha256:{report_digest}",
        authority_required=True,
        application_required=False,
        sender_ack_required=False,
    )
    return ObservationPath(intent)


def _reconstruct_path(raw: object) -> tuple[ObservationPath, dict[str, Any]]:
    if isinstance(raw, ObservationPath):
        snapshot = raw.to_dict()
    elif isinstance(raw, Mapping):
        snapshot = _copy_json(raw, "observation_path")
    else:
        raise TypeError("observation_path must be an ObservationPath or serialized mapping")
    allowed = {"attempt_id", "intent", "status", "terminal", "events"}
    if not isinstance(snapshot, Mapping) or set(snapshot) != allowed:
        raise ReferenceAcquisitionError("observation path has missing or unexpected top-level fields")
    intent_data = snapshot.get("intent")
    intent_fields = {
        "candidate_name", "query", "hypothesis_set_digest", "estimated_cost",
        "plan_ref", "authority_required", "application_required", "sender_ack_required",
    }
    if not isinstance(intent_data, Mapping) or set(intent_data) != intent_fields:
        raise ReferenceAcquisitionError("observation path intent has missing or unexpected fields")
    try:
        intent = ObservationIntent(
            attempt_id=snapshot["attempt_id"],
            candidate_name=intent_data["candidate_name"],
            query=intent_data["query"],
            hypothesis_set_digest=intent_data["hypothesis_set_digest"],
            estimated_cost=intent_data["estimated_cost"],
            plan_ref=intent_data["plan_ref"],
            authority_required=intent_data["authority_required"],
            application_required=intent_data["application_required"],
            sender_ack_required=intent_data["sender_ack_required"],
        )
        path = ObservationPath(intent)
        events = snapshot["events"]
        if not isinstance(events, list) or not events:
            raise ReferenceAcquisitionError("observation path requires a non-empty event list")
        event_fields = {
            "stage", "actor", "clock_value", "clock_domain", "evidence_ref", "details",
        }
        for index, event in enumerate(events[1:], start=1):
            if not isinstance(event, Mapping) or set(event) != event_fields:
                raise ReferenceAcquisitionError(
                    f"observation path event {index} has missing or unexpected fields"
                )
            path.append(
                event["stage"],
                event["actor"],
                clock_value=event["clock_value"],
                clock_domain=event["clock_domain"],
                evidence_ref=event["evidence_ref"],
                details=event["details"],
            )
    except (TypeError, ValueError, KeyError) as error:
        if isinstance(error, ReferenceAcquisitionError):
            raise
        raise ReferenceAcquisitionError(
            f"observation path failed lifecycle reconstruction: {error}"
        ) from error
    rebuilt = path.to_dict()
    if rebuilt != dict(snapshot):
        raise ReferenceAcquisitionError("observation path differs from independent lifecycle reconstruction")
    return path, rebuilt


def _event(snapshot: Mapping[str, Any], stage: str) -> dict[str, Any]:
    matches = [row for row in snapshot["events"] if row["stage"] == stage]
    if len(matches) != 1:
        raise ReferenceAcquisitionError(f"expected exactly one {stage!r} event")
    return dict(matches[0])


def build_reference_execution_record(
    *,
    reference_acquisition_report: Mapping[str, Any],
    observation_path: object,
) -> dict[str, Any]:
    """Convert one authorized interpreted reference reading into an RIV-009 update."""
    report, candidate = _selected_candidate(reference_acquisition_report)
    path, snapshot = _reconstruct_path(observation_path)
    if path.status != "interpreted" or path.terminal:
        raise ReferenceAcquisitionError(
            "reference execution must end at a non-terminal interpreted ObservationPath"
        )
    stages = tuple(row["stage"] for row in snapshot["events"])
    if stages != _REQUIRED_STAGES:
        raise ReferenceAcquisitionError(f"reference lifecycle must be exactly {_REQUIRED_STAGES!r}")

    intent = path.intent
    report_digest = report["report_digest"]
    cost = Fraction(**candidate["cost"])
    if intent.candidate_name != f"reference-calibration:{candidate['candidate_id']}":
        raise ReferenceAcquisitionMismatch("ObservationPath candidate differs from selected reference")
    if intent.hypothesis_set_digest != report_digest:
        raise ReferenceAcquisitionMismatch("ObservationPath is not bound to the reference-acquisition report")
    if intent.plan_ref != f"urn:sha256:{report_digest}":
        raise ReferenceAcquisitionMismatch("ObservationPath plan_ref differs from reference-acquisition report")
    if not intent.authority_required or intent.application_required or intent.sender_ack_required:
        raise ReferenceAcquisitionError(
            "reference measurement requires AUTHORIZED evidence and forbids application/ACK stages"
        )
    if intent.estimated_cost != float(cost):
        raise ReferenceAcquisitionMismatch("ObservationPath cost differs from selected reference cost")

    dispatched = _event(snapshot, "dispatched")
    admitted = _event(snapshot, "admitted")
    returned = _event(snapshot, "returned")
    authorized = _event(snapshot, "evidence_authorized")
    interpreted = _event(snapshot, "interpreted")
    returned_details = returned["details"]
    interpreted_details = interpreted["details"]
    for field in _RETURN_FIELDS:
        if field not in returned_details:
            raise ReferenceAcquisitionError(f"returned.details.{field} is required")
    expected_return = {
        "candidate_id": candidate["candidate_id"],
        "sensor_id": candidate["sensor_id"],
        "dimension": "calibration-reference",
        "known_hypothesis": candidate["known_hypothesis"],
        "reference_standard_ref": candidate["reference_standard_ref"],
        "reference_standard_sha256": candidate["reference_standard_sha256"],
        "reference_acquisition_report_digest": report_digest,
    }
    for field, expected in expected_return.items():
        if returned_details[field] != expected:
            raise ReferenceAcquisitionMismatch(f"returned.details.{field} differs from selected reference plan")
    observed_signal = returned_details["observed_outcome"]
    if type(observed_signal) is not str or observed_signal not in ("A", "B"):
        raise ReferenceAcquisitionMismatch("reference outcome must be exactly signal 'A' or 'B'")
    if interpreted_details.get("method") != _INTERPRETATION_METHOD:
        raise ReferenceAcquisitionError(
            f"interpretation method must be {_INTERPRETATION_METHOD!r}"
        )
    for field, expected in {
        **expected_return,
        "observed_outcome": observed_signal,
    }.items():
        if interpreted_details.get(field) != expected:
            raise ReferenceAcquisitionMismatch(
                f"interpreted.details.{field} differs from the returned reference reading"
            )

    selected_branches = [
        branch for branch in candidate["branches"]
        if branch["signal"] == observed_signal and branch["reachable"]
    ]
    if len(selected_branches) != 1:
        raise ReferenceAcquisitionMismatch(
            "observed reference signal was not a reachable branch in the selected plan"
        )
    predictive_probability = Fraction(**selected_branches[0]["predictive_probability"])
    if predictive_probability <= 0:
        raise ReferenceAcquisitionMismatch("reference outcome has zero predictive probability")

    observation_id = intent.attempt_id
    reference_observation = {
        "observation_id": observation_id,
        "sensor_id": candidate["sensor_id"],
        "known_hypothesis": candidate["known_hypothesis"],
        "signal": observed_signal,
        "reference_standard_ref": candidate["reference_standard_ref"],
        "reference_standard_sha256": candidate["reference_standard_sha256"],
        "observation_ref": returned["evidence_ref"],
        "observation_sha256": returned_details["payload_digest"],
        "cost": _fraction_doc(cost),
    }
    # Reuse RIV-009 for calibration posterior updating and all target filtering.
    try:
        updated_riv009 = _RIV009.build_report(
            prior_hypothesis_a=report["model"]["target_prior_hypothesis_a"],
            calibrations=report["model"]["calibrations_with_current_prior"],
            target_sensor_schedule=report["model"]["target_sensor_schedule"],
            reference_observations=(reference_observation,),
            max_histories=report["model"]["max_histories"],
        )
        _RIV009.validate_report(updated_riv009)
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        raise ReferenceAcquisitionError(
            f"RIV-009 rejected the authorized reference observation: {error}"
        ) from error

    manifest = {
        "format": "in-formation.reference-acquisition-measurement-manifest",
        "schema": "in-formation.reference-acquisition-measurement-manifest/0.1",
        "reference_acquisition_report_digest": report_digest,
        "attempt_id": intent.attempt_id,
        "candidate_id": candidate["candidate_id"],
        "sensor_id": candidate["sensor_id"],
        "known_hypothesis": candidate["known_hypothesis"],
        "reference_standard_ref": candidate["reference_standard_ref"],
        "reference_standard_sha256": candidate["reference_standard_sha256"],
        "signal": observed_signal,
        "cost": _fraction_doc(cost),
        "predictive_probability": _fraction_doc(predictive_probability),
        "observation_path_digest": _digest(snapshot),
        "dispatch_evidence_ref": dispatched["evidence_ref"],
        "admission_evidence_ref": admitted["evidence_ref"],
        "return_evidence_ref": returned["evidence_ref"],
        "encounter_id": returned_details["encounter_id"],
        "payload_digest": returned_details["payload_digest"],
        "canonicalization": returned_details["canonicalization"],
        "authority_evidence_ref": authorized["evidence_ref"],
        "authority_decision_status": authorized["details"]["decision_status"],
        "authority_policy_digest": authorized["details"]["policy_digest"],
        "authority_decision_digest": authorized["details"]["decision_digest"],
        "authority_quorum": authorized["details"]["quorum"],
        "authority_strict": authorized["details"]["strict"],
        "authority_observed_sources": authorized["details"]["observed_sources"],
        "authority_dissenting_sources": authorized["details"]["dissenting_sources"],
        "authority_missing_sources": authorized["details"]["missing_sources"],
        "authority_representative_source": authorized["details"]["representative_source"],
        "interpretation_evidence_ref": interpreted["evidence_ref"],
        "interpretation_method": interpreted_details["method"],
        "source_reference_report_digest": report["model"]["source_reference_report_digest"],
        "resulting_riv009_report_digest": updated_riv009["content_digest"],
    }
    manifest_digest = _digest(manifest)
    core = {
        "format": "in-formation.reference-acquisition-execution/0.1",
        "schema": "in-formation.reference-acquisition-execution/0.1",
        "reference_acquisition_report": report,
        "reference_acquisition_report_digest": report_digest,
        "observation_path": snapshot,
        "observation_path_digest": _digest(snapshot),
        "reference_observation": reference_observation,
        "measurement_manifest": {**manifest, "measurement_manifest_digest": manifest_digest},
        "updated_riv009_report": updated_riv009,
        "measurement_status": "interpreted_authorized_reference_observation",
        "belief_effect": "new_reference_conditioned_calibration_report",
        "ground_effect": "none",
        "sensor_model_effect": "none",
        "interpretation_limits": [
            "The ObservationPath is independently reconstructed, but referenced dispatch, admission, Encounter, authority, and interpretation artifacts are not fetched or authenticated here.",
            "AUTHORIZED is accepted as a structurally valid lifecycle decision; this module does not authenticate the authority actor, signer, policy, quorum members, or signature.",
            "The standard label is supplied by the selected plan and bound into the returned/interpreted event; this record does not independently prove the physical standard's truth or custody.",
            "The reference row is passed to RIV-009, which performs exact Bayesian updating under the supplied fixed calibration family.",
            "The target hypothesis prior and calibration profile are assumed independent before this reference reading.",
            "Digests provide content identity and reconstruction checks, not source authenticity.",
        ],
    }
    return {**core, "record_digest": _digest(core)}


def validate_reference_execution_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild the authorized reference row and nested RIV-009 report."""
    if not isinstance(record, Mapping):
        raise TypeError("reference execution record must be an object")
    supplied = _copy_json(record, "reference execution record")
    digest = supplied.pop("record_digest", None)
    if not isinstance(digest, str) or not _HEX_256.fullmatch(digest) or digest != _digest(supplied):
        raise ReferenceAcquisitionError("record_digest does not match contents")
    if supplied.get("format") != "in-formation.reference-acquisition-execution/0.1":
        raise ReferenceAcquisitionError("unsupported reference execution record format")
    rebuilt = build_reference_execution_record(
        reference_acquisition_report=supplied.get("reference_acquisition_report"),
        observation_path=supplied.get("observation_path"),
    )
    if rebuilt != dict(record):
        raise ReferenceAcquisitionError(
            "reference execution record differs from independent reconstruction"
        )
    return dict(record)


__all__ = [
    "FORMAT",
    "ReferenceAcquisitionError",
    "ReferenceAcquisitionMismatch",
    "build_report",
    "validate_report",
    "new_reference_acquisition_observation_path",
    "build_reference_execution_record",
    "validate_reference_execution_record",
]
