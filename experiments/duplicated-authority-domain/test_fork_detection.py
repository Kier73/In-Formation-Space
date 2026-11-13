from __future__ import annotations

import json
from pathlib import Path

import pytest

from fork_detection import (
    ForkDetectionError,
    observe_two_clusters,
    produce_cluster,
)


def make_clusters(root: Path, *, left_state="state-left", right_state="state-right"):
    left = root / "left"
    right = root / "right"
    produce_cluster(left, cluster_id="left", state_label=left_state)
    produce_cluster(right, cluster_id="right", state_label=right_state)
    return left, right


def test_two_isolated_copies_can_commit_conflicting_roots_under_identical_membership(tmp_path):
    left, right = make_clusters(tmp_path)
    report = observe_two_clusters(left, right)

    assert report["classification"] == "cloned_membership_split_brain"
    assert report["adjudication"] == "refuse_automatic_winner"
    assert report["shared_fixed_membership"] is True
    assert report["same_generation_and_predecessor"] is True
    assert report["generation"] == 1
    from fork_detection import GENESIS
    assert report["predecessor_digest"] == GENESIS
    assert report["conflicting_roots"] is True
    assert report["each_cluster_reconstructed_its_own_quorum"] is True
    assert report["left_rejects_right_manifest"] is True
    assert report["right_rejects_left_manifest"] is True
    assert report["winner"] is None
    assert report["physical_fault_domain_separation_established"] is False
    assert report["producer_attestations_verified_by_github"] is False

    for cluster in report["clusters"]:
        assert cluster["prepare_members"] == [
            "authority-a",
            "authority-b",
            "authority-c",
        ]
        assert cluster["commit_members"] == [
            "authority-a",
            "authority-b",
            "authority-c",
        ]
        assert cluster["local_quorum_reconstructed"] is True
        assert len(cluster["journal_reports"]) == 3
        assert all(row["replay_verified"] for row in cluster["journal_reports"])


def test_identical_successor_in_two_isolated_copies_is_not_misclassified_as_fork(tmp_path):
    left, right = make_clusters(
        tmp_path,
        left_state="same-state",
        right_state="same-state",
    )
    report = observe_two_clusters(left, right)
    assert report["classification"] == "matching_duplicate_authority_views"
    assert report["adjudication"] == "no_fork_observed"
    assert report["shared_fixed_membership"] is True
    assert report["conflicting_roots"] is False
    assert report["left_rejects_right_manifest"] is False
    assert report["right_rejects_left_manifest"] is False
    assert report["winner"] == "not_applicable"


def test_changed_journal_bytes_are_rejected_before_fork_classification(tmp_path):
    left, right = make_clusters(tmp_path)
    journal = left / "authorities" / "authority-b.jsonl"
    journal.write_bytes(journal.read_bytes() + b'{"unauthorized":"tail"}\n')
    with pytest.raises(ForkDetectionError, match="bytes differ"):
        observe_two_clusters(left, right)


def test_mixing_one_journal_from_the_other_copy_does_not_form_either_local_quorum(tmp_path):
    left, right = make_clusters(tmp_path)
    source = right / "authorities" / "authority-c.jsonl"
    destination = left / "authorities" / "authority-c.jsonl"
    destination.write_bytes(source.read_bytes())
    bundle = json.loads((left / "bundle.json").read_text(encoding="utf-8"))
    row = next(item for item in bundle["journal_evidence"] if item["member_id"] == "authority-c")
    row["sha256"] = __import__("hashlib").sha256(destination.read_bytes()).hexdigest()
    row["size_bytes"] = destination.stat().st_size
    # Recompute the bundle's public digest: the observer must reject the
    # participant journal on its own membership/chain semantics, not merely
    # because the outer document was left stale.
    from fork_detection import digest, write_json

    core = {key: value for key, value in bundle.items() if key != "bundle_digest"}
    bundle["bundle_digest"] = digest(core)
    write_json(left / "bundle.json", bundle)
    with pytest.raises(ForkDetectionError):
        observe_two_clusters(left, right)


def test_bundle_hash_cannot_be_recomputed_around_a_forged_quorum_proof(tmp_path):
    left, right = make_clusters(tmp_path)
    bundle_path = left / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["proof"]["proposal"]["result_state_digest"] = "f" * 64
    from fork_detection import digest, write_json

    core = {key: value for key, value in bundle.items() if key != "bundle_digest"}
    bundle["bundle_digest"] = digest(core)
    write_json(bundle_path, bundle)
    with pytest.raises(ForkDetectionError):
        observe_two_clusters(left, right)


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-q", __file__]))
