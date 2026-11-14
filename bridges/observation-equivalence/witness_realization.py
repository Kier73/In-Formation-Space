"""OE-003: signer-bound finite witness execution claims, independently checked.

This module verifies signed *assertions* from receiver and authority keys trusted
by a caller. A signature does not prove a sensor was honest, an action took
place on hardware, or the ObservationPath's unsigned transport events occurred.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from costed_navigation import CostedDistinctionNavigator

PLAN_SCHEMA = "in-formation.witness-realization-plan/0.1"
RECEIPT_SCHEMA = "in-formation.witness-receiver-claim/0.1"
AUTH_SCHEMA = "in-formation.witness-authority-claim/0.1"
RESULT_SCHEMA = "in-formation.witness-realization-verdict/0.1"
DOMAIN = b"IFS-OE003-ED25519-CLAIM-v1\x00"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _text(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def _keys(obj: Any, expected: set[str], label: str) -> None:
    if not isinstance(obj, dict) or set(obj) != expected:
        raise ValueError(f"{label} has incomplete or unexpected fields")


def _scalar(value: Any) -> Any:
    if type(value) not in (str, int, bool, type(None)):
        raise ValueError("model observations must be exact JSON scalar values")
    return value


def _labels(items: Any, label: str) -> list[str]:
    if not isinstance(items, list):
        raise ValueError(f"{label} must be a list")
    names = [_text(x, label) for x in items]
    if len(names) != len(set(names)):
        raise ValueError(f"{label} must be distinct")
    return names


def _model_from_navigator(nav: CostedDistinctionNavigator) -> dict[str, Any]:
    states = [_text(x, "state") for x in nav.states]
    actions = [_text(x, "action") for x in nav.actions]
    tests = [_text(x, "test") for x in nav.tests]
    outputs = [[_scalar(x) for x in line] for line in nav._outputs]
    transitions = [[states[nav._steps[(i, a)]] for a in range(len(actions))]
                   for i in range(len(states))]
    return {"states": states, "actions": actions, "tests": tests,
            "outputs": outputs, "transitions": transitions}


def _navigator_from_model(model: Any) -> CostedDistinctionNavigator:
    _keys(model, {"states", "actions", "tests", "outputs", "transitions"}, "finite model")
    states = _labels(model["states"], "states")
    actions = _labels(model["actions"], "actions")
    tests = _labels(model["tests"], "tests")
    if not states:
        raise ValueError("finite model requires states")
    if not isinstance(model["outputs"], list) or len(model["outputs"]) != len(states):
        raise ValueError("invalid finite model observation rows")
    if not isinstance(model["transitions"], list) or len(model["transitions"]) != len(states):
        raise ValueError("invalid finite model transition rows")
    for row in model["outputs"]:
        if not isinstance(row, list) or len(row) != len(tests):
            raise ValueError("invalid observation row")
        for item in row:
            _scalar(item)
    for row in model["transitions"]:
        if not isinstance(row, list) or len(row) != len(actions):
            raise ValueError("invalid transition row")
        if any(type(item) is not str or item not in states for item in row):
            raise ValueError("successor outside declared finite universe")
    state_index = {s: i for i, s in enumerate(states)}
    action_index = {a: i for i, a in enumerate(actions)}
    test_index = {t: i for i, t in enumerate(tests)}
    return CostedDistinctionNavigator(
        states, actions, tests,
        lambda state, test: model["outputs"][state_index[state]][test_index[test]],
        lambda state, action: model["transitions"][state_index[state]][action_index[action]],
    )


def build_plan(nav: CostedDistinctionNavigator, left: str, right: str, *,
               request_id: str, source_policy_digest: str,
               action_costs: tuple[int, ...], test_costs: tuple[int, ...]) -> dict[str, Any]:
    """Build a planned-only artifact, never an executed measurement."""
    _text(request_id, "request_id")
    _text(source_policy_digest, "source_policy_digest")
    model = _model_from_navigator(nav)
    result = nav.plan_min_cost(left, right, action_costs=action_costs, test_costs=test_costs)
    if result.witness.status != "distinguished":
        raise ValueError("cannot create a separating run from an equivalent pair")
    core = {
        "schema": PLAN_SCHEMA,
        "request_id": request_id,
        "source_policy_digest": source_policy_digest,
        "model": model,
        "model_digest": digest(model),
        "initial_states": {"left": left, "right": right},
        "action_costs": list(action_costs),
        "test_costs": list(test_costs),
        "selected": {
            "actions": list(result.witness.actions),
            "test": result.witness.distinguishing_test,
            "expected": {
                "left": {"state": result.witness.left_final,
                         "value": result.witness.left_observation},
                "right": {"state": result.witness.right_final,
                          "value": result.witness.right_observation},
            },
            "estimated_total_ns": result.total_cost,
        },
        "status": "planned-not-executed",
    }
    return {**core, "plan_digest": digest(core)}


def verify_plan(plan: Any, *, expected_model_digest: str,
                expected_source_policy_digest: str) -> CostedDistinctionNavigator:
    _keys(plan, {"schema", "request_id", "source_policy_digest", "model",
                 "model_digest", "initial_states", "action_costs", "test_costs",
                 "selected", "status", "plan_digest"}, "plan")
    if plan["schema"] != PLAN_SCHEMA or plan["status"] != "planned-not-executed":
        raise ValueError("unsupported witness plan or status")
    if type(plan["model_digest"]) is not str or plan["model_digest"] != expected_model_digest:
        raise ValueError("model not receiver-pinned")
    if plan["source_policy_digest"] != expected_source_policy_digest:
        raise ValueError("cost policy not receiver-pinned")
    if digest(plan["model"]) != plan["model_digest"]:
        raise ValueError("model digest mismatch")
    if digest({key: value for key, value in plan.items() if key != "plan_digest"}) != plan["plan_digest"]:
        raise ValueError("plan digest mismatch")
    _keys(plan["initial_states"], {"left", "right"}, "initial states")
    _keys(plan["selected"], {"actions", "test", "expected", "estimated_total_ns"}, "selection")
    _keys(plan["selected"]["expected"], {"left", "right"}, "expected observations")
    _text(plan["request_id"], "request_id")
    nav = _navigator_from_model(plan["model"])
    # Reconstruct from independently supplied model bytes; not from claimed action word.
    expected = build_plan(nav, plan["initial_states"]["left"],
                          plan["initial_states"]["right"],
                          request_id=plan["request_id"],
                          source_policy_digest=plan["source_policy_digest"],
                          action_costs=tuple(plan["action_costs"]),
                          test_costs=tuple(plan["test_costs"]))
    if expected != plan:
        raise ValueError("plan does not reconstruct from pinned model and cost policy")
    return nav


def sign_claim(payload: dict[str, Any], key: Any) -> dict[str, Any]:
    """Sign a claim supplied by an external receiver/authority; no key is saved."""
    return {"payload": payload, "signature": key.sign(DOMAIN + canonical(payload)).hex()}


def verify_claim(envelope: Any, public_key: bytes) -> dict[str, Any]:
    _keys(envelope, {"payload", "signature"}, "signed envelope")
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        raise ValueError("receiver-owned public key must be 32 bytes")
    signature = envelope["signature"]
    if type(signature) is not str or len(signature) != 128:
        raise ValueError("invalid Ed25519 signature encoding")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            bytes.fromhex(signature), DOMAIN + canonical(envelope["payload"])
        )
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise ValueError("signed claim failed Ed25519 verification") from exc
    return envelope["payload"]


def _path_valid(path: Any, plan: dict[str, Any], lane: str,
                receiver_envelope: dict[str, Any], authority_envelope: dict[str, Any],
                receiver: dict[str, Any], authority: dict[str, Any]) -> None:
    _keys(path, {"attempt_id", "intent", "status", "terminal", "events"}, "observation path")
    if path["attempt_id"] != f"{plan['request_id']}:{lane}":
        raise ValueError("wrong observation attempt")
    intent = path["intent"]
    _keys(intent, {"candidate_name", "query", "hypothesis_set_digest",
                   "estimated_cost", "plan_ref", "authority_required",
                   "application_required", "sender_ack_required"}, "observation intent")
    if (intent["candidate_name"] != f"witness-terminal:{lane}"
        or intent["hypothesis_set_digest"] != plan["model_digest"]
        or intent["plan_ref"] != f"urn:sha256:{plan['plan_digest']}"
        or intent["authority_required"] is not True
        or intent["application_required"] is not False
        or intent["sender_ack_required"] is not False):
        raise ValueError("observation intent is not bound to selected plan")
    if type(intent["estimated_cost"]) not in (int, float) or intent["estimated_cost"] <= 0:
        raise ValueError("observation path cost must be positive")
    _text(intent["query"], "observation query")
    events = path["events"]
    expected_stages = ["planned", "dispatched", "admitted", "returned",
                       "evidence_authorized", "interpreted"]
    if not isinstance(events, list) or [e.get("stage") for e in events if isinstance(e, dict)] != expected_stages or len(events) != len(expected_stages):
        raise ValueError("missing, reordered or refused observation lifecycle")
    if path["status"] != "interpreted" or path["terminal"] is not False:
        raise ValueError("not an interpreted observation path")
    for e in events:
        _keys(e, {"stage", "actor", "clock_value", "clock_domain", "evidence_ref", "details"}, "path event")
        _text(e["actor"], "path actor")
        if not isinstance(e["details"], dict):
            raise ValueError("path event details must be a mapping")
    if events[0]["evidence_ref"] != intent["plan_ref"]:
        raise ValueError("planned event is not bound to selected plan")
    if events[0]["details"] != {
        "attempt_id": path["attempt_id"], "candidate_name": intent["candidate_name"],
        "query": intent["query"], "hypothesis_set_digest": intent["hypothesis_set_digest"],
        "estimated_cost": float(intent["estimated_cost"]), "plan_ref": intent["plan_ref"],
    }:
        raise ValueError("planned stage does not match intent")
    for e in events[1:4]:
        if e["details"].get("plan_digest") != plan["plan_digest"] or e["details"].get("lane") != lane:
            raise ValueError("dispatch/admission/return do not identify plan and lane")
        _text(e["evidence_ref"], "stage evidence ref")
    returned = events[3]
    if returned["details"].get("payload_digest") != digest(receiver_envelope):
        raise ValueError("returned payload not the signed receiver evidence")
    if returned["details"].get("canonicalization") != "canonical-json-v1":
        raise ValueError("wrong payload encoding")
    if returned["details"].get("encounter_id") != receiver["observation_id"]:
        raise ValueError("encounter identity mismatch")
    auth = events[4]
    info = auth["details"]
    if (info.get("decision_status") != "AUTHORIZED"
        or info.get("policy_digest") != authority["policy_digest"]
        or info.get("decision_digest") != digest(authority)
        or info.get("quorum") != 1 or info.get("strict") is not True
        or info.get("observed_sources") != [receiver["receiver_key_id"]]
        or info.get("representative_source") != receiver["receiver_key_id"]
        or info.get("dissenting_sources") != [] or info.get("missing_sources") != []):
        raise ValueError("path authorization not bound to signed decision")
    if auth["evidence_ref"] != "urn:sha256:" + digest(authority_envelope):
        raise ValueError("authority evidence reference mismatch")
    interp = events[5]
    details = interp["details"]
    if (details.get("method") != "exact-witness-terminal-v1"
        or details.get("plan_digest") != plan["plan_digest"]
        or details.get("lane") != lane
        or details.get("test") != receiver["test"]
        or type(details.get("value")) is not type(receiver["value"])
        or details.get("value") != receiver["value"]):
        raise ValueError("interpreted output not bound to signed receiver claim")
    _text(interp["evidence_ref"], "interpretation evidence ref")


def verify_realization(plan: dict[str, Any], runs: dict[str, Any], *,
                       expected_model_digest: str, expected_source_policy_digest: str,
                       expected_request_id: str, expected_authority_policy_digest: str,
                       receiver_keys: Mapping[str, bytes], authority_key: bytes) -> dict[str, Any]:
    """Verify signed claims for both sides and reconstruct their modeled traces.

    Trusted keys and expected pins are supplied independently by the receiver.
    A signer may still lie; status means claims verified, *not physical proof*.
    """
    nav = verify_plan(plan, expected_model_digest=expected_model_digest,
                      expected_source_policy_digest=expected_source_policy_digest)
    if plan["request_id"] != expected_request_id:
        raise ValueError("request was not independently pinned")
    _keys(runs, {"left", "right"}, "two-lane evidence bundle")
    if set(receiver_keys) != {"left", "right"} or receiver_keys["left"] == receiver_keys["right"]:
        raise ValueError("left/right receiver keys must be separately pinned")
    if authority_key in tuple(receiver_keys.values()):
        raise ValueError("authority key must differ from receiver keys")
    _text(expected_authority_policy_digest, "expected_authority_policy_digest")
    states = plan["model"]["states"]
    actions = plan["selected"]["actions"]
    observed: dict[str, Any] = {}
    conformant = True
    references: dict[str, str] = {}
    for lane in ("left", "right"):
        run = runs[lane]
        _keys(run, {"receiver", "authority", "path"}, "lane bundle")
        received = verify_claim(run["receiver"], receiver_keys[lane])
        _keys(received, {"schema", "request_id", "plan_digest", "lane", "receiver_key_id",
                         "observation_id", "initial_state", "steps", "test", "state", "value"}, "receiver claim")
        if (received["schema"] != RECEIPT_SCHEMA or received["plan_digest"] != plan["plan_digest"]
            or received["request_id"] != plan["request_id"] or received["lane"] != lane
            or received["initial_state"] != plan["initial_states"][lane]
            or received["test"] != plan["selected"]["test"]):
            raise ValueError("receiver claim does not identify pinned intention")
        _text(received["receiver_key_id"], "receiver_key_id")
        _text(received["observation_id"], "observation_id")
        if not isinstance(received["steps"], list) or len(received["steps"]) != len(actions):
            raise ValueError("receiver claim has missing or surplus actions")
        current = received["initial_state"]
        predicted = current
        for index, (step, action) in enumerate(zip(received["steps"], actions)):
            _keys(step, {"sequence", "action", "before", "after"}, "transition step")
            if step["sequence"] != index or step["action"] != action or step["before"] != current:
                raise ValueError("signed action sequence is discontinuous or reordered")
            if type(step["after"]) is not str or step["after"] not in states:
                raise ValueError("signed successor not in declared model")
            expected_after = states[nav._steps[(nav._index[predicted], nav.actions.index(action))]]
            if step["after"] != expected_after:
                conformant = False
            predicted = expected_after
            current = step["after"]
        if received["state"] != current:
            raise ValueError("signed terminal state is not last signed transition state")
        _scalar(received["value"])
        test = received["test"]
        expected_value = nav._outputs[nav._index[predicted]][nav.tests.index(test)]
        if (current != plan["selected"]["expected"][lane]["state"]
            or type(received["value"]) is not type(expected_value)
            or received["value"] != expected_value):
            conformant = False

        authority = verify_claim(run["authority"], authority_key)
        _keys(authority, {"schema", "request_id", "plan_digest", "lane", "decision",
                          "receiver_key_id", "receiver_envelope_digest", "policy_digest"}, "authority claim")
        if (authority["schema"] != AUTH_SCHEMA or authority["request_id"] != plan["request_id"]
            or authority["plan_digest"] != plan["plan_digest"] or authority["lane"] != lane
            or authority["decision"] != "AUTHORIZED"
            or authority["receiver_key_id"] != received["receiver_key_id"]
            or authority["receiver_envelope_digest"] != digest(run["receiver"])
            or authority["policy_digest"] != expected_authority_policy_digest):
            raise ValueError("authority signature does not authorize exact receiver claim")
        _path_valid(run["path"], plan, lane, run["receiver"], run["authority"], received, authority)
        observed[lane] = {"state": current, "value": received["value"]}
        references[lane] = digest(run["receiver"])
    if not conformant:
        status = "signed-model-mismatch"
    elif (type(observed["left"]["value"]) is type(observed["right"]["value"])
          and observed["left"]["value"] == observed["right"]["value"]):
        status = "signed-not-distinguished"
    else:
        status = "signed-witness-confirmed-within-trusted-claim-model"
    core = {
        "schema": RESULT_SCHEMA, "plan_digest": plan["plan_digest"],
        "request_id": plan["request_id"], "status": status,
        "observed": observed, "receiver_envelope_digests": references,
        "trust_scope": "pinned-Ed25519-signers-assertions-not-physical-execution-proof",
        "ground_effect": "none", "authority_effect": "none",
    }
    return {**core, "verdict_digest": digest(core)}
