"""RE-007: finite-model observation completeness and active, state-changing probes.

Exact bounded reasoning, not a physical sensor or universal causal identification.
Missing, refused, and pending measurements never count as negative observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping
import hashlib
import hmac
import json

SCHEMA = "in-formation.response-re007/0.1"
LAWS = ("coupled", "quiet", "transient")
PROBES = ("snapshot", "archive", "deep", "prime", "resonance")
COST = {"snapshot": 1, "archive": 2, "deep": 4, "prime": 1, "resonance": 1}
IMPACT = {"snapshot": 0, "archive": 0, "deep": 0, "prime": 1, "resonance": 0}
HIDDEN_MODE = {"quiet": 0, "transient": 1, "coupled": 2}


class ObservationError(ValueError):
    """Invalid, unauthorized, or conflicting observation evidence."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class State:
    primed: bool = False
    revision: int = 0


def response(law: str, state: State, probe: str) -> int | str:
    if law not in LAWS or probe not in PROBES:
        raise ObservationError("unknown law or probe")
    if probe == "prime":
        raise ObservationError("an intervention acknowledgement is not a sensor reading")
    if probe == "snapshot":
        # +1 and -1 transients cancel before each instantaneous sample.
        return 0
    if probe == "archive":
        # Only complete within the supplied synthetic event-stream model.
        return "absent" if law == "quiet" else "present"
    if probe == "deep":
        return HIDDEN_MODE[law]
    if probe == "resonance":
        return HIDDEN_MODE[law] if state.primed else 0
    raise AssertionError("unreachable")


def apply_probe(state: State, probe: str) -> State:
    if probe not in PROBES:
        raise ObservationError("unknown probe")
    if probe == "prime":
        if state.primed:
            raise ObservationError("prime cannot be silently repeated")
        return State(primed=True, revision=state.revision + 1)
    return state


def sampled_world(law: str) -> tuple[int, ...]:
    """A transient may live wholly between sampling instants 0, 2, and 4."""
    if law not in LAWS:
        raise ObservationError("unknown law")
    return (0, 0, 0, 0, 0) if law == "quiet" else (0, 1, 0, 0, 0)


def assess_sampling(samples: Mapping[int, int]) -> dict[str, Any]:
    if not samples or any(type(t) is not int or type(v) is not int or t < 0
                          for t, v in samples.items()):
        raise ObservationError("sampling evidence must be finite integer coordinates")
    ordered = sorted(samples)
    return {
        "sampled_coordinates": ordered,
        "all_sample_values_zero": all(samples[t] == 0 for t in ordered),
        "unsampled_gaps": [[a, b] for a, b in zip(ordered, ordered[1:]) if b - a > 1],
        "absence_of_unobserved_events_established": False,
    }


def _groups(survivors: tuple[str, ...], primed: bool, probe: str) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for law in survivors:
        value = response(law, State(primed=primed), probe)
        groups.setdefault(str(value), []).append(law)
    return {k: tuple(v) for k, v in sorted(groups.items())}


def plan(*, dropout_budget: int | None, max_actions: int = 5,
         priority: str = "observation_cost", permitted: frozenset[str] | None = None,
         candidates: tuple[str, ...] = LAWS) -> dict[str, Any]:
    """Minimax finite decision tree; all at-most-budget missed reads are adversarial.

    `None` dropout budget means unbounded potential loss: no finite guarantee.
    Assumes every acknowledged prime is actually applied, a complete candidate
    catalogue, and no unmodelled drift. This is a conditional planning result.
    """
    if dropout_budget is not None and (type(dropout_budget) is not int or dropout_budget < 0):
        raise ValueError("dropout_budget must be non-negative integer or None")
    if type(max_actions) is not int or max_actions < 0 or max_actions > 10:
        raise ValueError("max_actions must be between zero and ten")
    if priority not in {"observation_cost", "no_intervention"}:
        raise ValueError("unknown decision objective")
    if not candidates or len(set(candidates)) != len(candidates) or any(c not in LAWS for c in candidates):
        raise ValueError("invalid candidate set")
    candidates = tuple(sorted(candidates))
    allowed = frozenset(PROBES if permitted is None else permitted)
    if not allowed.issubset(set(PROBES)):
        raise ValueError("unknown permitted probe")
    if dropout_budget is None:
        return {"status": "not_guaranteed_under_unbounded_dropout",
                "survivors": list(candidates), "policy": None,
                "model_completeness_assumed": True, "worst_case_guarantee": False}

    @lru_cache(None)
    def solve(survivors: tuple[str, ...], primed: bool, missing_left: int,
              actions_left: int) -> dict[str, Any] | None:
        if len(survivors) <= 1:
            return {"kind": "identified", "survivors": list(survivors),
                    "worst_observation_cost": 0, "worst_intervention_cost": 0,
                    "worst_actions": 0}
        if actions_left == 0:
            return None
        options = []
        for probe in sorted(allowed):
            if probe == "prime":
                if primed or "resonance" not in allowed:
                    continue
                result = solve(survivors, True, missing_left, actions_left - 1)
                if result is None:
                    continue
                children = {"applied": result}
            else:
                groups = _groups(survivors, primed, probe)
                # A returned constant result and a dropped result cannot resolve
                # an unchanged candidate set. Avoid cycling through useless reads.
                if len(groups) <= 1:
                    continue
                children = {}
                failed = False
                for outcome, group in groups.items():
                    subtree = solve(group, primed, missing_left, actions_left - 1)
                    if subtree is None:
                        failed = True
                        break
                    children["returned:" + outcome] = subtree
                if failed:
                    continue
                if missing_left:
                    dropout_child = solve(survivors, primed, missing_left - 1, actions_left - 1)
                    if dropout_child is None:
                        continue
                    children["dropped:no_value"] = dropout_child
            worst_observation = COST[probe] + max(c["worst_observation_cost"] for c in children.values())
            worst_impact = IMPACT[probe] + max(c["worst_intervention_cost"] for c in children.values())
            worst_actions = 1 + max(c["worst_actions"] for c in children.values())
            candidate = {"kind": "probe", "probe": probe, "children": children,
                         "worst_observation_cost": worst_observation,
                         "worst_intervention_cost": worst_impact,
                         "worst_actions": worst_actions}
            if priority == "observation_cost":
                score = (worst_observation, worst_impact, worst_actions, probe)
            else:
                score = (worst_impact, worst_observation, worst_actions, probe)
            options.append((score, candidate))
        return min(options, key=lambda pair: pair[0])[1] if options else None

    result = solve(candidates, False, dropout_budget, max_actions)
    if result is None:
        return {"status": "unresolved_within_budget", "survivors": list(candidates),
                "policy": None, "model_completeness_assumed": True,
                "worst_case_guarantee": False}
    return {"status": "identified_within_declared_finite_model", "survivors": list(candidates),
            "policy": result, "model_completeness_assumed": True,
            "dropout_bound_assumed": dropout_budget, "worst_case_guarantee": True}


def follow_policy(policy: Mapping[str, Any], law: str,
                  dropped_reads: tuple[int, ...] = ()) -> dict[str, Any]:
    """Execute a policy against a fixture. Missing reads still incur cost."""
    if law not in LAWS:
        raise ValueError("unknown law")
    node: Mapping[str, Any] = policy
    state = State()
    history = []
    read_idx = 0
    while node["kind"] == "probe":
        p = node["probe"]
        if p == "prime":
            state = apply_probe(state, p)
            key = "applied"
        else:
            missing = read_idx in dropped_reads
            read_idx += 1
            key = "dropped:no_value" if missing else "returned:" + str(response(law, state, p))
        history.append({"probe": p, "outcome": key, "state_revision": state.revision})
        if key not in node["children"]:
            raise ObservationError("observation violates declared dropout/model contract")
        node = node["children"][key]
    return {"identified": node["survivors"], "history": history,
            "intervention_applied": state.primed}


def _mac(key: bytes, value: Mapping[str, Any]) -> str:
    return hmac.new(key, canonical(value), hashlib.sha256).hexdigest()


def make_request(session: str, request_id: str, probe: str,
                 capture_revision: int) -> dict[str, Any]:
    if not session or not request_id or probe not in PROBES or probe == "prime":
        raise ObservationError("invalid observation request")
    if type(capture_revision) is not int or capture_revision < 0:
        raise ObservationError("invalid state revision")
    return {"schema": SCHEMA, "session": session, "request_id": request_id,
            "probe": probe, "capture_revision": capture_revision}


def issue_pending(request: Mapping[str, Any], *, state: State, law: str) -> tuple[dict[str, Any], int | str]:
    """The value is captured at request time but never exposed in pending evidence."""
    if state.revision != request.get("capture_revision"):
        raise ObservationError("capture revision not the actual state")
    pending = {"request": dict(request), "status": "pending", "value": None}
    return pending, response(law, state, str(request["probe"]))


def result_receipt(pending: Mapping[str, Any], *, value: int | str | None,
                   status: str, delivered_revision: int, sensor_key: bytes,
                   sensor_stamp: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if status not in {"returned", "dropped", "refused"}:
        raise ObservationError("unrecognized completion status")
    if status != "returned" and value is not None:
        raise ObservationError("a missing or refused result cannot carry a value")
    if status == "returned" and (type(value) not in (int, str)):
        raise ObservationError("a returned result must contain a typed value")
    if pending.get("status") != "pending" or pending.get("value") is not None:
        raise ObservationError("request must have a pending no-value receipt")
    if type(delivered_revision) is not int or delivered_revision < pending["request"]["capture_revision"]:
        raise ObservationError("delivery precedes capture revision")
    data = {"schema": SCHEMA, "request": pending["request"],
            "capture_digest": digest(pending), "status": status, "value": value,
            "delivery_revision": delivered_revision,
            "sensor_stamp": None if sensor_stamp is None else dict(sensor_stamp)}
    return {**data, "mac": _mac(sensor_key, data)}


def verify_receipt(request: Mapping[str, Any], pending: Mapping[str, Any],
                   receipt: Mapping[str, Any], *, sensor_key: bytes,
                   already_accepted: frozenset[str] = frozenset()) -> dict[str, Any]:
    """MAC proves fixture key possession, never external physical sensor identity."""
    if not isinstance(receipt, dict) or set(receipt) != {
            "schema", "request", "capture_digest", "status", "value",
            "delivery_revision", "sensor_stamp", "mac"}:
        raise ObservationError("malformed sensor receipt")
    if request.get("request_id") in already_accepted:
        raise ObservationError("replayed receipt")
    if (pending.get("request") != request or pending.get("status") != "pending"
            or pending.get("value") is not None or receipt["request"] != request
            or receipt["schema"] != SCHEMA or receipt["capture_digest"] != digest(pending)):
        raise ObservationError("receipt request/capture binding invalid")
    payload = {k: v for k, v in receipt.items() if k != "mac"}
    if not isinstance(receipt["mac"], str) or not hmac.compare_digest(
            receipt["mac"], _mac(sensor_key, payload)):
        raise ObservationError("invalid sensor key authentication")
    if type(receipt["delivery_revision"]) is not int or receipt["delivery_revision"] < request["capture_revision"]:
        raise ObservationError("invalid delivery revision")
    status, value = receipt["status"], receipt["value"]
    if status not in {"returned", "dropped", "refused"}:
        raise ObservationError("unknown evidence status")
    if status == "returned" and type(value) not in (int, str):
        raise ObservationError("returned value missing or invalid")
    if status != "returned" and value is not None:
        raise ObservationError("missing evidence is not a negative reading")
    return {"admitted_measurement": value if status == "returned" else None,
            "status": status, "capture_revision": request["capture_revision"],
            "delivery_revision": receipt["delivery_revision"]}


def demo() -> dict[str, Any]:
    normal = plan(dropout_budget=1)
    safe = plan(dropout_budget=1, priority="no_intervention")
    infinite = plan(dropout_budget=None)
    quiet = sampled_world("quiet")
    transient = sampled_world("transient")
    return {"schema": SCHEMA, "closed_model_assumption": True,
            "normal_policy": normal, "safe_policy": safe,
            "unbounded_dropout": infinite,
            "equal_samples_different_hidden_events":
                {"sample_coordinates": [0, 2, 4],
                 "quiet": [quiet[i] for i in (0, 2, 4)],
                 "transient": [transient[i] for i in (0, 2, 4)]},
            "sampling_assessment": assess_sampling({0: 0, 2: 0, 4: 0}),
            "physical_causal_completeness_proved": False}


if __name__ == "__main__":
    print(json.dumps(demo(), indent=2, sort_keys=True))
