"""Cross-repository USM-003 verifier tests that require no E-CPU installation."""

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "ifs_independent_model_verifier", Path(__file__).with_name("independent_verify.py")
)
assert SPEC is not None and SPEC.loader is not None
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


def fixture():
    case = {
        "stream_id": "case-affine", "session_id": "session-test",
        "kind": "affine", "seed": 201, "coordinate": 10**12 + 137,
        "policy": "high-request",
    }
    observed = [v.source_value("affine", 201, index) for index in range(40)]
    phase = "new"
    head = v.GENESIS
    events = []
    for index, (op, outcome, next_phase) in enumerate((
        ("observe", {
            "status": "observed", "window": observed[:24],
            "window_digest": v.canonical_digest(observed[:24]), "withheld_count": 16,
        }, "observed"),
        ("propose", {
            "status": "admitted", "ground_digest": "a" * 64,
            "certificate_digest": "b" * 64, "revision": 1,
            "verification_class": "witness_grounded",
        }, "admitted"),
        ("read", {
            "status": "completed", "value": v.source_value("affine", 201, case["coordinate"]),
            "ground_digest": "a" * 64, "read_receipt_id": "c" * 64,
            "verification_class": "witness_grounded",
        }, "complete"),
    )):
        call = {
            "schema": v.CALL_SCHEMA, "session_id": case["session_id"],
            "stream_id": case["stream_id"], "seq": index,
            "previous_head": head, "op": op,
            "coordinate": case["coordinate"] if op == "read" else None,
        }
        record = {"index": index, "previous_head": head,
                  "call": call, "output": outcome, "next_phase": next_phase}
        events.append({**record, "event_digest": v.canonical_digest(record)})
        head = events[-1]["event_digest"]
        phase = next_phase
    trace = {
        "schema": v.TRACE_SCHEMA,
        "session_id": case["session_id"],
        "stream_id": case["stream_id"],
        "observation_digest": v.canonical_digest(observed),
        "training_count": 24, "requested_coordinate": case["coordinate"],
        "phase": phase, "events": events, "head": head,
    }
    trace["trace_digest"] = v.canonical_digest(trace)
    episode = {
        "schema": v.EPISODE_SCHEMA, "model_digest": "d" * 64,
        "session": trace, "status": "complete",
        "decisions": [
            {"call": "observe", "probability": None, "request_digest": "e" * 64},
            {"call": "propose", "probability": 0.99, "request_digest": "f" * 64},
            {"call": "read", "probability": None, "request_digest": "1" * 64},
        ],
    }
    core = {"schema": v.BUNDLE_SCHEMA,
            "cases": [{"case": case, "episode": episode},
                      {"case": {**case, "stream_id": "case-other",
                                "session_id": "session-other"}, "episode": copy.deepcopy(episode)}]}
    second = core["cases"][1]["episode"]["session"]
    # Rebuild the distinct session's complete chain rather than pretending
    # that copying one receiver record constitutes independent evidence.
    head = v.GENESIS
    for event in second["events"]:
        event["previous_head"] = head
        event["call"]["session_id"] = "session-other"
        event["call"]["stream_id"] = "case-other"
        event["call"]["previous_head"] = head
        record = {k: event[k] for k in event if k != "event_digest"}
        event["event_digest"] = v.canonical_digest(record)
        head = event["event_digest"]
    second["session_id"] = "session-other"
    second["stream_id"] = "case-other"
    second["head"] = head
    second["trace_digest"] = v.canonical_digest({k: second[k] for k in second if k != "trace_digest"})
    core["bundle_digest"] = v.canonical_digest(core)
    return core


class IndependentReconstructionTests(unittest.TestCase):
    def test_full_two_session_bundle(self):
        result = v.verify_bundle(fixture())
        self.assertTrue(result["verified"])
        self.assertEqual(len(result["cases"]), 2)
        self.assertTrue(all(x["oracle_checked"] for x in result["cases"]))

    def test_modified_source_digest_fails(self):
        item = fixture()
        item["cases"][0]["episode"]["session"]["observation_digest"] = "0" * 64
        item["bundle_digest"] = v.canonical_digest({k: item[k] for k in item if k != "bundle_digest"})
        with self.assertRaises(v.IndependentVerificationError):
            v.verify_bundle(item)

    def test_modified_distant_value_fails_even_if_all_hashes_recomputed(self):
        item = fixture()
        trace = item["cases"][0]["episode"]["session"]
        trace["events"][2]["output"]["value"] += 1
        head = v.GENESIS
        for event in trace["events"]:
            event["previous_head"] = head
            event["call"]["previous_head"] = head
            event["event_digest"] = v.canonical_digest(
                {k: event[k] for k in event if k != "event_digest"}
            )
            head = event["event_digest"]
        trace["head"] = head
        trace["trace_digest"] = v.canonical_digest({k: trace[k] for k in trace if k != "trace_digest"})
        item["bundle_digest"] = v.canonical_digest({k: item[k] for k in item if k != "bundle_digest"})
        with self.assertRaisesRegex(v.IndependentVerificationError, "source oracle"):
            v.verify_bundle(item)

    def test_cross_session_replay_fails(self):
        item = fixture()
        trace = item["cases"][0]["episode"]["session"]
        trace["events"][1]["call"]["stream_id"] = "other"
        trace["events"][1]["event_digest"] = v.canonical_digest({
            k: trace["events"][1][k] for k in trace["events"][1] if k != "event_digest"
        })
        with self.assertRaises(v.IndependentVerificationError):
            v.verify_bundle(item)


if __name__ == "__main__":
    unittest.main()
