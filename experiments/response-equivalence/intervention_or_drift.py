"""RE-004: intervention-effect versus unobserved external evolution.

Exact finite-state synthetic fixture, not a physics sensor, authenticated host,
E-CPU transport, or proof of causal source attribution. The linked handoff
carries a digest commitment, not independent evidence of physical continuity.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SCHEMA = "in-formation.response-re004/0.1"
SESSION = "re004-controlled-generator-v1"
MOD = 31
# Different observer-local scales and offsets. No valid cross-host time subtraction.
CALIBRATION = {"A": (1, 0), "B": (3, 2)}
GRANTS = {"witness": "environment:read", "isolated_apply": "external:isolate"}
A_ACTIONS = ("apply", "idle")
B_ACTIONS = ("witness", "isolated_apply", "read")
RECORD_FIELDS = frozenset(("schema", "session", "actor", "sequence", "action", "status",
                           "raw", "readout", "local_tick", "handoff_digest", "parent",
                           "digest"))


class EvidenceError(ValueError):
    """A record, handoff or authority claim is inconsistent with its contract."""


@dataclass(frozen=True)
class Law:
    name: str
    action_gain: int
    autonomous_per_interval: int
    external_on_action: int
    private_alias: bool = False


LAWS = {law.name: law for law in (
    Law("high_gain", 2, 0, 0),
    Law("triggered_external", 1, 0, 1),
    Law("ambient_external", 1, 1, 0),
    Law("low_gain", 1, 0, 0),
    Law("coordinate_alias", 2, 0, 0, True),
)}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def initial_state() -> tuple[int, int, int]:
    return 0, 0, 0  # visible state, external-event counter, invisible alias state


def transition(law: Law, state: tuple[int, int, int], action: str) -> tuple[int, tuple[int, int, int], str]:
    """State changes are declared independently of the outcome observation.

    'apply' measures x after a command and a declared interval of possible drift.
    'idle' is the no-command control with the same declared interval.
    'witness' measures an accumulated external-event channel; it doesn't cause it.
    'isolated_apply' is a *model-assumed* block of external events, not proven isolation.
    """
    x, events, alias = state
    if action == "apply":
        spontaneous = law.autonomous_per_interval + law.external_on_action
        x = (x + law.action_gain + spontaneous) % MOD
        events = (events + spontaneous) % MOD
    elif action == "idle":
        x = (x + law.autonomous_per_interval) % MOD
        events = (events + law.autonomous_per_interval) % MOD
    elif action == "isolated_apply":
        x = (x + law.action_gain) % MOD
    elif action == "read":
        pass
    elif action == "witness":
        return events, state, "external_events"
    else:
        raise ValueError("unknown probe")
    alias = (alias * 5 + 1) % MOD if law.private_alias else alias
    return x, (x, events, alias), "x"


def raw_from(actor: str, value: int) -> int:
    gain, offset = CALIBRATION[actor]
    return gain * value + offset


def _record(actor: str, sequence: int, action: str, *, status: str,
            raw: int | None, readout: str, parent: str | None,
            handoff_digest: str | None) -> dict[str, Any]:
    record = {
        "schema": SCHEMA, "session": SESSION, "actor": actor,
        "sequence": sequence, "action": action, "status": status,
        "raw": raw, "readout": readout,
        "local_tick": (40000 + 17 * sequence) if actor == "A" else (-250000 + 37 * sequence),
        "handoff_digest": handoff_digest, "parent": parent,
    }
    record["digest"] = digest(record)
    return record


def produce_a(truth: str) -> dict[str, Any]:
    if truth not in LAWS:
        raise ValueError("unknown truth")
    state, chain, previous = initial_state(), [], None
    for k, action in enumerate(A_ACTIONS):
        value, state, readout = transition(LAWS[truth], state, action)
        rec = _record("A", k, action, status="applied" if action == "apply" else "observed",
                      raw=raw_from("A", value), readout=readout,
                      parent=previous, handoff_digest=None)
        chain.append(rec)
        previous = rec["digest"]
    nonce = secrets.token_hex(32)
    handoff = {"schema": SCHEMA, "session": SESSION, "from_actor": "A", "to_actor": "B",
               "source_head": chain[-1]["digest"],
               "checkpoint_digest": digest({"private_checkpoint": state, "secret_nonce": nonce})}
    handoff["digest"] = digest(handoff)
    # State remains private to the two producing processes, outside their records.
    # The secret random nonce keeps the tiny finite state from being trivially
    # recovered by public dictionary lookup. This is not producer attestation.
    return {"pid": os.getpid(), "records": chain, "handoff": handoff,
            "private_checkpoint": list(state), "private_nonce": nonce}


def produce_b(truth: str, handoff: Mapping[str, Any], private_checkpoint: Sequence[int],
              private_nonce: str, actions: Sequence[str], permits: Sequence[str] = ()) -> dict[str, Any]:
    if truth not in LAWS or len(private_checkpoint) != 3 or not all(type(v) is int for v in private_checkpoint):
        raise ValueError("unknown truth or malformed private checkpoint")
    if digest({"private_checkpoint": tuple(private_checkpoint), "secret_nonce": private_nonce}) != handoff.get("checkpoint_digest"):
        raise EvidenceError("checkpoint bytes fail handoff commitment")
    if handoff.get("schema") != SCHEMA or handoff.get("session") != SESSION or handoff.get("to_actor") != "B":
        raise EvidenceError("invalid handoff identity")
    if digest({k: v for k, v in handoff.items() if k != "digest"}) != handoff.get("digest"):
        raise EvidenceError("changed handoff")
    state, previous, chain = tuple(private_checkpoint), None, []
    for k, action in enumerate(actions):
        if action not in B_ACTIONS:
            raise ValueError("undeclared host B action")
        required = GRANTS.get(action)
        if required and required not in permits:
            status, raw, readout = "refused", None, "external_events" if action == "witness" else "x"
        else:
            value, state, readout = transition(LAWS[truth], state, action)
            raw = raw_from("B", value)
            status = "observed" if action in ("read", "witness") else "applied"
        rec = _record("B", k, action, status=status, raw=raw,
                      readout=readout, parent=previous, handoff_digest=handoff["digest"])
        chain.append(rec)
        previous = rec["digest"]
    return {"pid": os.getpid(), "records": chain, "acknowledged_handoff": handoff["digest"]}


def _valid_chain(records: Sequence[dict[str, Any]], actor: str, handoff_digest: str | None,
                 permits: frozenset[str]) -> None:
    previous, last_tick = None, None
    expected_actions = A_ACTIONS if actor == "A" else B_ACTIONS
    for index, rec in enumerate(records):
        if not isinstance(rec, dict) or set(rec) != RECORD_FIELDS:
            raise EvidenceError("invalid record fields")
        if (rec["schema"] != SCHEMA or rec["session"] != SESSION or rec["actor"] != actor
                or type(rec["sequence"]) is not int or rec["sequence"] != index
                or rec["action"] not in expected_actions or rec["parent"] != previous
                or rec["handoff_digest"] != handoff_digest):
            raise EvidenceError("record identity, continuity or action contract invalid")
        if actor == "A" and rec["action"] != A_ACTIONS[index]:
            raise EvidenceError("host A control schedule changed")
        if type(rec["local_tick"]) is not int or (last_tick is not None and rec["local_tick"] <= last_tick):
            raise EvidenceError("local clock invalid")
        if not isinstance(rec["digest"], str) or digest({k: v for k, v in rec.items() if k != "digest"}) != rec["digest"]:
            raise EvidenceError("record digest mismatch")
        expected_readout = "external_events" if rec["action"] == "witness" else "x"
        if rec["readout"] != expected_readout:
            raise EvidenceError("wrong readout")
        required = GRANTS.get(rec["action"])
        denied = required is not None and required not in permits
        expected_status = "refused" if denied else (
            "observed" if rec["action"] in ("idle", "read", "witness") else "applied")
        if rec["status"] != expected_status:
            raise EvidenceError("unadmitted observation or actuation")
        if denied:
            if rec["raw"] is not None:
                raise EvidenceError("refusal cannot carry a measurement")
        elif type(rec["raw"]) is not int or rec["raw"] not in {raw_from(actor, x) for x in range(MOD)}:
            raise EvidenceError("invalid calibrated measurement")
        previous, last_tick = rec["digest"], rec["local_tick"]


def validate(a: Sequence[dict[str, Any]], b: Sequence[dict[str, Any]],
             handoff: Mapping[str, Any], permits: frozenset[str]) -> None:
    if not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple)) or len(a) != len(A_ACTIONS):
        raise EvidenceError("missing host A evidence")
    if not isinstance(handoff, dict) or set(handoff) != {
        "schema", "session", "from_actor", "to_actor", "source_head", "checkpoint_digest", "digest"
    }:
        raise EvidenceError("malformed handoff")
    if handoff["schema"] != SCHEMA or handoff["session"] != SESSION or handoff["from_actor"] != "A" or handoff["to_actor"] != "B":
        raise EvidenceError("foreign handoff")
    if not isinstance(handoff["checkpoint_digest"], str) or len(handoff["checkpoint_digest"]) != 64:
        raise EvidenceError("invalid checkpoint commitment")
    if digest({k: v for k, v in handoff.items() if k != "digest"}) != handoff["digest"]:
        raise EvidenceError("changed handoff digest")
    _valid_chain(a, "A", None, frozenset())
    if a[-1]["digest"] != handoff["source_head"]:
        raise EvidenceError("source head disconnected from handoff")
    _valid_chain(b, "B", handoff["digest"], permits)


def reconstruct(a: Sequence[dict[str, Any]], b: Sequence[dict[str, Any]],
                handoff: Mapping[str, Any], permits: frozenset[str] = frozenset()) -> dict[str, Any]:
    validate(a, b, handoff, permits)
    survivors, rejected = [], {}
    for name, law in sorted(LAWS.items()):
        state, mismatch = initial_state(), None
        for record in list(a) + list(b):
            if record["status"] == "refused":
                continue
            value, state, readout = transition(law, state, record["action"])
            predicted = raw_from(record["actor"], value)
            if predicted != record["raw"]:
                mismatch = {"actor": record["actor"], "sequence": record["sequence"],
                            "action": record["action"], "predicted": predicted, "observed": record["raw"]}
                break
        if mismatch:
            rejected[name] = mismatch
        else:
            survivors.append(name)
    return {
        "schema": "in-formation.re004-reconstruction/1",
        "survivors": survivors,
        "status": "singleton_within_catalogue" if len(survivors) == 1 else (
            "unresolved_equivalence_class" if survivors else "no_candidate_fits"),
        "rejected": rejected, "global_elapsed": None, "physical_source_attribution": None,
        "causal_scope": "explicit A-head-to-B-handoff dependency only; no inferred external event causality",
        "evidence_scope": "unkeyed digests and synthetic permitted transitions; not host authentication",
    }


def subprocess_host(flag: str, request: object) -> dict[str, Any]:
    child = subprocess.run([sys.executable, os.path.abspath(__file__), flag],
                           input=json.dumps(request), capture_output=True, text=True, check=True)
    return json.loads(child.stdout)


def run(truth: str = "triggered_external", *, b_actions: Sequence[str] = ("witness",),
        grants: frozenset[str] = frozenset({"environment:read"})) -> dict[str, Any]:
    a = subprocess_host("--host-a", {"truth": truth})
    b = subprocess_host("--host-b", {"truth": truth, "handoff": a["handoff"],
                                      "private_checkpoint": a["private_checkpoint"],
                                      "private_nonce": a["private_nonce"], "actions": list(b_actions), "grants": sorted(grants)})
    report = subprocess_host("--verify", {"a": a["records"], "b": b["records"],
                                            "handoff": a["handoff"], "grants": sorted(grants)})
    a_only = reconstruct(a["records"], [], a["handoff"])
    return {"truth_fixture": truth,
            "a_only_survivors": a_only["survivors"],
            "b_actions": list(b_actions), "b_outcomes": [r["raw"] for r in b["records"]],
            "b_status": [r["status"] for r in b["records"]],
            "combined": report, "separate_producer_pids": a["pid"] != b["pid"]}


def report() -> dict[str, Any]:
    fixtures = (
        run("triggered_external"),
        run("triggered_external", grants=frozenset()),
        run("high_gain"),
        run("triggered_external", b_actions=("isolated_apply",), grants=frozenset({"external:isolate"})),
        run("ambient_external"),
    )
    return {"experiment": "RE-004", "schema": SCHEMA, "host_separation": "local OS processes",
            "results": [{k: v for k, v in fixture.items() if k != "separate_producer_pids"} for fixture in fixtures],
            "not_established": ["universal causal attribution", "source event authentication",
                                "physical host independence", "real interference-free isolation",
                                "distributed consensus", "shared wall or monotonic clock"]}


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--host-a":
        print(json.dumps(produce_a(json.load(sys.stdin)["truth"])))
    elif len(sys.argv) == 2 and sys.argv[1] == "--host-b":
        req = json.load(sys.stdin)
        print(json.dumps(produce_b(req["truth"], req["handoff"], req["private_checkpoint"],
                                   req["private_nonce"], req["actions"], req.get("grants", []))))
    elif len(sys.argv) == 2 and sys.argv[1] == "--verify":
        req = json.load(sys.stdin)
        print(json.dumps(reconstruct(req["a"], req["b"], req["handoff"], frozenset(req["grants"]))))
    elif len(sys.argv) == 1:
        print(json.dumps(report(), sort_keys=True, indent=2))
    else:
        raise SystemExit("usage: intervention_or_drift.py [--host-a|--host-b|--verify]")


if __name__ == "__main__":
    main()
