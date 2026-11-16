"""USM-005 independent recovery verifier unit tests, no E-CPU import needed."""

from __future__ import annotations

from copy import deepcopy
import unittest

from independent_verify import (
    IndependentVerificationError, canonical_digest, source_value,
)
from test_independent_verify import fixture as operation_fixture
from verify_recovered_model import verify_recovered_model


def recovery_fixture():
    """Construct a consistent independent receiver artifact with fixture receipts."""
    operation = operation_fixture()["cases"][0]
    case, episode = operation["case"], operation["episode"]
    trace = episode["session"]
    receipt = trace["events"][-1]["output"]
    recovered = {
        "schema": "mailcpu.usm005.receiver-recovery-result.v1",
        "status": "complete",
        "replayed_request_sequence": 3,
        "semantic_reentries": 0,
        "events": 3,
        "ground_digest": receipt["ground_digest"],
        "ground_revision": 1,
        "read_receipt_id": receipt["read_receipt_id"],
        "value": receipt["value"],
        "trace_digest": trace["trace_digest"],
        "session_trace": trace,
        "model_digest": episode["model_digest"],
        "first_quorum_generation": 1,
        "latest_quorum_generation": 2,
        "receiver_process": 300,
    }
    data = {
        "schema": "mailcpu.usm005.operational-report.v1",
        "independent_case": operation,
        "model_process": 100,
        "first_receiver_process": 200,
        "replacement_receiver_process": 300,
        "first_receiver_exit": 86,
        "model_unchanged_process": True,
        "read_pending_at_crash": True,
        "authenticated_reconnect": True,
        "model_calls": ["observe", "propose", "read"],
        "result": recovered,
        "source_oracle_match": True,
        "quorum_anchor_failure_domains": 1,
    }
    data["report_digest"] = canonical_digest(data)
    return data


def rehash(document):
    """Canonicalize only the outer report after exercising an adversarial rewrite."""
    document["report_digest"] = canonical_digest(
        {key: value for key, value in document.items() if key != "report_digest"}
    )


class RecoveredModelObserverTests(unittest.TestCase):
    def test_recovery_trace_and_oracle_are_independent(self):
        """Confirm a complete recovered Ground trace with no E-CPU dependency."""
        evidence = verify_recovered_model(recovery_fixture())
        self.assertTrue(evidence["verified"])
        self.assertEqual(evidence["event_count"], 3)
        self.assertTrue(evidence["independent_host_source_oracle_match"])
        self.assertFalse(evidence["native_quorum_signatures_independently_verified"])
        self.assertFalse(evidence["process_liveness_independently_attested"])

    def test_changed_result_with_rehashed_outer_report_fails(self):
        """A false result is rejected regardless of a fresh report digest."""
        evidence = recovery_fixture()
        evidence["result"]["value"] += 1
        rehash(evidence)
        with self.assertRaises(IndependentVerificationError):
            verify_recovered_model(evidence)

    def test_rewritten_trace_and_all_digests_still_fails_source_oracle(self):
        """Recomputed internal hashes cannot change a known physical-source fixture."""
        evidence = recovery_fixture()
        trace = evidence["independent_case"]["episode"]["session"]
        trace["events"][-1]["output"]["value"] += 1
        head = "0" * 64
        for event in trace["events"]:
            event["previous_head"] = head
            event["call"]["previous_head"] = head
            event["event_digest"] = canonical_digest(
                {key: val for key, val in event.items() if key != "event_digest"}
            )
            head = event["event_digest"]
        trace["head"] = head
        trace["trace_digest"] = canonical_digest(
            {key: val for key, val in trace.items() if key != "trace_digest"}
        )
        evidence["result"]["value"] = trace["events"][-1]["output"]["value"]
        evidence["result"]["trace_digest"] = trace["trace_digest"]
        rehash(evidence)
        with self.assertRaisesRegex(IndependentVerificationError, "source oracle"):
            verify_recovered_model(evidence)

    def test_forged_ack_resume_metadata_fails(self):
        """Incorrect transport-replay metadata cannot masquerade as the expected cut."""
        evidence = recovery_fixture()
        evidence["result"]["replayed_request_sequence"] = 99
        rehash(evidence)
        with self.assertRaisesRegex(IndependentVerificationError, "crash-cut"):
            verify_recovered_model(evidence)

    def test_conflicting_model_decisions_fail(self):
        """The independent verifier checks model decisions against receiver calls."""
        evidence = recovery_fixture()
        evidence["independent_case"]["episode"]["decisions"][1]["call"] = "stop"
        rehash(evidence)
        with self.assertRaises(IndependentVerificationError):
            verify_recovered_model(evidence)

    def test_wrong_replacement_identity_fails(self):
        """The receiver identity in the result must match the declared replacement."""
        evidence = recovery_fixture()
        evidence["result"]["receiver_process"] = 999
        rehash(evidence)
        with self.assertRaisesRegex(IndependentVerificationError, "process roles"):
            verify_recovered_model(evidence)


if __name__ == "__main__":
    unittest.main()
