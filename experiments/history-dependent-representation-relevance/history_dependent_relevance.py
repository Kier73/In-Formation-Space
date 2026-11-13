"""Finite exact comparison of reactive and history-dependent observers."""
from __future__ import annotations

import hashlib
import itertools
import json
from fractions import Fraction
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.history-dependent-representation-relevance/0.1"


class PolicyLimitError(ValueError):
    """Exact policy enumeration exceeded its declared cap."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _q(value: Any, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{label} must be an exact rational, not a float or bool")
    try:
        if isinstance(value, Mapping) and set(value) == {"numerator", "denominator"}:
            numerator, denominator = value["numerator"], value["denominator"]
            if isinstance(numerator, bool) or not isinstance(numerator, int):
                raise ValueError
            if isinstance(denominator, bool) or not isinstance(denominator, int) or denominator <= 0:
                raise ValueError
            result = Fraction(numerator, denominator)
        else:
            result = Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"{label} must be an exact rational") from exc
    if result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _unique(values: Sequence[str], label: str) -> list[str]:
    if not isinstance(values, (tuple, list)) or not values:
        raise ValueError(f"{label} must be a non-empty sequence")
    result = [_text(value, label) for value in values]
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must be unique")
    return sorted(result)


def _normalize_model(*, states, actions, initial_distribution, transitions, viable_states):
    state_list = _unique(states, "state")
    action_list = _unique(actions, "action")
    state_set, action_set = set(state_list), set(action_list)
    if not isinstance(initial_distribution, Mapping) or set(initial_distribution) != state_set:
        raise ValueError("initial_distribution must define every state exactly once")
    priors = {s: _q(initial_distribution[s], f"initial_distribution[{s}]") for s in state_list}
    if sum(priors.values(), Fraction()) != 1:
        raise ValueError("initial_distribution must sum exactly to 1")
    if not isinstance(transitions, Mapping) or set(transitions) != action_set:
        raise ValueError("transitions must define every action exactly once")
    table = {}
    for action in action_list:
        row = transitions[action]
        if not isinstance(row, Mapping) or set(row) != state_set:
            raise ValueError(f"transitions[{action}] must define every state exactly once")
        table[action] = {
            state: _text(row[state], f"transitions[{action}][{state}]")
            for state in state_list
        }
        if not set(table[action].values()) <= state_set:
            raise ValueError(f"transitions[{action}] contains an undeclared successor")
    if not isinstance(viable_states, (tuple, list)):
        raise ValueError("viable_states must be a sequence")
    viable = [_text(s, "viable state") for s in viable_states]
    if len(set(viable)) != len(viable) or not set(viable) <= state_set:
        raise ValueError("viable_states must be unique declared states")
    return {
        "states": state_list,
        "actions": action_list,
        "initial_distribution": {s: _doc(priors[s]) for s in state_list},
        "transitions": table,
        "viable_states": sorted(viable),
    }


def _normalize_representations(representations, states):
    if not isinstance(representations, (tuple, list)) or not representations:
        raise ValueError("representations must be a non-empty sequence")
    result, seen = [], set()
    for item in representations:
        if not isinstance(item, Mapping) or set(item) != {"representation_id", "cells"}:
            raise ValueError("each representation needs representation_id and cells")
        ident = _text(item["representation_id"], "representation_id")
        cells = item["cells"]
        if ident in seen or not isinstance(cells, Mapping) or set(cells) != set(states):
            raise ValueError(f"invalid or duplicate representation: {ident}")
        seen.add(ident)
        normalized = {s: _text(cells[s], f"{ident}.cells[{s}]") for s in states}
        result.append({"representation_id": ident, "cells": normalized})
    return sorted(result, key=lambda item: item["representation_id"])


def _refines(fine, coarse):
    mapping = {}
    for state, fine_cell in fine.items():
        coarse_cell = coarse[state]
        if fine_cell in mapping and mapping[fine_cell] != coarse_cell:
            return False
        mapping[fine_cell] = coarse_cell
    return True


def _diagnostics(model, cells):
    viable = set(model["viable_states"])
    viability_aligned = all(
        len({state in viable for state, observed in cells.items() if observed == cell}) == 1
        for cell in set(cells.values())
    )
    congruent = True
    for cell in set(cells.values()):
        members = [s for s in model["states"] if cells[s] == cell]
        for action in model["actions"]:
            successors = {cells[model["transitions"][action][s]] for s in members}
            if len(successors) > 1:
                congruent = False
                break
        if not congruent:
            break
    return congruent, viability_aligned


def _evaluate(model, cells, horizon, policy, *, policy_kind):
    priors = {
        s: Fraction(v["numerator"], v["denominator"])
        for s, v in model["initial_distribution"].items()
    }
    viable = set(model["viable_states"])
    score = Fraction(0)
    for initial in model["states"]:
        mass = priors[initial]
        if mass == 0 or initial not in viable:
            continue
        state, observations, survived = initial, [cells[initial]], True
        for step in range(horizon):
            if policy_kind == "history":
                action = policy[tuple(observations)]
            elif policy_kind == "time_aware":
                action = policy[(step, cells[state])]
            else:
                action = policy[cells[state]]
            state = model["transitions"][action][state]
            if state not in viable:
                survived = False
                break
            if step + 1 < horizon:
                observations.append(cells[state])
        if survived:
            score += mass
    return score


def _profile(model, representation, horizon, max_policies):
    cells = representation["cells"]
    alphabet = sorted(set(cells.values()))
    actions = model["actions"]

    stationary_count = len(actions) ** len(alphabet)
    if stationary_count > max_policies:
        raise PolicyLimitError(f"stationary policy count {stationary_count} exceeds cap {max_policies}")
    stationary_best, stationary_witness = Fraction(-1), None
    for choices in itertools.product(actions, repeat=len(alphabet)):
        policy = dict(zip(alphabet, choices))
        value = _evaluate(model, cells, horizon, policy, policy_kind="stationary")
        if value > stationary_best:
            stationary_best, stationary_witness = value, policy

    # Reactive control can know the finite-horizon step without retaining observations.
    time_keys = [(step, cell) for step in range(horizon) for cell in alphabet]
    time_aware_count = len(actions) ** len(time_keys)
    if time_aware_count > max_policies:
        raise PolicyLimitError(f"time-aware reactive policy count {time_aware_count} exceeds cap {max_policies}")
    time_aware_best, time_aware_witness = Fraction(-1), None
    for choices in itertools.product(actions, repeat=len(time_keys)):
        policy = dict(zip(time_keys, choices))
        value = _evaluate(model, cells, horizon, policy, policy_kind="time_aware")
        if value > time_aware_best:
            time_aware_best, time_aware_witness = value, policy

    # Enumerate only histories reachable from positive-prior viable initial states
    # under at least one viability-preserving action sequence. Impossible histories
    # cannot change the survival objective and need no policy entry.
    prior = {
        state: Fraction(value["numerator"], value["denominator"])
        for state, value in model["initial_distribution"].items()
    }
    viable = set(model["viable_states"])
    frontier = {
        (state, (cells[state],))
        for state in model["states"]
        if prior[state] > 0 and state in viable
    }
    reachable_histories = set()
    for step in range(horizon):
        reachable_histories.update(history for _, history in frontier)
        if step + 1 == horizon:
            break
        next_frontier = set()
        for state, history in frontier:
            for action in actions:
                successor = model["transitions"][action][state]
                if successor in viable:
                    next_frontier.add((successor, history + (cells[successor],)))
        frontier = next_frontier
    histories = sorted(reachable_histories)
    history_count = len(actions) ** len(histories)
    if history_count > max_policies:
        raise PolicyLimitError(
            f"history policy count {history_count} ({len(histories)} reachable histories) exceeds cap {max_policies}"
        )
    history_best, history_witness = Fraction(-1), None
    for choices in itertools.product(actions, repeat=len(histories)):
        policy = dict(zip(histories, choices))
        value = _evaluate(model, cells, horizon, policy, policy_kind="history")
        if value > history_best:
            history_best, history_witness = value, policy

    time_gain = time_aware_best - stationary_best
    memory_gain = history_best - time_aware_best
    if time_gain < 0 or memory_gain < 0:
        raise AssertionError("larger policy classes must include the preceding class")
    congruent, aligned = _diagnostics(model, cells)
    return {
        "representation_id": representation["representation_id"],
        "observation_cell_count": len(alphabet),
        "stationary_policy_count": stationary_count,
        "time_aware_reactive_policy_count": time_aware_count,
        "reachable_history_count": len(histories),
        "history_policy_count": history_count,
        "stationary": {
            "max_survival_probability": _doc(stationary_best),
            "optimal_policy": stationary_witness,
        },
        "time_aware_reactive": {
            "max_survival_probability": _doc(time_aware_best),
            "optimal_policy": [
                {"step": step, "observation": cell, "action": time_aware_witness[(step, cell)]}
                for step, cell in time_keys
            ],
        },
        "history_dependent": {
            "max_survival_probability": _doc(history_best),
            "optimal_policy": [
                {"observation_history": list(hist), "action": history_witness[hist]}
                for hist in histories
            ],
        },
        "time_awareness_gain": _doc(time_gain),
        "history_memory_gain": _doc(memory_gain),
        "transition_congruent": congruent,
        "viability_aligned": aligned,
    }


def build_report(*, states, actions, initial_distribution, transitions, viable_states,
                 representations, ablations, horizon, max_policies=100_000):
    """Compare stationary, time-aware reactive, and finite-history policies.

    Stationary maps current observation to action. Time-aware reactive maps
    (step, current observation) to action. History-dependent maps the complete
    observed prefix to action. The history class contains the time-aware class.
    Past actions are derivable from the observation history and deterministic
    policy. Only reachable histories are enumerated. Exact enumeration is
    exponential; max_policies is a fail-closed cap, not an approximation.
    """
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    if isinstance(max_policies, bool) or not isinstance(max_policies, int) or max_policies < 1:
        raise ValueError("max_policies must be a positive integer")
    model = _normalize_model(
        states=states, actions=actions, initial_distribution=initial_distribution,
        transitions=transitions, viable_states=viable_states,
    )
    reps = _normalize_representations(representations, model["states"])
    by_id = {r["representation_id"]: r for r in reps}
    if not isinstance(ablations, (tuple, list)) or not ablations:
        raise ValueError("ablations must be a non-empty sequence")
    pairs, seen = [], set()
    for pair in ablations:
        if not isinstance(pair, Mapping) or set(pair) != {"baseline", "ablated"}:
            raise ValueError("each ablation needs exactly baseline and ablated")
        fine, coarse = pair["baseline"], pair["ablated"]
        if fine not in by_id or coarse not in by_id or fine == coarse:
            raise ValueError("ablation references unknown or identical representations")
        if not _refines(by_id[fine]["cells"], by_id[coarse]["cells"]):
            raise ValueError(f"{fine} must refine {coarse}")
        if (fine, coarse) in seen:
            raise ValueError(f"duplicate ablation pair {fine}/{coarse}")
        seen.add((fine, coarse))
        pairs.append({"baseline": fine, "ablated": coarse})

    profiles = {r["representation_id"]: _profile(model, r, horizon, max_policies) for r in reps}
    ablation_results = []
    for pair in sorted(pairs, key=lambda x: (x["baseline"], x["ablated"])):
        fine, coarse = profiles[pair["baseline"]], profiles[pair["ablated"]]
        fs = Fraction(**fine["stationary"]["max_survival_probability"])
        cs = Fraction(**coarse["stationary"]["max_survival_probability"])
        ft = Fraction(**fine["time_aware_reactive"]["max_survival_probability"])
        ct = Fraction(**coarse["time_aware_reactive"]["max_survival_probability"])
        fh = Fraction(**fine["history_dependent"]["max_survival_probability"])
        ch = Fraction(**coarse["history_dependent"]["max_survival_probability"])
        losses = {"stationary": fs - cs, "time_aware_reactive": ft - ct, "history_dependent": fh - ch}
        if any(loss < 0 for loss in losses.values()):
            raise AssertionError("partition refinement cannot reduce achievable value")
        ablation_results.append({
            **pair,
            "stationary_baseline_value": _doc(fs),
            "stationary_ablated_value": _doc(cs),
            "stationary_viability_loss": _doc(losses["stationary"]),
            "time_aware_baseline_value": _doc(ft),
            "time_aware_ablated_value": _doc(ct),
            "time_aware_viability_loss": _doc(losses["time_aware_reactive"]),
            "history_baseline_value": _doc(fh),
            "history_ablated_value": _doc(ch),
            "history_viability_loss": _doc(losses["history_dependent"]),
            "baseline_time_awareness_gain": fine["time_awareness_gain"],
            "ablated_time_awareness_gain": coarse["time_awareness_gain"],
            "baseline_memory_gain": fine["history_memory_gain"],
            "ablated_memory_gain": coarse["history_memory_gain"],
        })

    report = {
        "format": FORMAT, "model": model, "representations": reps,
        "horizon": horizon, "max_policies": max_policies,
        "profiles": profiles, "ablations": ablation_results,
    }
    report["content_digest"] = _digest(report)
    return report


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct derived values from retained inputs and reject tampering."""
    if not isinstance(document, Mapping) or document.get("format") != FORMAT:
        raise ValueError("unsupported history-dependent relevance report")
    model = document.get("model")
    if not isinstance(model, Mapping):
        raise ValueError("report model is missing")
    rebuilt = build_report(
        states=model.get("states"), actions=model.get("actions"),
        initial_distribution=model.get("initial_distribution"),
        transitions=model.get("transitions"), viable_states=model.get("viable_states"),
        representations=document.get("representations"),
        ablations=[{"baseline": p["baseline"], "ablated": p["ablated"]}
                   for p in document.get("ablations", [])],
        horizon=document.get("horizon"), max_policies=document.get("max_policies"),
    )
    if dict(document) != rebuilt:
        raise ValueError("report differs from independent reconstruction")
    return rebuilt
