"""RCP-002: nontrivial causal meet of real forked E-CPU/VL-I histories."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from mailcpu.recovery_lineage import RecoveryLineageError
from vli.temporal_intelligence import TemporalIntelligenceGround
from temporal_meet import (
    TemporalMeetRefused,_observe,_quorum,construct_real_temporal_quorum_fork,
    find_common_temporal_section,fork_ground,initial_ground,
    observe_new_environment,original_membership,reconstitute_semantic_interpreter,
    verify_forked_quorums,
)


def test_nontrivial_common_interpreter_preexists_quorum_fork(tmp_path:Path):
    evidence=construct_real_temporal_quorum_fork(tmp_path)
    verified=verify_forked_quorums(evidence)
    assert verified["common_temporal_events"]==5
    assert verified["global_winner"] is None
    assert verified["forked_quorum_roots"][0]!=verified["forked_quorum_roots"][1]
    assert verified["shared_quorum_root"]==evidence.shared_manifest.digest
    assert evidence.meet["qualified_processor"]["rate"]==["2/1"]
    assert evidence.meet["verified_interpolation"]["values"]==["6/1"]
    assert evidence.meet["verified_interpolation"]["expanded_trajectory_steps"]==0
    assert evidence.meet["discarded_left_events"]==1
    assert evidence.meet["discarded_right_events"]==1
    # Both branch quorums have a complete valid gen-2 proof, but neither
    # knows the other fork as its own authoritative high-water.
    left=_quorum(evidence.left_directory,evidence.original_membership)
    right=_quorum(evidence.right_directory,evidence.original_membership)
    with pytest.raises(RecoveryLineageError):
        left.verify_state(evidence.right_manifest)
    with pytest.raises(RecoveryLineageError):
        right.verify_state(evidence.left_manifest)


def test_new_process_reconstructs_same_interpreter_then_qualifies_new_epoch(tmp_path:Path):
    evidence=construct_real_temporal_quorum_fork(tmp_path)
    recovered,manifest=reconstitute_semantic_interpreter(evidence,tmp_path)
    assert recovered.identity==evidence.original_temporal_identity
    assert recovered.head==evidence.meet["common_head"]
    assert recovered.compile_epoch(0,expected_head=recovered.head)["rate"]==["2/1"]
    # A completely new source observation belongs to neither fork.
    continued=observe_new_environment(recovered)
    assert continued.identity==evidence.original_temporal_identity
    assert [e["status"] for e in continued.epochs]==[
        "QUALIFIED_SAMPLES_ONLY","QUALIFIED_SAMPLES_ONLY",
    ]
    assert continued.compile_epoch(0,expected_head=continued.head)["rate"]==["2/1"]
    assert continued.compile_epoch(1,expected_head=continued.head)["rate"]==["1/1"]
    assert continued.events[5]["values"]==["20/1"]
    assert continued.events[5]["host"]=="fresh-observer-host-C"
    assert continued.navigate(
        "5/2",epoch_index=0,expected_head=continued.head,
    )["values"]==["6/1"]
    assert manifest.incarnation==2
    assert manifest.predecessor_digest==evidence.shared_manifest.digest
    assert manifest.membership_digest!=evidence.original_membership.digest
    assert manifest.state_digest==evidence.shared_manifest.state_digest


def test_missing_prefix_payload_cannot_be_derived_from_hash(tmp_path:Path):
    evidence=construct_real_temporal_quorum_fork(tmp_path)
    mutated=deepcopy(evidence.meet)
    mutated["common_checkpoint"]["events"][3]["values"]=["999/1"]
    forged=replace(evidence,meet=mutated)
    with pytest.raises(TemporalMeetRefused,match="shared prefix"):
        reconstitute_semantic_interpreter(forged,tmp_path)
    # A hash makes a missing original state addressable, not reconstructable.


def test_external_common_head_is_required_not_an_untrusted_source_suggestion():
    original=initial_ground()
    a,b=fork_ground(original)
    with pytest.raises(TemporalMeetRefused,match="external causal witness"):
        find_common_temporal_section(
            a.checkpoint(),b.checkpoint(),
            expected_identity=original.identity,
            expected_left_head=a.head,expected_right_head=b.head,
            externally_pinned_common_head="0"*64,
        )


def test_rehashed_tampered_temporal_snapshot_refused_before_meet():
    original=initial_ground()
    left,right=fork_ground(original)
    bad=deepcopy(left.checkpoint())
    bad["events"][2]["values"]=["999/1"]
    # Rehash only the outer snapshot: source event digests still disagree with
    # VL-I's independent event-by-event exact causal replay.
    from vli.ground import _digest
    body={k:v for k,v in bad.items() if k!="checkpoint_digest"}
    bad["checkpoint_digest"]=_digest(bad["schema"],body)
    with pytest.raises(TemporalMeetRefused,match="checkpoint"):
        find_common_temporal_section(
            bad,right.checkpoint(),expected_identity=original.identity,
            expected_left_head=left.head,expected_right_head=right.head,
            externally_pinned_common_head=original.head,
        )


def test_same_numeric_environment_but_changed_observer_provenance_shortens_meet():
    original=TemporalIntelligenceGround("rcp002:source-identity-test")
    for i in range(4):
        _observe(original,i,2*i+1,host="original-observer")
    cloned=original.checkpoint()
    a=TemporalIntelligenceGround.restore(
        cloned,expected_head=original.head,expected_identity=original.identity)
    b=TemporalIntelligenceGround.restore(
        cloned,expected_head=original.head,expected_identity=original.identity)
    _observe(a,4,9,host="observer-A")
    _observe(b,4,9,host="observer-B")
    assert a.events[-1]["values"]==b.events[-1]["values"]
    assert a.events[-1]["digest"]!=b.events[-1]["digest"]
    meet=find_common_temporal_section(
        a.checkpoint(),b.checkpoint(),
        expected_identity=original.identity,
        expected_left_head=a.head,expected_right_head=b.head,
        externally_pinned_common_head=original.head,
    )
    assert meet["common_event_count"]==4
    assert meet["qualified_processor"]["rate"]==["2/1"]


def test_genuine_quorum_journal_tamper_cannot_create_common_predecessor(tmp_path:Path):
    e=construct_real_temporal_quorum_fork(tmp_path)
    journal=e.left_directory/"old-b.jsonl"
    journal.write_bytes(journal.read_bytes()+b'{"invented":"journal-entry"}\n')
    with pytest.raises((TemporalMeetRefused,RecoveryLineageError,ValueError)):
        verify_forked_quorums(e)


def test_new_quorum_cannot_select_disputed_branch_as_valid_prefix(tmp_path:Path):
    e=construct_real_temporal_quorum_fork(tmp_path)
    clone=replace(e,meet={
        **e.meet,
        "common_checkpoint":deepcopy(e.meet["common_checkpoint"]),
    })
    clone.meet["common_checkpoint"]["head"]="0"*64
    with pytest.raises(TemporalMeetRefused,match="shared prefix"):
        reconstitute_semantic_interpreter(clone,tmp_path)


def test_no_branch_is_elected_from_equal_owner_and_member_labels(tmp_path:Path):
    evidence=construct_real_temporal_quorum_fork(tmp_path)
    report=verify_forked_quorums(evidence)
    assert report["global_winner"] is None
    assert report["original_membership_digest"]==original_membership().digest
    assert evidence.left_manifest.owner_id==evidence.right_manifest.owner_id
    assert evidence.left_manifest.owner_term==evidence.right_manifest.owner_term
    assert evidence.left_manifest.generation==evidence.right_manifest.generation==2
