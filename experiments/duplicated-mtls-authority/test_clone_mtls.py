from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from clone_mtls import run_cloned_mtls_authority_experiment


def test_cloned_mtls_credentials_can_authorize_two_conflicting_local_quorums(tmp_path: Path) -> None:
    report = run_cloned_mtls_authority_experiment(
        tmp_path / "divergent",
        left_state="left-root-state",
        right_state="right-root-state",
    )

    assert report["classification"] == "duplicated_mtls_identity_split_brain"
    assert report["adjudication"] == "refuse_automatic_winner"
    assert report["winner"] is None
    assert report["shared_fixed_membership"] is True
    assert report["same_generation_and_predecessor"] is True
    assert report["generation"] == 1
    assert report["predecessor_digest"] == report["clusters"][0]["manifest"]["predecessor_digest"]
    assert report["conflicting_roots"] is True
    assert report["left_accepts_right_manifest"] is False
    assert report["right_accepts_left_manifest"] is False

    credentials = report["credential_clone"]
    assert credentials["left_and_right_owner_certificate_identical"] is True
    assert credentials["left_and_right_owner_private_key_identical"] is True
    assert credentials["left_and_right_member_certificates_identical"] is True
    assert credentials["certificates_are_ephemeral_test_credentials"] is True

    peer_authentication = report["peer_authentication"]
    assert peer_authentication["mechanism"] == "mutually-authenticated TLS 1.2+"
    assert peer_authentication["wrong_ca_trusted_but_wrong_dns_client_rejected"] is True
    assert peer_authentication["correct_owner_identity_remained_serviceable"] is True

    process_layout = report["process_layout"]
    assert process_layout["same_host_process_test"] is True
    assert process_layout["physical_fault_domain_separation_established"] is False
    assert process_layout["distinct_process_ids"] is True
    assert process_layout["process_count"] == 7

    for cluster in report["clusters"]:
        assert cluster["local_quorum_reconstructed"] is True
        assert cluster["prepare_members"] == ["A", "B", "C"]
        assert cluster["commit_members"] == ["A", "B", "C"]
        assert len(cluster["journal_reports"]) == 3
        assert all(item["journal_replay_verified"] for item in cluster["journal_reports"])
        assert cluster["local_high_water"]["root_digest"] == cluster["manifest_digest"]

    schema_path = Path(__file__).with_name("mtls-cloned-authority-report.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)


def test_same_state_under_cloned_credentials_is_not_misclassified_as_a_fork(tmp_path: Path) -> None:
    report = run_cloned_mtls_authority_experiment(
        tmp_path / "matching",
        left_state="same-state",
        right_state="same-state",
    )

    assert report["classification"] == "matching_duplicate_identity_views"
    assert report["adjudication"] == "no_fork_observed"
    assert report["winner"] is None
    assert report["conflicting_roots"] is False
    assert report["left_accepts_right_manifest"] is True
    assert report["right_accepts_left_manifest"] is True
    assert report["credential_clone"]["left_and_right_owner_certificate_identical"] is True
    assert report["credential_clone"]["left_and_right_owner_private_key_identical"] is True


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main(["-q", __file__]))
