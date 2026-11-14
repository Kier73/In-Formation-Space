"""IFS USM-005: independently reconstruct a recovered model/E-CPU Ground.

Read only the E-CPU producer's JSON operation artifact. This module imports
no E-CPU, neural runtime, or VGI code; it uses IFS USM-003's independent
source oracle and hash-chain verifier. It checks neither physical host
attestation nor native quorum certificate signatures.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from independent_verify import (
    IndependentVerificationError,
    canonical_digest,
    source_value,
    verify_episode,
)

REPORT_SCHEMA = "mailcpu.usm005.operational-report.v1"
RESULT_SCHEMA = "mailcpu.usm005.receiver-recovery-result.v1"


def _require(ok: bool, detail: str) -> None:
    """Reject one unsupported independent-recovery assertion."""
    if not ok:
        raise IndependentVerificationError(detail)


def verify_recovered_model(document: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the recovery report's exact causal trace and mathematical result.

    Does not trust the producer's claim that effects were executed exactly
    once merely because a JSON status or unforgeable-looking digest says so.
    """
    expected = {
        "schema", "independent_case", "model_process", "first_receiver_process",
        "replacement_receiver_process", "first_receiver_exit",
        "model_unchanged_process", "read_pending_at_crash",
        "authenticated_reconnect", "model_calls", "result",
        "source_oracle_match", "quorum_anchor_failure_domains",
        "report_digest",
    }
    _require(isinstance(document, Mapping) and set(document) == expected,
             "invalid recovered model report fields")
    _require(document["schema"] == REPORT_SCHEMA, "unsupported recovery report version")
    _require(document["report_digest"] == canonical_digest(
        {key: document[key] for key in expected - {"report_digest"}}
    ), "recovery report digest mismatch")
    verified = verify_episode(document["independent_case"])
    item = document["independent_case"]
    trace = item["episode"]["session"]
    result = document["result"]
    result_fields = {
        "schema", "status", "replayed_request_sequence", "semantic_reentries",
        "events", "ground_digest", "ground_revision", "read_receipt_id",
        "value", "trace_digest", "session_trace", "model_digest",
        "first_quorum_generation", "latest_quorum_generation", "receiver_process",
    }
    _require(isinstance(result, Mapping) and set(result) == result_fields and
             result["schema"] == RESULT_SCHEMA, "invalid recovered receiver result")
    _require(
        verified["oracle_checked"] and verified["status"] == "complete"
        and result["status"] == "complete" and result["session_trace"] == trace,
        "recovered receiver's complete operation trace differs from evidence",
    )
    _require(document["model_calls"] == ["observe", "propose", "read"]
             and [event["call"]["op"] for event in trace["events"]]
             == ["observe", "propose", "read"], "recovered operation chronology diverges")
    receipt = trace["events"][-1]["output"]
    _require(
        result["trace_digest"] == trace["trace_digest"]
        and result["model_digest"] == item["episode"]["model_digest"]
        and result["events"] == len(trace["events"]) == 3
        and result["ground_revision"] == 1
        and result["ground_digest"] == receipt["ground_digest"]
        and result["read_receipt_id"] == receipt["read_receipt_id"]
        and result["value"] == receipt["value"],
        "recovered receipt/trace identity mismatch",
    )
    expected_value = source_value(
        item["case"]["kind"], item["case"]["seed"], item["case"]["coordinate"],
    )
    _require(result["value"] == expected_value and
             document["source_oracle_match"] is True,
             "recovered navigation disagrees with independent source law")
    _require(
        type(document["first_receiver_exit"]) is int
        and document["first_receiver_exit"] == 86
        and document["model_unchanged_process"] is True
        and document["read_pending_at_crash"] is True
        and document["authenticated_reconnect"] is True
        and type(result["replayed_request_sequence"]) is int
        and result["replayed_request_sequence"] == 3
        and type(result["semantic_reentries"]) is int
        and result["semantic_reentries"] == 0
        and result["first_quorum_generation"] == 1
        and result["latest_quorum_generation"] == 2
        and document["quorum_anchor_failure_domains"] == 1,
        "declared crash-cut and recovery metadata is inconsistent",
    )
    pids = [
        document["model_process"],
        document["first_receiver_process"],
        document["replacement_receiver_process"],
    ]
    _require(all(type(pid) is int and pid > 0 for pid in pids) and
             result["receiver_process"] == pids[2] and pids[0] != pids[1]
             and pids[0] != pids[2],
             "producer-declared process roles are inconsistent")
    core = {
        "schema": "in-formation-space.usm005.independent-recovery-report.v1",
        "verified": True,
        "verifier": "python-stdlib-independent-from-ecpu",
        "recoverable_source_kind": item["case"]["kind"],
        "oracle_value": expected_value,
        "event_count": len(trace["events"]),
        "trace_digest": trace["trace_digest"],
        "producer_report_digest": document["report_digest"],
        "model_digest": item["episode"]["model_digest"],
        "declared_recovery_generation": result["latest_quorum_generation"],
        "independent_host_source_oracle_match": True,
        # JSON alone cannot attest processes, TLS handshakes or filesystem durability.
        "process_liveness_independently_attested": False,
        "native_quorum_signatures_independently_verified": False,
        "native_semantic_reentry_counter_independently_attested": False,
    }
    return {**core, "report_digest": canonical_digest(core)}


def main() -> None:
    """Accept a transferred producer report and retain an independent verdict."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    record = json.loads(args.source_json.read_text(encoding="utf-8"))
    result = verify_recovered_model(record)
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
