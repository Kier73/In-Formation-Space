"""Exact reference-phase updating for a session-shared sensor calibration.

Known calibration standards update the latent calibration-profile prior. The
updated prior is then passed to RIV-007's joint hypothesis x calibration filter
for the unknown target observations. RIV-007 remains the owner of target-phase
Bayesian filtering semantics.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

FORMAT = "in-formation.reference-calibrated-evidence/0.1"
RIV007_FORMAT = "in-formation.calibration-aware-evidence/0.1"
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_REFERENCE_FIELDS = {
    "observation_id",
    "sensor_id",
    "known_hypothesis",
    "signal",
    "reference_standard_ref",
    "reference_standard_sha256",
    "observation_ref",
    "observation_sha256",
    "cost",
}


class ReferenceCalibrationError(ValueError):
    """Invalid calibration reference evidence or report."""


class ImpossibleReferenceEvidenceError(ReferenceCalibrationError):
    """The supplied reference sequence has zero likelihood under every profile."""


def _load_riv007():
    path = (
        Path(__file__).resolve().parents[1]
        / "calibration-aware-joint-evidence"
        / "calibration_aware_evidence.py"
    )
    spec = importlib.util.spec_from_file_location(
        "riv007_calibration_aware_evidence", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load the pinned RIV-007 module at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.FORMAT != RIV007_FORMAT:
        raise RuntimeError(
            f"unsupported RIV-007 contract {module.FORMAT!r}; expected {RIV007_FORMAT!r}"
        )
    return module


_RIV007 = _load_riv007()


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
        raise ReferenceCalibrationError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ReferenceCalibrationError(f"{label} must be non-empty text without NUL")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise ReferenceCalibrationError(f"{label} must be a lowercase SHA-256 digest")
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
        raise ReferenceCalibrationError(
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
        raise ReferenceCalibrationError(f"{label} must be an exact rational") from error
    if nonnegative and result < 0:
        raise ReferenceCalibrationError(f"{label} must be non-negative")
    if positive and result <= 0:
        raise ReferenceCalibrationError(f"{label} must be positive")
    if unit_interval and not 0 <= result <= 1:
        raise ReferenceCalibrationError(f"{label} must be in [0, 1]")
    return result


def _fraction_doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _fraction_value(value: object, label: str) -> Fraction:
    if not isinstance(value, Mapping) or set(value) != {"numerator", "denominator"}:
        raise ReferenceCalibrationError(f"{label} must be a rational document")
    return _rational(value, label)


def _normalize_reference_observations(
    raw: object,
    target_sensor_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw, (tuple, list)):
        raise ReferenceCalibrationError("reference_observations must be a sequence")
    if len(raw) > 128:
        raise ReferenceCalibrationError("at most 128 reference observations are supported")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, observation in enumerate(raw):
        if not isinstance(observation, Mapping) or set(observation) != _REFERENCE_FIELDS:
            raise ReferenceCalibrationError(
                f"reference_observations[{index}] must contain exactly {sorted(_REFERENCE_FIELDS)}"
            )
        observation_id = _text(observation["observation_id"], "observation_id")
        if observation_id in seen_ids:
            raise ReferenceCalibrationError(f"duplicate observation_id: {observation_id}")
        seen_ids.add(observation_id)
        sensor_id = _text(observation["sensor_id"], f"{observation_id}.sensor_id")
        if sensor_id not in target_sensor_ids:
            raise ReferenceCalibrationError(
                f"reference sensor {sensor_id!r} must also appear in the target sensor schedule"
            )
        known_hypothesis = observation["known_hypothesis"]
        signal = observation["signal"]
        if known_hypothesis not in ("A", "B"):
            raise ReferenceCalibrationError(
                f"{observation_id}.known_hypothesis must be A or B"
            )
        if signal not in ("A", "B"):
            raise ReferenceCalibrationError(f"{observation_id}.signal must be A or B")
        normalized.append({
            "observation_id": observation_id,
            "sensor_id": sensor_id,
            "known_hypothesis": known_hypothesis,
            "signal": signal,
            "reference_standard_ref": _text(
                observation["reference_standard_ref"],
                f"{observation_id}.reference_standard_ref",
            ),
            "reference_standard_sha256": _sha256(
                observation["reference_standard_sha256"],
                f"{observation_id}.reference_standard_sha256",
            ),
            "observation_ref": _text(
                observation["observation_ref"], f"{observation_id}.observation_ref"
            ),
            "observation_sha256": _sha256(
                observation["observation_sha256"],
                f"{observation_id}.observation_sha256",
            ),
            "cost": _fraction_doc(_rational(
                observation["cost"], f"{observation_id}.cost", positive=True
            )),
        })
    return normalized


def _signal_likelihood(
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


def _calibration_posterior_trace(
    calibrations: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Fraction], Fraction, list[dict[str, Any]], Fraction]:
    current = {
        item["calibration_id"]: Fraction(**item["prior_probability"])
        for item in calibrations
    }
    evidence_probability = Fraction(1)
    cumulative_cost = Fraction(0)
    trace: list[dict[str, Any]] = []
    for observation in observations:
        per_profile = {
            item["calibration_id"]: _signal_likelihood(
                item,
                observation["sensor_id"],
                observation["known_hypothesis"],
                observation["signal"],
            )
            for item in calibrations
        }
        conditional_probability = sum(
            (current[key] * per_profile[key] for key in current), Fraction(0)
        )
        if conditional_probability == 0:
            raise ImpossibleReferenceEvidenceError(
                f"reference observation {observation['observation_id']!r} is impossible under every remaining calibration profile"
            )
        current = {
            key: current[key] * per_profile[key] / conditional_probability
            for key in current
        }
        evidence_probability *= conditional_probability
        cumulative_cost += Fraction(**observation["cost"])
        trace.append({
            "observation_id": observation["observation_id"],
            "conditional_evidence_probability": _fraction_doc(conditional_probability),
            "cumulative_evidence_probability": _fraction_doc(evidence_probability),
            "profile_likelihoods": [
                {"calibration_id": key, "probability": _fraction_doc(per_profile[key])}
                for key in sorted(per_profile)
            ],
            "posterior_calibration_probabilities": [
                {"calibration_id": key, "probability": _fraction_doc(current[key])}
                for key in sorted(current)
            ],
            "cumulative_reference_cost": _fraction_doc(cumulative_cost),
        })
    return current, evidence_probability, trace, cumulative_cost


def _with_calibration_prior(
    calibrations: Sequence[Mapping[str, Any]],
    probabilities: Mapping[str, Fraction],
) -> list[dict[str, Any]]:
    return [
        {
            **dict(item),
            "prior_probability": _fraction_doc(probabilities[item["calibration_id"]]),
        }
        for item in calibrations
    ]


def _raw_rows(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        row["history"]: row
        for row in report["shared_calibration_full_history"]["raw_history_rows"]
    }


def _policy_accuracy(
    policy_report: Mapping[str, Any],
    evaluation_report: Mapping[str, Any],
    *,
    unreachable_fallback: Optional[str] = None,
) -> tuple[Fraction, Fraction]:
    policy = _raw_rows(policy_report)
    evaluation = _raw_rows(evaluation_report)
    if set(policy) != set(evaluation):
        raise AssertionError("RIV-007 target-history domains differ")
    accuracy = Fraction(0)
    fallback_mass = Fraction(0)
    for history in sorted(evaluation):
        actual = evaluation[history]
        decision = policy[history]["shared_calibration_map_decision"]
        mass_a = Fraction(**actual["joint_mass_shared_if_A"])
        mass_b = Fraction(**actual["joint_mass_shared_if_B"])
        if mass_a + mass_b == 0:
            continue
        if decision == "unreachable" and unreachable_fallback is not None:
            if unreachable_fallback not in ("A", "B"):
                raise ValueError("unreachable_fallback must be A or B")
            fallback_mass += mass_a + mass_b
            decision = unreachable_fallback
        if decision == "A":
            accuracy += mass_a
        elif decision == "B":
            accuracy += mass_b
        else:
            raise AssertionError(
                f"policy declared history {history!r} unreachable in the evaluation world"
            )
    return accuracy, fallback_mass


def _build_target_report(
    *,
    prior_hypothesis_a: object,
    calibrations: Sequence[Mapping[str, Any]],
    sensor_schedule: Sequence[str],
    max_histories: int,
) -> dict[str, Any]:
    report = _RIV007.build_report(
        prior_hypothesis_a=prior_hypothesis_a,
        calibrations=calibrations,
        sensor_schedule=sensor_schedule,
        max_histories=max_histories,
    )
    _RIV007.validate_report(report)
    return report


def build_report(
    *,
    prior_hypothesis_a: object,
    calibrations: Sequence[Mapping[str, Any]],
    target_sensor_schedule: Sequence[str],
    reference_observations: Sequence[Mapping[str, Any]],
    max_histories: int = 1_000_000,
) -> dict[str, Any]:
    """Update shared calibration using known standards, then filter target data.

    The known reference labels are treated as supplied exogenous facts. Their
    evidence updates C but does not update the unknown target hypothesis H. The
    same latent calibration profile is retained into the target phase.
    """
    baseline = _build_target_report(
        prior_hypothesis_a=prior_hypothesis_a,
        calibrations=calibrations,
        sensor_schedule=target_sensor_schedule,
        max_histories=max_histories,
    )
    normalized_calibrations = baseline["model"]["calibrations"]
    normalized_schedule = baseline["model"]["sensor_schedule"]
    normalized_references = _normalize_reference_observations(
        reference_observations,
        set(normalized_schedule),
    )
    posterior, evidence_probability, update_trace, total_reference_cost = (
        _calibration_posterior_trace(normalized_calibrations, normalized_references)
    )
    posterior_calibrations = _with_calibration_prior(normalized_calibrations, posterior)
    calibrated = _build_target_report(
        prior_hypothesis_a=baseline["model"]["prior_A"],
        calibrations=posterior_calibrations,
        sensor_schedule=normalized_schedule,
        max_histories=max_histories,
    )
    selected_profile = min(
        posterior,
        key=lambda key: (-posterior[key], key),
    )
    plugin_probabilities = {
        key: Fraction(1) if key == selected_profile else Fraction(0)
        for key in posterior
    }
    plugin = _build_target_report(
        prior_hypothesis_a=baseline["model"]["prior_A"],
        calibrations=_with_calibration_prior(normalized_calibrations, plugin_probabilities),
        sensor_schedule=normalized_schedule,
        max_histories=max_histories,
    )

    # Score every policy against one common target world: the final reference-
    # conditioned calibration posterior. This avoids comparing accuracies that
    # silently assume different data-generating calibration priors.
    accuracy_baseline, baseline_fallback_mass = _policy_accuracy(baseline, calibrated)
    accuracy_calibrated, calibrated_fallback_mass = _policy_accuracy(calibrated, calibrated)
    accuracy_plugin, plugin_fallback_mass = _policy_accuracy(
        plugin, calibrated, unreachable_fallback="A"
    )
    optimal_accuracy = Fraction(**calibrated["summary"]["shared_calibration_map_accuracy"])
    if accuracy_calibrated != optimal_accuracy:
        raise AssertionError("calibrated target policy does not match RIV-007 MAP accuracy")
    if accuracy_calibrated < accuracy_baseline:
        raise AssertionError("reference-conditioned Bayes policy cannot be worse than baseline under the same world")

    # Measure how each prefix's target policy performs in the same final
    # reference-conditioned world. The sequence need not be monotonic for a
    # particular realized reference stream.
    prefix_trace: list[dict[str, Any]] = []
    current_probabilities = {
        item["calibration_id"]: Fraction(**item["prior_probability"])
        for item in normalized_calibrations
    }
    prefix_reports: list[tuple[int, dict[str, Fraction], Fraction, Fraction, dict[str, Any]]] = [
        (0, dict(current_probabilities), Fraction(1), Fraction(0), baseline)
    ]
    for index, step in enumerate(update_trace, start=1):
        current_probabilities = {
            item["calibration_id"]: Fraction(**item["probability"])
            for item in step["posterior_calibration_probabilities"]
        }
        prefix_report = _build_target_report(
            prior_hypothesis_a=baseline["model"]["prior_A"],
            calibrations=_with_calibration_prior(normalized_calibrations, current_probabilities),
            sensor_schedule=normalized_schedule,
            max_histories=max_histories,
        )
        prefix_cost = Fraction(**step["cumulative_reference_cost"])
        prefix_evidence = Fraction(**step["cumulative_evidence_probability"])
        prefix_reports.append((index, dict(current_probabilities), prefix_evidence, prefix_cost, prefix_report))
    for count, probabilities, prefix_evidence, prefix_cost, prefix_report in prefix_reports:
        prefix_trace.append({
            "reference_count": count,
            "cumulative_evidence_probability": _fraction_doc(prefix_evidence),
            "cumulative_reference_cost": _fraction_doc(prefix_cost),
            "posterior_calibration_probabilities": [
                {"calibration_id": key, "probability": _fraction_doc(probabilities[key])}
                for key in sorted(probabilities)
            ],
            "target_policy_accuracy_under_final_reference_posterior_world": _fraction_doc(
                _policy_accuracy(prefix_report, calibrated)[0]
            ),
        })

    original_prior = [
        {"calibration_id": item["calibration_id"], "probability": item["prior_probability"]}
        for item in normalized_calibrations
    ]
    final_prior = [
        {"calibration_id": key, "probability": _fraction_doc(posterior[key])}
        for key in sorted(posterior)
    ]
    reference_likelihoods = []
    for item in normalized_calibrations:
        likelihood = Fraction(1)
        for observation in normalized_references:
            likelihood *= _signal_likelihood(
                item,
                observation["sensor_id"],
                observation["known_hypothesis"],
                observation["signal"],
            )
        reference_likelihoods.append({
            "calibration_id": item["calibration_id"],
            "likelihood": _fraction_doc(likelihood),
            "prior_probability": item["prior_probability"],
            "posterior_probability": _fraction_doc(posterior[item["calibration_id"]]),
        })
    core = {
        "format": FORMAT,
        "model": {
            "target_prior_hypothesis_a": baseline["model"]["prior_A"],
            "target_sensor_schedule": normalized_schedule,
            "calibrations_with_original_prior": normalized_calibrations,
            "reference_observations": normalized_references,
            "max_histories": max_histories,
            "reference_and_target_share_one_fixed_calibration_profile": True,
            "target_hypothesis_prior_independent_of_reference_standards": True,
            "conditional_independence_assumption": "reference and target signals are independent conditional on the same fixed calibration profile and their supplied known/unknown hypothesis values",
        },
        "reference_phase": {
            "observation_count": len(normalized_references),
            "observations": normalized_references,
            "prior_calibration_probabilities": original_prior,
            "profile_likelihoods_and_posterior": reference_likelihoods,
            "reference_evidence_probability": _fraction_doc(evidence_probability),
            "posterior_calibration_probabilities": final_prior,
            "support_count_before": sum(Fraction(**item["probability"]) > 0 for item in original_prior),
            "support_count_after": sum(posterior[key] > 0 for key in posterior),
            "total_declared_reference_cost": _fraction_doc(total_reference_cost),
            "update_trace": update_trace,
            "target_policy_prefix_trace": prefix_trace,
            "reference_evidence_digest": _digest(normalized_references),
        },
        "target_phase": {
            "uncalibrated_prior_filter_report": baseline,
            "reference_conditioned_filter_report": calibrated,
            "map_profile_plugin_filter_report": plugin,
            "map_profile_plugin_calibration_id": selected_profile,
        },
        "comparison_in_one_reference_conditioned_target_world": {
            "evaluation_world": "target observations generated under the target prior and the final reference-conditioned calibration posterior; the same fixed profile is shared across the complete reference and target session",
            "uncalibrated_prior_policy_accuracy": _fraction_doc(accuracy_baseline),
            "reference_conditioned_bayes_policy_accuracy": _fraction_doc(accuracy_calibrated),
            "map_profile_plugin_policy_accuracy": _fraction_doc(accuracy_plugin),
            "map_profile_plugin_unreachable_history_fallback": "A",
            "map_profile_plugin_probability_mass_requiring_fallback": _fraction_doc(plugin_fallback_mass),
            "reference_conditioned_gain_over_uncalibrated_prior_policy": _fraction_doc(
                accuracy_calibrated - accuracy_baseline
            ),
            "reference_conditioned_gain_over_map_profile_plugin": _fraction_doc(
                accuracy_calibrated - accuracy_plugin
            ),
            "optimal_target_map_accuracy": _fraction_doc(optimal_accuracy),
            "baseline_probability_mass_requiring_fallback": _fraction_doc(baseline_fallback_mass),
            "calibrated_probability_mass_requiring_fallback": _fraction_doc(calibrated_fallback_mass),
        },
        "interpretation_limits": [
            "Reference labels are supplied known standards; their truth, chain of custody, and authorization are not authenticated by this experiment.",
            "Reference and target observations share one fixed discrete calibration profile; drift, continuous calibration, and residual dependence after conditioning on the profile are not modeled.",
            "Reference readings update the calibration-profile posterior only; the target hypothesis prior is assumed independent of the reference standards.",
            "Reference and target sensor types must be drawn from the same declared sensor-model family; every reference sensor must also occur in the target schedule in this version.",
            "Declared reference costs are exact caller-supplied values in a common unit, not measured elapsed time, transport, admission, or energy costs.",
            "The target outcome comparison evaluates all policies under one final reference-conditioned model. It is model-conditional expected MAP accuracy, not measured real-world performance.",
            "The MAP-profile plug-in policy discards calibration uncertainty and is included as a plug-in baseline, not as an equivalent Bayesian method.",
            "SHA-256 digests bind supplied content for integrity and reconstruction; they do not authenticate sources, standards, actors, or physical sensor readings.",
            "The RIV-007 filter remains the target-phase implementation; the adapter checks its declared version and independently rebuilds each nested report.",
        ],
    }
    return {**core, "content_digest": _digest(core)}


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild reference updates and every nested target filter report."""
    if not isinstance(document, Mapping):
        raise TypeError("reference-calibrated report must be an object")
    supplied = json.loads(_canonical(document))
    digest = supplied.pop("content_digest", None)
    if not isinstance(digest, str) or not _HEX_256.fullmatch(digest) or digest != _digest(supplied):
        raise ReferenceCalibrationError("content_digest does not match report contents")
    if supplied.get("format") != FORMAT:
        raise ReferenceCalibrationError("unsupported reference-calibrated report format")
    model = supplied.get("model")
    if not isinstance(model, Mapping):
        raise ReferenceCalibrationError("report model is missing")
    rebuilt = build_report(
        prior_hypothesis_a=model.get("target_prior_hypothesis_a"),
        calibrations=model.get("calibrations_with_original_prior"),
        target_sensor_schedule=model.get("target_sensor_schedule"),
        reference_observations=model.get("reference_observations"),
        max_histories=model.get("max_histories"),
    )
    if rebuilt != dict(document):
        raise ReferenceCalibrationError(
            "report differs from independent reconstruction from retained inputs"
        )
    return dict(document)


__all__ = [
    "FORMAT",
    "ImpossibleReferenceEvidenceError",
    "ReferenceCalibrationError",
    "build_report",
    "validate_report",
]
