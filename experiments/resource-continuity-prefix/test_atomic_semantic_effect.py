"""RCP-003: real OS process death at every semantic/resource handoff cut.

All test cases use actual original VL-I observations, exact source-derived
processor and genuine E-CPU quorum journals (including the fork after a valid
generation-one state). A separate receiver database is the only effect
authority. It MUST NOT grant rights from a checkpoint or quorum proof alone.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from mailcpu.recovery_lineage import RecoveryLineageError
from temporal_meet import _quorum, _manifest, _bytes, successor_membership
from atomic_semantic_effect import (
    HandoffRefused, RESOURCE, create_workspace,load_workspace,
    open_receiver,seal_successor,continue_after_restart,navigation_for,
)

CUTS=("after_fork","after_freeze","after_seal","after_activate","after_effect",
      "before_activation_commit","before_effect_commit")


def _prepared(root:Path):
    """Two real valid but incompatible E-CPU gen-2 histories are already stored."""
    p=create_workspace(root)
    receiver=open_receiver(root)
    assert receiver.snapshot()["mode"]=="unprepared"
    assert p.evidence.meet["common_event_count"]==5
    return p,receiver


def _apply(receiver,p,*,root=None,context=None,epoch=2,
           operation_id="test-operation",nav=None):
    """Always supply a verified original VL-I mathematical navigation."""
    snap=receiver.snapshot()
    return receiver.apply(
        epoch=epoch,root=root if root is not None else snap["active_root"],
        context_digest=context if context is not None else snap["context_digest"],
        operation_id=operation_id,
        navigation=nav if nav is not None else navigation_for(receiver.path.parent),
    )


@pytest.mark.parametrize("cut",CUTS)
def test_hard_crash_at_every_durable_cut_recovers_without_duplicate_effect(
    tmp_path:Path,cut:str,
):
    """Original process dies; new process opens all journal/receiver state."""
    p,receiver=_prepared(tmp_path)
    worker=Path(__file__).with_name("atomic_handoff_crash_worker.py")
    child=subprocess.run(
        [sys.executable,str(worker),cut,str(tmp_path)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=25,
        check=False,
    )
    expected=71+CUTS.index(cut)
    assert child.returncode==expected,(child.stdout,child.stderr)
    reopened=open_receiver(tmp_path)
    before=reopened.snapshot()
    expected_mode={
        "after_fork":"unprepared","after_freeze":"frozen",
        "after_seal":"frozen","after_activate":"active",
        "after_effect":"active",
        "before_activation_commit":"frozen",
        "before_effect_commit":"active",
    }[cut]
    assert before["mode"]==expected_mode
    assert before["committed_effects"]==(1 if cut=="after_effect" else 0)
    assert before["old_fork_winner"] is None
    assert before["receiver_revision"]==(
        0 if cut=="after_fork" else
        1 if cut in ("after_freeze","after_seal","before_activation_commit") else 2
    )
    if cut in ("after_seal","after_activate","after_effect",
               "before_activation_commit","before_effect_commit"):
        fresh=_quorum(tmp_path/"new-members",
                       successor_membership(p.evidence.shared_manifest.digest))
        assert fresh.high_water()[0]==1
    else:
        assert not (tmp_path/"new-members").exists()
    # Every obsolete branch's root is refused on the same receiver, even
    # if an attacker substitutes its requested epoch with the new one.
    for old_root in (p.evidence.left_manifest.digest,p.evidence.right_manifest.digest):
        with pytest.raises(HandoffRefused):
            _apply(reopened,p,root=old_root,
                   context="0"*64,epoch=2,operation_id="stale-branch")
    # Recovery in THIS separate Python process must verify original stored
    # evidence and finish all remaining phases, without guessing a winner.
    completed=continue_after_restart(tmp_path)
    assert completed["effect"]["receiver_local_commit"] is True
    assert completed["effect"]["value"]==["6/1"]
    assert completed["effect"]["source_observed_at_navigation"] is False
    assert completed["effect"]["old_fork_winner_elected"] is False
    assert completed["snapshot"]["committed_effects"]==1
    assert completed["snapshot"]["receiver_revision"]==2
    # If the original died AFTER a committed effect but before ack, exactly
    # the same receipt must be replayed, never a second effect.
    assert continue_after_restart(tmp_path)["effect"]==completed["effect"]
    assert open_receiver(tmp_path).snapshot()["committed_effects"]==1


def test_new_quorum_validity_does_not_activate_effect_without_receiver_freeze(
    tmp_path:Path,
):
    p,receiver=_prepared(tmp_path)
    new_head=seal_successor(tmp_path,p)
    q=_quorum(tmp_path/"new-members",
              successor_membership(p.evidence.shared_manifest.digest))
    assert q.verify_state(new_head)
    with pytest.raises(HandoffRefused,match="not frozen"):
        receiver.activate(p,quorum=q,manifest=new_head)
    with pytest.raises(HandoffRefused):
        _apply(receiver,p,root=new_head.digest,context="0"*64)
    assert receiver.snapshot()["committed_effects"]==0


def test_frozen_receiver_does_not_accept_effect_before_quorum_seal(
    tmp_path:Path,
):
    p,receiver=_prepared(tmp_path)
    freeze=receiver.freeze(p)
    assert freeze["old_forks_effect_eligible"] is False
    m=successor_membership(p.evidence.shared_manifest.digest)
    q=_quorum(tmp_path/"new-members",m)
    proposed=_manifest(
        m,generation=1,predecessor=p.evidence.shared_manifest.digest,
        state=_bytes(p.evidence.meet["common_checkpoint"]),
    )
    with pytest.raises(HandoffRefused,match="quorum"):
        receiver.activate(p,quorum=q,manifest=proposed)
    with pytest.raises(HandoffRefused):
        _apply(receiver,p,root=proposed.digest,context=freeze["context_digest"])
    assert receiver.snapshot()["mode"]=="frozen"
    assert receiver.snapshot()["committed_effects"]==0


def test_tampered_source_payload_cannot_thaw_original_receiver(tmp_path:Path):
    p,receiver=_prepared(tmp_path)
    source=tmp_path/"fork-evidence.json"
    text=json.loads(source.read_text(encoding="utf8"))
    text["left_checkpoint"]["events"][2]["values"]=["999/1"]
    # Rehash no outer evidence? Current proof is independently grounded in
    # durable E-CPU quorum manifest + actual VL-I event chain.
    source.write_text(json.dumps(text),encoding="utf8")
    with pytest.raises(HandoffRefused,match="source|fork|checkpoint|independent"):
        receiver.freeze(load_workspace(tmp_path))
    assert receiver.snapshot()["mode"]=="unprepared"


def test_changed_fork_journals_do_not_activate_after_freeze(tmp_path:Path):
    p,receiver=_prepared(tmp_path)
    receiver.freeze(p)
    successor=seal_successor(tmp_path,p)
    journal=p.evidence.left_directory/"old-b.jsonl"
    journal.write_bytes(journal.read_bytes()+b'{"forged":"journal-tail"}\n')
    with pytest.raises(HandoffRefused,match="independent"):
        receiver.activate(
            p,quorum=_quorum(tmp_path/"new-members",
                             successor_membership(p.evidence.shared_manifest.digest)),
            manifest=successor,
        )
    assert receiver.snapshot()["mode"]=="frozen"
    assert receiver.snapshot()["committed_effects"]==0


def test_wrong_navigation_and_stale_semantic_capsule_are_refused(tmp_path:Path):
    p,receiver=_prepared(tmp_path)
    complete=continue_after_restart(tmp_path)
    assert receiver.snapshot()["committed_effects"]==1
    altered=deepcopy(navigation_for(tmp_path))
    altered["values"]=["999/1"]
    with pytest.raises((HandoffRefused,ValueError)):
        _apply(receiver,p,operation_id="forged-math",nav=altered)
    with pytest.raises(HandoffRefused):
        _apply(receiver,p,operation_id="wrong-context",context="0"*64)
    with pytest.raises(HandoffRefused):
        _apply(receiver,p,operation_id="wrong-root",root=p.evidence.left_manifest.digest)
    with pytest.raises(HandoffRefused):
        _apply(receiver,p,operation_id="wrong-epoch",epoch=True)
    with pytest.raises(HandoffRefused):
        _apply(receiver,p,operation_id="wrong-epoch",epoch=1)
    assert receiver.snapshot()["committed_effects"]==1
    assert complete["effect"]["navigation_digest"]==navigation_for(tmp_path)["navigation_digest"]


def test_concurrent_duplicate_effects_linearize_under_one_receiver(tmp_path:Path):
    _prepared(tmp_path)
    continue_after_restart(tmp_path)
    def invoke(_):
        r=open_receiver(tmp_path)
        return _apply(r,None,operation_id="concurrent-single-identity")
    with ThreadPoolExecutor(max_workers=6) as executor:
        observations=list(executor.map(invoke,range(18)))
    assert len({e["digest"] for e in observations})==1
    assert open_receiver(tmp_path).snapshot()["committed_effects"]==2
    r=open_receiver(tmp_path)
    with pytest.raises(HandoffRefused,match="conflicting"):
        # Same effect ID cannot be reused for a different, *valid* navigation.
        candidate=__import__("temporal_meet").initial_ground()
        r.apply(
            epoch=2,root=r.snapshot()["active_root"],
            context_digest=r.snapshot()["context_digest"],
            operation_id="concurrent-single-identity",
            navigation=candidate.navigate(
                "3/2",epoch_index=0,expected_head=candidate.head,
            ),
        )
    assert r.snapshot()["committed_effects"]==2


def test_receiver_itself_cannot_be_cloned_if_global_effect_uniqueness_is_claimed(
    tmp_path:Path,
):
    """Negative control: cloned destination storage creates two effect histories."""
    p,receiver=_prepared(tmp_path)
    complete=continue_after_restart(tmp_path)
    other=tmp_path/"copied-receiver.sqlite3"
    with sqlite3.connect(str(receiver.path)) as original, sqlite3.connect(str(other)) as replica:
        original.backup(replica)
    from atomic_semantic_effect import AtomicSemanticResourceReceiver
    policy=receiver.policy
    cloned=AtomicSemanticResourceReceiver(
        other,resource=RESOURCE,
        source_identity=policy["source_identity"],
        temporal_head=policy["temporal_head"],
        common_quorum_root=policy["common_quorum_root"],
        original_membership_digest=policy["original_membership"],
        successor_membership_digest=policy["successor_membership"],
    )
    a=_apply(receiver,p,operation_id="effect-A")
    b=_apply(cloned,p,operation_id="effect-B")
    assert a["digest"]!=b["digest"]
    assert receiver.snapshot()["committed_effects"]==cloned.snapshot()["committed_effects"]==2
    assert receiver.snapshot()["effect_history_digest"]!=cloned.snapshot()["effect_history_digest"]
    # The test deliberately proves a local DB, if copied, has no global
    # uniqueness property. This must not be represented as a passed global
    # safety guarantee.
