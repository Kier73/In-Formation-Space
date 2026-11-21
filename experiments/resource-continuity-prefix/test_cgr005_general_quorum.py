"""CGR-005: original E-CPU majority and original IPS-008 after general NCR stage.

Source is a synthetic deterministic *observed* finite system; all native
execution, TLS, quorum, SQLite and independent-process recovery are real.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
from time import monotonic,sleep

import pytest

from mailcpu.fenced_effect_receiver import EffectFencingRefused,published_effect
from mailcpu.fenced_generated_ground import FencedGroundCandidate
from mailcpu.recovery_lineage import RecoveryLineageError
from mailcpu.semantic_translation import canonical_value_digest
from test_effect_receiver_service import _client,_kill
from test_fenced_generated_ground import _receiver,_restart
from test_recovery_lineage_service import _make_certificates

from cgr003_observed_ecpu import persist_epoch
from cgr004_language_hypervisor import qualify_finite_host
from cgr005_general_quorum import (
    GeneralGroundLineage,GeneralGroundRefused,RESOURCE,open_general,
)
from test_cgr004_language_hypervisor import non_affine_epoch

WORKER=Path(__file__).resolve().with_name("cgr005_receiver_worker.py")


def epoch():
    return replace(non_affine_epoch(),initial=tuple(range(6)),
                   context="cgr005-qualified-continuous-six-state-epoch")


def selected_host(root:Path,name:str):
    source=epoch()
    return qualify_finite_host(root,name,expected_head=source.source_head,
                               allowed_hosts=frozenset({
                                   "cgr005-old-host","cgr005-replacement-host",
                                   "cgr005-third-host",
                               }))


def bootstrap(root:Path):
    source=epoch()
    persist_epoch(root,source)
    lineage=open_general(root)
    os,identity,envelope,ground,pid=_receiver()
    head=lineage.bootstrap(identity,ground)
    assert len(head.checkpoint["payload"]["stages"])==0
    return lineage,head,os,envelope,pid


def start(root:Path,certificates:dict):
    marker=root/"cgr005-ready.json"
    marker.unlink(missing_ok=True)
    process=subprocess.Popen([
        sys.executable,str(WORKER),str(root),
        str(certificates["B_cert"]),str(certificates["B_key"]),
        str(certificates["ca"]),str(marker),"owner-a.mailcpu.test",
    ],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=monotonic()+18
        while monotonic()<deadline:
            if marker.exists():
                return process,json.loads(marker.read_text(encoding="ascii"))
            if process.poll() is not None:
                out,err=process.communicate(timeout=4)
                raise AssertionError("original IPS-008 receiver startup refused: "+err[-2400:]+out[-400:])
            sleep(.025)
        raise AssertionError("mTLS native receiver not ready")
    except BaseException:
        _kill(process)
        raise


def test_exact_native_dag_checkpoint_survives_independent_reconstruction(tmp_path):
    lineage,head,os,envelope,pid=bootstrap(tmp_path)
    old=selected_host(tmp_path,"cgr005-old-host")
    assigned=lineage.assign(head,old)
    candidate=lineage.compute(assigned,old,os,pid)
    original=lineage.publish(assigned,candidate)
    assert original.checkpoint["payload"]["stages"][0]["stage_receipt"]["output"]["value"]==3
    assert original.checkpoint["payload"]["stages"][0]["hypervisor_effect"]["operator_id"]=="cgr004.qualified_finite_word"
    assert lineage._session(original.checkpoint).dag.result("ips003.stage.000")["value"]==3

    recovered=open_general(tmp_path)
    reopened=recovered.restore_latest()
    assert reopened.manifest.digest==original.manifest.digest
    assert recovered._session(reopened.checkpoint).value==3
    assert recovered._session(reopened.checkpoint).dag.snapshot()==original.checkpoint["payload"]["dag_snapshot"]
    # Historical worker is neither available nor invoked during reconstruction.
    second=selected_host(tmp_path,"cgr005-replacement-host")
    successor=recovered.assign(reopened,second)
    new_os,new_pid=_restart(envelope)
    moved=recovered.compute(successor,second,new_os,new_pid)
    published=recovered.publish(successor,moved)
    session=recovered._session(published.checkpoint)
    assert session.complete and session.value==4
    assert session.dag.result("ips003.stage.001")["input"]==3
    assert session.dag.result("ips003.stage.001")["value"]==4
    assert [x["host"] for x in session.stages]==["cgr005-old-host","cgr005-replacement-host"]


def test_rehashed_false_general_ground_checkpoint_is_rejected(tmp_path):
    lineage,head,os,envelope,pid=bootstrap(tmp_path)
    old=selected_host(tmp_path,"cgr005-old-host")
    assigned=lineage.assign(head,old)
    candidate=lineage.compute(assigned,old,os,pid)
    forged=deepcopy(candidate.next_checkpoint)
    record=forged["payload"]["stages"][0]
    # Attempt a false output plus rehashing of the stage and the parent.
    record["stage_receipt"]["output"]["value"]=5
    altered={k:v for k,v in record["stage_receipt"].items()
             if k!="receipt_digest"}
    record["stage_receipt"]["receipt_digest"]=canonical_value_digest(altered)
    forged["digest"]=canonical_value_digest(forged["payload"])
    with pytest.raises(GeneralGroundRefused):
        lineage.publish(assigned,replace(candidate,next_checkpoint=forged))
    assert lineage.restore_latest().manifest.digest==assigned.manifest.digest


def test_source_revision_and_stale_host_cannot_publish(tmp_path):
    lineage,head,os,envelope,pid=bootstrap(tmp_path)
    old=selected_host(tmp_path,"cgr005-old-host")
    replacement=selected_host(tmp_path,"cgr005-replacement-host")
    assigned=lineage.assign(head,old)
    slow=lineage.compute(assigned,old,os,pid)
    moved=lineage.assign(assigned,replacement)
    with pytest.raises((RecoveryLineageError,GeneralGroundRefused)):
        lineage.publish(assigned,slow)
    restarted=open_general(tmp_path)
    assert restarted.restore_latest().manifest.digest==moved.manifest.digest
    successor_os,successor_pid=_restart(envelope)
    accepted=restarted.compute(moved,replacement,successor_os,successor_pid)
    published=restarted.publish(moved,accepted)
    assert restarted._session(published.checkpoint).value==3
    # The native majority high-water check rejects the stale assignment
    # before the adapter's host-specific admission check is reached.
    with pytest.raises((RecoveryLineageError,GeneralGroundRefused)):
        restarted.compute(moved,old,successor_os,successor_pid)


@pytest.mark.skipif(shutil.which("openssl") is None,
                    reason="original E-CPU test TLS certificates require OpenSSL")
def test_nonaffine_original_mtls_receiver_effect_handoff_and_crash(tmp_path):
    lineage,head,os,envelope,pid=bootstrap(tmp_path)
    old=selected_host(tmp_path,"cgr005-old-host")
    assigned=lineage.assign(head,old)
    first=lineage.publish(assigned,lineage.compute(assigned,old,os,pid))
    assert first.checkpoint["payload"]["stages"][0]["stage_receipt"]["output"]["value"]==3
    old_effect=published_effect(first,RESOURCE)
    certificates=_make_certificates(tmp_path)
    proc,info=start(tmp_path,certificates)
    recovered_proc=None
    try:
        owner=_client(info,certificates)
        initial_install=owner.activate(first.manifest.digest)
        assert initial_install["event"]=="publish"
        assert owner.apply(old_effect)["value"]==3

        next_host=selected_host(tmp_path,"cgr005-replacement-host")
        barrier=owner.prepare(first.manifest.digest,next_host.host_id)
        assert barrier["target_host"]==next_host.host_id
        assert barrier["target_epoch"]==2
        with pytest.raises(EffectFencingRefused):
            owner.apply(old_effect)
        _kill(proc)

        # Receiver restarts with its original source policy and durable freeze,
        # BEFORE the quorum has issued the next root.
        recovered_proc,info2=start(tmp_path,certificates)
        owner2=_client(info2,certificates)
        snapshot=owner2.snapshot()
        assert snapshot["pending_handoff_digest"]==barrier["barrier_digest"]
        with pytest.raises(EffectFencingRefused):
            owner2.apply(old_effect)

        publisher=open_general(tmp_path)
        current=publisher.restore_latest()
        assert current.manifest.digest==first.manifest.digest
        successor=publisher.assign(current,next_host)
        assigned_install=owner2.activate(successor.manifest.digest)
        assert assigned_install["event"]=="assign"
        with pytest.raises(EffectFencingRefused):
            owner2.apply(old_effect)

        new_os,new_pid=_restart(envelope)
        new_candidate=publisher.compute(successor,next_host,new_os,new_pid)
        final=publisher.publish(successor,new_candidate)
        session=publisher._session(final.checkpoint)
        assert session.complete and session.value==4
        # Native receiver itself independently reconstructs both DAG stages
        # and checks the quorum before installing any resource head.
        final_install=owner2.activate(final.manifest.digest)
        assert final_install["expected_value"]==4
        new_effect=published_effect(final,RESOURCE)
        assert owner2.apply(new_effect)["value"]==4
        assert owner2.apply(new_effect)["value"]==4
        receiver_snapshot=owner2.snapshot()
        assert receiver_snapshot["register_value"]==4
        assert receiver_snapshot["accepted_effects"]==2
        with pytest.raises(EffectFencingRefused):
            owner2.apply(old_effect)

        # An unrelated host cannot unlock the durable receiver by claiming
        # a mathematical certificate, or make the stale source current.
        other=owner2.prepare(final.manifest.digest,"cgr005-third-host")
        assert other["target_epoch"]==3
        with pytest.raises(EffectFencingRefused):
            owner2.apply(new_effect)
    finally:
        _kill(proc)
        if recovered_proc is not None:
            _kill(recovered_proc)
