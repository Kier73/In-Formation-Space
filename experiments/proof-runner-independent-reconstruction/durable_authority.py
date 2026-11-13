"""SQLite-backed route-authority experiment with real process restart phases.

This module deliberately reuses bridges/proof-attention/sqlite_route_epoch_store.py.
The SQLite adapter is a local, single-host CAS authority; it is not a multi-host
consensus service. The producer runs open, resume/claim, and stale-token replay
in separate operating-system processes, then exports the database and revision
history for independent reconstruction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
PROOF_ATTENTION = ROOT / "bridges" / "proof-attention"
ECPU = ROOT / "external" / "E-CPU"
for item in (str(PROOF_ATTENTION), str(ECPU)):
    if item not in sys.path:
        sys.path.insert(0, item)

from formats.canonical_metadata_v1 import canonical_bytes, canonical_digest, decode_canonical_document


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(dict(value)) + b"\n")


def _read(path: Path) -> dict[str, Any]:
    return decode_canonical_document(path.read_bytes())


def _digest(value: Any) -> str:
    return canonical_digest(value)


def _process_record(
    phase: str,
    *,
    events: list[str],
    revision: int,
    decision: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "process_id": os.getpid(),
        "process_instance_id": str(uuid.uuid4()),
        "event_digests": list(events),
        "observed_store_revision": revision,
        "decision": decision,
    }


def _route(
    run_id: str,
    *,
    fixture: bool = False,
) -> dict[str, Any]:
    suffix = "fixture" if fixture else run_id
    return {
        "host_id": f"proof-host-{suffix}",
        "worker_id": f"proof-worker-{suffix}",
        "request_channel": f"proof-request-{suffix}",
        "result_channel": f"proof-result-{suffix}",
        "policy": {"lease_ticks": 3, "max_attempts": 4, "window_size": 8},
    }


def _request(run_id: str, *, fixture: bool = False) -> dict[str, Any]:
    suffix = "fixture" if fixture else run_id
    core = {
        "format": "in-formation.proof-action-request/0.1",
        "attempt_id": f"proof-run:{suffix}:000001",
        "query_label": "establish identity",
        "plan_digest": "1" * 64,
        "proof_ground_digest": "2" * 64,
        "candidate_transition": {
            "transition_id": "transition-identity",
            "source_id": "obligation-root",
            "tactic": "rfl",
            "proposed_subgoal_ids": [],
        },
    }
    return {**core, "request_digest": _digest(core)}


def _load_types():
    try:
        from proof_action_route_epoch import ProofActionRouteEpochLedger
        from sqlite_route_epoch_store import SQLiteRouteEpochLedgerStore
    except ImportError as exc:
        raise RuntimeError(
            "proof-attention and the pinned E-CPU checkout must be on PYTHONPATH"
        ) from exc
    return ProofActionRouteEpochLedger, SQLiteRouteEpochLedgerStore


def _phase_init(args: argparse.Namespace) -> None:
    Ledger, Store = _load_types()
    store = Store(args.database)
    ledger = Ledger(store=store)
    event = ledger.open_epoch(
        args.epoch_id,
        _read(Path(args.route)),
        owner_id=args.initial_owner,
    )
    _write(
        Path(args.phase_output),
        _process_record(
            "initial_open",
            events=[event["event_digest"]],
            revision=len(store.revision_history()),
            decision="opened",
        ),
    )


def _phase_resume(args: argparse.Namespace) -> None:
    Ledger, Store = _load_types()
    store = Store(args.database)
    ledger = Ledger(store=store)
    active = ledger.active_epoch
    if active is None or active["epoch_id"] != args.epoch_id:
        raise RuntimeError("resumed process did not recover the active route epoch")
    if active["owner_id"] != args.initial_owner or active["owner_generation"] != 1:
        raise RuntimeError("resumed process observed unexpected pre-restart ownership")

    claim = ledger.claim_epoch(
        args.epoch_id,
        owner_id=args.replacement_owner,
        expected_owner_id=args.initial_owner,
        expected_owner_generation=1,
    )
    request = _read(Path(args.request))
    active = ledger.active_epoch
    admitted = ledger.record_request_admission(
        args.epoch_id,
        active["route_digest"],
        owner_id=args.replacement_owner,
        owner_generation=active["owner_generation"],
        request_sequence=1,
        attempt_id=request["attempt_id"],
        request_digest=request["request_digest"],
    )
    if not admitted:
        raise RuntimeError("replacement owner could not durably admit the request")
    execution_id = ledger.record_execution_authorization(
        args.epoch_id,
        active["route_digest"],
        owner_id=args.replacement_owner,
        owner_generation=active["owner_generation"],
        attempt_id=request["attempt_id"],
        request_digest=request["request_digest"],
        runner_id=args.runner_id,
    )
    if not execution_id:
        raise RuntimeError("replacement owner could not authorize the runner")

    reopened_store = Store(args.database)
    reopened_document = reopened_store.load()
    reopened_ledger = Ledger.from_dict(reopened_document, store=reopened_store)
    if reopened_ledger.active_epoch["owner_generation"] != 2:
        raise RuntimeError("fresh SQLite adapter did not recover owner generation two")
    if reopened_ledger.active_epoch["owner_id"] != args.replacement_owner:
        raise RuntimeError("fresh SQLite adapter did not recover the replacement owner")

    events = [claim["event_digest"]]
    events.extend(
        event["event_digest"]
        for event in reopened_ledger.entries
        if event["event_type"] in ("admitted", "execution_authorized")
    )
    _write(
        Path(args.phase_output),
        _process_record(
            "restart_claim_admit_authorize",
            events=events,
            revision=len(reopened_store.revision_history()),
            decision="replacement_owner_authorized",
        ),
    )


def _phase_stale_replay(args: argparse.Namespace) -> None:
    Ledger, Store = _load_types()
    store = Store(args.database)
    ledger = Ledger(store=store)
    active = ledger.active_epoch
    if active is None or active["owner_generation"] != 2:
        raise RuntimeError("stale replay process did not observe replacement ownership")
    request = _read(Path(args.request))
    accepted = ledger.record_request_admission(
        args.epoch_id,
        active["route_digest"],
        owner_id=args.initial_owner,
        owner_generation=1,
        request_sequence=2,
        attempt_id=f"{request['attempt_id']}:stale-replay",
        request_digest=request["request_digest"],
    )
    if accepted:
        raise RuntimeError("stale owner token was accepted after process restart")
    reopened_store = Store(args.database)
    reopened_ledger = Ledger.from_dict(
        reopened_store.load(),
        store=reopened_store,
    )
    if any(
        event["event_type"] == "admitted"
        and event["details"]["attempt_id"].endswith(":stale-replay")
        for event in reopened_ledger.entries
    ):
        raise RuntimeError("stale owner attempt appeared in the authoritative ledger")
    _write(
        Path(args.phase_output),
        _process_record(
            "stale_generation_replay",
            events=[],
            revision=len(reopened_store.revision_history()),
            decision="rejected",
        )
        | {
            "stale_attempt_id": f"{request['attempt_id']}:stale-replay",
            "accepted": False,
            "observed_owner_id": reopened_ledger.active_epoch["owner_id"],
            "observed_owner_generation": reopened_ledger.active_epoch["owner_generation"],
        },
    )


def _run_phase(arguments: list[str], env: Mapping[str, str]) -> None:
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=dict(env),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "authority child phase failed "
            f"({arguments[0]}, exit={completed.returncode})\\n"
            f"stdout:\\n{completed.stdout}\\n"
            f"stderr:\\n{completed.stderr}"
        )
    if completed.stdout.strip():
        print(completed.stdout.strip())


def build_sqlite_authority_bundle(
    out_dir: Path,
    *,
    run_id: str,
    runner_id: str,
) -> dict[str, Any]:
    """Create a genuine SQLite authority history across three fresh Python processes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    database = out_dir / "authority-store.sqlite3"
    route_path = out_dir / "route.json"
    request_path = out_dir / "request.json"
    request = _request(run_id)
    route = _route(run_id)
    epoch_id = f"proof-route-epoch-{run_id}"
    initial_owner = f"route-owner-{run_id}-process-1"
    replacement_owner = f"route-owner-{run_id}-process-2"
    _write(route_path, route)
    _write(request_path, request)

    env = os.environ.copy()
    extra_paths = [
        str(PROOF_ATTENTION),
        str(ECPU),
        str(ROOT),
    ]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(extra_paths + ([existing] if existing else []))

    phases = [
        out_dir / "phase-initial-open.json",
        out_dir / "phase-restart-claim.json",
        out_dir / "phase-stale-replay.json",
    ]
    _run_phase(
        [
            "init",
            "--database", str(database),
            "--route", str(route_path),
            "--epoch-id", epoch_id,
            "--initial-owner", initial_owner,
            "--phase-output", str(phases[0]),
        ],
        env,
    )
    _run_phase(
        [
            "resume",
            "--database", str(database),
            "--route", str(route_path),
            "--request", str(request_path),
            "--epoch-id", epoch_id,
            "--initial-owner", initial_owner,
            "--replacement-owner", replacement_owner,
            "--runner-id", runner_id,
            "--phase-output", str(phases[1]),
        ],
        env,
    )
    _run_phase(
        [
            "stale-replay",
            "--database", str(database),
            "--request", str(request_path),
            "--epoch-id", epoch_id,
            "--initial-owner", initial_owner,
            "--phase-output", str(phases[2]),
        ],
        env,
    )

    Ledger, Store = _load_types()
    store = Store(database)
    document = store.load()
    if document is None:
        raise RuntimeError("SQLite authority did not retain a ledger document")
    ledger = Ledger.from_dict(document, store=store)
    history = list(store.revision_history())
    process_phases = [_read(path) for path in phases]
    process_ids = [item["process_instance_id"] for item in process_phases]
    if len(process_ids) != len(set(process_ids)):
        raise RuntimeError("authority phase process instance IDs are not unique")
    if [item["phase"] for item in process_phases] != [
        "initial_open",
        "restart_claim_admit_authorize",
        "stale_generation_replay",
    ]:
        raise RuntimeError("authority process phases are incomplete or reordered")
    stale = process_phases[-1]
    if stale["accepted"] is not False or stale["observed_owner_generation"] != 2:
        raise RuntimeError("stale owner replay was not rejected under generation two")

    # Ensure a self-contained database file can cross the artifact boundary.
    connection = sqlite3.connect(str(database))
    try:
        result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if result is not None and int(result[0]) != 0:
            raise RuntimeError("SQLite WAL checkpoint reported a busy database")
    finally:
        connection.close()

    bundle = {
        "ledger": document,
        "request": request,
        "history": history,
        "process_evidence": {
            "format": "in-formation.proof-runner-authority-process-evidence/0.1",
            "authority_store_type": "sqlite-local-file",
            "authority_process_count": 3,
            "phases": process_phases,
            "final_store_revision": len(history),
            "final_ledger_digest": document["ledger_digest"],
            "stale_owner_attempt_rejected": True,
        },
        "stale_owner_attempt": stale,
        "database_path": database,
        "database_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "store_revision_count": len(history),
        "active_epoch": ledger.active_epoch,
    }
    _write(out_dir / "route-ledger.json", bundle["ledger"])
    _write(out_dir / "request.json", bundle["request"])
    _write(out_dir / "store-history.json", {"entries": bundle["history"]})
    _write(out_dir / "process-evidence.json", bundle["process_evidence"])
    _write(out_dir / "stale-owner-attempt.json", bundle["stale_owner_attempt"])
    _write(
        out_dir / "store-summary.json",
        {
            "store_type": "sqlite-local-file",
            "database_sha256": bundle["database_sha256"],
            "history_digest": _digest(bundle["history"]),
            "revision_count": bundle["store_revision_count"],
            "ledger_digest": document["ledger_digest"],
            "stale_owner_attempt_rejected": True,
        },
    )
    return bundle


def validate_revision_history(
    ledger: Mapping[str, Any],
    history: list[Mapping[str, Any]],
) -> None:
    """Recompute every intermediate ledger-prefix digest from SQLite audit deltas."""
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not isinstance(history, list) or not history:
        raise ValueError("SQLite history and route ledger must be non-empty")
    event_offset = 0
    previous_ledger_digest: str | None = None
    for expected_revision, row in enumerate(history, 1):
        required = {
            "revision", "previous_ledger_digest", "ledger_digest", "actor_id",
            "appended_event_digests", "committed_utc",
        }
        if set(row) != required:
            raise ValueError(f"SQLite revision {expected_revision} fields are invalid")
        if type(row["revision"]) is not int or row["revision"] != expected_revision:
            raise ValueError("SQLite revision sequence is not contiguous")
        if row["previous_ledger_digest"] != previous_ledger_digest:
            raise ValueError("SQLite revision predecessor digest mismatch")
        actor = row["actor_id"]
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("SQLite revision actor ID is invalid")
        committed = row["committed_utc"]
        if not isinstance(committed, str) or not committed:
            raise ValueError("SQLite revision commit marker is invalid")
        appended = row["appended_event_digests"]
        if not isinstance(appended, list) or not appended:
            raise ValueError("SQLite revision must append one or more event digests")
        end_offset = event_offset + len(appended)
        if end_offset > len(entries):
            raise ValueError("SQLite revision appends beyond the route ledger")
        batch = entries[event_offset:end_offset]
        actual_digests = [event.get("event_digest") for event in batch]
        if actual_digests != appended:
            raise ValueError("SQLite revision append index differs from route ledger events")
        for event in batch:
            details = event.get("details", {})
            event_actor = details.get("owner_id") if isinstance(details, Mapping) else None
            if actor != event_actor:
                raise ValueError("SQLite revision actor differs from the appended route event owner")
        prefix = {
            "format": ledger["format"],
            "entries": entries[:end_offset],
        }
        computed_digest = _digest(prefix)
        if row["ledger_digest"] != computed_digest:
            raise ValueError(f"SQLite revision {expected_revision} intermediate ledger digest mismatch")
        previous_ledger_digest = computed_digest
        event_offset = end_offset
    if event_offset != len(entries) or previous_ledger_digest != ledger.get("ledger_digest"):
        raise ValueError("SQLite revision history does not reproduce the complete route ledger")


def verify_sqlite_authority_bundle(
    database_path: Path,
    *,
    expected_ledger: Mapping[str, Any],
    expected_history: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Open the transferred DB on the verifier host and use the repository adapter."""
    Ledger, Store = _load_types()
    store = Store(database_path)
    document = store.load()
    if document != dict(expected_ledger):
        raise ValueError("transferred SQLite database does not contain the attested route ledger")
    restored = Ledger.from_dict(document, store=store)
    actual_history = list(store.revision_history())
    if actual_history != list(expected_history):
        raise ValueError("transferred SQLite revision audit differs from the exported history")
    validate_revision_history(document, actual_history)
    return {
        "verified": True,
        "store_type": "sqlite-local-file",
        "ledger_digest": document["ledger_digest"],
        "revision_count": len(actual_history),
        "active_epoch_id": restored.active_epoch["epoch_id"],
        "active_owner_id": restored.active_epoch["owner_id"],
        "active_owner_generation": restored.active_epoch["owner_generation"],
        "history_digest": _digest(actual_history),
    }


def _phase_cas(args: argparse.Namespace) -> None:
    _Ledger, Store = _load_types()
    deadline = time.monotonic() + 20.0
    gate = Path(args.start_gate)
    while not gate.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("timed out waiting for the concurrent CAS start gate")
        time.sleep(0.005)
    store = Store(args.database)
    accepted = store.compare_and_swap(
        args.expected_digest,
        _read(Path(args.candidate)),
        actor_id=args.actor_id,
    )
    _write(
        Path(args.result),
        {
            "actor_id": args.actor_id,
            "accepted": accepted,
            "process_id": os.getpid(),
            "process_instance_id": str(uuid.uuid4()),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--database", required=True)
    init.add_argument("--route", required=True)
    init.add_argument("--epoch-id", required=True)
    init.add_argument("--initial-owner", required=True)
    init.add_argument("--phase-output", required=True)

    resume = sub.add_parser("resume")
    resume.add_argument("--database", required=True)
    resume.add_argument("--route", required=True)
    resume.add_argument("--request", required=True)
    resume.add_argument("--epoch-id", required=True)
    resume.add_argument("--initial-owner", required=True)
    resume.add_argument("--replacement-owner", required=True)
    resume.add_argument("--runner-id", required=True)
    resume.add_argument("--phase-output", required=True)

    stale = sub.add_parser("stale-replay")
    stale.add_argument("--database", required=True)
    stale.add_argument("--request", required=True)
    stale.add_argument("--epoch-id", required=True)
    stale.add_argument("--initial-owner", required=True)
    stale.add_argument("--phase-output", required=True)

    cas = sub.add_parser("cas")
    cas.add_argument("--database", required=True)
    cas.add_argument("--candidate", required=True)
    cas.add_argument("--expected-digest", required=True)
    cas.add_argument("--actor-id", required=True)
    cas.add_argument("--start-gate", required=True)
    cas.add_argument("--result", required=True)

    args = parser.parse_args()
    if args.command == "init":
        _phase_init(args)
    elif args.command == "resume":
        _phase_resume(args)
    elif args.command == "stale-replay":
        _phase_stale_replay(args)
    else:
        _phase_cas(args)


if __name__ == "__main__":
    main()
