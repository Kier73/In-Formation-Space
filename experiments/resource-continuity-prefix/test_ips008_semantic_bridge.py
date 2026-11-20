"""RCP-004 — real IPS-008 mutual-TLS fencing around RCP-003 recovered Ground.

Native E-CPU test fixtures construct and execute the real IPS-004/005 stage
Graph, durable quorum assignments, mutual-TLS owner/receiver and actual
SQLite IPS-008 barrier. A distinct recovered VL-I state from a genuine
late fork is admitted via the same receiver DB only after an independently
verified native rehome. No mock mTLS, quorum or numerical interpretation.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import monotonic,sleep

import pytest

from mailcpu.effect_receiver_service import (
    EffectReceiverServiceError,AuthenticatedGroundEffectClient,
)
from mailcpu.fenced_effect_receiver import EffectFencingRefused,published_effect
from atomic_semantic_effect import (
    create_workspace,load_workspace,seal_successor,
)
from ips008_semantic_bridge import (
    NATIVE_RESOURCE,TARGET_HOST,semantic_apply_body,
)
from test_effect_receiver_service import (
    _published_first,_client,_kill,
)
from test_recovery_lineage_service import _make_certificates
from test_fenced_generated_ground import _host,_restart,_lineage

MODULE=Path(__file__).parent
STARTUP=MODULE/"ips008_semantic_service_worker.py"


def start(root:Path,certificates,*,faults:bool=True):
    """Launch a NEW receiver service process with original native TLS socket."""
    marker=root/"rcp004-ready.json"
    if marker.exists():
        marker.unlink()
    proc=subprocess.Popen([
        sys.executable,str(STARTUP),str(root),
        str(certificates["B_cert"]),str(certificates["B_key"]),
        str(certificates["ca"]),str(marker),
        "owner-a.mailcpu.test","test" if faults else "disabled",
    ],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=monotonic()+18
        while monotonic()<deadline:
            if marker.exists():
                return proc,json.loads(marker.read_text(encoding="ascii"))
            if proc.poll() is not None:
                out,err=proc.communicate(timeout=3)
                raise AssertionError("native receiver child died: "+err[-2000:]+out[-500:])
            sleep(.025)
        raise AssertionError("receiver did not advertise real TLS listener")
    except BaseException:
        _kill(proc)
        raise


def setup(root:Path):
    """Provision independent original semantic and native quorum histories."""
    root.mkdir(parents=True,exist_ok=True)
    source=create_workspace(root/"temporal")
    native,first,envelope=_published_first(root/"native")
    with (root/"ips008-original-root.txt").open("wb") as file:
        file.write(first.manifest.digest.encode("ascii"))
        file.flush()
        os.fsync(file.fileno())
    assert source.evidence.meet["common_event_count"]==5
    assert first.state["epoch"]==1
    return source,native,first,envelope


def semantic(client:AuthenticatedGroundEffectClient,kind:str,data=None):
    """Use the original native E-CPU typed Message and TLS response/ACK channel."""
    return client.request(kind,{} if data is None else data)


def _rehome(root:Path,first,envelope,client):
    """Perform IPS-008 prepare BEFORE native original quorum assignment."""
    target=_host(root/"native",TARGET_HOST)
    barrier=client.prepare(first.manifest.digest,target.locus)
    assert barrier["source_root"]==first.manifest.digest
    assert barrier["target_epoch"]==2
    fresh=_lineage(root/"native")
    assigned=fresh.assign(first,target)
    installed=client.activate(assigned.manifest.digest)
    assert installed["event"]=="assign"
    next_os,next_pid=_restart(envelope)
    final=fresh.publish(assigned,fresh.compute(assigned,target,next_os,next_pid))
    finished=client.activate(final.manifest.digest)
    assert finished["event"]=="publish"
    assert finished["epoch"]==2
    assert finished["host"]==TARGET_HOST
    return barrier,final


@pytest.mark.skipif(shutil.which("openssl") is None,
                    reason="native E-CPU real mTLS certificate fixture needs OpenSSL")
def test_native_authenticated_rehome_qualifies_and_fences_temporal_effect(tmp_path:Path):
    """True receiver crash + old worker replay + new semantic effect pre-ACK kill."""
    p,old_lineage,first,envelope=setup(tmp_path)
    certificates=_make_certificates(tmp_path)
    proc,info=start(tmp_path,certificates)
    restarted=None
    after_lost_ack=None
    try:
        owner=_client(info,certificates)
        original=owner.activate(first.manifest.digest)
        assert original["event"]=="publish"
        previous=published_effect(first,NATIVE_RESOURCE)
        assert owner.apply(previous)["committed"]

        # RCP-003 common Ground is source-qualified before it is effect-authorized.
        frozen=semantic(owner,"semantic_freeze")
        assert frozen["old_forks_effect_eligible"] is False
        assert semantic(owner,"semantic_snapshot")["mode"]=="frozen"
        successor=seal_successor(tmp_path/"temporal",p)
        with pytest.raises(EffectFencingRefused,match="native"):
            semantic(owner,"semantic_activate",{
                "expected_root":successor.digest,
                "native_root":first.manifest.digest,
            })
        with pytest.raises(EffectFencingRefused):
            semantic(owner,"semantic_apply",semantic_apply_body({
                "receiver_epoch":2,"root":successor.digest,
                "context_digest":frozen["context_digest"],
            },operation_id="not-yet-authorized"))

        # Only the original IPS-008 mTLS PREPARE can freeze old published effects.
        target=_host(tmp_path/"native",TARGET_HOST)
        barrier=owner.prepare(first.manifest.digest,target.locus)
        assert owner.snapshot()["pending_handoff_digest"]==barrier["barrier_digest"]
        with pytest.raises(EffectFencingRefused,match="handoff barrier"):
            owner.apply(previous)

        # Hard kill the receiver after durable network ACK, then reopen the same
        # SQLite source/authority storage in a DIFFERENT OS receiver process.
        _kill(proc)
        restarted,info2=start(tmp_path,certificates)
        owner2=_client(info2,certificates)
        assert owner2.snapshot()["pending_handoff_digest"]==barrier["barrier_digest"]
        assert semantic(owner2,"semantic_snapshot")["mode"]=="frozen"
        with pytest.raises(EffectFencingRefused):
            owner2.apply(previous)

        new_lineage=_lineage(tmp_path/"native")
        assigned=new_lineage.assign(first,target)
        assert owner2.activate(assigned.manifest.digest)["event"]=="assign"
        with pytest.raises(EffectFencingRefused,match="native"):
            semantic(owner2,"semantic_activate",{
                "expected_root":successor.digest,
                "native_root":assigned.manifest.digest,
            })
        next_os,next_pid=_restart(envelope)
        final=new_lineage.publish(
            assigned,new_lineage.compute(assigned,target,next_os,next_pid),
        )
        assert owner2.activate(final.manifest.digest)["event"]=="publish"
        with pytest.raises(EffectFencingRefused,match="native"):
            semantic(owner2,"semantic_activate",{
                "expected_root":successor.digest,
                "native_root":first.manifest.digest,
            })
        activated=semantic(owner2,"semantic_activate",{
            "expected_root":successor.digest,
            "native_root":final.manifest.digest,
        })
        assert activated["native_ips008_root"]==final.manifest.digest
        assert activated["processor_digest"]==p.evidence.meet["qualified_processor"]["processor_digest"]
        assert semantic(owner2,"semantic_snapshot")["native_ips008_root"]==final.manifest.digest
        with pytest.raises(EffectFencingRefused):
            owner2.apply(previous)

        # Actual E-CPU TCP/mTLS connection dies AFTER the protected SQLite effect
        # commits, BEFORE its original Message reply and ACK protocol completes.
        content=semantic_apply_body(activated,operation_id="continuity-effect")
        with pytest.raises((EffectReceiverServiceError,EffectFencingRefused)):
            semantic(owner2,"semantic_apply_crash_after_commit",content)
        # The receiver process is actually gone; no ACK from the original RPC.
        assert restarted.wait(timeout=10)==89
        restarted=None

        after_lost_ack,info3=start(tmp_path,certificates)
        owner3=_client(info3,certificates)
        before=semantic(owner3,"semantic_snapshot")
        assert before["committed_effects"]==1
        result=semantic(owner3,"semantic_apply",content)
        assert result["value"]==["6/1"]
        assert result["native_ips008_root"]==final.manifest.digest
        assert result["old_fork_winner_elected"] is False
        assert result["external_effect_attested"] is False
        assert semantic(owner3,"semantic_apply",content)==result
        assert semantic(owner3,"semantic_snapshot")["committed_effects"]==1

        # A *new* pending IPS-008 barrier must fence the RCP-003 semantic effect
        # too, including a duplicate operation ID from the previous successful
        # semantic epoch. This is checked in the SAME SQLite write transaction.
        next_barrier=owner3.prepare(final.manifest.digest,"rcp004-later-host")
        assert next_barrier["source_root"]==final.manifest.digest
        for operation in ("new-after-fence","continuity-effect"):
            payload=semantic_apply_body(activated,operation_id=operation)
            with pytest.raises(EffectFencingRefused,match="native"):
                semantic(owner3,"semantic_apply",payload)
        assert semantic(owner3,"semantic_snapshot")["committed_effects"]==1
        with pytest.raises(EffectFencingRefused):
            owner3.apply(published_effect(final,NATIVE_RESOURCE))

        # A CA-issued but WRONG owner certificate and a wrong server DNS cannot
        # access either the native or semantic receiver commands.
        outsider=_client(info3,certificates,certificate="C")
        with pytest.raises((EffectReceiverServiceError,EffectFencingRefused)):
            semantic(outsider,"semantic_snapshot")
        invalid_dns=_client(info3,certificates,dns="member-c.mailcpu.test")
        with pytest.raises(EffectReceiverServiceError,match="TLS"):
            semantic(invalid_dns,"semantic_snapshot")
    finally:
        _kill(proc)
        if restarted is not None:
            _kill(restarted)
        if after_lost_ack is not None:
            _kill(after_lost_ack)


@pytest.mark.skipif(shutil.which("openssl") is None,reason="mTLS fixture uses OpenSSL")
def test_signed_identity_does_not_override_native_pinned_host_or_proof(tmp_path:Path):
    """Valid owner certificate can't bypass quorum, exact host, or source history."""
    p,_,first,envelope=setup(tmp_path)
    certs=_make_certificates(tmp_path)
    child,info=start(tmp_path,certs,faults=False)
    try:
        owner=_client(info,certs)
        owner.activate(first.manifest.digest)
        freeze=semantic(owner,"semantic_freeze")
        successor=seal_successor(tmp_path/"temporal",p)

        # A valid quorum certificate about the recovered mathematical source
        # cannot serve as the current IPS-008 receiver publication.
        with pytest.raises(EffectFencingRefused):
            semantic(owner,"semantic_activate",{
                "expected_root":successor.digest,
                "native_root":successor.digest,
            })
        with pytest.raises(EffectFencingRefused):
            semantic(owner,"semantic_activate",{
                "expected_root":p.evidence.left_manifest.digest,
                "native_root":first.manifest.digest,
            })
        with pytest.raises(EffectFencingRefused):
            semantic(owner,"semantic_apply_crash_after_commit",{})
        assert semantic(owner,"semantic_snapshot")["committed_effects"]==0
        assert semantic(owner,"semantic_snapshot")["mode"]=="frozen"
    finally:
        _kill(child)
