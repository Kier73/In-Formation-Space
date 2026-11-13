"""RE-003: independent-process, intervention-aware observable-law reconstruction.

This is a synthetic finite deterministic research fixture, not real E-CPU
transport, host authentication, physical sensors, or a universal inference engine.
Process-local state is intentionally never included in observer records.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

MODULUS = 17
FORMAT = "in-formation.response-reconstruction/0.1"
SESSION = "re003-synthetic-fixture-v1"
HOSTS = {"A": (1, 0), "B": (2, 1)}  # raw = gain * underlying + offset
ALLOWED = {"A": frozenset({"pulse", "observe"}), "B": frozenset({"pulse", "observe", "inspect"})}
ACTION_COST = {"pulse": 1, "observe": 1, "inspect": 2}
FIELDS = frozenset({"format", "session", "host", "seq", "action", "status", "readout", "raw", "local_tick", "authority", "previous_digest", "digest"})


class EvidenceError(ValueError):
    """A received record fails its declared finite-evidence contract."""


@dataclass(frozen=True)
class Law:
    name: str
    response_gain: int
    hidden_advance: int
    extra_mode: bool = False


LAWS = {
    h.name: h for h in (
        Law("reference", 1, 1),
        Law("gain_variant", 2, 1),
        Law("hidden_variant", 1, 2),
        Law("both_variant", 2, 2),
        Law("observational_alias", 1, 1, True),
    )
}


def canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(payload: object) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def initial_state() -> tuple[int, int, int]:
    return (0, 0, 0)


def transition(law: Law, state: tuple[int, int, int], action: str) -> tuple[int, tuple[int, int, int], str]:
    """Return the visible, *pre/post* specified outcome and the new private state.

    pulse: observe x AFTER state-changing actuation.
    inspect: observe z BEFORE a state-changing inspection (+1 z).
    observe: observe x BEFORE a nonintervening read.
    """
    x, z, h = state
    if action == "pulse":
        x_new = (x + 1 + law.response_gain * z) % MODULUS
        z_new = (z + law.hidden_advance) % MODULUS
        h_new = (3 * h + 1) % MODULUS if law.extra_mode else h
        return x_new, (x_new, z_new, h_new), "x"
    if action == "inspect":
        return z, (x, (z + 1) % MODULUS, h), "z"
    if action == "observe":
        return x, state, "x"
    raise ValueError("unknown action")


def encode(host: str, value: int) -> int:
    gain, offset = HOSTS[host]
    return gain * value + offset


def make_record(*, host: str, seq: int, action: str, law: Law,
                state: tuple[int, int, int], previous_digest: str | None,
                permissions: frozenset[str], clock_origin: int) -> tuple[dict[str, Any], tuple[int, int, int]]:
    if host not in HOSTS or action not in ALLOWED[host]:
        raise ValueError("undeclared host/action")
    granted = action != "inspect" or "inspect:z" in permissions
    if not granted:
        outcome, next_state, readout, status, authority = None, state, "z", "refused", None
    else:
        value, next_state, readout = transition(law, state, action)
        outcome, status = encode(host, value), "applied" if action != "observe" else "observed"
        authority = "inspect:z" if action == "inspect" else None
    record = {
        "format": FORMAT, "session": SESSION, "host": host, "seq": seq,
        "action": action, "status": status, "readout": readout,
        "raw": outcome, "local_tick": clock_origin + (seq + 1) * (11 if host == "A" else 29),
        "authority": authority, "previous_digest": previous_digest,
    }
    record["digest"] = digest(record)
    return record, next_state


def produce(host: str, truth: str, actions: Sequence[str],
            permissions: frozenset[str] = frozenset()) -> dict[str, Any]:
    """A producer's complete private state lives only inside its process."""
    if host not in HOSTS or truth not in LAWS:
        raise ValueError("unknown host or law")
    state, records, previous = initial_state(), [], None
    for seq, action in enumerate(actions):
        rec, state = make_record(
            host=host, seq=seq, action=action, law=LAWS[truth],
            state=state, previous_digest=previous, permissions=permissions,
            clock_origin=900000 if host == "A" else -700000,
        )
        records.append(rec)
        previous = rec["digest"]
    # Not signed, and not an attestation of physical machine identity.
    return {"pid": os.getpid(), "host": host, "records": records}


def validate(records: Sequence[Mapping[str, Any]],
             authority_manifest: Mapping[str, Sequence[str]]) -> dict[str, list[dict[str, Any]]]:
    """Fail closed before using any raw value. Hashes detect accidental edits,
    not a malicious producer that can rewrite all records and hashes.
    """
    if not isinstance(records, (list, tuple)):
        raise EvidenceError("records must be a sequence")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in records:
        if not isinstance(source, dict) or set(source) != FIELDS:
            raise EvidenceError("record must have exact declared field set")
        rec = dict(source)
        if rec["format"] != FORMAT or rec["session"] != SESSION:
            raise EvidenceError("foreign schema or session")
        host, seq, action = rec["host"], rec["seq"], rec["action"]
        if host not in HOSTS or action not in ALLOWED[host]:
            raise EvidenceError("foreign host or action")
        if type(seq) is not int or seq < 0 or type(rec["local_tick"]) is not int:
            raise EvidenceError("invalid local sequence or tick")
        if type(rec["digest"]) is not str or len(rec["digest"]) != 64:
            raise EvidenceError("malformed record digest")
        if digest({k: v for k, v in rec.items() if k != "digest"}) != rec["digest"]:
            raise EvidenceError("changed record payload")
        expected_readout = "z" if action == "inspect" else "x"
        if rec["readout"] != expected_readout:
            raise EvidenceError("incorrect readout label")
        granted = action != "inspect" or "inspect:z" in authority_manifest.get(host, ())
        if action == "inspect" and not granted:
            if rec["status"] != "refused" or rec["raw"] is not None or rec["authority"] is not None:
                raise EvidenceError("unauthorized inspection claimed as evidence")
        else:
            expected_status = "observed" if action == "observe" else "applied"
            if rec["status"] != expected_status:
                raise EvidenceError("status does not match action")
            if rec["authority"] != ("inspect:z" if action == "inspect" else None):
                raise EvidenceError("authority descriptor mismatch")
            if type(rec["raw"]) is not int or rec["raw"] not in [encode(host, i) for i in range(MODULUS)]:
                raise EvidenceError("raw observation outside the calibrated finite domain")
        grouped[host].append(rec)
    for host, chain in grouped.items():
        chain.sort(key=lambda x: x["seq"])
        previous, last_tick = None, None
        for position, rec in enumerate(chain):
            if rec["seq"] != position or rec["previous_digest"] != previous:
                raise EvidenceError("missing, reordered or substituted host-chain event")
            if last_tick is not None and rec["local_tick"] <= last_tick:
                raise EvidenceError("host-local clock regressed")
            previous, last_tick = rec["digest"], rec["local_tick"]
    return dict(grouped)


def reconstruct(records: Sequence[dict[str, Any]],
                authority_manifest: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """Reconstruct the compatible generator names and private predicted states.

    Each host's history is replayed separately; cross-host wall/tick ordering
    and any undocumented causal edge are intentionally never inferred.
    """
    grouped = validate(records, authority_manifest)
    survivors, rejected = [], {}
    for name, law in sorted(LAWS.items()):
        first_mismatch = None
        for host, chain in sorted(grouped.items()):
            state = initial_state()
            for rec in chain:
                if rec["status"] == "refused":
                    continue  # Refusal is neither a negative measurement nor an intervention.
                predicted, state, readout = transition(law, state, rec["action"])
                actual = encode(host, predicted)
                if actual != rec["raw"]:
                    first_mismatch = {"host": host, "seq": rec["seq"], "action": rec["action"],
                                      "predicted": actual, "observed": rec["raw"]}
                    break
            if first_mismatch:
                break
        if first_mismatch:
            rejected[name] = first_mismatch
        else:
            survivors.append(name)
    return {
        "schema": "re003-reconstruction/v1", "survivors": survivors,
        "status": "singleton_within_catalogue" if len(survivors) == 1 else (
            "unresolved_equivalence_class" if survivors else "no_candidate_fits"),
        "rejected": rejected,
        "per_host_event_count": {host: len(chain) for host, chain in sorted(grouped.items())},
        "inference_scope": "finite declared models, exact synthetic transitions, host-local chains",
        "global_event_order": None,
    }


def prospective_outputs(law: Law, actions: Sequence[str], host: str) -> tuple[int, ...]:
    state, out = initial_state(), []
    for action in actions:
        y, state, _ = transition(law, state, action)
        out.append(encode(host, y))
    return tuple(out)


def select_active_sequence(survivors: Sequence[str], host: str = "B",
                           permits: frozenset[str] = frozenset({"inspect:z"}),
                           max_steps: int = 2) -> dict[str, Any]:
    """Bounded, future-state-aware discriminating-sequence search.

    Decisions assume a host with a fresh known initial state. This is a
    deterministic catalogue search, not a globally optimal contingent policy.
    """
    if host not in HOSTS or max_steps < 1:
        raise ValueError("unsupported planning context")
    unique = sorted(set(survivors))
    if not unique or any(k not in LAWS for k in unique):
        raise ValueError("candidate set must be nonempty and declared")
    actions = tuple(a for a in ("pulse", "inspect", "observe") if a in ALLOWED[host]
                    and (a != "inspect" or "inspect:z" in permits))
    best = None
    for depth in range(1, max_steps + 1):
        for sequence in itertools.product(actions, repeat=depth):
            families: dict[tuple[int, ...], list[str]] = defaultdict(list)
            for name in unique:
                families[prospective_outputs(LAWS[name], sequence, host)].append(name)
            groups = tuple(sorted(tuple(sorted(g)) for g in families.values()))
            if len(groups) == 1:
                continue
            cost = sum(ACTION_COST[a] for a in sequence)
            key = (max(len(g) for g in groups), cost, depth, sequence)
            if best is None or key < best[0]:
                best = (key, sequence, groups)
    if best is None:
        return {"status": "no_discriminating_sequence_within_scope", "actions": [],
                "partitions": [unique]}
    _, sequence, groups = best
    return {"status": "discriminating_sequence_found", "actions": list(sequence),
            "partitions": [list(g) for g in groups]}


def call_host(host: str, truth: str, actions: Sequence[str],
              permissions: Sequence[str] = ()) -> dict[str, Any]:
    """Use an actual OS subprocess with independent private memory and PID."""
    request = {"host": host, "truth": truth, "actions": list(actions),
               "permissions": list(permissions)}
    child = subprocess.run([sys.executable, os.path.abspath(__file__), "--host"],
                           input=json.dumps(request), capture_output=True, text=True, check=True)
    return json.loads(child.stdout)


def call_verifier(records: Sequence[dict[str, Any]], grants: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    child = subprocess.run([sys.executable, os.path.abspath(__file__), "--verify"],
                           input=json.dumps({"records": records, "grants": grants}),
                           capture_output=True, text=True, check=True)
    return json.loads(child.stdout)


def noninvasive_counterfactual(law: Law, actions: Sequence[str], host: str) -> list[int]:
    """Incorrect model for an intervention: inspect reports z but does not mutate it."""
    state, out = initial_state(), []
    for action in actions:
        value, updated, _ = transition(law, state, action)
        out.append(encode(host, value))
        state = state if action == "inspect" else updated
    return out


def run_encounter(truth: str = "gain_variant", *, grant_inspection: bool = True) -> dict[str, Any]:
    """Two independently evolving observer processes plus a verifier process."""
    a = call_host("A", truth, ("pulse", "pulse"))
    partial = call_verifier(a["records"], {})
    plan = select_active_sequence(partial["survivors"], permits=frozenset({"inspect:z"})
                                  if grant_inspection else frozenset())
    # The selected inspect-then-pulse probe itself distinguishes interventions:
    # the inspect result is identical, but its state change affects the pulse.
    actions = plan["actions"]
    # For the refusal run, attempt the same justified inspect despite denied
    # authority, preserving a refusal record without inferring a measurement.
    if not grant_inspection:
        actions = ["pulse", "inspect", "pulse"]
    b = call_host("B", truth, actions, ("inspect:z",) if grant_inspection else ())
    grants = {"B": ["inspect:z"]} if grant_inspection else {}
    shuffled = list(reversed(a["records"] + b["records"]))
    host_B_alone = call_verifier(b["records"], grants)
    combined = call_verifier(shuffled, grants)
    return {
        "scenario": truth, "inspection_granted": grant_inspection,
        "different_process_ids": a["pid"] != b["pid"],
        "producer_process_ids": {"A": a["pid"], "B": b["pid"]},
        "initial_host_A_survivors": partial["survivors"],
        "host_B_alone_survivors": host_B_alone["survivors"],
        "selected_host_B_probe": plan,
        "host_A_raw": [r["raw"] for r in a["records"]],
        "host_B_actions": actions,
        "host_B_raw": [r["raw"] for r in b["records"]],
        "host_B_statuses": [r["status"] for r in b["records"]],
        "host_A_local_ticks": [r["local_tick"] for r in a["records"]],
        "host_B_local_ticks": [r["local_tick"] for r in b["records"]],
        "independent_verifier": combined,
        "noninvasive_inspection_counterfactual": (
            noninvasive_counterfactual(LAWS[truth], actions, "B")
            if "inspect" in actions and grant_inspection else None),
    }


def report() -> dict[str, Any]:
    runs = [run_encounter("gain_variant"), run_encounter("gain_variant", grant_inspection=False),
            run_encounter("reference"), run_encounter("observational_alias")]
    for run in runs:
        # PID data is evidence of local process separation but makes the
        # archive report nondeterministic; omit it from the stored report.
        del run["producer_process_ids"]
    return {
        "experiment": "RE-003", "schema": FORMAT,
        "status": "exact synthetic fixture with independent localhost processes",
        "claims_not_made": ["physical host independence", "authenticated producers",
                            "real E-CPU or VGI runtime admission", "universal law recovery",
                            "distributed wall-clock synchronization"],
        "encounters": runs,
    }


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--host":
        request = json.load(sys.stdin)
        print(json.dumps(produce(request["host"], request["truth"], request["actions"],
                                 frozenset(request["permissions"]))))
    elif len(sys.argv) == 2 and sys.argv[1] == "--verify":
        request = json.load(sys.stdin)
        print(json.dumps(reconstruct(request["records"], request["grants"])))
    elif len(sys.argv) == 1:
        print(json.dumps(report(), indent=2, sort_keys=True))
    else:
        raise SystemExit("usage: python multi_host_reconstruction.py [--host|--verify]")


if __name__ == "__main__":
    main()
