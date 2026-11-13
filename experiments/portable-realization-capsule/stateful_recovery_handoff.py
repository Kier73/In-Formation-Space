"""PSC-bound recovery rehoming through E-CPU's quorum-anchored execution claims.

This experiment moves one deterministic next-transition operation at a time.
The PSC checkpoint is the portable state; the E-CPU claim is the live,
quorum-checked authority to publish the next checkpoint.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from mailcpu.transferable_execution_claim import (
    ExecutionClaimStatus,
    PortableExecutionClaimBundle,
    TransferableExecutionClaimError,
    TransferableExecutionClaimStore,
)
from mailcpu.virtual_layer import OperatorSpec

from portable_stateful_checkpoint import (
    PortableStatefulCheckpointError,
    decode_checkpoint,
    encode_checkpoint,
    restore_runtime,
)


SCHEMA = "in-formation-space.stateful-runtime-recovery-handoff.v1"
_MAX_CHECKPOINT_BYTES = 64 * 1024 * 1024
_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class StatefulRuntimeRehomeError(ValueError):
    """A PSC-bound recovery handoff, target admission, or continuation is invalid."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StatefulRuntimeRehomeError("handoff metadata is outside canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StatefulRuntimeRehomeError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_session_id(value: Any) -> str:
    if not isinstance(value, str) or _SESSION_ID.fullmatch(value) is None:
        raise StatefulRuntimeRehomeError("session_id must be a safe 1-128 character identifier")
    return value


def _session_parent_digest(session_id: str) -> str:
    return _digest({"schema": SCHEMA, "session_id": session_id, "role": "session"})


def _session_address_digest(session_id: str) -> str:
    return _digest({"schema": SCHEMA, "session_id": session_id, "role": "stateful-runtime-address"})


def _resume_operator_spec() -> OperatorSpec:
    """Describe the pure transition-to-checkpoint map; publication is separately quorum-admitted."""
    return OperatorSpec(
        operator_id="ifs.psc.stateful-transition-resume",
        version=1,
        description=(
            "Replay a PSC-bound typed stateful runtime, apply its declared next controls, "
            "and produce the next canonical PSC checkpoint."
        ),
        input_kind="object",
        output_kind="object",
        substrates=("cpu",),
        deterministic=True,
        effect_mode="pure",
    )


def _ground_fingerprint(checkpoint: bytes) -> str:
    runtime = restore_runtime(checkpoint)
    return _digest(
        {
            "schema": "ifs.psc.stateful-runtime-ground.v1",
            "compiler_id": runtime.snapshot()["compiler_id"],
            "program_digest": runtime.program_digest,
        }
    )


def _claim_specification(session_id: str, checkpoint: bytes) -> dict[str, Any]:
    checkpoint_digest = _bytes_digest(checkpoint)
    return {
        "parent_request_digest": _session_parent_digest(session_id),
        "child_request_digest": checkpoint_digest,
        "address_digest": _session_address_digest(session_id),
        "operator_spec": _resume_operator_spec(),
        "computational_ground_fingerprint": _ground_fingerprint(checkpoint),
    }


@dataclass(frozen=True)
class StatefulRuntimeRecoveryEnvelope:
    """Portable checkpoint plus the current compact E-CPU authority ticket."""

    session_id: str
    checkpoint: bytes
    ticket: PortableExecutionClaimBundle
    envelope_sha256: str

    @property
    def checkpoint_sha256(self) -> str:
        return _bytes_digest(self.checkpoint)

    @property
    def claim_id(self) -> str:
        return self.ticket.claim.claim_id

    @classmethod
    def build(
        cls,
        session_id: str,
        checkpoint: bytes,
        ticket: PortableExecutionClaimBundle,
    ) -> "StatefulRuntimeRecoveryEnvelope":
        selected_session = _require_session_id(session_id)
        if not isinstance(checkpoint, bytes) or not checkpoint:
            raise StatefulRuntimeRehomeError("checkpoint must be non-empty bytes")
        if len(checkpoint) > _MAX_CHECKPOINT_BYTES:
            raise StatefulRuntimeRehomeError("checkpoint exceeds the finite 64 MiB handoff bound")
        if not isinstance(ticket, PortableExecutionClaimBundle):
            raise StatefulRuntimeRehomeError("handoff requires a typed portable execution-claim ticket")
        if ticket.claim.status is not ExecutionClaimStatus.ASSIGNED:
            raise StatefulRuntimeRehomeError("only an assigned claim can authorize a recovery envelope")

        runtime = restore_runtime(checkpoint)
        expected = _claim_specification(selected_session, checkpoint)
        claim = ticket.claim
        if (
            claim.parent_request_digest != expected["parent_request_digest"]
            or claim.child_request_digest != expected["child_request_digest"]
            or claim.address_digest != expected["address_digest"]
            or claim.operator_spec.to_dict() != expected["operator_spec"].to_dict()
            or claim.computational_ground_fingerprint != expected["computational_ground_fingerprint"]
        ):
            raise StatefulRuntimeRehomeError(
                "claim semantic identity is not bound to this session, checkpoint, Ground, and resume operator"
            )
        if runtime.program_digest == "":
            raise StatefulRuntimeRehomeError("restored runtime has no active typed program identity")

        core = {
            "schema": SCHEMA,
            "session_id": selected_session,
            "checkpoint_sha256": _bytes_digest(checkpoint),
            "checkpoint_base64": base64.b64encode(checkpoint).decode("ascii"),
            "ticket": ticket.to_dict(),
        }
        return cls(selected_session, checkpoint, ticket, _digest(core))

    def to_dict(self) -> dict[str, Any]:
        core = {
            "schema": SCHEMA,
            "session_id": self.session_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "checkpoint_base64": base64.b64encode(self.checkpoint).decode("ascii"),
            "ticket": self.ticket.to_dict(),
        }
        if _digest(core) != self.envelope_sha256:
            raise StatefulRuntimeRehomeError("handoff envelope changed after construction")
        return {**core, "envelope_sha256": self.envelope_sha256}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StatefulRuntimeRecoveryEnvelope":
        expected_fields = {
            "schema",
            "session_id",
            "checkpoint_sha256",
            "checkpoint_base64",
            "ticket",
            "envelope_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected_fields:
            raise StatefulRuntimeRehomeError("handoff envelope fields do not match v1")
        if payload.get("schema") != SCHEMA:
            raise StatefulRuntimeRehomeError("unsupported stateful recovery handoff schema")
        selected_session = _require_session_id(payload.get("session_id"))
        expected_checkpoint_digest = _require_digest(
            payload.get("checkpoint_sha256"), "checkpoint_sha256"
        )
        supplied_envelope_digest = _require_digest(
            payload.get("envelope_sha256"), "envelope_sha256"
        )
        encoded_checkpoint = payload.get("checkpoint_base64")
        if not isinstance(encoded_checkpoint, str) or len(encoded_checkpoint) > (
            (_MAX_CHECKPOINT_BYTES + 2) // 3
        ) * 4:
            raise StatefulRuntimeRehomeError("checkpoint Base64 is missing or exceeds the finite handoff bound")
        try:
            checkpoint = base64.b64decode(encoded_checkpoint, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise StatefulRuntimeRehomeError("checkpoint Base64 is malformed") from exc
        if not checkpoint or len(checkpoint) > _MAX_CHECKPOINT_BYTES:
            raise StatefulRuntimeRehomeError("decoded checkpoint is empty or exceeds its finite byte bound")
        if _bytes_digest(checkpoint) != expected_checkpoint_digest:
            raise StatefulRuntimeRehomeError("checkpoint digest does not match the envelope")
        if not isinstance(payload.get("ticket"), Mapping):
            raise StatefulRuntimeRehomeError("handoff envelope is missing its portable claim ticket")

        core = {key: payload[key] for key in (
            "schema", "session_id", "checkpoint_sha256", "checkpoint_base64", "ticket"
        )}
        if _digest(core) != supplied_envelope_digest:
            raise StatefulRuntimeRehomeError("handoff envelope SHA-256 mismatch")
        try:
            ticket = PortableExecutionClaimBundle.from_dict(payload["ticket"])
        except (TransferableExecutionClaimError, TypeError, ValueError) as exc:
            raise StatefulRuntimeRehomeError("portable claim ticket is invalid") from exc
        return cls.build(selected_session, checkpoint, ticket)


@dataclass(frozen=True)
class StatefulRuntimeRehomeResult:
    """Accepted one-step continuation, its typed receipt, and the next owner ticket."""

    completed_ticket: PortableExecutionClaimBundle
    receipt: Mapping[str, Any]
    receipt_sha256: str
    next_envelope: StatefulRuntimeRecoveryEnvelope
    recovered_from_completed_claim: bool = False


def _issue_for_checkpoint(
    store: TransferableExecutionClaimStore,
    session_id: str,
    checkpoint: bytes,
    *,
    owner_peer_id: str,
    owner_host_id: str,
    implementation_fingerprint: str,
) -> StatefulRuntimeRecoveryEnvelope:
    session_id = _require_session_id(session_id)
    _require_digest(implementation_fingerprint, "implementation_fingerprint")
    restore_runtime(checkpoint)
    specification = _claim_specification(session_id, checkpoint)
    ticket = store.create(
        **specification,
        owner_peer_id=owner_peer_id,
        owner_host_id=owner_host_id,
        implementation_fingerprint=implementation_fingerprint,
    )
    return StatefulRuntimeRecoveryEnvelope.build(session_id, checkpoint, ticket)


def issue_stateful_recovery_envelope(
    store: TransferableExecutionClaimStore,
    *,
    session_id: str,
    runtime: Any,
    realization_capsules: tuple[bytes, ...] | list[bytes],
    resume_controls: Mapping[str, int],
    owner_peer_id: str,
    owner_host_id: str,
    implementation_fingerprint: str,
) -> StatefulRuntimeRecoveryEnvelope:
    """Create a source-owned claim over one exact, replay-verified PSC checkpoint."""
    if not isinstance(store, TransferableExecutionClaimStore):
        raise StatefulRuntimeRehomeError("recovery handoff requires a TransferableExecutionClaimStore")
    try:
        checkpoint = encode_checkpoint(runtime, realization_capsules, resume_controls)
        return _issue_for_checkpoint(
            store,
            session_id,
            checkpoint,
            owner_peer_id=owner_peer_id,
            owner_host_id=owner_host_id,
            implementation_fingerprint=implementation_fingerprint,
        )
    except (PortableStatefulCheckpointError, TransferableExecutionClaimError) as exc:
        raise StatefulRuntimeRehomeError(f"could not issue a PSC recovery envelope: {exc}") from exc


def reassign_after_source_loss(
    store: TransferableExecutionClaimStore,
    envelope: StatefulRuntimeRecoveryEnvelope,
    *,
    target_peer_id: str,
    target_host_id: str,
    target_implementation_fingerprint: str,
    failure_evidence_digest: str,
) -> StatefulRuntimeRecoveryEnvelope:
    """Quorum-reassign a checkpoint after source loss; a stale source cannot publish its result."""
    if not isinstance(store, TransferableExecutionClaimStore):
        raise StatefulRuntimeRehomeError("recovery handoff requires a TransferableExecutionClaimStore")
    if not isinstance(envelope, StatefulRuntimeRecoveryEnvelope):
        raise StatefulRuntimeRehomeError("reassignment requires a typed recovery envelope")
    _require_digest(target_implementation_fingerprint, "target_implementation_fingerprint")
    _require_digest(failure_evidence_digest, "failure_evidence_digest")
    assignment = envelope.ticket.claim.current_assignment
    if envelope.ticket.claim.status is not ExecutionClaimStatus.ASSIGNED:
        raise StatefulRuntimeRehomeError("completed checkpoint operation cannot be reassigned")
    try:
        ticket = store.reassign(
            envelope.claim_id,
            expected_epoch=assignment.epoch,
            owner_peer_id=target_peer_id,
            owner_host_id=target_host_id,
            implementation_fingerprint=target_implementation_fingerprint,
            failure_evidence_digest=failure_evidence_digest,
        )
        return StatefulRuntimeRecoveryEnvelope.build(
            envelope.session_id,
            envelope.checkpoint,
            ticket,
        )
    except TransferableExecutionClaimError as exc:
        raise StatefulRuntimeRehomeError(f"quorum reassignment was refused: {exc}") from exc


def resume_on_recovery_host(
    store: TransferableExecutionClaimStore,
    envelope: StatefulRuntimeRecoveryEnvelope,
    *,
    owner_peer_id: str,
    owner_host_id: str,
    implementation_fingerprint: str,
    next_resume_controls: Mapping[str, int],
    before_claim_complete: Callable[[bytes, Mapping[str, Any], str], str | None] | None = None,
    after_claim_complete: Callable[[PortableExecutionClaimBundle], None] | None = None,
    after_successor_claim: Callable[[StatefulRuntimeRecoveryEnvelope], None] | None = None,
) -> StatefulRuntimeRehomeResult:
    """Continue an assigned claim or reconstruct a quorum-completed result after worker loss."""
    if not isinstance(store, TransferableExecutionClaimStore):
        raise StatefulRuntimeRehomeError("recovery handoff requires a TransferableExecutionClaimStore")
    if not isinstance(envelope, StatefulRuntimeRecoveryEnvelope):
        raise StatefulRuntimeRehomeError("resume requires a typed recovery envelope")
    _require_digest(implementation_fingerprint, "implementation_fingerprint")

    try:
        semantics = _claim_specification(envelope.session_id, envelope.checkpoint)
        current_ticket = store.get(envelope.claim_id)
        claim = current_ticket.claim
        if claim.claim_id != envelope.ticket.claim.claim_id:
            raise StatefulRuntimeRehomeError("live claim identity differs from the received recovery envelope")

        assignment = claim.current_assignment
        if assignment.epoch != envelope.ticket.claim.current_assignment.epoch:
            raise StatefulRuntimeRehomeError(
                "recovery envelope assignment epoch is stale relative to the live claim"
            )
        if claim.status is ExecutionClaimStatus.ASSIGNED:
            current_ticket.verify_for_target(
                store.coordinator,
                **semantics,
                owner_peer_id=owner_peer_id,
                owner_host_id=owner_host_id,
                implementation_fingerprint=implementation_fingerprint,
            )
        elif claim.status is ExecutionClaimStatus.COMPLETED:
            # A previous worker may have quorum-committed the deterministic
            # result and died before its outbox was fsynced. The completed
            # claim is the durable result commitment; replay must reproduce
            # both its output checkpoint and its continuation receipt.
            current_ticket.verify_current(store.coordinator)
            expected_semantics = (
                claim.parent_request_digest == semantics["parent_request_digest"]
                and claim.child_request_digest == semantics["child_request_digest"]
                and claim.address_digest == semantics["address_digest"]
                and claim.operator_spec.to_dict() == semantics["operator_spec"].to_dict()
                and claim.computational_ground_fingerprint
                == semantics["computational_ground_fingerprint"]
            )
            expected_owner = (
                assignment.owner_peer_id == owner_peer_id
                and assignment.owner_host_id == owner_host_id
                and assignment.implementation_fingerprint == implementation_fingerprint
            )
            if not expected_semantics or not expected_owner:
                raise StatefulRuntimeRehomeError(
                    "completed claim is not bound to this checkpoint, session, target, and implementation"
                )
        else:
            raise StatefulRuntimeRehomeError("recovery claim has an unsupported terminal status")

        runtime = restore_runtime(envelope.checkpoint)
        header = decode_checkpoint(envelope.checkpoint)
        before = runtime.snapshot()
        runtime.step(header["resume_controls"])
        realization_capsules = tuple(
            base64.b64decode(item["capsule_base64"], validate=True)
            for item in header["realizations"]
        )
        next_checkpoint = encode_checkpoint(
            runtime,
            realization_capsules,
            next_resume_controls,
        )
        receipt_core = {
            "schema": "ifs.stateful-runtime-rehome-receipt.v1",
            "session_id": envelope.session_id,
            "input_checkpoint_sha256": envelope.checkpoint_sha256,
            "input_claim_id": envelope.claim_id,
            "assignment_epoch": assignment.epoch,
            "owner_peer_id": owner_peer_id,
            "owner_host_id": owner_host_id,
            "implementation_fingerprint": implementation_fingerprint,
            "tick_before": before["tick"],
            "tick_after": runtime.tick,
            "state_before": list(before["state"]),
            "state_after": list(runtime.state),
            "revision": runtime.revision,
            "program_digest": runtime.program_digest,
            "model_digest": runtime.model_digest,
            "transition_event_digest": runtime.chain_head_digest,
            "output_checkpoint_sha256": _bytes_digest(next_checkpoint),
            "output_checkpoint_bytes": len(next_checkpoint),
        }
        receipt_digest = _digest(receipt_core)
        output_digest = _bytes_digest(next_checkpoint)
        if before_claim_complete is not None:
            independent_verification_digest = before_claim_complete(
                next_checkpoint,
                receipt_core,
                receipt_digest,
            )
            if independent_verification_digest is not None:
                _require_digest(
                    independent_verification_digest,
                    "independent_verification_digest",
                )
                receipt_core["independent_verification_digest"] = independent_verification_digest
                receipt_digest = _digest(receipt_core)
    except (
        PortableStatefulCheckpointError,
        TransferableExecutionClaimError,
        StatefulRuntimeRehomeError,
        KeyError,
        TypeError,
        ValueError,
        binascii.Error,
    ) as exc:
        raise StatefulRuntimeRehomeError(f"recovery target could not admit or replay the checkpoint: {exc}") from exc

    recovered_from_completed_claim = claim.status is ExecutionClaimStatus.COMPLETED
    try:
        if recovered_from_completed_claim:
            if (
                claim.result_digest != output_digest
                or claim.child_receipt_digest != receipt_digest
            ):
                raise StatefulRuntimeRehomeError(
                    "deterministic replay does not reproduce the quorum-committed result and receipt"
                )
            completed_ticket = current_ticket
        else:
            completed_ticket = store.complete(
                envelope.claim_id,
                expected_epoch=assignment.epoch,
                owner_peer_id=owner_peer_id,
                owner_host_id=owner_host_id,
                implementation_fingerprint=implementation_fingerprint,
                result_digest=output_digest,
                child_receipt_digest=receipt_digest,
            )
            if after_claim_complete is not None:
                after_claim_complete(completed_ticket)

        # Claim creation is content-addressed. If a previous worker created
        # this exact successor before dying, create() returns that same
        # assignment; if it died before that point, this creates it now.
        next_envelope = _issue_for_checkpoint(
            store,
            envelope.session_id,
            next_checkpoint,
            owner_peer_id=owner_peer_id,
            owner_host_id=owner_host_id,
            implementation_fingerprint=implementation_fingerprint,
        )
        if after_successor_claim is not None:
            after_successor_claim(next_envelope)

        # The successor publication advances the global ledger root; refresh
        # the completed input ticket so its proof is current at the new root.
        completed_ticket = store.get(envelope.claim_id)
    except (TransferableExecutionClaimError, StatefulRuntimeRehomeError) as exc:
        raise StatefulRuntimeRehomeError(
            f"recovery result did not match or commit at the current quorum epoch: {exc}"
        ) from exc

    receipt = {**receipt_core, "receipt_sha256": receipt_digest}
    return StatefulRuntimeRehomeResult(
        completed_ticket=completed_ticket,
        receipt=json.loads(_canonical(receipt).decode("utf-8")),
        receipt_sha256=receipt_digest,
        next_envelope=next_envelope,
        recovered_from_completed_claim=recovered_from_completed_claim,
    )
