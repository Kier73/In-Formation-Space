"""Exact bounded synthesis of deterministic finite-state observation controllers."""
from __future__ import annotations
import hashlib
import itertools
import json
from fractions import Fraction
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.bounded-memory-representation-relevance/0.1"


class ControllerLimitError(ValueError):
    """Finite-state controller enumeration exceeded its declared cap."""


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _q(value: Any, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{label} must be an exact rational")
    try:
        if isinstance(value, Mapping) and set(value) == {"numerator", "denominator"}:
            n, d = value["numerator"], value["denominator"]
            if isinstance(n, bool) or not isinstance(n, int):
                raise ValueError
            if isinstance(d, bool) or not isinstance(d, int) or d <= 0:
                raise ValueError
            result = Fraction(n, d)
        else:
            result = Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"{label} must be an exact rational") from exc
    if result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _doc(value: Fraction):
    return {"numerator": value.numerator, "denominator": value.denominator}


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _unique(values: Sequence[str], label: str):
    if not isinstance(values, (tuple, list)) or not values:
        raise ValueError(f"{label} must be a non-empty sequence")
    items = [_text(x, label) for x in values]
    if len(set(items)) != len(items):
        raise ValueError(f"{label} must be unique")
    return sorted(items)


def _model(*, states, actions, initial_distribution, transitions, viable_states):
    ss, aa = _unique(states, "state"), _unique(actions, "action")
    if not isinstance(initial_distribution, Mapping) or set(initial_distribution) != set(ss):
        raise ValueError("initial_distribution must define every state exactly once")
    prior = {s: _q(initial_distribution[s], f"prior[{s}]") for s in ss}
    if sum(prior.values(), Fraction()) != 1:
        raise ValueError("initial_distribution must sum exactly to 1")
    if not isinstance(transitions, Mapping) or set(transitions) != set(aa):
        raise ValueError("transitions must define every action exactly once")
    table = {}
    for a in aa:
        row = transitions[a]
        if not isinstance(row, Mapping) or set(row) != set(ss):
            raise ValueError(f"transitions[{a}] must define every state exactly once")
        table[a] = {s: _text(row[s], f"transition[{a}][{s}]") for s in ss}
        if not set(table[a].values()) <= set(ss):
            raise ValueError(f"transitions[{a}] contains an undeclared successor")
    if not isinstance(viable_states, (tuple, list)):
        raise ValueError("viable_states must be a sequence")
    viable = [_text(s, "viable state") for s in viable_states]
    if len(set(viable)) != len(viable) or not set(viable) <= set(ss):
        raise ValueError("viable_states must be unique declared states")
    return {
        "states": ss, "actions": aa,
        "initial_distribution": {s: _doc(prior[s]) for s in ss},
        "transitions": table, "viable_states": sorted(viable),
    }


def _representations(items, states):
    if not isinstance(items, (tuple, list)) or not items:
        raise ValueError("representations must be a non-empty sequence")
    result, seen = [], set()
    for item in items:
        if not isinstance(item, Mapping) or set(item) != {"representation_id", "cells"}:
            raise ValueError("each representation needs representation_id and cells")
        ident, cells = _text(item["representation_id"], "representation_id"), item["cells"]
        if ident in seen or not isinstance(cells, Mapping) or set(cells) != set(states):
            raise ValueError(f"invalid or duplicate representation: {ident}")
        seen.add(ident)
        result.append({
            "representation_id": ident,
            "cells": {s: _text(cells[s], f"{ident}.cells[{s}]") for s in states},
        })
    return sorted(result, key=lambda x: x["representation_id"])


def _refines(fine, coarse):
    assignment = {}
    for state, cell in fine.items():
        target = coarse[state]
        if cell in assignment and assignment[cell] != target:
            return False
        assignment[cell] = target
    return True


def _history_target(model, cells, horizon, cap):
    prior = {s: Fraction(**v) for s, v in model["initial_distribution"].items()}
    viable = set(model["viable_states"])
    frontier = {(s, (cells[s],)) for s in model["states"] if prior[s] > 0 and s in viable}
    histories = set()
    for step in range(horizon):
        histories.update(h for _, h in frontier)
        if step + 1 == horizon:
            break
        following = set()
        for state, hist in frontier:
            for action in model["actions"]:
                target = model["transitions"][action][state]
                if target in viable:
                    following.add((target, hist + (cells[target],)))
        frontier = following
    histories = sorted(histories)
    count = len(model["actions"]) ** len(histories)
    if count > cap:
        raise ControllerLimitError(f"full-history target requires {count} policies; cap is {cap}")
    best, witness = Fraction(-1), None
    for choices in itertools.product(model["actions"], repeat=len(histories)):
        policy = dict(zip(histories, choices))
        value = _evaluate_history(model, cells, horizon, policy)
        if value > best:
            best, witness = value, policy
    return {
        "max_survival_probability": _doc(best),
        "reachable_history_count": len(histories),
        "policy_count": count,
        "optimal_policy": [
            {"observation_history": list(h), "action": witness[h]} for h in histories
        ],
    }


def _evaluate_history(model, cells, horizon, policy):
    prior = {s: Fraction(**v) for s, v in model["initial_distribution"].items()}
    viable, score = set(model["viable_states"]), Fraction(0)
    for initial in model["states"]:
        if prior[initial] == 0 or initial not in viable:
            continue
        state, hist, survives = initial, [cells[initial]], True
        for step in range(horizon):
            state = model["transitions"][policy[tuple(hist)]][state]
            if state not in viable:
                survives = False
                break
            if step + 1 < horizon:
                hist.append(cells[state])
        if survives:
            score += prior[initial]
    return score


def _evaluate_fsc(model, cells, horizon, actions, updates, memory_size):
    prior = {s: Fraction(**v) for s, v in model["initial_distribution"].items()}
    viable, score = set(model["viable_states"]), Fraction(0)
    for initial in model["states"]:
        if prior[initial] == 0 or initial not in viable:
            continue
        state, memory, survives = initial, 0, True
        for step in range(horizon):
            observation = cells[state]
            action = actions[(memory, observation)]
            state = model["transitions"][action][state]
            if state not in viable:
                survives = False
                break
            if step + 1 < horizon:
                memory = updates[(memory, observation)]
                assert 0 <= memory < memory_size
        if survives:
            score += prior[initial]
    return score


def _fsc_profile(model, cells, horizon, k, cap):
    alphabet, actions = sorted(set(cells.values())), model["actions"]
    keys = [(q, obs) for q in range(k) for obs in alphabet]
    count = (len(actions) ** len(keys)) * (k ** len(keys))
    if count > cap:
        raise ControllerLimitError(f"{k}-state FSC class has {count} controllers; cap is {cap}")
    best, witness = Fraction(-1), None
    for action_choices in itertools.product(actions, repeat=len(keys)):
        action_map = dict(zip(keys, action_choices))
        for update_choices in itertools.product(range(k), repeat=len(keys)):
            update_map = dict(zip(keys, update_choices))
            value = _evaluate_fsc(model, cells, horizon, action_map, update_map, k)
            if value > best:
                best = value
                witness = {
                    "initial_memory_state": 0,
                    "action_map": [
                        {"memory_state": q, "observation": o, "action": action_map[(q, o)]}
                        for q, o in keys
                    ],
                    "memory_update_map": [
                        {"memory_state": q, "observation": o, "next_memory_state": update_map[(q, o)]}
                        for q, o in keys
                    ],
                }
    return {
        "memory_state_count": k, "controller_count": count,
        "max_survival_probability": _doc(best), "optimal_controller": witness,
    }


def build_report(*, states, actions, initial_distribution, transitions, viable_states,
                 representations, ablations, horizon, memory_sizes=(1, 2),
                 max_controllers=1_000_000):
    """Synthesize bounded deterministic FSCs and compare with a full-history target.

    Each FSC has an action map gamma(q, o) -> a and an update map eta(q, o) -> q'.
    Its initial memory is 0. The update is after the chosen action and uses the
    current observation; an action argument is redundant because gamma is
    deterministic. The next decision sees updated memory plus next observation.
    """
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    if isinstance(max_controllers, bool) or not isinstance(max_controllers, int) or max_controllers < 1:
        raise ValueError("max_controllers must be a positive integer")
    if not isinstance(memory_sizes, (tuple, list)) or not memory_sizes:
        raise ValueError("memory_sizes must be a non-empty sequence")
    sizes = []
    for k in memory_sizes:
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            raise ValueError("memory sizes must be positive integers")
        sizes.append(k)
    if len(set(sizes)) != len(sizes):
        raise ValueError("memory_sizes must be unique")
    sizes.sort()
    model = _model(
        states=states, actions=actions, initial_distribution=initial_distribution,
        transitions=transitions, viable_states=viable_states,
    )
    reps = _representations(representations, model["states"])
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
            raise ValueError("duplicate ablation pair")
        seen.add((fine, coarse))
        pairs.append({"baseline": fine, "ablated": coarse})

    profiles = {}
    for rep in reps:
        ident, cells = rep["representation_id"], rep["cells"]
        target = _history_target(model, cells, horizon, max_controllers)
        controllers = [_fsc_profile(model, cells, horizon, k, max_controllers) for k in sizes]
        target_value = Fraction(**target["max_survival_probability"])
        values = [Fraction(**item["max_survival_probability"]) for item in controllers]
        if any(values[i] > values[i + 1] for i in range(len(values) - 1)):
            raise AssertionError("adding memory states cannot reduce the best FSC value")
        if any(value > target_value for value in values):
            raise AssertionError("an FSC exceeded the full-history policy class")
        attaining = [
            item["memory_state_count"] for item, value in zip(controllers, values)
            if value == target_value
        ]
        profiles[ident] = {
            "representation_id": ident,
            "observation_cell_count": len(set(cells.values())),
            "full_history_target": target,
            "finite_state_controllers": controllers,
            "smallest_tested_memory_size_attaining_history_value": min(attaining) if attaining else None,
        }

    ablation_results = []
    for pair in sorted(pairs, key=lambda p: (p["baseline"], p["ablated"])):
        fine, coarse = profiles[pair["baseline"]], profiles[pair["ablated"]]
        fine_target = Fraction(**fine["full_history_target"]["max_survival_probability"])
        coarse_target = Fraction(**coarse["full_history_target"]["max_survival_probability"])
        memory_losses = []
        for k in sizes:
            f = next(x for x in fine["finite_state_controllers"] if x["memory_state_count"] == k)
            c = next(x for x in coarse["finite_state_controllers"] if x["memory_state_count"] == k)
            fv, cv = Fraction(**f["max_survival_probability"]), Fraction(**c["max_survival_probability"])
            loss = fv - cv
            if loss < 0:
                raise AssertionError("representation refinement cannot reduce FSC value")
            memory_losses.append({
                "memory_state_count": k, "baseline_value": _doc(fv),
                "ablated_value": _doc(cv), "viability_loss": _doc(loss),
            })
        history_loss = fine_target - coarse_target
        if history_loss < 0:
            raise AssertionError("representation refinement cannot reduce full-history value")
        ablation_results.append({
            **pair, "history_baseline_value": _doc(fine_target),
            "history_ablated_value": _doc(coarse_target),
            "history_viability_loss": _doc(history_loss),
            "finite_memory_losses": memory_losses,
            "baseline_smallest_tested_memory_size": fine["smallest_tested_memory_size_attaining_history_value"],
            "ablated_smallest_tested_memory_size": coarse["smallest_tested_memory_size_attaining_history_value"],
        })

    report = {
        "format": FORMAT, "model": model, "representations": reps, "horizon": horizon,
        "memory_sizes": sizes, "max_controllers": max_controllers,
        "profiles": profiles, "ablations": ablation_results,
    }
    report["content_digest"] = _digest(report)
    return report


def validate_report(document: Mapping[str, Any]):
    if not isinstance(document, Mapping) or document.get("format") != FORMAT:
        raise ValueError("unsupported bounded-memory relevance report")
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
        horizon=document.get("horizon"), memory_sizes=document.get("memory_sizes"),
        max_controllers=document.get("max_controllers"),
    )
    if dict(document) != rebuilt:
        raise ValueError("report differs from independent reconstruction")
    return rebuilt
