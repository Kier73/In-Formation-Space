from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import independent_host_path as path


def runner_env(role: str, *, runner_name: str, runner_os: str = "Linux") -> dict[str, str]:
    return {
        "GITHUB_REPOSITORY": path.REPOSITORY,
        "GITHUB_JOB": role,
        "GITHUB_WORKFLOW_REF": f"{path.REPOSITORY}/{path.WORKFLOW_PATH}@{path.SOURCE_REF}",
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_REF": path.SOURCE_REF,
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "123456789",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_NUMBER": "42",
        "RUNNER_NAME": runner_name,
        "RUNNER_OS": runner_os,
        "RUNNER_ARCH": "X64",
        "RUNNER_ENVIRONMENT": "github-hosted",
    }


class IndependentHostOperationPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source_path = self.root / "host-a.json"
        self.receiver_path = self.root / "host-b.json"
        self.source = path.produce_source(
            self.source_path,
            runner_env("source_host", runner_name="host-a-vm"),
        )
        self.verifier_host = path.host_metadata(
            "verifier_host",
            runner_env("verifier_host", runner_name="verifier-vm", runner_os="macOS"),
        )
        with patch.object(path, "verify_artifact_attestation", return_value={"verified": True}):
            self.receiver = path.produce_receiver(
                self.source_path,
                self.receiver_path,
                runner_env("receiver_host", runner_name="host-b-vm", runner_os="Windows"),
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def attestations(self) -> tuple[dict[str, object], dict[str, object]]:
        def summary(file_path: Path) -> dict[str, object]:
            return {
                "verified": True,
                "subject_sha256": path.sha256_file(file_path),
                "predicate_type": path.PREDICATE_TYPE,
                "signer_workflow": path.SIGNER_WORKFLOW,
                "source_ref": path.SOURCE_REF,
                "self_hosted_runners_denied": True,
                "verified_signature_certificate_present": True,
                "verified_timestamp_count": 1,
            }
        return summary(self.source_path), summary(self.receiver_path)

    def test_separate_host_records_reconstruct_one_causal_edge_without_clock_calibration(self) -> None:
        source_attestation, receiver_attestation = self.attestations()
        report = path.build_report(
            self.source,
            self.receiver,
            source_attestation=source_attestation,
            receiver_attestation=receiver_attestation,
            receiver_artifact_sha256=path.sha256_file(self.receiver_path),
            verifier_host=self.verifier_host,
        )
        self.assertEqual(report["causal_reconstruction"]["status"], "verified_from_independent_attested_host_records")
        self.assertEqual(report["causal_reconstruction"]["edge_count"], 1)
        self.assertEqual(
            report["causal_reconstruction"]["topological_order"],
            [
                self.source["operation_span"]["span_digest"],
                self.receiver["operation_span"]["span_digest"],
            ],
        )
        self.assertTrue(report["host_separation"]["distinct_jobs"])
        self.assertTrue(report["host_separation"]["distinct_temporal_actors"])
        self.assertTrue(report["host_separation"]["both_github_hosted"])
        self.assertTrue(report["host_separation"]["cross_os"])
        self.assertIsNone(report["duration"]["combined_cross_host_elapsed_ns"])
        self.assertEqual(
            report["duration"]["status"],
            "not_computed_independent_unaligned_clock_domains",
        )

    def test_source_record_digest_does_not_substitute_for_exact_artifact_binding(self) -> None:
        changed = copy.deepcopy(self.receiver)
        changed["source_record_sha256"] = "f" * 64
        core = {key: value for key, value in changed.items() if key != "record_digest"}
        changed["record_digest"] = path.digest_object(core)
        source_attestation, receiver_attestation = self.attestations()
        with self.assertRaisesRegex(path.EvidenceError, "attestation summary does not verify"):
            path.build_report(
                self.source,
                changed,
                source_attestation=source_attestation,
                receiver_attestation=receiver_attestation,
                receiver_artifact_sha256=path.sha256_file(self.receiver_path),
                verifier_host=self.verifier_host,
            )

    def test_rehashed_source_payload_forgery_is_rejected(self) -> None:
        forged = copy.deepcopy(self.source)
        forged["temporal_frame"]["causal"]["vector"][forged["host"]["actor_id"]] += 2
        core = {key: value for key, value in forged.items() if key != "record_digest"}
        forged["record_digest"] = path.digest_object(core)
        with self.assertRaisesRegex(path.EvidenceError, "handoff payload cannot be independently rebuilt"):
            path._validate_record(forged, "source_host")

    def test_crossed_run_identity_is_rejected(self) -> None:
        forged = copy.deepcopy(self.receiver)
        forged["host"]["run_attempt"] = "2"
        core = {key: value for key, value in forged.items() if key != "record_digest"}
        forged["record_digest"] = path.digest_object(core)
        source_attestation, receiver_attestation = self.attestations()
        with self.assertRaisesRegex(path.EvidenceError, "shared run field run_attempt"):
            path.build_report(
                self.source,
                forged,
                source_attestation=source_attestation,
                receiver_attestation=receiver_attestation,
                receiver_artifact_sha256=path.sha256_file(self.receiver_path),
                verifier_host=self.verifier_host,
            )

    def test_concurrent_vector_stamps_do_not_establish_precedence(self) -> None:
        forged = copy.deepcopy(self.receiver)
        source_actor = self.source["host"]["actor_id"]
        receiver_actor = forged["host"]["actor_id"]
        frame = copy.deepcopy(forged["temporal_frame"])
        frame["causal"] = {
            "actor_id": receiver_actor,
            "lamport": 10,
            "vector": {source_actor: 0, receiver_actor: 1},
        }
        forged["temporal_frame"] = frame
        forged["handoff_witness"] = path.build_causal_handoff_witness(
            payload=self.source["handoff_payload"],
            successor_span_digest=forged["operation_span"]["span_digest"],
            channel_id=path.RELAY_CHANNEL,
            message_sequence=1,
            received_sequence=1,
            receiver_start_frame=frame,
        )
        core = {key: value for key, value in forged.items() if key != "record_digest"}
        forged["record_digest"] = path.digest_object(core)
        source_attestation, receiver_attestation = self.attestations()
        with self.assertRaisesRegex(ValueError, "does not strictly follow"):
            path.build_report(
                self.source,
                forged,
                source_attestation=source_attestation,
                receiver_attestation=receiver_attestation,
                receiver_artifact_sha256=path.sha256_file(self.receiver_path),
                verifier_host=self.verifier_host,
            )

    def test_self_hosted_or_non_main_runner_context_is_refused(self) -> None:
        bad = runner_env("source_host", runner_name="untrusted")
        bad["RUNNER_ENVIRONMENT"] = "self-hosted"
        with self.assertRaisesRegex(path.EvidenceError, "GitHub-hosted"):
            path.host_metadata("source_host", bad)
        bad = runner_env("source_host", runner_name="untrusted")
        bad["GITHUB_REF"] = "refs/heads/feature"
        with self.assertRaisesRegex(path.EvidenceError, "on main"):
            path.host_metadata("source_host", bad)

    def test_attestation_command_pins_repo_workflow_ref_and_denies_self_hosted(self) -> None:
        command = path._attestation_command(self.source_path, "gh")
        self.assertIn("--repo", command)
        self.assertIn(path.REPOSITORY, command)
        self.assertIn("--signer-workflow", command)
        self.assertIn(path.SIGNER_WORKFLOW, command)
        self.assertIn("--source-ref", command)
        self.assertIn(path.SOURCE_REF, command)
        self.assertIn("--deny-self-hosted-runners", command)
        self.assertIn("--predicate-type", command)
        self.assertIn(path.PREDICATE_TYPE, command)

    def test_attestation_predicate_and_subject_are_both_checked(self) -> None:
        expected_predicate = path._predicate_for(self.source)
        statement = {
            "subject": [{"name": "host-a.json", "digest": {"sha256": path.sha256_file(self.source_path)}}],
            "predicateType": path.PREDICATE_TYPE,
            "predicate": expected_predicate,
        }
        output = [{
            "verificationResult": {
                "statement": statement,
                "signature": {"certificate": {"identity": "verified-by-cli"}},
                "verifiedTimestamps": [{"kind": "transparency-log"}],
            }
        }]
        from unittest.mock import CompletedProcess
        with patch.object(path, "_gh_version", return_value=(2, 104, 0)):
            with patch.object(
                path.subprocess,
                "run",
                return_value=CompletedProcess([], 0, json.dumps(output), ""),
            ) as run:
                result = path.verify_artifact_attestation(
                    self.source_path, self.source, "source_host"
                )
        self.assertTrue(result["verified"])
        self.assertTrue(result["verified_signature_certificate_present"])
        self.assertEqual(result["verified_timestamp_count"], 1)
        command = run.call_args.args[0]
        self.assertIn("--deny-self-hosted-runners", command)

        altered = copy.deepcopy(output)
        altered[0]["verificationResult"]["statement"]["predicate"]["role"] = "receiver_host"
        with patch.object(path, "_gh_version", return_value=(2, 104, 0)):
            with patch.object(
                path.subprocess,
                "run",
                return_value=CompletedProcess([], 0, json.dumps(altered), ""),
            ):
                with self.assertRaisesRegex(path.EvidenceError, "predicate does not match"):
                    path.verify_artifact_attestation(self.source_path, self.source, "source_host")

    def test_report_predicate_binds_third_verifier_and_exact_report_bytes(self) -> None:
        source_attestation, receiver_attestation = self.attestations()
        report = path.build_report(
            self.source,
            self.receiver,
            source_attestation=source_attestation,
            receiver_attestation=receiver_attestation,
            receiver_artifact_sha256=path.sha256_file(self.receiver_path),
            verifier_host=self.verifier_host,
        )
        report_path = self.root / "independent-report.json"
        predicate_path = self.root / "independent-report.predicate.json"
        path.write_json(report_path, report)
        predicate = path.write_report_predicate(
            report_path,
            predicate_path,
            runner_env("verifier_host", runner_name="verifier-vm", runner_os="macOS"),
        )
        self.assertEqual(predicate["schema"], "in-formation.independent-host-report-predicate/0.1")
        self.assertEqual(predicate["report_sha256"], path.sha256_file(report_path))
        self.assertEqual(predicate["report_digest"], report["report_digest"])
        self.assertEqual(predicate["job"], "verifier_host")
        self.assertEqual(predicate["actor_id"], self.verifier_host["actor_id"])
        self.assertEqual(
            predicate["source_record_sha256"],
            source_attestation["subject_sha256"],
        )
        self.assertEqual(
            predicate["receiver_record_sha256"],
            receiver_attestation["subject_sha256"],
        )
        self.assertEqual(
            json.loads(predicate_path.read_text(encoding="utf-8")),
            predicate,
        )

        altered = copy.deepcopy(report)
        altered["verifier"]["actor_id"] = "other-host"
        core = {key: value for key, value in altered.items() if key != "report_digest"}
        altered["report_digest"] = path.digest_object(core)
        path.write_json(report_path, altered)
        with self.assertRaisesRegex(path.EvidenceError, "does not match the current verifier"):
            path.write_report_predicate(
                report_path,
                predicate_path,
                runner_env("verifier_host", runner_name="verifier-vm", runner_os="macOS"),
            )

    def test_old_github_cli_is_rejected_before_attestation_verification(self) -> None:
        with patch.object(path, "_gh_version", return_value=(2, 101, 0)):
            with patch.object(path.subprocess, "run") as run:
                with self.assertRaisesRegex(path.EvidenceError, "2.103.3 or newer"):
                    path.verify_artifact_attestation(
                        self.source_path, self.source, "source_host"
                    )
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
