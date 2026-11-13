from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from diverse_host_verifier import (
    HANDOFF_SCHEMA,
    PAYLOAD_SCHEMA,
    RELAY_CHANNEL,
    REPOSITORY,
    WORKFLOW_REF,
    DiverseVerificationError,
    host_metadata,
    object_digest,
    reconstruct,
    write_json,
    write_report_predicate,
)


def seal(document):
    core = {key: value for key, value in document.items() if key not in {"record_digest"}}
    return {**core, "record_digest": object_digest(core)}

def encode(document):
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8") + b"\n"


def host(role, runner_name, runner_os="Linux"):
    run_id = "123456789"
    attempt = "1"
    return {
        "role": role,
        "repository": REPOSITORY,
        "run_id": run_id,
        "run_attempt": attempt,
        "run_number": "42",
        "workflow_ref": WORKFLOW_REF,
        "workflow_sha": "a" * 40,
        "git_ref": "refs/heads/main",
        "git_sha": "a" * 40,
        "job": role,
        "runner_name": runner_name,
        "runner_os": runner_os,
        "runner_arch": "X64",
        "runner_environment": "github-hosted",
        "actor_id": f"{REPOSITORY}#run-{run_id}.attempt-{attempt}.{role}.{runner_name}",
        "clock_segment_id": "0",
    }


def frame(actor, elapsed, vector, lamport):
    return {
        "actor_id": actor,
        "monotonic": {"actor_id": actor, "segment": 0, "elapsed_ns": elapsed},
        "wall": None,
        "causal": {"actor_id": actor, "lamport": lamport, "vector": vector},
        "scheduler": None,
        "event_lambda": None,
        "chronon_phase": None,
        "chemical_tau": None,
    }


def span(actor, span_id, operation_id, start, end):
    core = {
        "format": "in-formation.operation-span",
        "schema": "in-formation.operation-span/0.1",
        "attempt_id": "run-123456789-attempt-1",
        "span_id": span_id,
        "operation_id": operation_id,
        "clock_actor_id": actor,
        "clock_segment_id": "0",
        "monotonic_start_ns": start,
        "monotonic_end_ns": end,
        "elapsed_ns": end - start,
        "clock_status": "measured",
        "outcome": "succeeded",
        "exception_type": None,
        "context": {"operation": operation_id},
        "measurement_scope": (
            "Elapsed monotonic time between the recorder's immediately-before and "
            "immediately-after samples around one synchronous callable invocation; "
            "includes blocking within the call and excludes later work."
        ),
    }
    return {**core, "span_digest": object_digest(core)}


def make_pair():
    source_host = host("source_host", "runner-a")
    receiver_host = host("receiver_host", "runner-b", "Windows")
    verifier_host = host("diverse_verifier_host", "runner-c", "macOS")
    source_actor = source_host["actor_id"]
    receiver_actor = receiver_host["actor_id"]

    source_span = span(source_actor, "source-prepare", "host-a.prepare", 10, 19)
    source_frame = frame(source_actor, 20, {source_actor: 1}, 1)
    payload_core = {
        "schema": PAYLOAD_SCHEMA,
        "path_id": "run-123456789-distributed-path",
        "attempt_id": source_span["attempt_id"],
        "predecessor_span_digest": source_span["span_digest"],
        "sender_actor_id": source_actor,
        "sender_completion_frame": source_frame,
    }
    payload = {**payload_core, "payload_digest": object_digest(payload_core)}
    source = seal({
        "format": "in-formation.independent-host-operation-record",
        "schema": "in-formation.independent-host-operation-record/0.1",
        "role": "source_host",
        "host": source_host,
        "operation_span": source_span,
        "temporal_frame": source_frame,
        "handoff_payload": payload,
        "source_record_sha256": None,
        "handoff_witness": None,
    })
    source_bytes = json.dumps(
        source, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8") + b"\n"

    receiver_span = span(receiver_actor, "receiver-continue", "host-b.continue", 31, 41)
    receiver_frame = frame(
        receiver_actor, 30,
        {source_actor: 1, receiver_actor: 1},
        2,
    )
    witness_core = {
        "schema": HANDOFF_SCHEMA,
        "path_id": payload["path_id"],
        "attempt_id": payload["attempt_id"],
        "predecessor_span_digest": source_span["span_digest"],
        "successor_span_digest": receiver_span["span_digest"],
        "channel_id": RELAY_CHANNEL,
        "message_sequence": 1,
        "received_sequence": 1,
        "sender_actor_id": source_actor,
        "receiver_actor_id": receiver_actor,
        "payload_digest": payload["payload_digest"],
        "sender_completion_frame": source_frame,
        "receiver_start_frame": receiver_frame,
    }
    witness = {**witness_core, "handoff_digest": object_digest(witness_core)}
    receiver = seal({
        "format": "in-formation.independent-host-operation-record",
        "schema": "in-formation.independent-host-operation-record/0.1",
        "role": "receiver_host",
        "host": receiver_host,
        "operation_span": receiver_span,
        "temporal_frame": receiver_frame,
        "handoff_payload": None,
        "source_record_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "handoff_witness": witness,
    })
    receiver_bytes = json.dumps(
        receiver, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8") + b"\n"
    return source, source_bytes, receiver, receiver_bytes, verifier_host


def verifier_env(verifier):
    return {
        "GITHUB_REPOSITORY": verifier["repository"],
        "GITHUB_JOB": verifier["job"],
        "GITHUB_WORKFLOW_REF": verifier["workflow_ref"],
        "GITHUB_WORKFLOW_SHA": verifier["workflow_sha"],
        "GITHUB_REF": verifier["git_ref"],
        "GITHUB_SHA": verifier["git_sha"],
        "GITHUB_RUN_ID": verifier["run_id"],
        "GITHUB_RUN_ATTEMPT": verifier["run_attempt"],
        "GITHUB_RUN_NUMBER": verifier["run_number"],
        "RUNNER_NAME": verifier["runner_name"],
        "RUNNER_OS": verifier["runner_os"],
        "RUNNER_ARCH": verifier["runner_arch"],
        "RUNNER_ENVIRONMENT": verifier["runner_environment"],
    }


class DiverseHostVerifierTests(unittest.TestCase):
    def setUp(self):
        (
            self.source,
            self.source_bytes,
            self.receiver,
            self.receiver_bytes,
            self.verifier,
        ) = make_pair()

    def run_reconstruction(self, source=None, source_bytes=None, receiver=None, receiver_bytes=None):
        return reconstruct(
            self.source if source is None else source,
            self.source_bytes if source_bytes is None else source_bytes,
            self.receiver if receiver is None else receiver,
            self.receiver_bytes if receiver_bytes is None else receiver_bytes,
            self.verifier,
        )

    def test_reconstructs_one_strict_causal_edge_without_cross_clock_duration(self):
        report = self.run_reconstruction()
        self.assertEqual(report["causal_reconstruction"]["edge_count"], 1)
        self.assertEqual(report["causal_reconstruction"]["vector_relation"], "before")
        self.assertEqual(
            report["causal_reconstruction"]["topological_order"],
            [
                self.source["operation_span"]["span_digest"],
                self.receiver["operation_span"]["span_digest"],
            ],
        )
        self.assertTrue(report["checks"]["source_artifact_bytes_bound_by_receiver"])
        self.assertIsNone(report["duration"]["combined_cross_host_elapsed_ns"])
        self.assertEqual(
            report["duration"]["status"],
            "not_computed_independent_unaligned_clock_domains",
        )
        self.assertTrue(any("does not authenticate" in item for item in report["scope"]))

    def test_record_digest_tampering_is_rejected(self):
        changed = copy.deepcopy(self.source)
        changed["host"]["runner_name"] = "invented-runner"
        with self.assertRaisesRegex(DiverseVerificationError, "record digest"):
            self.run_reconstruction(source=changed, source_bytes=encode(changed))

    def test_payload_digest_is_recomputed_not_trusted(self):
        changed = copy.deepcopy(self.source)
        changed["handoff_payload"]["path_id"] = "different-path"
        changed = seal(changed)
        with self.assertRaisesRegex(DiverseVerificationError, "payload digest"):
            self.run_reconstruction(source=changed, source_bytes=encode(changed))

    def test_receiver_must_bind_exact_source_artifact_bytes(self):
        changed = copy.deepcopy(self.receiver)
        changed["source_record_sha256"] = "f" * 64
        changed = seal(changed)
        with self.assertRaisesRegex(DiverseVerificationError, "exact source artifact bytes"):
            self.run_reconstruction(receiver=changed, receiver_bytes=encode(changed))

    def test_noncanonical_source_bytes_are_rejected(self):
        with self.assertRaisesRegex(DiverseVerificationError, "canonical JSON"):
            self.run_reconstruction(source_bytes=self.source_bytes + b" ")

    def test_concurrent_vector_clocks_do_not_establish_precedence(self):
        changed = copy.deepcopy(self.receiver)
        actor = changed["host"]["actor_id"]
        concurrent_frame = frame(actor, 30, {actor: 1}, 1)
        witness = changed["handoff_witness"]
        witness["receiver_start_frame"] = concurrent_frame
        witness_core = {key: value for key, value in witness.items() if key != "handoff_digest"}
        witness["handoff_digest"] = object_digest(witness_core)
        changed["temporal_frame"] = concurrent_frame
        changed = seal(changed)
        raw = json.dumps(
            changed, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8") + b"\n"
        with self.assertRaisesRegex(DiverseVerificationError, "does not strictly follow"):
            self.run_reconstruction(receiver=changed, receiver_bytes=raw)

    def test_cross_run_receiver_is_rejected_even_after_resigning_record_digest(self):
        changed = copy.deepcopy(self.receiver)
        changed["host"]["run_attempt"] = "2"
        changed = seal(changed)
        raw = json.dumps(
            changed, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8") + b"\n"
        with self.assertRaisesRegex(DiverseVerificationError, "differ in run_attempt"):
            self.run_reconstruction(receiver=changed, receiver_bytes=raw)

    def test_report_predicate_binds_exact_bytes_and_fourth_job_identity(self):
        report = self.run_reconstruction()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            predicate_path = root / "predicate.json"
            write_json(report_path, report)
            env = verifier_env(self.verifier)
            predicate = write_report_predicate(report_path, predicate_path, env)
            self.assertEqual(
                predicate["report_sha256"],
                hashlib.sha256(report_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(predicate["job"], "diverse_verifier_host")
            self.assertEqual(
                json.loads(predicate_path.read_text(encoding="utf-8")),
                predicate,
            )
            report_path.write_bytes(report_path.read_bytes() + b" ")
            with self.assertRaisesRegex(DiverseVerificationError, "canonical JSON"):
                write_report_predicate(report_path, predicate_path, env)

    def test_verifier_rejects_non_main_or_non_hosted_environment(self):
        env = verifier_env(self.verifier)
        env["GITHUB_REF"] = "refs/heads/feature"
        with self.assertRaisesRegex(DiverseVerificationError, "on main"):
            host_metadata("diverse_verifier_host", env)
        env = verifier_env(self.verifier)
        env["RUNNER_ENVIRONMENT"] = "self-hosted"
        with self.assertRaisesRegex(DiverseVerificationError, "GitHub-hosted"):
            host_metadata("diverse_verifier_host", env)


if __name__ == "__main__":
    unittest.main()
