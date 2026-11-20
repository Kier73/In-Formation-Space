"""RCP-001: true cloned E-CPU quorum evidence with shared-prefix effect recovery.

This is not a mocked consensus certificate. Both forked source artifacts are
created by the existing IFS DAD-001 producer, which invokes E-CPU's actual
RecoveryLineageCoordinator and persists six separate authority journals.
The receiver independently reopens and checks all of them before quarantine.
A new and DIFFERENT E-CPU quorum must then seal the genuine shared seed bytes
before an effect can be committed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import sqlite3

import pytest

from fork_detection import (
    GENESIS,configured_membership,observe_two_clusters,produce_cluster,
)
from mailcpu.recovery_lineage import (
    RecoveryLineageAuthority,RecoveryLineageCoordinator,RecoveryStateManifest,
)
from receiver import (
    ForkContinuityRefused,ForkSafeEffectReceiver,SEED,successor_membership,
)

RESOURCE="/ifs/ground/continuous-effect"


def forked(root:Path,*,same:bool=False):
    """Create real separate durable quorum histories with copied identities."""
    left=root/"left"
    right=root/"right"
    produce_cluster(left,cluster_id="left",state_label="same" if same else "branch-left")
    produce_cluster(right,cluster_id="right",state_label="same" if same else "branch-right")
    return left,right


def resource(root:Path, *, name=RESOURCE)->ForkSafeEffectReceiver:
    return ForkSafeEffectReceiver(
        root/"receiver.db",resource=name,
        old_membership_digest=configured_membership().digest,
        new_membership_digest=successor_membership().digest,
    )


def new_quorum(root:Path, *, state_bytes=SEED):
    """Seal a real successor incarnation in fresh independently owned journals."""
    membership=successor_membership()
    path=root/"replacement-authority"
    path.mkdir(parents=True,exist_ok=True)
    authorities={
        member:RecoveryLineageAuthority(
            membership,member,path/(member+".jsonl"),
        )
        for member in membership.member_ids
    }
    quorum=RecoveryLineageCoordinator(membership,authorities)
    manifest=RecoveryStateManifest(
        machine_id=membership.system_id,incarnation=membership.incarnation,
        owner_id=membership.owner_id,owner_term=membership.owner_term,
        membership_digest=membership.digest,generation=1,
        predecessor_digest=GENESIS,
        state_digest=sha256(state_bytes).hexdigest(),
        capture_cut="after_response_publish",
    )
    proof=quorum.seal(manifest)
    assert quorum.high_water()==(1,manifest.digest)
    assert quorum.verify_state(manifest).snapshot()==proof.snapshot()
    return membership,quorum,manifest


def test_cloned_identity_has_no_automatic_effect_eligibility(tmp_path:Path):
    left,right=forked(tmp_path)
    observation=observe_two_clusters(left,right)
    assert observation["classification"]=="cloned_membership_split_brain"
    assert observation["winner"] is None
    assert observation["each_cluster_reconstructed_its_own_quorum"] is True
    receiver=resource(tmp_path)
    for branch in observation["clusters"]:
        with pytest.raises(ForkContinuityRefused,match="stale|cloned|reconstituted"):
            receiver.apply(epoch=1,root=branch["root_digest"],
                           operation_id="old-branch",value=1)
    witness=receiver.observe_and_freeze(left,right)
    assert witness["common_prefix"]==GENESIS
    assert witness["globally_legitimate_winner"] is None
    assert witness["automatic_winner_selected"] is False
    assert receiver.snapshot()["mode"]=="quarantined"
    for branch in observation["clusters"]:
        with pytest.raises(ForkContinuityRefused,match="stale|cloned|reconstituted"):
            receiver.apply(epoch=1,root=branch["root_digest"],
                           operation_id="late-"+branch["cluster_id"],value=13)
    assert receiver.snapshot()["committed_effect_count"]==0


def test_reconstruct_only_shared_seed_and_reconstitute_new_verified_quorum(tmp_path:Path):
    left,right=forked(tmp_path)
    receiver=resource(tmp_path)
    receiver.observe_and_freeze(left,right)
    assert sha256(SEED).hexdigest()==GENESIS
    membership,quorum,manifest=new_quorum(tmp_path)
    qualified=receiver.reconstitute(
        checkpoint_bytes=SEED,membership=membership,
        coordinator=quorum,manifest=manifest,
    )
    assert qualified["epoch"]==2
    assert qualified["status"]=="reconstituted_from_common_prefix"
    assert qualified["old_fork_still_has_no_global_winner"] is True
    answer=receiver.apply(
        epoch=2,root=manifest.digest,operation_id="new-host-effect",
        value=41,
    )
    assert answer["receiver_local_commit"] is True
    assert answer["physical_host_attested"] is False
    assert answer["global_quorum_winner_proven"] is False
    assert receiver.apply(epoch=2,root=manifest.digest,
                          operation_id="new-host-effect",value=41)==answer
    recovered=resource(tmp_path)
    assert recovered.snapshot()["committed_effect_count"]==1
    assert recovered.snapshot()["global_fork_winner"] is None
    old=observe_two_clusters(left,right)["clusters"]
    for branch in old:
        with pytest.raises(ForkContinuityRefused):
            recovered.apply(epoch=1,root=branch["root_digest"],
                            operation_id="old-after-restart",value=99)
        with pytest.raises(ForkContinuityRefused):
            recovered.apply(epoch=2,root=branch["root_digest"],
                            operation_id="forged-new-epoch",value=99)
    with pytest.raises(ForkContinuityRefused,match="conflicting"):
        recovered.apply(epoch=2,root=manifest.digest,
                        operation_id="new-host-effect",value=42)
    assert recovered.snapshot()["committed_effect_count"]==1


def test_genuine_checkpoint_bytes_are_required_not_merely_matching_authority_labels(tmp_path:Path):
    left,right=forked(tmp_path)
    owner=resource(tmp_path)
    owner.observe_and_freeze(left,right)
    membership,quorum,manifest=new_quorum(tmp_path,state_bytes=b"branch-right")
    with pytest.raises(ForkContinuityRefused,match="checkpoint|common"):
        owner.reconstitute(checkpoint_bytes=b"branch-right",
                           membership=membership,coordinator=quorum,
                           manifest=manifest)
    with pytest.raises(ForkContinuityRefused,match="new root"):
        owner.reconstitute(checkpoint_bytes=SEED,
                           membership=membership,coordinator=quorum,
                           manifest=manifest)
    assert owner.snapshot()["mode"]=="quarantined"


def test_mismatched_or_absent_external_continuation_cannot_thaw_fork(tmp_path:Path):
    left,right=forked(tmp_path)
    owner=resource(tmp_path)
    owner.observe_and_freeze(left,right)
    membership,quorum,manifest=new_quorum(tmp_path)
    with pytest.raises(ForkContinuityRefused):
        owner.reconstitute(checkpoint_bytes=SEED,
                           membership=configured_membership(),
                           coordinator=quorum,manifest=manifest)
    with pytest.raises(ForkContinuityRefused,match="immutable"):
        resource(tmp_path,name="/ifs/other-resource")
    # Proof correctness at old membership is not authority to thaw the
    # receiver's explicitly different, separately installed trust root.
    assert owner.snapshot()["mode"]=="quarantined"


def test_repeated_fork_freeze_is_idempotent_but_conflicting_fork_is_refused(tmp_path:Path):
    left,right=forked(tmp_path)
    owner=resource(tmp_path)
    first=owner.observe_and_freeze(left,right)
    assert owner.observe_and_freeze(left,right)==first
    changed_left=tmp_path/"other-left"
    changed_right=tmp_path/"other-right"
    produce_cluster(changed_left,cluster_id="left",state_label="different-L")
    produce_cluster(changed_right,cluster_id="right",state_label="different-R")
    with pytest.raises(ForkContinuityRefused,match="cannot replace"):
        owner.observe_and_freeze(changed_left,changed_right)
    assert owner.snapshot()["receiver_revision"]==1


def test_identical_clones_are_not_mistaken_for_a_fork(tmp_path:Path):
    left,right=forked(tmp_path,same=True)
    assert observe_two_clusters(left,right)["conflicting_roots"] is False
    with pytest.raises(ForkContinuityRefused,match="no qualified common-prefix"):
        resource(tmp_path).observe_and_freeze(left,right)


def test_concurrent_effects_are_serialized_and_idempotent_across_observers(tmp_path:Path):
    left,right=forked(tmp_path)
    owner=resource(tmp_path)
    owner.observe_and_freeze(left,right)
    member,quorum,manifest=new_quorum(tmp_path)
    owner.reconstitute(checkpoint_bytes=SEED,membership=member,
                       coordinator=quorum,manifest=manifest)
    def invoke(_):
        reopened=resource(tmp_path)
        return reopened.apply(
            epoch=2,root=manifest.digest,operation_id="only-once",
            value=7,
        )
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(invoke,range(24)))
    assert len({r["digest"] for r in results})==1
    assert owner.snapshot()["committed_effect_count"]==1


def test_cloning_the_effect_receiver_itself_destroys_global_uniqueness(tmp_path:Path):
    """Important negative control: no single external authority if it is copied."""
    left,right=forked(tmp_path)
    one=resource(tmp_path)
    one.observe_and_freeze(left,right)
    m,q,h=new_quorum(tmp_path)
    one.reconstitute(checkpoint_bytes=SEED,membership=m,coordinator=q,manifest=h)
    clone_path=tmp_path/"cloned-resource.db"
    with sqlite3.connect(str(one.path)) as src, sqlite3.connect(str(clone_path)) as dst:
        src.backup(dst)
    clone=ForkSafeEffectReceiver(
        clone_path,resource=RESOURCE,
        old_membership_digest=configured_membership().digest,
        new_membership_digest=successor_membership().digest,
    )
    one.apply(epoch=2,root=h.digest,operation_id="domain-A",value=1)
    clone.apply(epoch=2,root=h.digest,operation_id="domain-B",value=2)
    assert one.snapshot()["effect_history_digest"]!=clone.snapshot()["effect_history_digest"]
    assert one.snapshot()["committed_effect_count"]==clone.snapshot()["committed_effect_count"]==1
    # Do not interpret either cloned receiver ledger as globally exclusive.


def test_effect_witness_never_uses_python_numeric_type_aliases(tmp_path:Path):
    left,right=forked(tmp_path)
    owner=resource(tmp_path)
    owner.observe_and_freeze(left,right)
    m,q,h=new_quorum(tmp_path)
    owner.reconstitute(checkpoint_bytes=SEED,membership=m,coordinator=q,manifest=h)
    for changed in (True,2.0):
        with pytest.raises(ForkContinuityRefused):
            owner.apply(epoch=changed,root=h.digest,operation_id="bad-epoch",value=1)
    for changed in (True,1.0):
        with pytest.raises(ForkContinuityRefused):
            owner.apply(epoch=2,root=h.digest,operation_id="bad-value",value=changed)
    assert owner.snapshot()["committed_effect_count"]==0
