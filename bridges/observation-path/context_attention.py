"""Plan which missing context observations would best separate attempts.

This adapter represents the attempts in one transition cell as states in a
synthetic VGI observer-space Ground. Context capture methods are actions and
caller-declared values are counterfactual branches. VGI's own exact minimax
AND/OR planner chooses a finite measurement policy; this module does not
dispatch observations or revise the source transition model.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from typing import Any, Mapping, Optional, Sequence


_FORMAT = "in-formation.context-attention-policy"
_SCHEMA = "in-formation.context-attention-policy/0.1"
_VGI_REVISION = "ac13c1bbd92dfd09f17de51adef7adb2d2088bf6"
_ALLOWED_SCALARS = (str, int, bool, type(None))


class ContextAttentionError(ValueError):
    """Invalid context-attention request or unreconstructable proposal."""


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ContextAttentionError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise ContextAttentionError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextAttentionError(f"{label} must be non-empty text")
    return value


def _scalar(value: object, label: str) -> object:
    if type(value) not in _ALLOWED_SCALARS:
        raise ContextAttentionError(
            f"{label} must be a string, integer, Boolean, or null"
        )
    _canonical(value)
    return value


def _fraction(value: object, label: str, *, positive: bool = False) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise ContextAttentionError(f"{label} must be an exact integer or Fraction")
    try:
        result = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise ContextAttentionError(f"{label} must be an exact rational") from error
    if positive and result <= 0:
        raise ContextAttentionError(f"{label} must be positive")
    return result


def _fraction_record(value: Optional[Fraction]) -> Optional[dict[str, int]]:
    if value is None:
        return None
    return {"numerator": value.numerator, "denominator": value.denominator}


def _parse_fraction_record(value: object, label: str) -> Optional[Fraction]:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"numerator", "denominator"}:
        raise ContextAttentionError(f"{label} must be a numerator/denominator object")
    numerator, denominator = value["numerator"], value["denominator"]
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise ContextAttentionError(f"{label} contains invalid rational components")
    return Fraction(numerator, denominator)


def _encode_index(index: int, width: int) -> tuple[int, ...]:
    digits = [0] * width
    current = index
    for position in range(width - 1, -1, -1):
        digits[position] = current % 8
        current //= 8
    if current:
        raise ContextAttentionError("internal context-value encoding width is insufficient")
    return tuple(digits)


@dataclass(frozen=True, slots=True)
class ContextProbeMethod:
    """One context dimension's capture method, exact cost, and finite value set."""

    method_id: str
    dimension: str
    possible_values: tuple[object, ...]
    cost: object = Fraction(1, 1)
    source_ref: Optional[str] = None

    def __post_init__(self) -> None:
        method_id = _text(self.method_id, "method_id")
        dimension = _text(self.dimension, "dimension")
        if not isinstance(self.possible_values, (tuple, list)) or not self.possible_values:
            raise ContextAttentionError("possible_values must be a non-empty sequence")
        values = tuple(_scalar(value, f"possible_values[{index}]")
                       for index, value in enumerate(self.possible_values))
        keyed = {_canonical(value): value for value in values}
        if len(keyed) != len(values):
            raise ContextAttentionError("possible_values must be unique")
        normalized_values = tuple(keyed[key] for key in sorted(keyed))
        cost = _fraction(self.cost, "method cost", positive=True)
        if self.source_ref is not None:
            _text(self.source_ref, "source_ref")
        object.__setattr__(self, "method_id", method_id)
        object.__setattr__(self, "dimension", dimension)
        object.__setattr__(self, "possible_values", normalized_values)
        object.__setattr__(self, "cost", cost)


def _normalize_methods(methods: object) -> tuple[ContextProbeMethod, ...]:
    if not isinstance(methods, (tuple, list)) or not methods:
        raise ContextAttentionError("methods must be a non-empty sequence")
    normalized = []
    for index, method in enumerate(methods):
        if isinstance(method, ContextProbeMethod):
            normalized.append(method)
            continue
        if not isinstance(method, Mapping):
            raise TypeError(f"methods[{index}] must be a ContextProbeMethod or object")
        raw = dict(method)
        allowed = {"method_id", "dimension", "possible_values", "cost", "source_ref"}
        if set(raw) - allowed or not {"method_id", "dimension", "possible_values"} <= set(raw):
            raise ContextAttentionError(f"methods[{index}] has missing or unexpected fields")
        normalized.append(ContextProbeMethod(
            method_id=raw["method_id"],
            dimension=raw["dimension"],
            possible_values=tuple(raw["possible_values"]),
            cost=raw.get("cost", 1),
            source_ref=raw.get("source_ref"),
        ))
    normalized.sort(key=lambda item: (item.method_id, item.dimension))
    ids = [item.method_id for item in normalized]
    dimensions = [item.dimension for item in normalized]
    if len(set(ids)) != len(ids):
        raise ContextAttentionError("each context method_id must be unique")
    if len(set(dimensions)) != len(dimensions):
        raise ContextAttentionError(
            "the initial policy supports one capture method per context dimension"
        )
    return tuple(normalized)


def _method_record(
    method: ContextProbeMethod,
    observed_values: Sequence[object],
    output_width: int,
) -> dict[str, Any]:
    values_by_key = {_canonical(value): value for value in method.possible_values}
    for value in observed_values:
        values_by_key[_canonical(value)] = value
    keys = sorted(values_by_key)
    values = [values_by_key[key] for key in keys]
    entries = [
        {"value": value, "output": list(_encode_index(index, output_width))}
        for index, value in enumerate(values)
    ]
    record: dict[str, Any] = {
        "method_id": method.method_id,
        "dimension": method.dimension,
        "possible_values": list(method.possible_values),
        "cost": _fraction_record(method.cost),
        "value_encoding": entries,
        "encoding_semantics": "injective_base8_categorical_code_for_synthetic_vgi_observer_ground",
    }
    if method.source_ref is not None:
        record["source_ref"] = method.source_ref
    return record


def _attempt_context_status(
    attempt_id: str,
    dimension: str,
    assignments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    assignment = assignments.get(attempt_id)
    if assignment is None:
        return {"status": "unassigned"}
    descriptor = assignment["dimensions"].get(dimension)
    if descriptor is None:
        return {"status": "not_supplied"}
    if descriptor["status"] == "unknown":
        return {"status": "unknown", "reason": descriptor["reason"]}
    return {"status": "observed", "value": descriptor["value"]}


def _pair_relation_summary(
    records: Sequence[Mapping[str, Any]],
    comparison: object,
) -> dict[str, Any]:
    statuses = {"equivalent": 0, "distinguishable": 0, "unresolved": 0}
    full_pairs = {
        status: {"pair_count": 0, "transition_disagreement_count": 0}
        for status in statuses
    }
    transitions = {
        record["attempt_id"]: record["observed_transition"]
        for record in records
    }
    full = {
        attempt_id: transition
        for attempt_id, transition in transitions.items()
        if transition["next_state"] is not None
    }
    attempt_ids = sorted(transitions)
    for index, left in enumerate(attempt_ids):
        for right in attempt_ids[index + 1:]:
            status = comparison.status(left, right)
            if status not in statuses:
                raise ContextAttentionError(f"VGI returned unexpected pair status {status!r}")
            statuses[status] += 1
            if left in full and right in full:
                full_pairs[status]["pair_count"] += 1
                left_transition = {
                    "outcome": full[left]["outcome"],
                    "next_state": full[left]["next_state"],
                }
                right_transition = {
                    "outcome": full[right]["outcome"],
                    "next_state": full[right]["next_state"],
                }
                if left_transition != right_transition:
                    full_pairs[status]["transition_disagreement_count"] += 1
    full_pair_count = sum(item["pair_count"] for item in full_pairs.values())
    full_disagreement_count = sum(
        item["transition_disagreement_count"] for item in full_pairs.values()
    )
    return {
        "attempt_pair_status_counts": statuses,
        "full_transition_pair_count": full_pair_count,
        "full_transition_disagreement_pair_count": full_disagreement_count,
        "full_transition_pair_relations": full_pairs,
        "outcome_only_attempt_count": len(records) - len(full),
        "pair_semantics": "VGI_one_step_observer_relation_over_only_selected_context_dimensions",
        "transition_comparison_semantics": "exact_observed_outcome_and_next_state_pair",
    }


def _resolve_vgi_api(vgi_api: object) -> object:
    if vgi_api is None:
        raise TypeError("vgi_api must be the pinned VGI module or compatible public API")
    required = (
        "GroundTransitionSystem", "TransitionObservation", "TransitionOutcome",
        "ObserverContext", "ProbeScenario", "TransitionProbe",
        "plan_partial_probe_policy", "sparse_partial_contextual_comparison",
    )
    missing = [name for name in required if not hasattr(vgi_api, name)]
    if missing:
        raise ContextAttentionError(f"VGI API is missing required exports: {missing}")
    return vgi_api


def build_context_attention_plan(
    *,
    context_analysis: Mapping[str, Any],
    model_document: Mapping[str, Any],
    probe_id: str,
    current_state: str,
    methods: Sequence[ContextProbeMethod],
    vgi_api: object,
    budget: Optional[object] = None,
    max_probes: Optional[int] = None,
    max_states: int = 10_000,
) -> dict[str, Any]:
    """Build a VGI minimax policy over attempts' missing context observations.

    Each attempt in one repeated-transition cell becomes a synthetic Ground
    state. Each context-capture method is an action. Declared values become
    unweighted scenario branches. The returned policy is a proposal only.
    """
    from transition_context import validate_transition_context_analysis

    vgi = _resolve_vgi_api(vgi_api)
    probe = _text(probe_id, "probe_id")
    state = _text(current_state, "current_state")
    try:
        source = validate_transition_context_analysis(
            context_analysis, model_document=model_document
        )
    except (TypeError, ValueError, KeyError) as error:
        raise ContextAttentionError(
            f"context analysis failed independent reconstruction: {error}"
        ) from error

    normalized_methods = _normalize_methods(methods)
    if type(max_states) is not int or max_states <= 0:
        raise ContextAttentionError("max_states must be a positive integer")
    if max_probes is not None and (type(max_probes) is not int or max_probes < 0):
        raise ContextAttentionError("max_probes must be a non-negative integer or null")
    normalized_budget = None if budget is None else _fraction(
        budget, "budget", positive=False
    )
    if normalized_budget is not None and normalized_budget < 0:
        raise ContextAttentionError("budget must be non-negative")

    records = [
        record for record in source["source_conformance_records"]
        if record["probe_id"] == probe and record["current_state"] == state
    ]
    records.sort(key=lambda item: item["attempt_id"])
    if len(records) < 2:
        raise ContextAttentionError(
            "context attention requires at least two attempts in the selected transition cell"
        )
    attempt_ids = [record["attempt_id"] for record in records]
    if len(set(attempt_ids)) != len(attempt_ids):
        raise ContextAttentionError("selected cell contains duplicate attempt identifiers")

    assignments = {
        item["attempt_id"]: item
        for item in source["source_context_assignments"]
    }
    observed_by_dimension: dict[str, list[object]] = {}
    context_status: dict[str, dict[str, dict[str, Any]]] = {}
    for method in normalized_methods:
        statuses = {}
        observed_values = []
        for attempt_id in attempt_ids:
            descriptor = _attempt_context_status(
                attempt_id, method.dimension, assignments
            )
            statuses[attempt_id] = descriptor
            if descriptor["status"] == "observed":
                observed_values.append(descriptor["value"])
        context_status[method.method_id] = statuses
        observed_by_dimension[method.dimension] = observed_values

    # Use one shared output width. All per-method category codes are injective
    # in the same finite Z/8Z channel vector space.
    max_categories = max(
        len({_canonical(value) for value in method.possible_values}
            | {_canonical(value) for value in observed_by_dimension[method.dimension]})
        for method in normalized_methods
    )
    output_width = 1
    while 8 ** output_width < max_categories:
        output_width += 1
    channel_names = tuple(f"context_digit_{index}" for index in range(output_width))
    method_records = [
        _method_record(
            method, observed_by_dimension[method.dimension], output_width
        )
        for method in normalized_methods
    ]
    encodings = {
        record["method_id"]: {
            _canonical(item["value"]): tuple(item["output"])
            for item in record["value_encoding"]
        }
        for record in method_records
    }
    method_by_id = {method.method_id: method for method in normalized_methods}

    observations = []
    for method in normalized_methods:
        for attempt_id in attempt_ids:
            descriptor = context_status[method.method_id][attempt_id]
            if descriptor["status"] != "observed":
                continue
            assignment = assignments[attempt_id]
            output = encodings[method.method_id][_canonical(descriptor["value"])]
            observations.append(vgi.TransitionObservation(
                source=attempt_id,
                action=method.method_id,
                outcomes=(vgi.TransitionOutcome(attempt_id, output),),
                support_count=1,
                evidence=(f"context-assignment:{assignment['assignment_digest']}",),
            ))

    metadata = {
        "purpose": "synthetic_observer_space_for_context_attention",
        "source_context_analysis_digest": source["analysis_digest"],
        "source_model_ref": source["model_ref"],
        "source_model_digest": source["model_digest"],
        "selected_transition_cell": {
            "probe_id": probe,
            "current_state": state,
        },
        "context_status_by_method_and_attempt": context_status,
        "method_value_encodings": method_records,
        "source_context_assignment_digests": sorted(
            item["assignment_digest"] for item in source["source_context_assignments"]
            if item["attempt_id"] in attempt_ids
        ),
        "semantic_boundary": (
            "synthetic observer-space Ground; state names are attempt IDs, "
            "actions are caller-declared context capture methods, and transitions "
            "encode reported context values only"
        ),
    }
    synthetic_ground = vgi.GroundTransitionSystem(
        states=tuple(attempt_ids),
        actions=tuple(method.method_id for method in normalized_methods),
        initial_state=attempt_ids[0],
        channels=channel_names,
        observations=tuple(observations),
        metadata=metadata,
    )
    observer = vgi.ObserverContext.full(
        synthetic_ground, name="context-discrimination"
    )
    baseline = vgi.sparse_partial_contextual_comparison(
        synthetic_ground, observer, 1
    )
    baseline_relations = _pair_relation_summary(records, baseline)

    candidates = []
    for method in normalized_methods:
        encoded_values = encodings[method.method_id]
        scenario_values = sorted(
            (item["value"] for item in next(
                record for record in method_records
                if record["method_id"] == method.method_id
            )["value_encoding"]),
            key=_canonical,
        )
        scenarios = tuple(
            vgi.ProbeScenario(vgi.TransitionOutcome(
                target=attempt_id,
                output=encoded_values[_canonical(value)],
            ))
            for value in scenario_values
        )
        for attempt_id in attempt_ids:
            if context_status[method.method_id][attempt_id]["status"] == "observed":
                continue
            candidates.append(vgi.TransitionProbe(
                state=attempt_id,
                action=method.method_id,
                scenarios=scenarios,
                cost=method.cost,
                label=method.method_id,
            ))
    candidates.sort(key=lambda item: (
        item.state, item.action, item.label, item.cost.numerator, item.cost.denominator
    ))

    try:
        effective_max_probes = (
            None if max_probes is None
            else min(max_probes, len(candidates))
        )
        policy = vgi.plan_partial_probe_policy(
            synthetic_ground,
            observer,
            tuple(candidates),
            1,
            budget=normalized_budget,
            max_probes=effective_max_probes,
            max_states=max_states,
        )
    except (TypeError, ValueError, KeyError) as error:
        raise ContextAttentionError(f"VGI context-policy planning failed: {error}") from error

    next_measurement = None
    if policy.first_probe is not None:
        selected = policy.first_probe
        method = method_by_id[selected.action]
        value_by_output = {
            tuple(item["output"]): item["value"]
            for item in next(
                row for row in method_records if row["method_id"] == method.method_id
            )["value_encoding"]
        }
        next_measurement = {
            "attempt_id": selected.state,
            "method_id": selected.action,
            "dimension": method.dimension,
            "label": selected.label,
            "cost": _fraction_record(method.cost),
            "declared_scenario_values": [
                value_by_output[tuple(scenario.outcome.output)]
                for scenario in selected.scenarios
            ],
            "status": context_status[method.method_id][selected.state]["status"],
        }

    unselected_dimensions = sorted({
        dimension
        for assignment in source["source_context_assignments"]
        if assignment["attempt_id"] in attempt_ids
        for dimension in assignment["dimensions"]
        if dimension not in {method.dimension for method in normalized_methods}
    })
    core = {
        "format": _FORMAT,
        "schema": _SCHEMA,
        "source_context_analysis_digest": source["analysis_digest"],
        "source_model_ref": source["model_ref"],
        "source_model_digest": source["model_digest"],
        "selected_transition_cell": {
            "probe_id": probe,
            "current_state": state,
            "attempt_ids": attempt_ids,
        },
        "vgi_revision": _VGI_REVISION,
        "vgi_revision_semantics": "focused_and_regression_ci_dependency_pin; runtime_api_argument_is_not_cryptographically_attested",
        "vgi_api_contract": "Virtual-Ground-Interpreter/vgi partial_attention + partial_policy exports",
        "synthetic_ground": {
            "fingerprint": synthetic_ground.fingerprint,
            "document": synthetic_ground.to_dict(),
        },
        "observer": {
            "name": observer.name,
            "actions": list(observer.actions),
            "channels": list(observer.channels),
        },
        "methods": method_records,
        "unselected_context_dimensions": unselected_dimensions,
        "initial_context_pair_relations": baseline_relations,
        "candidate_probe_count": len(candidates),
        "plan_config": {
            "horizon": 1,
            "budget": _fraction_record(normalized_budget),
            "max_probes_requested": max_probes,
            "max_probes_effective": policy.max_probes,
            "max_states": max_states,
        },
        "policy": policy.to_dict(),
        "next_measurement": next_measurement,
        "execution_status": "proposal_only_not_dispatched",
        "ground_effect": "none",
        "model_effect": "none",
        "attention_policy_effect": "none",
        "interpretation_limits": [
            "Attempt IDs are synthetic observer-space states; they are not asserted to be physical system states.",
            "Context capture methods are caller-declared actions and their finite value sets are proposal branches, not claims of exhaustiveness or probabilities.",
            "The VGI minimax objective reduces worst-case unresolved pairs over the supplied attempts, methods, and declared values only.",
            "Equal observed context profiles induce observer-relative equivalence; they do not establish physical hidden-state identity or causal explanation.",
            "The disagreement among context-equivalent full transition pairs is descriptive residual variation; it may reflect omitted conditions, drift, concurrency, observation error, or selection effects.",
            "Outcome-only transition records participate in context attention but are excluded from full-transition disagreement denominators.",
            "Unknown, not-supplied, and unassigned context remain distinct in the synthetic Ground metadata and are not treated as observed values.",
            "No context observation is dispatched, no ObservationPath is advanced, and no source Ground or transition model is modified.",
            "An eventual measurement outside the declared scenario set must be retained as model mismatch, not mapped to the nearest branch.",
            "Digests provide content identity and reconstruction checks, not authentication of external context sources.",
            "The VGI revision field records the CI dependency pin; the supplied runtime API object is not independently authenticated by this report.",
        ],
    }
    return {**core, "report_digest": _digest(core)}


def validate_context_attention_plan(
    report: Mapping[str, Any],
    *,
    context_analysis: Mapping[str, Any],
    model_document: Mapping[str, Any],
    vgi_api: object,
) -> dict[str, Any]:
    """Rebuild the proposal from the embedded validated context analysis."""
    if not isinstance(report, Mapping):
        raise TypeError("context attention report must be a mapping")
    supplied = _copy_json(report, "context attention report")
    digest = supplied.pop("report_digest", None)
    if not isinstance(digest, str) or digest != _digest(supplied):
        raise ContextAttentionError("report digest does not match its contents")
    if supplied.get("format") != _FORMAT or supplied.get("schema") != _SCHEMA:
        raise ContextAttentionError("unsupported context attention report format/schema")

    raw_methods = supplied.get("methods")
    if not isinstance(raw_methods, list):
        raise ContextAttentionError("report methods must be an array")
    methods = []
    for index, item in enumerate(raw_methods):
        if not isinstance(item, Mapping):
            raise ContextAttentionError(f"report methods[{index}] must be an object")
        methods.append(ContextProbeMethod(
            method_id=item["method_id"],
            dimension=item["dimension"],
            possible_values=tuple(item["possible_values"]),
            cost=_parse_fraction_record(item["cost"], f"methods[{index}].cost"),
            source_ref=item.get("source_ref"),
        ))
    selected = supplied.get("selected_transition_cell")
    config = supplied.get("plan_config")
    if not isinstance(selected, Mapping) or not isinstance(config, Mapping):
        raise ContextAttentionError("report cell and plan_config must be objects")
    rebuilt = build_context_attention_plan(
        context_analysis=context_analysis,
        model_document=model_document,
        probe_id=selected.get("probe_id"),
        current_state=selected.get("current_state"),
        methods=methods,
        vgi_api=vgi_api,
        budget=_parse_fraction_record(config.get("budget"), "plan_config.budget"),
        max_probes=config.get("max_probes_requested"),
        max_states=config.get("max_states"),
    )
    if rebuilt != dict(report):
        raise ContextAttentionError(
            "context attention report differs from independent reconstruction"
        )
    return dict(report)


__all__ = [
    "ContextAttentionError",
    "ContextProbeMethod",
    "build_context_attention_plan",
    "validate_context_attention_plan",
]
