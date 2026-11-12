"""Finite counterfactual measurement of task-relative representation value."""
from __future__ import annotations

import hashlib
import itertools
import json
from fractions import Fraction
from typing import Any, Mapping

FORMAT = "in-formation.task-relative-relevance/0.1"


class PolicyLimitError(ValueError):
    """Exact policy enumeration exceeded its declared cap."""


def _q(value: Any, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{label} must be an exact rational, not a float or bool")
    try:
        if isinstance(value, Mapping) and set(value) == {"numerator", "denominator"}:
            if any(isinstance(value[k], bool) or not isinstance(value[k], int) for k in value):
                raise ValueError
            if value["denominator"] <= 0:
                raise ValueError
            result = Fraction(value["numerator"], value["denominator"])
        else:
            result = Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"{label} must be an exact rational") from exc
    if result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _model(states, actions, initial, transitions, viable):
    if not states or len(set(states)) != len(states) or any(not isinstance(s, str) or not s for s in states):
        raise ValueError("states must be unique non-empty strings")
    if not actions or len(set(actions)) != len(actions) or any(not isinstance(a, str) or not a for a in actions):
        raise ValueError("actions must be unique non-empty strings")
    if set(initial) != set(states):
        raise ValueError("initial_distribution must define every state exactly once")
    priors = {s: _q(initial[s], f"initial_distribution[{s}]") for s in states}
    if sum(priors.values(), Fraction()) != 1:
        raise ValueError("initial_distribution must sum exactly to 1")
    if set(transitions) != set(actions):
        raise ValueError("transitions must define every action exactly once")
    table = {}
    for action in actions:
        if set(transitions[action]) != set(states):
            raise ValueError(f"transitions[{action}] must define every state exactly once")
        table[action] = {}
        for state in states:
            target = transitions[action][state]
            if target not in states:
                raise ValueError(f"transition {action}/{state} targets an unknown state")
            table[action][state] = target
    if len(set(viable)) != len(viable) or not set(viable) <= set(states):
        raise ValueError("viable_states must be a unique subset of states")
    return {
        "states": sorted(states), "actions": sorted(actions),
        "initial_distribution": {s: _doc(priors[s]) for s in sorted(states)},
        "transitions": {a: {s: table[a][s] for s in sorted(states)} for a in sorted(actions)},
        "viable_states": sorted(viable),
    }


def _normalise_representations(representations, states):
    if not representations:
        raise ValueError("representations must not be empty")
    result, seen = [], set()
    for item in representations:
        if set(item) != {"representation_id", "cells"}:
            raise ValueError("each representation needs representation_id and cells")
        ident, cells = item["representation_id"], item["cells"]
        if not isinstance(ident, str) or not ident or ident in seen or set(cells) != set(states):
            raise ValueError("representation IDs must be unique and every state assigned exactly once")
        if any(not isinstance(c, str) or not c for c in cells.values()):
            raise ValueError("cell IDs must be non-empty strings")
        seen.add(ident)
        result.append({"representation_id": ident, "cells": dict(cells)})
    return sorted(result, key=lambda x: x["representation_id"])


def _refines(fine, coarse):
    mapping = {}
    for state, cell in fine.items():
        target = coarse[state]
        if cell in mapping and mapping[cell] != target:
            return False
        mapping[cell] = target
    return True


def _profile(model, representation, horizon, max_policies):
    states, actions = model["states"], model["actions"]
    cells_by_state = representation["cells"]
    cells = sorted(set(cells_by_state.values()))
    count = len(actions) ** len(cells)
    if count > max_policies:
        raise PolicyLimitError(f"{representation['representation_id']} requires {count} policies; cap is {max_policies}")
    prior = {s: Fraction(v["numerator"], v["denominator"]) for s, v in model["initial_distribution"].items()}
    viable = set(model["viable_states"])
    best, witness = Fraction(-1), None
    for choices in itertools.product(actions, repeat=len(cells)):
        policy = dict(zip(cells, choices))
        score = Fraction()
        for start in states:
            mass = prior[start]
            if not mass or start not in viable:
                continue
            state, survives = start, True
            for _ in range(horizon):
                action = policy[cells_by_state[state]]
                state = model["transitions"][action][state]
                if state not in viable:
                    survives = False
                    break
            if survives:
                score += mass
        if score > best:
            best, witness = score, policy
    transition_congruent = True
    for cell in cells:
        members = [s for s in states if cells_by_state[s] == cell]
        for action in actions:
            if len({cells_by_state[model["transitions"][action][s]] for s in members}) > 1:
                transition_congruent = False
                break
    viability_aligned = all(len({s in viable for s in states if cells_by_state[s] == cell}) == 1 for cell in cells)
    return {
        "representation_id": representation["representation_id"],
        "cell_count": len(cells), "policy_count": count,
        "max_survival_probability": _doc(best), "optimal_policy": witness,
        "transition_congruent": transition_congruent,
        "viability_aligned": viability_aligned,
    }


def build_report(*, states, actions, initial_distribution, transitions, viable_states,
                 representations, ablations, horizon, max_policies=100_000):
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    if isinstance(max_policies, bool) or not isinstance(max_policies, int) or max_policies < 1:
        raise ValueError("max_policies must be a positive integer")
    model = _model(states, actions, initial_distribution, transitions, viable_states)
    reps = _normalise_representations(representations, model["states"])
    by_id = {r["representation_id"]: r for r in reps}
    if not ablations:
        raise ValueError("ablations must not be empty")
    comparisons = []
    for pair in ablations:
        if set(pair) != {"baseline", "ablated"}:
            raise ValueError("each ablation needs baseline and ablated IDs")
        fine, coarse = pair["baseline"], pair["ablated"]
        if fine not in by_id or coarse not in by_id or fine == coarse:
            raise ValueError("ablation references unknown or identical representations")
        if not _refines(by_id[fine]["cells"], by_id[coarse]["cells"]):
            raise ValueError(f"baseline {fine} must refine ablated representation {coarse}")
        comparisons.append({"baseline": fine, "ablated": coarse})
    profiles = {r["representation_id"]: _profile(model, r, horizon, max_policies) for r in reps}
    results = []
    for pair in sorted(comparisons, key=lambda x: (x["baseline"], x["ablated"])):
        fine = profiles[pair["baseline"]]["max_survival_probability"]
        coarse = profiles[pair["ablated"]]["max_survival_probability"]
        loss = Fraction(fine["numerator"], fine["denominator"]) - Fraction(coarse["numerator"], coarse["denominator"])
        if loss < 0:
            raise AssertionError("refinement must not reduce the best achievable value")
        results.append({**pair, "baseline_value": fine, "ablated_value": coarse, "task_relative_viability_loss": _doc(loss)})
    report = {"format": FORMAT, "model": model, "representations": reps,
              "horizon": horizon, "max_policies": max_policies,
              "profiles": profiles, "ablations": results}
    report["content_digest"] = _digest(report)
    return report


def validate_report(document: Mapping[str, Any]):
    if not isinstance(document, Mapping) or document.get("format") != FORMAT:
        raise ValueError("unsupported task-relative relevance report")
    expected = build_report(
        states=document["model"]["states"], actions=document["model"]["actions"],
        initial_distribution=document["model"]["initial_distribution"],
        transitions=document["model"]["transitions"], viable_states=document["model"]["viable_states"],
        representations=document["representations"],
        ablations=[{"baseline": p["baseline"], "ablated": p["ablated"]} for p in document["ablations"]],
        horizon=document["horizon"], max_policies=document["max_policies"])
    if dict(document) != expected:
        raise ValueError("report differs from independent reconstruction")
    return expected
