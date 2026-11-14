"""IFS USM-003: independently reconstruct model-issued E-CPU operation evidence.

This verifier deliberately imports no E-CPU, VGI, or model runtime. It checks
a producer-declared mathematical source, the E-CPU receiver's linked trace,
and a separate formula for the queried coordinate. It does not elevate a
digest into an authentication signature or mathematical proof.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

BUNDLE_SCHEMA = "in-formation-space.usm003.bundle.v1"
TRACE_SCHEMA = "mailcpu.model-syscall-trace.v1"
EPISODE_SCHEMA = "mailcpu.model-operating-session.v1"
CALL_SCHEMA = "mailcpu.model-syscall.v1"
GENESIS = "0" * 64


class IndependentVerificationError(ValueError):
    """A producer record does not support the stated independent conclusion."""


def canonical_digest(item: Any) -> str:
    """Reimplement the record's canonicalization without importing E-CPU."""
    return hashlib.sha256(json.dumps(
        item, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise IndependentVerificationError(detail)


def _hex(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _int(value: Any) -> bool:
    return type(value) is int


def source_value(kind: str, seed: int, coordinate: int) -> int:
    """Independent closed-form fixture source; not a physical world observation."""
    _require(kind in ("affine", "nonlinear"), "unrecognized source family")
    _require(_int(seed) and seed >= 0 and _int(coordinate) and coordinate >= 0,
             "invalid source coordinates")
    if kind == "affine":
        return (7 + seed + 5 * coordinate) % 97
    return ((coordinate + seed) ** 3 + 17 * coordinate * coordinate + 3) % 97


def verify_episode(item: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct one operation's causal order and independently checked output."""
    _require(isinstance(item, Mapping) and set(item) == {"case", "episode"}, "invalid case envelope")
    case, episode = item["case"], item["episode"]
    case_fields = {"stream_id", "session_id", "kind", "seed", "coordinate", "policy"}
    _require(isinstance(case, Mapping) and set(case) == case_fields, "invalid source declaration")
    _require(isinstance(episode, Mapping) and set(episode) ==
             {"schema", "model_digest", "session", "decisions", "status"}, "invalid episode")
    _require(episode["schema"] == EPISODE_SCHEMA and _hex(episode["model_digest"]),
             "invalid model identity")
    _require(case["policy"] in ("trained", "high-request"), "invalid controller mode")
    trace = episode["session"]
    trace_fields = {"schema", "session_id", "stream_id", "observation_digest",
                    "training_count", "requested_coordinate", "phase",
                    "events", "head", "trace_digest"}
    _require(isinstance(trace, Mapping) and set(trace) == trace_fields and
             trace["schema"] == TRACE_SCHEMA, "invalid E-CPU trace schema")
    _require(trace["session_id"] == case["session_id"] and
             trace["stream_id"] == case["stream_id"] and
             trace["requested_coordinate"] == case["coordinate"],
             "source and E-CPU session disagree")
    _require(_int(trace["training_count"]) and trace["training_count"] == 24,
             "unexpected observation split")
    _require(_int(case["coordinate"]) and 0 <= case["coordinate"] <= 10**18,
             "invalid target coordinate")
    _require(_int(case["seed"]) and 0 <= case["seed"] < 10**9, "invalid fixture seed")
    source = [source_value(case["kind"], case["seed"], t) for t in range(40)]
    _require(trace["observation_digest"] == canonical_digest(source),
             "E-CPU source digest differs from independently reconstructed fixture")
    _require(trace["trace_digest"] == canonical_digest(
        {key: trace[key] for key in trace_fields - {"trace_digest"}}
    ), "trace digest mismatch")

    head, phase = GENESIS, "new"
    transitions = {
        ("new", "observe", "observed"): "observed",
        ("observed", "propose", "admitted"): "admitted",
        ("observed", "propose", "refused_by_ecpu"): "refused",
        ("observed", "stop", "deferred_by_model"): "deferred",
        ("admitted", "read", "completed"): "complete",
        ("admitted", "read", "refused_by_ecpu"): "refused",
        ("admitted", "stop", "deferred_by_model"): "deferred",
    }
    admitted_digest = None
    calls = []
    for index, event in enumerate(trace["events"]):
        fields = {"index", "previous_head", "call", "output", "next_phase", "event_digest"}
        _require(isinstance(event, Mapping) and set(event) == fields, "invalid event")
        _require(_int(event["index"]) and event["index"] == index and
                 event["previous_head"] == head, "reordered/duplicated event")
        _require(event["event_digest"] == canonical_digest(
            {k: event[k] for k in fields - {"event_digest"}}
        ), "event digest mismatch")
        call, output = event["call"], event["output"]
        call_fields = {"schema", "session_id", "stream_id", "seq",
                       "previous_head", "op", "coordinate"}
        _require(isinstance(call, Mapping) and set(call) == call_fields and
                 call["schema"] == CALL_SCHEMA and _int(call["seq"]) and
                 call["seq"] == index, "invalid sequence or system-call ABI")
        _require(call["session_id"] == trace["session_id"] and
                 call["stream_id"] == trace["stream_id"] and
                 call["previous_head"] == head, "cross-session model call")
        _require(isinstance(output, Mapping) and "status" in output, "missing receiver outcome")
        target_phase = transitions.get((phase, call["op"], output["status"]))
        _require(target_phase is not None and event["next_phase"] == target_phase,
                 "E-CPU phase or outcome is inconsistent")
        if call["op"] == "read":
            _require(call["coordinate"] == case["coordinate"], "model rewrote caller target")
        else:
            _require(call["coordinate"] is None, "non-read call injected a coordinate")
        if call["op"] == "observe":
            _require(set(output) == {"status", "window", "window_digest", "withheld_count"} and
                     output["window"] == source[:24] and output["withheld_count"] == 16 and
                     output["window_digest"] == canonical_digest(source[:24]),
                     "receiver observation differs from source")
        elif call["op"] == "propose" and target_phase == "admitted":
            _require(_hex(output.get("ground_digest")) and
                     _hex(output.get("certificate_digest")) and
                     _int(output.get("revision")) and output["revision"] >= 1,
                     "Ground admission lacks bound evidence")
            admitted_digest = output["ground_digest"]
        elif call["op"] == "read" and target_phase == "complete":
            _require(_int(output.get("value")) and
                     output["value"] == source_value(case["kind"], case["seed"], case["coordinate"]),
                     "distant-coordinate state fails independent source oracle")
            _require(output.get("ground_digest") == admitted_digest and
                     _hex(output.get("read_receipt_id")),
                     "read does not bind the admitted Ground")
        calls.append(call["op"])
        phase = target_phase
        head = event["event_digest"]
    _require(phase == trace["phase"] == episode["status"] and
             head == trace["head"], "final operation state diverges")
    _require(len(calls) == len(episode["decisions"]), "model decisions missing")
    for operation, decision in zip(calls, episode["decisions"]):
        _require(isinstance(decision, Mapping) and set(decision) ==
                 {"call", "probability", "request_digest"} and
                 decision["call"] == operation and _hex(decision["request_digest"]),
                 "reported model decision differs from receiver call")
        prob = decision["probability"]
        _require(prob is None or (type(prob) in (float, int) and 0 <= prob <= 1),
                 "invalid model probability")
        if operation == "propose":
            _require(prob is not None and prob >= 0.5, "model proposal contradicts declared threshold")
        if operation == "stop":
            _require(prob is not None and prob < 0.5, "model deferral contradicts declared threshold")
    _require(bool(calls) and calls[0] == "observe", "model did not observe before operating")
    return {
        "stream_id": case["stream_id"],
        "source_kind": case["kind"],
        "model_policy": case["policy"],
        "status": phase,
        "verified_event_count": len(calls),
        "trace_digest": trace["trace_digest"],
        "oracle_checked": phase == "complete",
    }


def verify_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Verify exact producer record and replay distinct sessions on this host."""
    _require(isinstance(bundle, Mapping) and set(bundle) ==
             {"schema", "cases", "bundle_digest"}, "invalid bundle")
    _require(bundle["schema"] == BUNDLE_SCHEMA and isinstance(bundle["cases"], list)
             and len(bundle["cases"]) >= 2, "missing source cases")
    _require(bundle["bundle_digest"] == canonical_digest({
        "schema": bundle["schema"], "cases": bundle["cases"]
    }), "bundle digest mismatch")
    seen = set()
    results = []
    for item in bundle["cases"]:
        checked = verify_episode(item)
        _require(checked["stream_id"] not in seen, "duplicate source stream identity")
        seen.add(checked["stream_id"])
        results.append(checked)
    _require(any(x["oracle_checked"] for x in results),
             "no actual navigated result available for independent source comparison")
    core = {"schema": "in-formation-space.usm003.verification-report.v1",
            "verifier": "python-stdlib-independent-from-ecpu",
            "verified": True, "cases": results, "source_bundle_digest": bundle["bundle_digest"]}
    return {**core, "report_digest": canonical_digest(core)}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verified = verify_bundle(json.loads(args.source_json.read_text(encoding="utf-8")))
    result = json.dumps(verified, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
