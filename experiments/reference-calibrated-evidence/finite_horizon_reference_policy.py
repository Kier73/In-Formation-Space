"""Finite-horizon dynamic programming for repeated calibration references.

RIV-010 evaluates one reference before a fixed target schedule. RIV-011
optimizes a bounded sequential policy: after every authorized reference
outcome, it can stop or choose another known-standard measurement subject to a
per-path budget. The comparator re-runs RIV-010's one-step value/cost rule at
each state. All probabilities and costs use exact Fraction arithmetic.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

FORMAT = "in-formation.finite-horizon-reference-acquisition/0.1"
RIV007_FORMAT = "in-formation.calibration-aware-evidence/0.1"
RIV010_FORMAT = "in-formation.reference-acquisition-lookahead/0.1"
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_FIELDS = {
    "candidate_id",
    "sensor_id",
    "known_hypothesis",
    "reference_standard_ref",
    "reference_standard_sha256",
    "cost",
}


class FiniteHorizonReferenceError(ValueError):
    """Invalid finite-horizon model, policy, or reconstruction request."""


class PolicyStateLimitError(FiniteHorizonReferenceError):
    """The exact policy search exceeded its declared state cap."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load required module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[2]
_RIV007 = _load_module(
    "riv011_riv007",
    _ROOT / "experiments" / "calibration-aware-joint-evidence" / "calibration_aware_evidence.py",
)
_RIV010 = _load_module(
    "riv011_riv010",
    Path(__file__).resolve().with_name("reference_acquisition_lookahead.py"),
)
if _RIV007.FORMAT != RIV007_FORMAT:
    raise RuntimeError("RIV-011 requires the declared RIV-007 report contract")
if _RIV010.FORMAT != RIV010_FORMAT:
    raise RuntimeError("RIV-011 requires the declared RIV-010 report contract")


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
        raise FiniteHorizonReferenceError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise FiniteHorizonReferenceError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise FiniteHorizonReferenceError(f"{label} must be non-empty text without NUL")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise FiniteHorizonReferenceError(f"{label} must be a lowercase SHA-256 digest")
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
        raise FiniteHorizonReferenceError(
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
        raise FiniteHorizonReferenceError(f"{label} must be an exact rational") from error
    if nonnegative and result < 0:
        raise FiniteHorizonReferenceError(f"{label} must be non-negative")
    if positive and result <= 0:
        raise FiniteHorizonReferenceError(f"{label} must be positive")
    if unit_interval and not 0 <= result <= 1:
        raise FiniteHorizonReferenceError(f"{label} must be in [0, 1]")
    return result


def _fraction_doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _normalize_candidates(
    raw: object,
    sensor_schedule: Sequence[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw, (tuple, list)) or not raw:
        raise FiniteHorizonReferenceError("reference_candidates must be a non-empty sequence")
    if len(raw) > 64:
        raise FiniteHorizonReferenceError("at most 64 reference candidates are supported")
    allowed_sensors = set(sensor_schedule)
    seen: set[str] = set()
    normalized = []
    for index, candidate in enumerate(raw):
        if not isinstance(candidate, Mapping) or set(candidate) != _CANDIDATE_FIELDS:
            raise FiniteHorizonReferenceError(
                f"reference_candidates[{index}] must contain exactly {sorted(_CANDIDATE_FIELDS)}"
            )
        candidate_id = _text(candidate["candidate_id"], "candidate_id")
        if candidate_id in seen:
            raise FiniteHorizonReferenceError(f"duplicate candidate_id: {candidate_id}")
        seen.add(candidate_id)
        sensor_id = _text(candidate["sensor_id"], f"{candidate_id}.sensor_id")
        if sensor_id not in allowed_sensors:
            raise FiniteHorizonReferenceError(
                f"{candidate_id}.sensor_id must appear in the target sensor schedule"
            )
        standard = candidate["known_hypothesis"]
        if standard not in ("A", "B"):
            raise FiniteHorizonReferenceError(
                f"{candidate_id}.known_hypothesis must be A or B"
            )
        normalized.append({
            "candidate_id": candidate_id,
            "sensor_id": sensor_id,
            "known_hypothesis": standard,
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


def _reference_signal_probability(
    calibration: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> Fraction:
    model = calibration["sensor_models"][candidate["sensor_id"]]
    field = (
        "p_signal_a_given_hypothesis_a"
        if candidate["known_hypothesis"] == "A"
        else "p_signal_a_given_hypothesis_b"
    )
    return Fraction(**model[field])


def _belief_after_signal(
    belief: tuple[Fraction, ...],
    calibrations: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    signal: str,
) -> tuple[Fraction, Optional[tuple[Fraction, ...]]]:
    likelihoods = [
        _reference_signal_probability(item, candidate)
        for item in calibrations
    ]
    if signal == "B":
        likelihoods = [1 - value for value in likelihoods]
    weighted = tuple(value * likelihood for value, likelihood in zip(belief, likelihoods))
    probability = sum(weighted, Fraction(0))
    if probability == 0:
        return probability, None
    return probability, tuple(value / probability for value in weighted)


def _belief_rows(
    belief: tuple[Fraction, ...],
    calibrations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "calibration_id": calibration["calibration_id"],
            "probability": _fraction_doc(belief[index]),
        }
        for index, calibration in enumerate(calibrations)
    ]


def _normalized_calibration_prior(
    calibrations: Sequence[Mapping[str, Any]],
    belief: tuple[Fraction, ...],
) -> list[dict[str, Any]]:
    return [
        {
            **dict(calibration),
            "prior_probability": _fraction_doc(belief[index]),
        }
        for index, calibration in enumerate(calibrations)
    ]


def build_report(
    *,
    prior_hypothesis_a: object,
    calibrations: Sequence[Mapping[str, Any]],
    target_sensor_schedule: Sequence[str],
    reference_candidates: Sequence[Mapping[str, Any]],
    max_reference_steps: int,
    cost_budget: object,
    max_policy_states: int = 50_000,
    max_histories: int = 1_000_000,
) -> dict[str, Any]:
    """Optimize a finite reference policy under a per-realized-path cost cap.

    The optimal policy may stop early or choose a different next reference
    after different signals. Repeated use of a candidate is permitted and
    represents another conditionally independent reading under the same
    fixed calibration profile.
    """
    if isinstance(max_reference_steps, bool) or not isinstance(max_reference_steps, int):
        raise FiniteHorizonReferenceError("max_reference_steps must be an integer")
    if not 0 <= max_reference_steps <= 8:
        raise FiniteHorizonReferenceError("max_reference_steps must be between 0 and 8")
    if isinstance(max_policy_states, bool) or not isinstance(max_policy_states, int) or max_policy_states < 1:
        raise FiniteHorizonReferenceError("max_policy_states must be a positive integer")
    if isinstance(max_histories, bool) or not isinstance(max_histories, int) or max_histories < 1:
        raise FiniteHorizonReferenceError("max_histories must be a positive integer")
    budget = _rational(cost_budget, "cost_budget", nonnegative=True)

    try:
        baseline = _RIV007.build_report(
            prior_hypothesis_a=prior_hypothesis_a,
            calibrations=calibrations,
            sensor_schedule=target_sensor_schedule,
            max_histories=max_histories,
        )
        _RIV007.validate_report(baseline)
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        raise FiniteHorizonReferenceError(
            f"RIV-007 could not construct the baseline target filter: {error}"
        ) from error

    normalized_calibrations = baseline["model"]["calibrations"]
    schedule = baseline["model"]["sensor_schedule"]
    normalized_candidates = _normalize_candidates(reference_candidates, schedule)
    prior_a = baseline["model"]["prior_A"]
    initial_belief = tuple(
        Fraction(**item["prior_probability"])
        for item in normalized_calibrations
    )
    calibration_ids = tuple(item["calibration_id"] for item in normalized_calibrations)

    target_accuracy_cache: dict[tuple[Fraction, ...], tuple[Fraction, dict[str, Any]]] = {}

    def target_accuracy(belief: tuple[Fraction, ...]) -> Fraction:
        if belief not in target_accuracy_cache:
            try:
                target_report = _RIV007.build_report(
                    prior_hypothesis_a=prior_a,
                    calibrations=_normalized_calibration_prior(normalized_calibrations, belief),
                    sensor_schedule=schedule,
                    max_histories=max_histories,
                )
                _RIV007.validate_report(target_report)
            except (TypeError, ValueError, KeyError, AssertionError) as error:
                raise FiniteHorizonReferenceError(
                    f"RIV-007 could not construct a target filter for a reachable calibration belief: {error}"
                ) from error
            accuracy = Fraction(**target_report["summary"]["shared_calibration_map_accuracy"])
            target_accuracy_cache[belief] = (accuracy, target_report)
        return target_accuracy_cache[belief][0]

    initial_accuracy = target_accuracy(initial_belief)

    dp_memo: dict[tuple[tuple[Fraction, ...], int, Fraction], dict[str, Any]] = {}
    dp_state_count = 0

    def solve_dp(
        belief: tuple[Fraction, ...],
        steps_left: int,
        remaining_budget: Fraction,
    ) -> dict[str, Any]:
        nonlocal dp_state_count
        key = (belief, steps_left, remaining_budget)
        if key in dp_memo:
            return dp_memo[key]
        dp_state_count += 1
        if dp_state_count > max_policy_states:
            raise PolicyStateLimitError(
                f"exact policy search exceeded max_policy_states={max_policy_states}"
            )

        current_accuracy = target_accuracy(belief)
        best = {
            "action": None,
            "candidate_id": None,
            "sensor_id": None,
            "known_hypothesis": None,
            "cost": None,
            "current_target_map_accuracy": _fraction_doc(current_accuracy),
            "expected_target_map_accuracy": _fraction_doc(current_accuracy),
            "expected_reference_cost": _fraction_doc(Fraction(0)),
            "expected_reference_count": _fraction_doc(Fraction(0)),
            "stop_reason": (
                "reference_horizon_exhausted" if steps_left == 0
                else "no_positive_value_action_within_remaining_budget"
            ),
            "branches": [],
        }
        if steps_left == 0:
            dp_memo[key] = best
            return best

        best_value = current_accuracy
        best_cost = Fraction(0)
        best_count = Fraction(0)
        for candidate in normalized_candidates:
            action_cost = Fraction(**candidate["cost"])
            if action_cost > remaining_budget:
                continue
            expected_accuracy = Fraction(0)
            expected_child_cost = Fraction(0)
            expected_child_count = Fraction(0)
            branches = []
            for signal in ("A", "B"):
                signal_probability, posterior = _belief_after_signal(
                    belief, normalized_calibrations, candidate, signal
                )
                if signal_probability == 0 or posterior is None:
                    branches.append({
                        "signal": signal,
                        "predictive_probability": _fraction_doc(Fraction(0)),
                        "reachable": False,
                        "posterior_calibration_probabilities": None,
                        "child": None,
                    })
                    continue
                child = solve_dp(
                    posterior,
                    steps_left - 1,
                    remaining_budget - action_cost,
                )
                expected_accuracy += signal_probability * Fraction(
                    **child["expected_target_map_accuracy"]
                )
                expected_child_cost += signal_probability * Fraction(
                    **child["expected_reference_cost"]
                )
                expected_child_count += signal_probability * Fraction(
                    **child["expected_reference_count"]
                )
                branches.append({
                    "signal": signal,
                    "predictive_probability": _fraction_doc(signal_probability),
                    "reachable": True,
                    "posterior_calibration_probabilities": _belief_rows(
                        posterior, normalized_calibrations
                    ),
                    "child": child,
                })

            total_cost = action_cost + expected_child_cost
            total_count = Fraction(1) + expected_child_count
            better = (
                expected_accuracy > best_value
                or (
                    expected_accuracy == best_value
                    and expected_accuracy > current_accuracy
                    and (
                        total_cost < best_cost
                        or (
                            total_cost == best_cost
                            and candidate["candidate_id"] < (best["candidate_id"] or "\uffff")
                        )
                    )
                )
            )
            if better:
                best_value = expected_accuracy
                best_cost = total_cost
                best_count = total_count
                best = {
                    "action": "acquire_reference",
                    "candidate_id": candidate["candidate_id"],
                    "sensor_id": candidate["sensor_id"],
                    "known_hypothesis": candidate["known_hypothesis"],
                    "reference_standard_ref": candidate["reference_standard_ref"],
                    "reference_standard_sha256": candidate["reference_standard_sha256"],
                    "cost": candidate["cost"],
                    "current_target_map_accuracy": _fraction_doc(current_accuracy),
                    "expected_target_map_accuracy": _fraction_doc(expected_accuracy),
                    "expected_reference_cost": _fraction_doc(total_cost),
                    "expected_reference_count": _fraction_doc(total_count),
                    "stop_reason": None,
                    "branches": branches,
                }
        dp_memo[key] = best
        return best

    dp_root = solve_dp(initial_belief, max_reference_steps, budget)

    greedy_memo: dict[tuple[tuple[Fraction, ...], int, Fraction], dict[str, Any]] = {}
    greedy_state_count = 0

    def solve_greedy(
        belief: tuple[Fraction, ...],
        steps_left: int,
        remaining_budget: Fraction,
    ) -> dict[str, Any]:
        nonlocal greedy_state_count
        key = (belief, steps_left, remaining_budget)
        if key in greedy_memo:
            return greedy_memo[key]
        greedy_state_count += 1
        if greedy_state_count > max_policy_states:
            raise PolicyStateLimitError(
                f"greedy comparator exceeded max_policy_states={max_policy_states}"
            )
        current_accuracy = target_accuracy(belief)
        stop = {
            "action": None,
            "candidate_id": None,
            "sensor_id": None,
            "known_hypothesis": None,
            "cost": None,
            "current_target_map_accuracy": _fraction_doc(current_accuracy),
            "expected_target_map_accuracy": _fraction_doc(current_accuracy),
            "expected_reference_cost": _fraction_doc(Fraction(0)),
            "expected_reference_count": _fraction_doc(Fraction(0)),
            "stop_reason": (
                "reference_horizon_exhausted" if steps_left == 0
                else "no_positive_one_step_value_within_remaining_budget"
            ),
            "branches": [],
        }
        if steps_left == 0:
            greedy_memo[key] = stop
            return stop

        ranked = []
        for candidate in normalized_candidates:
            cost = Fraction(**candidate["cost"])
            if cost > remaining_budget:
                continue
            expected_accuracy = Fraction(0)
            for signal in ("A", "B"):
                probability, posterior = _belief_after_signal(
                    belief, normalized_calibrations, candidate, signal
                )
                if probability and posterior is not None:
                    expected_accuracy += probability * target_accuracy(posterior)
            gain = expected_accuracy - current_accuracy
            if gain > 0:
                ranked.append((
                    gain / cost,
                    gain,
                    -cost,
                    candidate["candidate_id"],
                    candidate,
                ))
        if not ranked:
            greedy_memo[key] = stop
            return stop

        # Mirrors RIV-010: value/cost, then absolute value, then lower cost,
        # then lexical candidate ID.
        chosen = max(ranked, key=lambda row: row[:4])[4]
        action_cost = Fraction(**chosen["cost"])
        expected_accuracy = Fraction(0)
        expected_child_cost = Fraction(0)
        expected_child_count = Fraction(0)
        branches = []
        for signal in ("A", "B"):
            probability, posterior = _belief_after_signal(
                belief, normalized_calibrations, chosen, signal
            )
            if probability == 0 or posterior is None:
                branches.append({
                    "signal": signal,
                    "predictive_probability": _fraction_doc(Fraction(0)),
                    "reachable": False,
                    "posterior_calibration_probabilities": None,
                    "child": None,
                })
                continue
            child = solve_greedy(
                posterior,
                steps_left - 1,
                remaining_budget - action_cost,
            )
            expected_accuracy += probability * Fraction(
                **child["expected_target_map_accuracy"]
            )
            expected_child_cost += probability * Fraction(
                **child["expected_reference_cost"]
            )
            expected_child_count += probability * Fraction(
                **child["expected_reference_count"]
            )
            branches.append({
                "signal": signal,
                "predictive_probability": _fraction_doc(probability),
                "reachable": True,
                "posterior_calibration_probabilities": _belief_rows(
                    posterior, normalized_calibrations
                ),
                "child": child,
            })

        result = {
            "action": "acquire_reference",
            "candidate_id": chosen["candidate_id"],
            "sensor_id": chosen["sensor_id"],
            "known_hypothesis": chosen["known_hypothesis"],
            "reference_standard_ref": chosen["reference_standard_ref"],
            "reference_standard_sha256": chosen["reference_standard_sha256"],
            "cost": chosen["cost"],
            "current_target_map_accuracy": _fraction_doc(current_accuracy),
            "expected_target_map_accuracy": _fraction_doc(expected_accuracy),
            "expected_reference_cost": _fraction_doc(action_cost + expected_child_cost),
            "expected_reference_count": _fraction_doc(Fraction(1) + expected_child_count),
            "stop_reason": None,
            "branches": branches,
        }
        greedy_memo[key] = result
        return result

    greedy_root = solve_greedy(initial_belief, max_reference_steps, budget)
    dp_value = Fraction(**dp_root["expected_target_map_accuracy"])
    greedy_value = Fraction(**greedy_root["expected_target_map_accuracy"])
    if dp_value < greedy_value:
        raise AssertionError("finite-horizon optimal policy cannot underperform the feasible greedy policy")

    core = {
        "format": FORMAT,
        "model": {
            "target_prior_hypothesis_a": prior_a,
            "calibrations_with_current_prior": normalized_calibrations,
            "target_sensor_schedule": schedule,
            "reference_candidates": normalized_candidates,
            "max_reference_steps": max_reference_steps,
            "cost_budget": _fraction_doc(budget),
            "max_policy_states": max_policy_states,
            "max_histories": max_histories,
            "calibration_scope": "one fixed discrete calibration profile shared across all reference and target observations",
            "reference_observation_assumption": "each reference reading is conditionally independent given the shared calibration profile and its supplied known standard hypothesis",
            "budget_semantics": "the exact cost sum on every realized policy path must not exceed cost_budget",
            "repetition_semantics": "a candidate may be selected more than once; each selection represents a new conditionally independent reading",
        },
        "baseline_target_map_accuracy": _fraction_doc(initial_accuracy),
        "finite_horizon_policy": {
            "expected_target_map_accuracy": _fraction_doc(dp_value),
            "expected_downstream_decision_value": _fraction_doc(dp_value - initial_accuracy),
            "expected_reference_cost": dp_root["expected_reference_cost"],
            "expected_reference_count": dp_root["expected_reference_count"],
            "policy_state_count": dp_state_count,
            "unique_calibration_belief_count": len(target_accuracy_cache),
            "root": dp_root,
        },
        "greedy_reselection_policy": {
            "objective": "repeat RIV-010's one-reference-step downstream value per cost rule after each signal",
            "expected_target_map_accuracy": _fraction_doc(greedy_value),
            "expected_downstream_decision_value": _fraction_doc(greedy_value - initial_accuracy),
            "expected_reference_cost": greedy_root["expected_reference_cost"],
            "expected_reference_count": greedy_root["expected_reference_count"],
            "policy_state_count": greedy_state_count,
            "root": greedy_root,
        },
        "comparison": {
            "finite_horizon_accuracy_gain_over_greedy": _fraction_doc(dp_value - greedy_value),
            "finite_horizon_expected_cost_minus_greedy": _fraction_doc(
                Fraction(**dp_root["expected_reference_cost"])
                - Fraction(**greedy_root["expected_reference_cost"])
            ),
            "same_pathwise_cost_budget": True,
            "same_reference_horizon": max_reference_steps,
            "same_target_schedule": schedule,
        },
        "interpretation_limits": [
            "The dynamic programme is optimal only for the supplied finite calibration family, candidate actions, target schedule, horizon, likelihood model, and pathwise cost budget.",
            "The greedy comparator is the repeated RIV-010 one-step downstream-value-per-cost rule; it is a named heuristic, not a universal reference policy.",
            "Reference standard labels, sensor response probabilities, and costs are supplied assumptions, not authenticated physical facts or measured sensor performance.",
            "The same discrete calibration profile is shared across all reference and target readings; calibration drift and residual dependence after conditioning on the profile are not modeled.",
            "Repeated selections are assumed conditionally independent given the fixed calibration profile and supplied known standard. Shared sample artifacts or correlated readout errors are not represented.",
            "Costs are exact caller-declared values; they are not measured dispatch, admission, transport, authority, interpretation, latency, or energy costs.",
            "The planner returns a policy tree only. It does not dispatch reference measurements, create ObservationPaths, authenticate authority receipts, or update a live RIV-009 report.",
            "The state cap fails closed and does not silently approximate the exact policy.",
            "The terminal objective is expected target MAP accuracy. Other task-loss matrices or downstream utility functions can produce a different optimal policy.",
        ],
    }
    return {**core, "report_digest": _digest(core)}


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild DP and greedy policy trees from their retained exact inputs."""
    if not isinstance(document, Mapping):
        raise TypeError("finite-horizon report must be an object")
    supplied = _copy_json(document, "finite-horizon report")
    digest = supplied.pop("report_digest", None)
    if not isinstance(digest, str) or not _HEX_256.fullmatch(digest) or digest != _digest(supplied):
        raise FiniteHorizonReferenceError("report_digest does not match contents")
    if supplied.get("format") != FORMAT:
        raise FiniteHorizonReferenceError("unsupported finite-horizon report format")
    model = supplied.get("model")
    if not isinstance(model, Mapping):
        raise FiniteHorizonReferenceError("report model is missing")
    rebuilt = build_report(
        prior_hypothesis_a=model.get("target_prior_hypothesis_a"),
        calibrations=model.get("calibrations_with_current_prior"),
        target_sensor_schedule=model.get("target_sensor_schedule"),
        reference_candidates=[
            {
                key: candidate[key]
                for key in (
                    "candidate_id", "sensor_id", "known_hypothesis",
                    "reference_standard_ref", "reference_standard_sha256", "cost",
                )
            }
            for candidate in model.get("reference_candidates", [])
        ],
        max_reference_steps=model.get("max_reference_steps"),
        cost_budget=model.get("cost_budget"),
        max_policy_states=model.get("max_policy_states"),
        max_histories=model.get("max_histories"),
    )
    if rebuilt != dict(document):
        raise FiniteHorizonReferenceError(
            "report differs from independent reconstruction from retained finite model"
        )
    return dict(document)


__all__ = [
    "FORMAT",
    "FiniteHorizonReferenceError",
    "PolicyStateLimitError",
    "build_report",
    "validate_report",
]
