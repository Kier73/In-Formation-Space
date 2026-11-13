from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

import reconstruct as experiment


def runner_env(role: str, *, runner_name: str | None = None, runner_os: str = "Linux") -> dict[str, str]:
    return {
        "GITHUB_REPOSITORY": experiment.REPOSITORY,
        "GITHUB_JOB": role,
        "GITHUB_WORKFLOW_REF": f"{experiment.SIGNER_WORKFLOW}@{experiment.SOURCE_REF}",
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_REF": experiment.SOURCE_REF,
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "123456789",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_NUMBER": "42",
        "RUNNER_NAME": runner_name or f"runner-{role}",
        "RUNNER_OS": runner_os,
        "RUNNER_ARCH": "X64",
        "RUNNER_ENVIRONMENT": "github-hosted",
    }


def attestation_summary(path: Path) -> dict[str, object]:
    return {
        "verified": True,
        "subject_sha256": experiment.sha256_file(path),
        "predicate_type": experiment.RECORD_PREDICATE_TYPE,
        "signer_workflow": experiment.SIGNER_WORKFLOW,
        "source_ref": experiment.SOURCE_REF,
        "self_hosted_runners_denied": True,
        "verified_signature_certificate_present": True,
        "verified_timestamp_count": 1,
    }


class MultiObserverCausalReconstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source_path = self.root / "source.json"
        self.receiver_path = self.root / "receiver.json"
        self.observer_path = self.root / "observer.json"

        self.source = experiment.produce_source(
            self.source_path,
            runner_env("source_host"),
        )

        def verify_source(path, record, role, *, gh="gh"):
            self.assertEqual(role, "source_host")
            return attestation_summary(path)

        self.receiver = experiment.produce_receiver(
            self.source_path,
            self.receiver_path,
            runner_env("receiver_host", runner_os="Windows"),
            attestation_verifier=verify_source,
        )
        self.observer = experiment.produce_observer(
            self.observer_path,
            runner_env("observer_host", runner_os="macOS"),
        )
        self.verifier = experiment.host_metadata(
            "verifier_host",
            runner_env("verifier_host", runner_os="Linux"),
        )
        self.attestations = {
            "source_host": attestation_summary(self.source_path),
            "receiver_host": attestation_summary(self.receiver_path),
            "observer_host": attestation_summary(self.observer_path),
        }
        self.artifact_sha256 = {
            "source_host": experiment.sha256_file(self.source_path),
            "receiver_host": experiment.sha256_file(self.receiver_path),
            "observer_host": experiment.sha256_file(self.observer_path),
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def report(self):
        return experiment.build_report(
            self.source,
            self.receiver,
            self.observer,
            attestations=self.attestations,
            artifact_sha256=self.artifact_sha256,
            verifier_host=self.verifier,
        )

    def test_reconstructs_precedence_concurrency_and_unobserved_pairs(self) -> None:
        report = self.report()
        observed = {
            (pair["left_event_id"], pair["right_event_id"]): pair["causal_status"]
            for pair in report["pairwise_relations"]
        }
        self.assertEqual(observed, {
            ("A1", "A2"): "before",
            ("A1", "B1"): "before",
            ("A1", "C1"): "unobserved",
            ("A2", "B1"): "concurrent",
            ("A2", "C1"): "unobserved",
            ("B1", "C1"): "unobserved",
        })
        self.assertEqual(
            report["causal_summary"]["pair_status_counts"],
            {"before": 2, "after": 0, "equal": 0, "concurrent": 1, "unobserved": 3},
        )
        self.assertIsNone(report["causal_summary"]["global_total_order"])

    def test_a2_is_not_part_of_the_transferred_a1_payload(self) -> None:
        payload = self.source["handoff_payload"]
        self.assertEqual(
            payload["predecessor_span_digest"],
            self.source["events"][0]["operation_span"]["span_digest"],
        )
        self.assertEqual(payload["sender_completion_frame"], self.source["events"][0]["temporal_frame"])
        self.assertNotEqual(
            payload["predecessor_span_digest"],
            self.source["events"][1]["operation_span"]["span_digest"],
        )
        self.assertEqual(self.receiver["handoff_witness"]["predecessor_span_digest"], payload["predecessor_span_digest"])

    def test_missing_causal_stamp_is_unobserved_not_concurrent(self) -> None:
        c1 = self.observer["events"][0]["temporal_frame"]
        self.assertIsNone(c1["causal"])
        report = self.report()
        involving_c1 = [
            pair for pair in report["pairwise_relations"]
            if "C1" in (pair["left_event_id"], pair["right_event_id"])
        ]
        self.assertEqual(len(involving_c1), 3)
        self.assertTrue(all(pair["causal_status"] == "unobserved" for pair in involving_c1))
        self.assertFalse(any(pair["causal_status"] == "concurrent" for pair in involving_c1))

    def test_wall_offsets_are_retained_but_never_used_for_causal_order(self) -> None:
        report = self.report()
        offsets = report["wall_clock"]["configured_offsets_ns"]
        self.assertEqual(offsets, experiment.WALL_OFFSETS_NS)
        self.assertEqual(len(set(offsets.values())), 3)
        self.assertFalse(report["wall_clock"]["used_for_causal_order"])
        self.assertTrue(all(not sample["used_for_causal_order"] for sample in report["wall_clock"]["samples"]))
        self.assertTrue(all(pair["wall_status"] == "not_used" for pair in report["pairwise_relations"]))

    def test_local_durations_remain_separate_and_combined_duration_is_null(self) -> None:
        report = self.report()
        durations = report["duration"]["local_operation_durations"]
        self.assertEqual({item["event_id"] for item in durations}, {"A1", "A2", "B1", "C1"})
        self.assertEqual(len({item["actor_id"] for item in durations}), 3)
        self.assertTrue(all(item["elapsed_ns"] >= 0 for item in durations))
        self.assertIsNone(report["duration"]["combined_cross_host_elapsed_ns"])
        self.assertEqual(
            report["duration"]["combined_duration_status"],
            "not_computed_independent_unaligned_clock_domains",
        )

    def test_receiver_must_bind_exact_source_artifact_bytes(self) -> None:
        altered = copy.deepcopy(self.receiver)
        altered["source_record_sha256"] = "f" * 64
        core = {key: value for key, value in altered.items() if key != "record_digest"}
        altered["record_digest"] = experiment.digest_object(core)
        with self.assertRaisesRegex(experiment.ReconstructionError, "exact source artifact"):
            experiment.build_report(
                self.source,
                altered,
                self.observer,
                attestations=self.attestations,
                artifact_sha256=self.artifact_sha256,
                verifier_host=self.verifier,
            )

    def test_tampered_record_digest_is_rejected(self) -> None:
        altered = copy.deepcopy(self.source)
        altered["events"][1]["temporal_frame"]["wall"]["utc_ns"] += 1
        with self.assertRaisesRegex(experiment.ReconstructionError, "record digest"):
            experiment.validate_record(altered, "source_host")

    def test_tampered_handoff_witness_is_rejected(self) -> None:
        altered = copy.deepcopy(self.receiver)
        altered["handoff_witness"]["message_sequence"] += 1
        core = {key: value for key, value in altered.items() if key != "record_digest"}
        altered["record_digest"] = experiment.digest_object(core)
        with self.assertRaisesRegex(ValueError, "handoff digest"):
            experiment.build_report(
                self.source,
                altered,
                self.observer,
                attestations=self.attestations,
                artifact_sha256=self.artifact_sha256,
                verifier_host=self.verifier,
            )

    def test_four_roles_must_have_distinct_temporal_actors(self) -> None:
        altered_verifier = copy.deepcopy(self.verifier)
        altered_verifier["actor_id"] = self.source["host"]["actor_id"]
        with self.assertRaisesRegex(experiment.ReconstructionError, "actor ID is not bound"):
            experiment.build_report(
                self.source,
                self.receiver,
                self.observer,
                attestations=self.attestations,
                artifact_sha256=self.artifact_sha256,
                verifier_host=altered_verifier,
            )

    def test_report_predicate_binds_report_bytes_and_all_three_records(self) -> None:
        report = self.report()
        report_path = self.root / "report.json"
        predicate_path = self.root / "report.predicate.json"
        experiment.write_json(report_path, report)
        predicate = experiment.write_report_predicate(
            report_path, predicate_path, runner_env("verifier_host")
        )
        self.assertEqual(predicate["schema"], experiment.REPORT_PREDICATE_SCHEMA)
        self.assertEqual(predicate["report_sha256"], experiment.sha256_file(report_path))
        self.assertEqual(predicate["report_digest"], report["report_digest"])
        self.assertEqual(set(predicate["producer_record_sha256"]), set(experiment.PRODUCER_ROLES))
        self.assertEqual(
            predicate["producer_record_sha256"]["source_host"],
            self.artifact_sha256["source_host"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
