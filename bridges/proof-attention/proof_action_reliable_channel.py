"""Host/worker adapter over E-CPU's at-least-once ReliableChannel.

The host owns a ProofAttentionSession and sends portable proof-action requests.
A worker endpoint receives each request once (despite transport duplication),
returns a correlated proof-action result, and the host imports it only after
the reliable return frame has arrived.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from mailcpu.reliability import (
    ReliabilityPolicy,
    ReliableChannel,
    ReliableChannelError,
)
from mailcpu.transport import Transport

from proof_action_execution import ProofAttentionSession
from vgi.proof import VerifiedKernelReceipt
from proof_action_protocol import (
    ImportedProofActionResult,
    ProofActionProtocolError,
    build_proof_action_request,
    import_proof_action_result,
    validate_proof_action_request,
)


class ProofActionReliableChannelError(ValueError):
    """Invalid worker transport state or an uncorrelated reliable-channel frame."""


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProofActionReliableChannelError(
            "worker payload must be finite canonical JSON"
        ) from exc


@dataclass(frozen=True)
class DispatchedProofAction:
    """Host-visible receipt for one reliable request send."""

    attempt_id: str
    request_sequence: int
    request_digest: str
    request: dict[str, Any]


@dataclass(frozen=True)
class ReceivedProofActionRequest:
    """Worker-visible request received and acknowledged by ReliableChannel."""

    request_sequence: int
    request: dict[str, Any]


class ProofActionReliableWorker:
    """Worker-side reliable endpoints; tactic execution remains an injected host concern."""

    def __init__(
        self,
        transport: Transport,
        *,
        worker_id: str,
        host_id: str,
        request_channel: str = "proof-action-request",
        result_channel: str = "proof-action-result",
        policy: ReliabilityPolicy | None = None,
    ) -> None:
        if not worker_id or not host_id or worker_id == host_id:
            raise ProofActionReliableChannelError(
                "worker_id and host_id must be distinct non-empty identities"
            )
        if not request_channel or not result_channel or request_channel == result_channel:
            raise ProofActionReliableChannelError(
                "request_channel and result_channel must be distinct non-empty names"
            )
        self.transport = transport
        self.worker_id = worker_id
        self.host_id = host_id
        self.request_channel = request_channel
        self.result_channel = result_channel
        self.policy = policy or ReliabilityPolicy()
        self._request_receiver = ReliableChannel(
            transport,
            source=worker_id,
            destination=worker_id,
            channel=request_channel,
            policy=self.policy,
            peer=host_id,
        )
        self._result_sender = ReliableChannel(
            transport,
            source=worker_id,
            destination=host_id,
            channel=result_channel,
            policy=self.policy,
        )
        self._admitted_requests: dict[str, str] = {}
        self._result_sent_attempt_ids: set[str] = set()

    def receive_request(self) -> ReceivedProofActionRequest | None:
        """Receive one in-order request; duplicate frames are acknowledged but not redelivered."""
        validated_payload: dict[str, Any] = {}

        def validate_before_ack(sequence: int, payload: Any) -> None:
            if not isinstance(payload, Mapping):
                raise ProofActionReliableChannelError(
                    "proof-action request frame must contain a JSON object"
                )
            try:
                validated = validate_proof_action_request(payload)
            except ProofActionProtocolError as exc:
                raise ProofActionReliableChannelError(
                    f"received proof-action request is invalid: {exc}"
                ) from exc
            attempt_id = validated["attempt_id"]
            request_digest = validated["request_digest"]
            previous = self._admitted_requests.get(attempt_id)
            if previous is not None and previous != request_digest:
                raise ProofActionReliableChannelError(
                    "one worker attempt ID was admitted with conflicting request digests"
                )
            # Commit the worker's application-level admission before
            # ReliableChannel consumes the frame and emits its ACK.
            self._admitted_requests[attempt_id] = request_digest
            validated_payload.update(validated)

        received = self._request_receiver.receive(commit=validate_before_ack)
        if received is None:
            return None
        sequence, _payload = received
        # A successful new delivery has already committed the attempt identity
        # in validate_before_ack. Duplicate deliveries return None after ACK.
        return ReceivedProofActionRequest(sequence, validated_payload)

    def send_result(self, result_document: Mapping[str, Any]) -> int:
        """Send one portable result envelope over the reliable response channel."""
        if not isinstance(result_document, Mapping):
            raise ProofActionReliableChannelError("proof-action result must be a JSON object")
        copied = json.loads(_canonical(dict(result_document)))
        attempt_id = copied.get("attempt_id")
        request_digest = copied.get("request_digest")
        if not isinstance(attempt_id, str) or not isinstance(request_digest, str):
            raise ProofActionReliableChannelError(
                "proof-action result must identify its admitted attempt and request digest"
            )
        if self._admitted_requests.get(attempt_id) != request_digest:
            raise ProofActionReliableChannelError(
                "worker result does not match a request admitted by this endpoint"
            )
        if attempt_id in self._result_sent_attempt_ids:
            raise ProofActionReliableChannelError(
                "worker has already submitted a result for this attempt"
            )
        sequence = self._result_sender.send(copied)
        self._result_sent_attempt_ids.add(attempt_id)
        return sequence

    def process_result_acknowledgements(self) -> tuple[int, ...]:
        """Clear result sequences acknowledged after host-side receiver admission."""
        return self._result_sender.process_ack()

    def advance_result_retry_tick(self) -> tuple[int, ...]:
        """Advance the result sender's bounded retry clock and report exhausted sequences."""
        return self._result_sender.tick()

    @property
    def pending_result_sequences(self) -> tuple[int, ...]:
        return self._result_sender.pending_sequences()


class ProofActionReliableHost:
    """Session-owning proof host that dispatches and imports through E-CPU channels."""

    def __init__(
        self,
        session: ProofAttentionSession,
        proof_ground: Any,
        transport: Transport,
        *,
        host_id: str,
        worker_id: str,
        request_channel: str = "proof-action-request",
        result_channel: str = "proof-action-result",
        policy: ReliabilityPolicy | None = None,
    ) -> None:
        if not isinstance(session, ProofAttentionSession):
            raise ProofActionReliableChannelError(
                "session must be a ProofAttentionSession"
            )
        if not host_id or not worker_id or host_id == worker_id:
            raise ProofActionReliableChannelError(
                "host_id and worker_id must be distinct non-empty identities"
            )
        if not request_channel or not result_channel or request_channel == result_channel:
            raise ProofActionReliableChannelError(
                "request_channel and result_channel must be distinct non-empty names"
            )
        self.session = session
        self.proof_ground = proof_ground
        self.transport = transport
        self.host_id = host_id
        self.worker_id = worker_id
        self.request_channel = request_channel
        self.result_channel = result_channel
        self.policy = policy or ReliabilityPolicy()
        self._request_sender = ReliableChannel(
            transport,
            source=host_id,
            destination=worker_id,
            channel=request_channel,
            policy=self.policy,
        )
        self._result_receiver = ReliableChannel(
            transport,
            source=host_id,
            destination=host_id,
            channel=result_channel,
            policy=self.policy,
            peer=worker_id,
        )
        self._active_attempt = None
        self._active_request: dict[str, Any] | None = None
        self._request_sequence: int | None = None
        self._quarantined_results: list[dict[str, Any]] = []

    @property
    def active_attempt(self):
        return self._active_attempt

    @property
    def active_request(self) -> dict[str, Any] | None:
        return None if self._active_request is None else json.loads(_canonical(self._active_request))

    @property
    def request_pending_sequences(self) -> tuple[int, ...]:
        return self._request_sender.pending_sequences()

    @property
    def quarantined_results(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(_canonical(item)) for item in self._quarantined_results)

    def _quarantine_result(self, sequence: int, payload: Any, reason: str) -> None:
        """Retain and hash-chain a received response that cannot belong to the active action."""
        try:
            raw = _canonical(payload)
            canonicalization = "canonical-json-v1"
        except ProofActionReliableChannelError:
            raw = repr(payload)
            canonicalization = "python-repr-fallback-v1"
        attempt_id = payload.get("attempt_id") if isinstance(payload, Mapping) else None
        request_digest = payload.get("request_digest") if isinstance(payload, Mapping) else None
        core = {
            "sequence": len(self._quarantined_results) + 1,
            "response_sequence": sequence,
            "channel": self.result_channel,
            "attempt_id": attempt_id if isinstance(attempt_id, str) else None,
            "request_digest": request_digest if isinstance(request_digest, str) else None,
            "reason": reason,
            "canonicalization": canonicalization,
            "payload_digest": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "previous_event_digest": (
                self._quarantined_results[-1]["event_digest"]
                if self._quarantined_results else "0" * 64
            ),
        }
        self._quarantined_results.append({
            **core,
            "event_digest": hashlib.sha256(_canonical(core).encode("utf-8")).hexdigest(),
        })

    def dispatch_next(self) -> DispatchedProofAction | None:
        """Select one action and reliably dispatch its request.

        If the bounded sender window is full or the underlying transport raises,
        the attempt remains planned; a repeated call retries the same action
        instead of selecting a different candidate.
        """
        if self._active_attempt is None:
            attempt = self.session.begin_next()
            if attempt is None:
                return None
            self._active_attempt = attempt
            self._active_request = None
            self._request_sequence = None

        attempt = self._active_attempt
        if attempt is None:
            raise ProofActionReliableChannelError("host active request state is incomplete")
        if self._active_request is None:
            self._active_request = build_proof_action_request(
                self.session, self.proof_ground
            )
        request = self._active_request
        if attempt.status != "planned" or self._request_sequence is not None:
            raise ProofActionReliableChannelError(
                f"host already dispatched the active proof action at stage {attempt.status!r}"
            )

        try:
            sequence = self._request_sender.send(request)
        except ReliableChannelError:
            raise

        evidence_ref = f"mailcpu://{self.request_channel}/sequence/{sequence}"
        attempt.mark_dispatched(
            self.host_id,
            evidence_ref,
            details={
                "transport": "mailcpu.reliable-channel",
                "channel": self.request_channel,
                "sequence": sequence,
                "request_digest": request["request_digest"],
                "destination": self.worker_id,
            },
        )
        self._request_sequence = sequence
        return DispatchedProofAction(
            attempt_id=attempt.attempt_id,
            request_sequence=sequence,
            request_digest=request["request_digest"],
            request=json.loads(_canonical(request)),
        )

    def observe_request_admission(self) -> bool:
        """Record admission only after the worker's ReliableChannel ACK is received."""
        attempt = self._active_attempt
        sequence = self._request_sequence
        if attempt is None or sequence is None:
            raise ProofActionReliableChannelError("there is no dispatched proof request")
        if attempt.status != "dispatched":
            raise ProofActionReliableChannelError(
                f"request admission cannot be recorded from stage {attempt.status!r}"
            )
        acknowledged = self._request_sender.process_ack()
        if sequence not in acknowledged:
            return False
        attempt.mark_admitted(
            self.worker_id,
            f"mailcpu://{self.request_channel}/ack/{sequence}",
            details={
                "transport": "mailcpu.reliable-channel",
                "channel": self.request_channel,
                "sequence": sequence,
                "acknowledgement": "received",
            },
        )
        return True

    def advance_request_retry_tick(self) -> tuple[int, ...]:
        """Advance retries; exhausted acknowledgement is recorded as unconfirmed delivery."""
        failed = self._request_sender.tick()
        sequence = self._request_sequence
        attempt = self._active_attempt
        if (
            sequence is not None
            and sequence in failed
            and attempt is not None
            and attempt.status == "dispatched"
        ):
            attempt.mark_failure(
                "delivery_unconfirmed",
                self.host_id,
                "E-CPU ReliableChannel exhausted retries before request admission was acknowledged",
                evidence_ref=f"mailcpu://{self.request_channel}/sequence/{sequence}",
            )
            self._clear_active()
        return failed

    def mark_no_result(self, reason: str) -> None:
        """Close an admitted request when the worker produces no result by the host's deadline."""
        attempt = self._active_attempt
        if attempt is None or attempt.status != "admitted":
            raise ProofActionReliableChannelError(
                "no_result requires an admitted active proof-action request"
            )
        attempt.mark_failure("no_result", self.host_id, reason)
        self._clear_active()

    def receive_result(
        self,
        *,
        interpretation_ref: str | None = None,
        verified_receipts: Sequence[VerifiedKernelReceipt] = (),
    ) -> ImportedProofActionResult | None:
        """Receive, record, correlate and import one worker result.

        The result frame is admitted only after ReliableChannel consumes it.
        A duplicate response is acknowledged by E-CPU but never interpreted
        twice. A malformed returned payload is retained as a raw return and
        closed with interpretation_failed.
        """
        attempt = self._active_attempt
        if attempt is None:
            peeked = self._result_receiver.peek()
            if peeked is None:
                return None
            sequence, _payload = peeked
            received = self._result_receiver.receive()
            if received is None:
                return None
            received_sequence, payload = received
            self._quarantine_result(
                received_sequence,
                payload,
                "response arrived after its proof-action attempt was closed",
            )
            return None
        if attempt.status != "admitted":
            raise ProofActionReliableChannelError(
                f"worker result requires an admitted request; current stage is {attempt.status!r}"
            )

        peeked = self._result_receiver.peek()
        if peeked is None:
            return None
        _peek_sequence, peek_payload = peeked
        correlation_matches = (
            isinstance(peek_payload, Mapping)
            and peek_payload.get("attempt_id") == attempt.attempt_id
            and peek_payload.get("request_digest") == (
                self._active_request.get("request_digest")
                if self._active_request is not None else None
            )
        )
        if not correlation_matches:
            received = self._result_receiver.receive()
            if received is not None:
                received_sequence, payload = received
                reason = (
                    "response payload is not a correlated proof-action result"
                    if not isinstance(payload, Mapping)
                    else "response attempt ID or request digest does not match the active action"
                )
                self._quarantine_result(received_sequence, payload, reason)
            return None

        received = self._result_receiver.receive()
        if received is None:
            return None
        result_sequence, payload = received
        receipt = payload.get("return_evidence") if isinstance(payload, Mapping) else None

        try:
            if not isinstance(receipt, Mapping) or set(receipt) != {
                "evidence_ref", "encounter_id", "payload_digest", "canonicalization"
            }:
                raise ProofActionReliableChannelError(
                    "worker result lacks the required return_evidence receipt"
                )
            evidence_ref = receipt["evidence_ref"]
            encounter_id = receipt["encounter_id"]
            payload_digest = receipt["payload_digest"]
            canonicalization = receipt["canonicalization"]
            if not all(isinstance(item, str) and item for item in (
                evidence_ref, encounter_id, payload_digest, canonicalization
            )):
                raise ProofActionReliableChannelError(
                    "worker return_evidence fields must be non-empty strings"
                )
            attempt.record_return(
                self.worker_id,
                evidence_ref=evidence_ref,
                encounter_id=encounter_id,
                payload_digest=payload_digest,
                canonicalization=canonicalization,
                details={
                    "transport": "mailcpu.reliable-channel",
                    "response_channel": self.result_channel,
                    "response_sequence": result_sequence,
                    "request_channel": self.request_channel,
                    "request_sequence": self._request_sequence,
                },
            )
        except (ProofActionReliableChannelError, ValueError, TypeError) as exc:
            self._record_fallback_return(attempt, result_sequence, payload)
            attempt.mark_failure(
                "interpretation_failed",
                self.host_id,
                f"worker result could not be admitted into the proof protocol: {exc}",
                evidence_ref=f"mailcpu://{self.result_channel}/sequence/{result_sequence}",
            )
            self._clear_active()
            raise ProofActionReliableChannelError(str(exc)) from exc

        try:
            imported = import_proof_action_result(
                self.session,
                self.proof_ground,
                self._active_request,
                payload,
                actor=self.host_id,
                interpretation_ref=interpretation_ref or (
                    f"mailcpu://{self.result_channel}/sequence/{result_sequence}"
                ),
                verified_receipts=tuple(verified_receipts),
            )
        except (ProofActionProtocolError, ValueError, TypeError) as exc:
            attempt.mark_failure(
                "interpretation_failed",
                self.host_id,
                f"worker result failed proof-action correlation: {exc}",
                evidence_ref=f"mailcpu://{self.result_channel}/sequence/{result_sequence}",
            )
            self._clear_active()
            raise ProofActionReliableChannelError(str(exc)) from exc

        self.proof_ground = imported.proof_ground
        self._clear_active()
        return imported

    def _record_fallback_return(
        self,
        attempt: Any,
        result_sequence: int,
        payload: Any,
    ) -> None:
        """Record the raw reliable-channel result even when its proof envelope is malformed."""
        try:
            payload_bytes = _canonical(payload).encode("utf-8")
            canonicalization = "canonical-json-v1"
        except ProofActionReliableChannelError:
            payload_bytes = repr(payload).encode("utf-8")
            canonicalization = "python-repr-fallback-v1"
        attempt.record_return(
            self.worker_id,
            evidence_ref=f"mailcpu://{self.result_channel}/sequence/{result_sequence}",
            encounter_id=f"mailcpu:{self.result_channel}:{result_sequence}",
            payload_digest=hashlib.sha256(payload_bytes).hexdigest(),
            canonicalization=canonicalization,
            details={
                "transport": "mailcpu.reliable-channel",
                "response_channel": self.result_channel,
                "response_sequence": result_sequence,
                "request_channel": self.request_channel,
                "request_sequence": self._request_sequence,
                "receipt_validation": "failed",
            },
        )

    def _clear_active(self) -> None:
        self._active_attempt = None
        self._active_request = None
        self._request_sequence = None


__all__ = [
    "ProofActionReliableChannelError",
    "DispatchedProofAction",
    "ReceivedProofActionRequest",
    "ProofActionReliableWorker",
    "ProofActionReliableHost",
]
