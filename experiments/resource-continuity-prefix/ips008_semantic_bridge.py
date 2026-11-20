"""RCP-004: put RCP-003's semantic-effect admission behind NATIVE IPS-008 mTLS.

No new TLS framing or recovery quorum is introduced: E-CPU's original
AuthenticatedGroundEffectService handles mutual TLS, DNS SAN, SocketTransport,
framed Message request/result/ACK and its original prepare/activate/apply RPCs.

This adapter adds *only* the qualified temporal commands, using the SAME
receiver-owned SQLite database as the original IPS-008 protected register.
RCP-003's receiver checks the installed IPS-008 published generation/host/root
and any pending freeze INSIDE the same BEGIN IMMEDIATE transaction as its
semantic effect insert. Authentication does not elevate a checkpoint, a
quorum certificate, or a mathematical navigation receipt into a capability.

Local process experiment only; no physical actuator or global anti-cloning.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from mailcpu.effect_receiver_service import (
    AuthenticatedGroundEffectService,EffectReceiverServiceError,
)
from mailcpu.fenced_effect_receiver import FencedGroundEffectReceiver
from mailcpu.fenced_generated_ground import FencedGroundLineage

from atomic_semantic_effect import (
    AtomicSemanticResourceReceiver, RESOURCE, HandoffRefused,
    load_workspace,
)
from temporal_meet import (
    initial_ground,original_membership,successor_membership,
    _bytes,_manifest,_quorum,GENESIS,
)

NATIVE_RESOURCE="/virtual-layer/effects/ips008-register"
TARGET_HOST="rcp004-ips008-replacement"
SEMANTIC_NAMESPACE="rcp004.semantic"


def open_bound_semantic_receiver(
    root:Path,publisher:FencedGroundLineage,*,source_root:str,
    database:Path|None=None,
)->AtomicSemanticResourceReceiver:
    """Provision semantic receiver from independently pinned pre-fork source.

    It is an application/supervisor bootstrap, not a network-supplied policy.
    The native target root is unknown before assignment; however exact
    original source root, expected target host and epoch are frozen here.
    The original IPS-008 quorum must later publish the correct successor.
    """
    original=initial_ground()
    old=original_membership()
    common=_manifest(old,generation=1,predecessor=GENESIS,
                    state=_bytes(original.checkpoint()))
    native_guard={
        "resource":NATIVE_RESOURCE,
        "plan_digest":publisher.plan.digest,
        "source_root":source_root,
        "target_host":TARGET_HOST,
        "target_epoch":2,
    }
    return AtomicSemanticResourceReceiver(
        database or root/"protected-receiver.sqlite3",
        resource=RESOURCE,
        source_identity=original.identity,
        temporal_head=original.head,
        common_quorum_root=common.digest,
        original_membership_digest=old.digest,
        successor_membership_digest=successor_membership(common.digest).digest,
        native_guard=native_guard,
    )


class AuthenticatedTemporalIPS008Service(AuthenticatedGroundEffectService):
    """Extend original IPS-008 handler with exact source-qualified effect path.

    Native PREPARE, ACTIVATE, APPLY and SNAPSHOT still dispatch through
    the unmodified E-CPU superclass, including original quorum freshness.
    """

    def __init__(
        self, receiver:FencedGroundEffectReceiver,
        publisher:FencedGroundLineage, listener:Any,
        tls_context:Any, *, expected_owner_dns:str,
        publisher_factory:Any,
        semantic_receiver:AtomicSemanticResourceReceiver,
        source_root:str, temporal_root:Path,
        fault_injection:bool=False,
    )->None:
        super().__init__(
            receiver,publisher,listener,tls_context,
            expected_owner_dns=expected_owner_dns,
            publisher_factory=publisher_factory,
        )
        if (not isinstance(semantic_receiver,AtomicSemanticResourceReceiver)
                or semantic_receiver.path.resolve()!=receiver.path.resolve()
                or semantic_receiver.policy.get("ips008_native_guard") is None
                or semantic_receiver.policy["ips008_native_guard"]["source_root"]!=source_root):
            raise EffectReceiverServiceError(
                "qualified temporal receiver must share native resource authority DB"
            )
        self.semantic=semantic_receiver
        self.temporal_root=temporal_root
        self.fault_injection=fault_injection

    def _dispatch(self,request:Any)->dict[str,Any]:
        """Dispatch only four bounded semantic commands over native mTLS."""
        if not isinstance(request,Mapping) or set(request)!={"kind","data"}:
            raise EffectReceiverServiceError("semantic command envelope is not exact")
        kind,data=request["kind"],request["data"]
        if kind not in {
            "semantic_freeze","semantic_activate",
            "semantic_apply","semantic_snapshot",
            "semantic_apply_crash_after_commit",
        }:
            return super()._dispatch(request)
        if not isinstance(data,Mapping):
            raise EffectReceiverServiceError("semantic request must be an object")
        if kind=="semantic_snapshot":
            if data:
                raise EffectReceiverServiceError("semantic snapshot takes no arguments")
            return self.semantic.snapshot()
        if kind=="semantic_freeze":
            if data:
                raise EffectReceiverServiceError("semantic freeze takes no arguments")
            return self.semantic.freeze(load_workspace(self.temporal_root))
        if kind=="semantic_activate":
            if set(data)!={"expected_root","native_root"}:
                raise EffectReceiverServiceError("semantic activation is not exact")
            p=load_workspace(self.temporal_root)
            fresh=successor_membership(p.evidence.shared_manifest.digest)
            quorum=_quorum(self.temporal_root/"new-members",fresh)
            current=quorum.high_water()
            if current!=(1,data["expected_root"]):
                raise HandoffRefused("semantic successor quorum is not current")
            manifest=_manifest(
                fresh,generation=1,
                predecessor=p.evidence.shared_manifest.digest,
                state=_bytes(p.evidence.meet["common_checkpoint"]),
            )
            if manifest.digest!=data["expected_root"]:
                raise HandoffRefused("remote activation root differs from exact Ground")
            return self.semantic.activate(
                p,quorum=quorum,manifest=manifest,
                native_root=data["native_root"],
            )
        if kind in ("semantic_apply","semantic_apply_crash_after_commit"):
            if set(data)!={
                "epoch","root","context_digest","operation_id","navigation",
            }:
                raise EffectReceiverServiceError("semantic effect fields are not exact")
            if kind=="semantic_apply_crash_after_commit" and not self.fault_injection:
                raise EffectReceiverServiceError("forced crash is not enabled")
            result=self.semantic.apply(
                epoch=data["epoch"],
                root=data["root"],
                context_digest=data["context_digest"],
                operation_id=data["operation_id"],
                navigation=data["navigation"],
            )
            if kind=="semantic_apply_crash_after_commit":
                # Test-only failure cut AFTER SQLite COMMIT and BEFORE the
                # original native E-CPU mTLS response frame is sent.
                import os
                os._exit(89)
            return result
        raise EffectReceiverServiceError("unreachable semantic operation")


def semantic_apply_body(activation:Mapping[str,Any],
                        *,operation_id:str)->dict[str,Any]:
    """Build one inert and independently verifiable VL-I navigation request."""
    ground=initial_ground()
    return {
        "epoch":activation["receiver_epoch"],
        "root":activation["root"],
        "context_digest":activation["context_digest"],
        "operation_id":operation_id,
        "navigation":ground.navigate(
            "5/2",epoch_index=0,expected_head=ground.head,
        ),
    }
