"""Exact finite-horizon attention planning when probes alter the observed system.

Trial 08 extends non-intervening adaptive attention. A candidate hypothesis
retains its identity and original query value while its current world state
changes after every selected probe. Probe outcomes determine the policy branch;
next-state transitions determine what later probes can observe.

The planner returns a Pareto frontier over expected and worst-case observation
cost and intervention cost. All costs and priors use exact rational arithmetic.
This is a bounded deterministic model, not a stochastic POMDP solver.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.intervention-attention"
SCHEMA = "in-formation.intervention-attention/0.1"
LIMITS = [
    "The hypothesis set, state set, and deterministic probe transition tables are finite and fully supplied.",
    "The query is about the initial hypothesis and does not change when probes intervene on the world.",
    "A probe outcome is the only information available to the policy; hidden next states are not directly observed.",
    "Probe observation costs and state-dependent intervention costs are non-negative and additive along a path.",
    "The solver enumerates exact policies only up to the declared action depth and frontier/combinations limits.",
    "No stochastic outcomes, unmodelled autonomous drift, concurrent probes, or external disturbances are inferred.",
    "The returned frontier is Pareto-nondominated only for the four declared cost dimensions and supplied model.",
    "A finite-model result is not evidence that its hypothesis set or transition table is complete for an external system.",
]


class FrontierLimitError(ValueError):
    """Raised when exact enumeration exceeds an explicitly declared bound."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _fraction(value: object, label: str, *, strictly_positive: bool = False) -> Fraction:
    """Parse an exact rational; floats are rejected rather than approximated."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{label} must be an exact integer, rational string, or rational object")
    try:
        if isinstance(value, Fraction):
            result = value
        elif isinstance(value, int):
            result = Fraction(value, 1)
        elif isinstance(value, str):
            result = Fraction(value)
        elif isinstance(value, Mapping) and set(value) == {"numerator", "denominator"}:
            numerator = _integer(value["numerator"], f"{label}.numerator", minimum=-(2**63))
            denominator = _integer(value["denominator"], f"{label}.denominator", minimum=1)
            result = Fraction(numerator, denominator)
        else:
            raise ValueError
    except (ValueError, ZeroDivisionError, TypeError, OverflowError) as error:
        raise ValueError(f"{label} must be an exact rational") from error
    if result < 0 or (strictly_positive and result == 0):
        relation = "positive" if strictly_positive else "non-negative"
        raise ValueError(f"{label} must be {relation}")
    return result


def _fraction_doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _cost_key(costs: tuple[Fraction, Fraction, Fraction, Fraction]) -> tuple[Fraction, ...]:
    return costs


@dataclass(frozen=True)
class _Option:
    tree: dict[str, Any]
    path_costs: tuple[tuple[str, Fraction, Fraction], ...]
    expected_observation: Fraction
    expected_intervention: Fraction
    worst_observation: Fraction
    worst_intervention: Fraction

    @property
    def costs(self) -> tuple[Fraction, Fraction, Fraction, Fraction]:
        return (
            self.expected_observation,
            self.expected_intervention,
            self.worst_observation,
            self.worst_intervention,
        )


def _dominates(left: _Option, right: _Option) -> bool:
    """Use per-hypothesis costs so pruning remains safe under ancestor costs.

    Aggregate expected/worst costs alone are not compositional: a parent can
    add different state-dependent costs to different hypotheses. Two child
    plans with the same aggregate vector can therefore produce different root
    worst cases. Componentwise path dominance is preserved under every
    non-negative prefix-cost assignment.
    """
    if tuple(row[0] for row in left.path_costs) != tuple(row[0] for row in right.path_costs):
        return False
    left_paths = {identifier: (observation, intervention)
                  for identifier, observation, intervention in left.path_costs}
    right_paths = {identifier: (observation, intervention)
                   for identifier, observation, intervention in right.path_costs}
    comparisons = [
        (left_paths[identifier][dimension], right_paths[identifier][dimension])
        for identifier in left_paths
        for dimension in (0, 1)
    ]
    return all(a <= b for a, b in comparisons) and any(a < b for a, b in comparisons)


def _pareto(options: Sequence[_Option], limit: int) -> list[_Option]:
    """Retain a compositional path-cost antichain for recursive subproblems."""
    by_paths: dict[tuple[tuple[str, Fraction, Fraction], ...], _Option] = {}
    for option in options:
        key = option.path_costs
        previous = by_paths.get(key)
        if previous is None or _canonical(option.tree) < _canonical(previous.tree):
            by_paths[key] = option
    unique = list(by_paths.values())
    frontier = [
        candidate for candidate in unique
        if not any(_dominates(other, candidate) for other in unique if other is not candidate)
    ]
    frontier.sort(key=lambda item: (item.costs, item.path_costs, _canonical(item.tree)))
    if len(frontier) > limit:
        raise FrontierLimitError(
            f"Pareto frontier has {len(frontier)} plans, exceeding max_frontier={limit}"
        )
    return frontier


def _pareto_aggregate(options: Sequence[_Option], limit: int) -> list[_Option]:
    """Collapse equivalent root metrics and return the requested four-cost frontier."""
    by_vector: dict[tuple[Fraction, ...], _Option] = {}
    for option in options:
        key = _cost_key(option.costs)
        previous = by_vector.get(key)
        if previous is None or _canonical(option.tree) < _canonical(previous.tree):
            by_vector[key] = option
    unique = list(by_vector.values())
    frontier = [
        candidate for candidate in unique
        if not any(
            all(a <= b for a, b in zip(other.costs, candidate.costs))
            and any(a < b for a, b in zip(other.costs, candidate.costs))
            for other in unique if other is not candidate
        )
    ]
    frontier.sort(key=lambda item: (item.costs, _canonical(item.tree)))
    if len(frontier) > limit:
        raise FrontierLimitError(
            f"Root Pareto frontier has {len(frontier)} plans, exceeding max_frontier={limit}"
        )
    return frontier


def _normalize_model(
    world_states: Sequence[str],
    hypotheses: Sequence[Mapping[str, Any]],
    probes: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Fraction], dict[str, bool], dict[str, dict[str, Any]]]:
    if not isinstance(world_states, (tuple, list)) or not world_states:
        raise ValueError("world_states must be a non-empty sequence")
    states = [_text(state, "world state") for state in world_states]
    if len(set(states)) != len(states):
        raise ValueError("world_states must be unique")
    state_set = set(states)

    if not isinstance(hypotheses, (tuple, list)) or not hypotheses:
        raise ValueError("hypotheses must be a non-empty sequence")
    normalized_hypotheses = []
    priors: dict[str, Fraction] = {}
    query_values: dict[str, bool] = {}
    initial_states: dict[str, str] = {}
    for item in hypotheses:
        if not isinstance(item, Mapping) or set(item) != {
            "hypothesis_id", "initial_state", "query_value", "prior"
        }:
            raise ValueError("each hypothesis must contain exactly hypothesis_id, initial_state, query_value, prior")
        identifier = _text(item["hypothesis_id"], "hypothesis_id")
        if identifier in priors:
            raise ValueError(f"duplicate hypothesis_id: {identifier}")
        initial = _text(item["initial_state"], f"{identifier}.initial_state")
        if initial not in state_set:
            raise ValueError(f"unknown initial state for {identifier}: {initial}")
        query = item["query_value"]
        if not isinstance(query, bool):
            raise ValueError(f"{identifier}.query_value must be bool")
        prior = _fraction(item["prior"], f"{identifier}.prior", strictly_positive=True)
        priors[identifier] = prior
        query_values[identifier] = query
        initial_states[identifier] = initial
        normalized_hypotheses.append({
            "hypothesis_id": identifier,
            "initial_state": initial,
            "query_value": query,
            "prior": _fraction_doc(prior),
        })
    if sum(priors.values(), Fraction(0, 1)) != 1:
        raise ValueError("hypothesis priors must sum exactly to 1")
    normalized_hypotheses.sort(key=lambda row: row["hypothesis_id"])

    if not isinstance(probes, (tuple, list)):
        raise ValueError("probes must be a sequence")
    normalized_probes = []
    probe_map: dict[str, dict[str, Any]] = {}
    for item in probes:
        if not isinstance(item, Mapping) or set(item) != {"probe_id", "observation_cost", "transitions"}:
            raise ValueError("each probe must contain exactly probe_id, observation_cost, transitions")
        identifier = _text(item["probe_id"], "probe_id")
        if identifier in probe_map:
            raise ValueError(f"duplicate probe_id: {identifier}")
        observation_cost = _fraction(item["observation_cost"], f"{identifier}.observation_cost")
        transitions = item["transitions"]
        if not isinstance(transitions, Mapping) or set(transitions) != state_set:
            raise ValueError(f"{identifier}.transitions must define every declared world state exactly once")
        normalized_transitions = {}
        for state in states:
            transition = transitions[state]
            if not isinstance(transition, Mapping) or set(transition) != {
                "outcome", "next_state", "intervention_cost"
            }:
                raise ValueError(
                    f"{identifier}.transitions[{state}] must contain exactly outcome, next_state, intervention_cost"
                )
            outcome = _text(transition["outcome"], f"{identifier}.{state}.outcome")
            next_state = _text(transition["next_state"], f"{identifier}.{state}.next_state")
            if next_state not in state_set:
                raise ValueError(f"{identifier}.{state} transitions to undeclared state: {next_state}")
            intervention = _fraction(
                transition["intervention_cost"], f"{identifier}.{state}.intervention_cost"
            )
            normalized_transitions[state] = {
                "outcome": outcome,
                "next_state": next_state,
                "intervention_cost": _fraction_doc(intervention),
            }
        normalized = {
            "probe_id": identifier,
            "observation_cost": _fraction_doc(observation_cost),
            "transitions": normalized_transitions,
        }
        normalized_probes.append(normalized)
        probe_map[identifier] = {
            "probe_id": identifier,
            "observation_cost": observation_cost,
            "transitions": {
                state: {
                    "outcome": normalized_transitions[state]["outcome"],
                    "next_state": normalized_transitions[state]["next_state"],
                    "intervention_cost": _fraction(
                        normalized_transitions[state]["intervention_cost"], "intervention_cost"
                    ),
                }
                for state in states
            },
        }
    normalized_probes.sort(key=lambda row: row["probe_id"])
    model = {
        "world_states": states,
        "hypotheses": normalized_hypotheses,
        "probes": normalized_probes,
    }
    return model, priors, query_values, {key: probe_map[key] for key in sorted(probe_map)}


def build_intervention_attention_frontier(
    *,
    world_states: Sequence[str],
    hypotheses: Sequence[Mapping[str, Any]],
    probes: Sequence[Mapping[str, Any]],
    max_depth: int,
    max_hypotheses: int = 10,
    max_frontier: int = 128,
    max_combinations: int = 4096,
) -> dict[str, Any]:
    """Build exact Pareto-nondominated policies for an intervention-aware query.

    A hypothesis has a stable identity, an initial world state, a Boolean query
    value about that initial hypothesis, and an exact prior. A selected probe
    emits an outcome and changes the world state. The observer sees only the
    outcome, so all hypotheses with the same outcome enter one policy branch,
    each carrying its own updated hidden state.

    The Pareto dimensions are expected observation cost, expected intervention
    cost, worst-case observation cost, and worst-case intervention cost. No
    weighted scalarization is imposed on those distinct preferences.
    """
    max_depth = _integer(max_depth, "max_depth")
    max_hypotheses = _integer(max_hypotheses, "max_hypotheses", minimum=1)
    max_frontier = _integer(max_frontier, "max_frontier", minimum=1)
    max_combinations = _integer(max_combinations, "max_combinations", minimum=1)
    model, priors, query_values, probe_map = _normalize_model(world_states, hypotheses, probes)
    if len(priors) > max_hypotheses:
        raise ValueError(
            f"exact search is limited to {max_hypotheses} hypotheses; got {len(priors)}"
        )
    initial_by_id = {
        row["hypothesis_id"]: row["initial_state"] for row in model["hypotheses"]
    }
    model_digest = _digest(model)
    ordered_ids = tuple(sorted(priors))
    start = tuple((identifier, initial_by_id[identifier]) for identifier in ordered_ids)

    cache: dict[tuple[tuple[tuple[str, str], ...], int], list[_Option]] = {}
    explored_states = 0

    def solve(candidates: tuple[tuple[str, str], ...], depth_left: int) -> list[_Option]:
        nonlocal explored_states
        key = (candidates, depth_left)
        if key in cache:
            return cache[key]
        explored_states += 1
        if explored_states > max_combinations:
            raise FrontierLimitError(
                f"exact search exceeded max_combinations={max_combinations} memoized states"
            )

        active_ids = tuple(identifier for identifier, _ in candidates)
        active_queries = {query_values[identifier] for identifier in active_ids}
        candidate_state_doc = [
            {"hypothesis_id": identifier, "current_state": state}
            for identifier, state in candidates
        ]
        if len(active_queries) == 1:
            result = next(iter(active_queries))
            terminal = _Option(
                tree={
                    "candidate_states": candidate_state_doc,
                    "resolved_initial_query": result,
                    "probe_id": None,
                    "branches": [],
                },
                path_costs=tuple((identifier, Fraction(0), Fraction(0)) for identifier in active_ids),
                expected_observation=Fraction(0),
                expected_intervention=Fraction(0),
                worst_observation=Fraction(0),
                worst_intervention=Fraction(0),
            )
            cache[key] = [terminal]
            return [terminal]
        if depth_left == 0:
            cache[key] = []
            return []

        total_mass = sum((priors[identifier] for identifier in active_ids), Fraction(0))
        options: list[_Option] = []
        for probe_id, probe in probe_map.items():
            grouped: dict[str, list[tuple[str, str]]] = {}
            all_outcomes = set()
            all_next_states = set()
            for identifier, current_state in candidates:
                transition = probe["transitions"][current_state]
                outcome = transition["outcome"]
                next_state = transition["next_state"]
                all_outcomes.add(outcome)
                all_next_states.add(next_state)
                grouped.setdefault(outcome, []).append((identifier, next_state))

            # A constant-output probe can still be useful if it changes hidden
            # states differently. But if all survivors get the same result and
            # the same next state, it cannot refine the belief now or later.
            if len(all_outcomes) == 1 and len(all_next_states) == 1:
                continue

            branches = [
                (outcome, tuple(sorted(grouped[outcome])))
                for outcome in sorted(grouped)
            ]
            child_frontiers = [solve(next_candidates, depth_left - 1) for _, next_candidates in branches]
            if any(not frontier for frontier in child_frontiers):
                continue
            combination_count = 1
            for frontier in child_frontiers:
                combination_count *= len(frontier)
            if combination_count > max_combinations:
                raise FrontierLimitError(
                    f"probe {probe_id} requires {combination_count} child-policy combinations, "
                    f"exceeding max_combinations={max_combinations}"
                )

            for child_selection in itertools.product(*child_frontiers):
                branch_docs = []
                child_paths_by_outcome: dict[str, dict[str, tuple[Fraction, Fraction]]] = {}
                for (outcome, next_candidates), child in zip(branches, child_selection):
                    child_paths_by_outcome[outcome] = {
                        identifier: (observation_cost, intervention_cost)
                        for identifier, observation_cost, intervention_cost in child.path_costs
                    }
                    branch_docs.append({"outcome": outcome, "next_candidate_states": [
                        {"hypothesis_id": identifier, "current_state": state}
                        for identifier, state in next_candidates
                    ], "child": child.tree})

                # Retain each hypothesis's full path separately. In particular,
                # max(current intervention) + max(future intervention) can pair
                # costs from different hypotheses and is not an exact worst case.
                path_costs = []
                for identifier, current_state in candidates:
                    transition = probe["transitions"][current_state]
                    child_observation, child_intervention = child_paths_by_outcome[transition["outcome"]][identifier]
                    path_costs.append((
                        identifier,
                        probe["observation_cost"] + child_observation,
                        transition["intervention_cost"] + child_intervention,
                    ))
                expected_observation = sum(
                    (priors[identifier] * observation_cost / total_mass
                     for identifier, observation_cost, _ in path_costs),
                    Fraction(0),
                )
                expected_intervention = sum(
                    (priors[identifier] * intervention_cost / total_mass
                     for identifier, _, intervention_cost in path_costs),
                    Fraction(0),
                )
                worst_observation = max((observation_cost for _, observation_cost, _ in path_costs), default=Fraction(0))
                worst_intervention = max((intervention_cost for _, _, intervention_cost in path_costs), default=Fraction(0))
                options.append(_Option(
                    tree={
                        "candidate_states": candidate_state_doc,
                        "resolved_initial_query": None,
                        "probe_id": probe_id,
                        "branches": branch_docs,
                    },
                    path_costs=tuple(path_costs),
                    expected_observation=expected_observation,
                    expected_intervention=expected_intervention,
                    worst_observation=worst_observation,
                    worst_intervention=worst_intervention,
                ))

        frontier = _pareto(options, max_frontier) if options else []
        cache[key] = frontier
        return frontier

    root_options = _pareto_aggregate(solve(start, max_depth), max_frontier)
    frontier_docs = []
    for option in root_options:
        costs = {
            "expected_observation": _fraction_doc(option.expected_observation),
            "expected_intervention": _fraction_doc(option.expected_intervention),
            "worst_case_observation": _fraction_doc(option.worst_observation),
            "worst_case_intervention": _fraction_doc(option.worst_intervention),
        }
        path_cost_docs = [
            {
                "hypothesis_id": identifier,
                "observation_cost": _fraction_doc(observation_cost),
                "intervention_cost": _fraction_doc(intervention_cost),
            }
            for identifier, observation_cost, intervention_cost in option.path_costs
        ]
        policy_digest = _digest({"policy": option.tree, "costs": costs, "path_costs": path_cost_docs})
        frontier_docs.append({
            "policy": option.tree,
            "costs": costs,
            "path_costs": path_cost_docs,
            "policy_digest": policy_digest,
        })

    initially_resolved = len({query_values[identifier] for identifier in ordered_ids}) == 1
    status = (
        "resolved_without_probes" if initially_resolved
        else "complete_frontier" if frontier_docs
        else "unresolved_within_depth"
    )
    core = {
        "format": FORMAT,
        "schema": SCHEMA,
        "model": model,
        "model_digest": model_digest,
        "query_scope": "initial_hypothesis",
        "max_depth": max_depth,
        "solver_limits": {
            "max_hypotheses": max_hypotheses,
            "max_frontier": max_frontier,
            "max_combinations": max_combinations,
        },
        "status": status,
        "frontier": frontier_docs,
        "explored_dynamic_program_states": explored_states,
        "interpretation_limits": list(LIMITS),
    }
    return {**core, "plan_digest": _digest(core)}


def validate_intervention_attention_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild a plan from its embedded finite model and require exact equality."""
    if not isinstance(document, Mapping):
        raise TypeError("intervention-attention document must be a mapping")
    expected = {
        "format", "schema", "model", "model_digest", "query_scope", "max_depth",
        "solver_limits", "status", "frontier", "explored_dynamic_program_states",
        "interpretation_limits", "plan_digest",
    }
    if set(document) != expected:
        raise ValueError("intervention-attention document fields are incomplete or unexpected")
    if document["format"] != FORMAT or document["schema"] != SCHEMA:
        raise ValueError("unsupported intervention-attention format or schema")
    if document["query_scope"] != "initial_hypothesis":
        raise ValueError("unsupported query scope")
    model = document["model"]
    limits = document["solver_limits"]
    if not isinstance(model, Mapping) or set(model) != {"world_states", "hypotheses", "probes"}:
        raise ValueError("embedded model has an invalid shape")
    if not isinstance(limits, Mapping) or set(limits) != {
        "max_hypotheses", "max_frontier", "max_combinations"
    }:
        raise ValueError("solver_limits has an invalid shape")
    rebuilt = build_intervention_attention_frontier(
        world_states=model["world_states"],
        hypotheses=model["hypotheses"],
        probes=model["probes"],
        max_depth=document["max_depth"],
        max_hypotheses=limits["max_hypotheses"],
        max_frontier=limits["max_frontier"],
        max_combinations=limits["max_combinations"],
    )
    if rebuilt != dict(document):
        raise ValueError("intervention-attention document differs from independent reconstruction")
    return dict(document)
