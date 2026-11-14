"""USM-007: fence competing model-result publishers with existing IFS route epochs.

The durable CAS and owner generations are provided by ProofActionRouteEpochLedger
and SQLiteRouteEpochLedgerStore, without implementing another authority. A
recovered E-CPU result is independently checked *before* an owner may publish
its result. Two replacement OS processes race the same expected owner epoch:
only the successful claimant can append an execution authorization.

Scope: single-host SQLite authority and one known E-CPU result, not an
independent-machine quorum or a fence against arbitrary external side effects.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

# Existing IFS route ledger depends on E-CPU's reliable policy type, but the
# separate recovered-Ground source verifier remains standard-library only.
PROOF_ATTENTION = Path(__file__).resolve().parents[1] / "proof-attention"
if str(PROOF_ATTENTION) not in sys.path:
    sys.path.insert(0, str(PROOF_ATTENTION))

from independent_verify import canonical_digest
from verify_recovered_model import verify_recovered_model
from proof_action_route_epoch import (
    ProofActionRouteEpochError,
    ProofActionRouteEpochLedger,
)
from sqlite_route_epoch_store import SQLiteRouteEpochLedgerStore

SCHEMA = "in-formation-space.usm007.model-result-fencing.v1"
EPOCH = "model-ground-publication-epoch"
RUNNER = "model-ground-result-publisher"
MODEL_CH = "model.syscall.call"
RECEIVER_CH = "model.syscall.prompt"


class ModelPublicationRefused(ValueError):
    """A stale, conflicting, or unverifiable model publication request."""


def prepared_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a complete real E-CPU recovery record before opening authority."""
    witness = verify_recovered_model(source)
    case = source["independent_case"]
    trace = case["episode"]["session"]
    call = trace["events"][-1]["call"]
    receipt = trace["events"][-1]["output"]
    if (call["op"] != "read" or call["seq"] != 2
            or receipt["status"] != "completed"
            or witness["trace_digest"] != trace["trace_digest"]):
        raise ModelPublicationRefused("unverified or incomplete E-CPU Ground result")
    return {
        "trace_digest": trace["trace_digest"],
        "source_report_digest": source["report_digest"],
        "attempt_id": "ground-" + trace["trace_digest"],
        "request_digest": canonical_digest(call),
        "receipt_id": receipt["read_receipt_id"],
        "ground_digest": receipt["ground_digest"],
        "value": receipt["value"],
        "coordinate": case["case"]["coordinate"],
        "source": case["case"]["kind"],
    }


def route_description(trace_digest: str) -> dict[str, Any]:
    """Adapt actual MailCPU model channels into IFS's existing route schema."""
    return {
        "host_id": "model-" + trace_digest[:16],
        "worker_id": "ecpu-receiver-" + trace_digest[:16],
        "request_channel": MODEL_CH,
        "result_channel": RECEIVER_CH,
        "policy": {
            "lease_ticks": 4, "max_attempts": 12, "window_size": 4,
        },
    }


def open_authority(database: Path, verified: Mapping[str, Any]) -> dict[str, Any]:
    """Durably record the admitted request in the original receiver epoch."""
    owner = "original-receiver-" + verified["trace_digest"][:12]
    ledger = ProofActionRouteEpochLedger(SQLiteRouteEpochLedgerStore(database))
    opened = ledger.open_epoch(
        EPOCH, route_description(verified["trace_digest"]), owner_id=owner,
    )
    active = ledger.active_epoch
    if active is None or active["owner_id"] != owner:
        raise ModelPublicationRefused("original model Ground route was not opened")
    admitted = ledger.record_request_admission(
        EPOCH, active["route_digest"], owner_id=owner, owner_generation=1,
        request_sequence=3, attempt_id=verified["attempt_id"],
        request_digest=verified["request_digest"],
    )
    if not admitted:
        raise ModelPublicationRefused("E-CPU request was not durably admitted")
    return {"owner": owner, "epoch": EPOCH, "route_digest": active["route_digest"],
            "opened_event_digest": opened["event_digest"],
            "request_digest": verified["request_digest"]}


def compete(
    *,
    database: Path,
    source_json: Path,
    owner_id: str,
    expected_old_owner: str,
    readiness: Path,
    start: Path,
    timeout: float = 12,
) -> dict[str, Any]:
    """Run one actual contender process against the same SQLite authority."""
    source = json.loads(source_json.read_text(encoding="utf-8"))
    verified = prepared_source(source)
    if not owner_id.startswith("replacement-receiver-"):
        raise ModelPublicationRefused("only a configured replacement owner can claim")
    ledger = ProofActionRouteEpochLedger(SQLiteRouteEpochLedgerStore(database))
    stale_snapshot = ledger.active_epoch
    if (stale_snapshot is None or stale_snapshot["epoch_id"] != EPOCH
            or stale_snapshot["owner_id"] != expected_old_owner
            or stale_snapshot["owner_generation"] != 1):
        raise ModelPublicationRefused("contender did not observe the original owner epoch")
    readiness.write_text(owner_id + "\n", encoding="utf-8")
    until = time.monotonic() + timeout
    while not start.exists():
        if time.monotonic() >= until:
            raise ModelPublicationRefused("contender barrier was never released")
        time.sleep(0.005)
    try:
        claim = ledger.claim_epoch(
            EPOCH, owner_id=owner_id, expected_owner_id=expected_old_owner,
            expected_owner_generation=1,
        )
    except ProofActionRouteEpochError as exc:
        # CAS conflict and already-superseded owner are both safe refusals.
        return {
            "owner_id": owner_id, "outcome": "superseded",
            "reason": type(exc).__name__, "publication": None,
            "contender_process": os.getpid(),
        }
    ledger.refresh()
    active = ledger.active_epoch
    if active is None or active["owner_id"] != owner_id or active["owner_generation"] != 2:
        raise ModelPublicationRefused("claim did not publish a new owner generation")
    ticket = ledger.record_execution_authorization(
        EPOCH, active["route_digest"], owner_id=owner_id, owner_generation=2,
        attempt_id=verified["attempt_id"], request_digest=verified["request_digest"],
        runner_id=RUNNER,
    )
    if not isinstance(ticket, str) or not ticket.startswith("urn:sha256:"):
        raise ModelPublicationRefused("claimed owner did not obtain an execution ticket")
    # A logical publication record, not an external side effect. Its admission
    # is the durable ledger event, whose owner and ticket can be audited.
    return {
        "owner_id": owner_id, "outcome": "authorized",
        "reason": None, "contender_process": os.getpid(),
        "publication": {
            "execution_id": ticket, "trace_digest": verified["trace_digest"],
            "read_receipt_id": verified["receipt_id"],
            "ground_digest": verified["ground_digest"],
            "value": verified["value"], "coordinate": verified["coordinate"],
            "source_report_digest": verified["source_report_digest"],
            "owner_generation": 2,
        },
    }


def run_race(source: Mapping[str, Any], directory: Path) -> dict[str, Any]:
    """Exercise real competing replacement interpreters, not sequential mocks."""
    verified = prepared_source(source)
    directory.mkdir(parents=True, exist_ok=True)
    input_path = directory / "source.json"
    input_path.write_text(json.dumps(source, sort_keys=True) + "\n", encoding="utf-8")
    db = directory / "route-authority.sqlite"
    original = open_authority(db, verified)
    start = directory / "start-contenders"
    candidates = [
        "replacement-receiver-a-" + verified["trace_digest"][:10],
        "replacement-receiver-b-" + verified["trace_digest"][:10],
    ]
    procs: list[subprocess.Popen[str]] = []
    try:
        for index, name in enumerate(candidates):
            args = [
                sys.executable, str(Path(__file__).resolve()), "claim",
                "--database", str(db), "--source", str(input_path),
                "--owner", name, "--old-owner", original["owner"],
                "--ready", str(directory / f"contender-{index}.ready"),
                "--start", str(start),
            ]
            procs.append(subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
            ))
        timeout = time.monotonic() + 15
        while not all((directory / f"contender-{i}.ready").exists() for i in range(2)):
            if time.monotonic() >= timeout or any(p.poll() is not None for p in procs):
                raise ModelPublicationRefused("both contenders were not ready to race")
            time.sleep(0.01)
        start.write_text("go\n", encoding="utf-8")
        reports = []
        for p in procs:
            stdout, stderr = p.communicate(timeout=20)
            if p.returncode != 0:
                raise ModelPublicationRefused(
                    "model result contender crashed: " + stderr[-700:]
                )
            reports.append(json.loads(stdout))
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
            p.communicate(timeout=5)
    authorized = [r for r in reports if r["outcome"] == "authorized"]
    denied = [r for r in reports if r["outcome"] == "superseded"]
    if len(authorized) != 1 or len(denied) != 1:
        raise ModelPublicationRefused("ownership competition did not fence one contender")
    surviving = ProofActionRouteEpochLedger(SQLiteRouteEpochLedgerStore(db))
    active = surviving.active_epoch
    events = surviving.entries
    authorizations = [e for e in events if e["event_type"] == "execution_authorized"]
    claims = [e for e in events if e["event_type"] == "claimed"]
    if (len(claims) != 1 or len(authorizations) != 1
            or active is None or active["owner_id"] != authorized[0]["owner_id"]
            or active["owner_generation"] != 2):
        raise ModelPublicationRefused("durable route owner is not the unique publisher")
    ticket = authorizations[0]["details"]["execution_id"]
    if (authorized[0]["publication"]["execution_id"] != ticket
            or authorizations[0]["details"]["request_digest"] != verified["request_digest"]):
        raise ModelPublicationRefused("published model result is not the authorized request")
    # Verify that the original/stale receiver *cannot* gain a fresh execution
    # ticket after the claimant has superseded its route generation.
    stale = ProofActionRouteEpochLedger(SQLiteRouteEpochLedgerStore(db))
    stale_result = stale.record_execution_authorization(
        EPOCH, original["route_digest"],
        owner_id=original["owner"], owner_generation=1,
        attempt_id=verified["attempt_id"], request_digest=verified["request_digest"],
        runner_id=RUNNER,
    )
    if stale_result is not None:
        raise ModelPublicationRefused("stale receiver was authorized after handoff")
    store = SQLiteRouteEpochLedgerStore(db)
    audit = store.revision_history()
    core = {
        "schema": SCHEMA,
        "producer_report_digest": verified["source_report_digest"],
        "verified_source_trace_digest": verified["trace_digest"],
        "prior_model_recovery_verified": True,
        "contenders": reports,
        "one_owner_claim": len(claims) == 1,
        "one_execution_authorization": len(authorizations) == 1,
        "stale_receiver_refused": True,
        "winning_owner": authorized[0]["owner_id"],
        "winning_ticket": ticket,
        "recovered_value": verified["value"],
        "read_receipt_id": verified["receipt_id"],
        "durable_route_ledger_digest": surviving.to_dict()["ledger_digest"],
        "route_authority_revision_count": len(audit),
        "single_host_authority": True,
        "remote_quorum_fencing_verified": False,
    }
    return {**core, "report_digest": canonical_digest(core)}


def main() -> None:
    """Provide a bounded contender worker and a reproducible race experiment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("claim", "demo"))
    parser.add_argument("--database", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--old-owner")
    parser.add_argument("--owner")
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--start", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.role == "claim":
        if any(value is None for value in (
            args.database, args.owner, args.old_owner, args.ready, args.start
        )):
            parser.error("claim requires database, owner, old-owner, ready and start")
        report = compete(
            database=args.database, source_json=args.source, owner_id=args.owner,
            expected_old_owner=args.old_owner, readiness=args.ready, start=args.start,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="usm007-") as folder:
            report = run_race(
                json.loads(args.source.read_text(encoding="utf-8")),
                Path(folder),
            )
    content = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
