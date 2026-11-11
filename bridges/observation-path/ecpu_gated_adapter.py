"""Thin, duck-typed adapter for E-CPU's GatedObservationCoordinator.

This module intentionally does not import E-CPU. The caller supplies the
E-CPU coordinator and its typed observation decoder. The adapter reuses the
coordinator's public finalize_event(), commit_event(), snapshot(),
save_checkpoint(), and VM snapshot/register-read interfaces.

The adapter records consensus authorization and receiver-side application
only after validating E-CPU's finalized state, evidence links, consume/apply
markers, VM observation receipt, and actual register readback.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from observation_path import ObservationPath


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _event_entry(items: object, kind: str, logical_time: int, label: str) -> Mapping[str, Any]:
    if not isinstance(items, (list, tuple)):
        raise ValueError(f"E-CPU snapshot {label} must be a sequence")
    matches = [
        item for item in items
        if isinstance(item, Mapping)
        and item.get("kind") == kind
        and item.get("logical_time") == logical_time
    ]
    if len(matches) != 1:
        raise ValueError(f"E-CPU snapshot must contain exactly one {label} entry for {kind}:{logical_time}")
    return matches[0]


@dataclass(frozen=True)
class ECPUDecisionRecord:
    event_kind: str
    logical_time: int
    status: str
    policy_digest: str
    decision_digest: str
    representative_source: str | None
    observed_sources: tuple[str, ...]
    dissenting_sources: tuple[str, ...]
    missing_sources: tuple[str, ...]


@dataclass(frozen=True)
class ECPUApplicationRecord:
    event_kind: str
    logical_time: int
    target_pid: int
    representative_source: str
    representative_sequence: int
    projection_digest: str
    checkpoint_ref: str
    checkpoint_digest: str


class ECPUGatedObservationAdapter:
    """Record E-CPU quorum and VM-commit evidence into an ObservationPath."""

    def __init__(
        self,
        coordinator: object,
        decode_observation: Callable[[Sequence[Any]], object],
    ) -> None:
        if not callable(decode_observation):
            raise TypeError("decode_observation must be callable")
        for method_name in ("finalize_event", "commit_event", "snapshot", "save_checkpoint"):
            if not callable(getattr(coordinator, method_name, None)):
                raise TypeError(f"coordinator must expose {method_name}()")
        vm = getattr(coordinator, "vm", None)
        if vm is None or not callable(getattr(vm, "snapshot", None)):
            raise TypeError("coordinator.vm must expose snapshot()")
        self.coordinator = coordinator
        self.decode_observation = decode_observation

    def record_finalized_decision(
        self,
        path: ObservationPath,
        kind: str,
        logical_time: int,
        *,
        decision_ref: str,
        refusal_reason: str = "E-CPU finalized the observation without authorization",
        actor: str = "ecpu-consensus",
    ) -> ECPUDecisionRecord:
        """Finalize through E-CPU and record AUTHORIZED, CONFLICT, or REFUSED.

        A QUORUM/PENDING pre-finalization status is not accepted as authorization.
        E-CPU's finalize_event() performs the actual finalization.
        """
        if not isinstance(path, ObservationPath):
            raise TypeError("path must be an ObservationPath")
        if path.status != "returned":
            raise ValueError("E-CPU consensus finalization requires a returned raw observation")
        if not path.intent.authority_required:
            raise ValueError("E-CPU quorum adapter requires intent.authority_required=True")
        _nonempty(kind, "kind")
        _nonempty(decision_ref, "decision_ref")
        if isinstance(logical_time, bool) or not isinstance(logical_time, int) or logical_time < 0:
            raise ValueError("logical_time must be a non-negative integer")

        decision = self.coordinator.finalize_event(kind, logical_time)
        status = getattr(decision, "status", None)
        if status not in {"AUTHORIZED", "CONFLICT", "REFUSED"}:
            raise ValueError(f"E-CPU event was not finalized: {status!r}")
        if getattr(decision, "kind", None) != kind or getattr(decision, "logical_time", None) != logical_time:
            raise ValueError("E-CPU decision event identity does not match the requested event")

        snapshot = self.coordinator.snapshot()
        if not isinstance(snapshot, Mapping):
            raise ValueError("E-CPU coordinator snapshot must be a mapping")
        consensus = snapshot.get("policy_consensus")
        if not isinstance(consensus, Mapping):
            raise ValueError("E-CPU snapshot lacks policy_consensus")
        policy = consensus.get("policy")
        if not isinstance(policy, Mapping):
            raise ValueError("E-CPU consensus snapshot lacks policy")
        if policy.get("kind") != kind:
            raise ValueError("E-CPU policy kind does not match the finalized event")
        quorum = getattr(decision, "quorum", None)
        strict = getattr(decision, "strict", None)
        if policy.get("quorum") != quorum or policy.get("strict") is not strict:
            raise ValueError("E-CPU decision quorum/strictness does not match its policy")
        finalized = _event_entry(consensus.get("finalized"), kind, logical_time, "finalized consensus")
        if finalized.get("status") != status:
            raise ValueError("E-CPU decision status does not match finalized snapshot")

        observed = tuple(getattr(decision, "observed_sources", ()))
        dissenting = tuple(getattr(decision, "dissenting_sources", ()))
        missing = tuple(getattr(decision, "missing_sources", ()))
        if any(not isinstance(source, str) or not source for source in observed + dissenting + missing):
            raise ValueError("E-CPU decision source sets contain invalid identifiers")
        if len(set(observed)) != len(observed) or len(set(dissenting)) != len(dissenting) or len(set(missing)) != len(missing):
            raise ValueError("E-CPU decision source sets contain duplicates")

        link_event = _event_entry(snapshot.get("links"), kind, logical_time, "evidence links")
        raw_links = link_event.get("sources")
        if not isinstance(raw_links, (list, tuple)) or not raw_links:
            raise ValueError("E-CPU finalized event lacks evidence links")
        link_sources = tuple(sorted(
            _nonempty(link.get("source"), "evidence link source")
            for link in raw_links if isinstance(link, Mapping)
        ))
        if len(link_sources) != len(raw_links) or tuple(sorted(observed)) != link_sources:
            raise ValueError("E-CPU decision observed sources do not match its evidence links")

        policy_digest = _digest(dict(policy))
        representative_source = None
        if status == "AUTHORIZED":
            representative_event = _event_entry(
                snapshot.get("representatives"), kind, logical_time, "representative"
            )
            representative_link = representative_event.get("link")
            if not isinstance(representative_link, Mapping):
                raise ValueError("E-CPU representative link is malformed")
            representative_source = _nonempty(
                representative_link.get("source"), "representative source"
            )
            if representative_source not in observed or representative_source in dissenting:
                raise ValueError("E-CPU representative source is not an observed winning source")
            if getattr(decision, "canonical_payload", None) is None:
                raise ValueError("E-CPU authorized decision has no canonical representative payload")
        elif status not in {"CONFLICT", "REFUSED"}:
            raise ValueError(f"unsupported E-CPU final status: {status}")

        decision_payload = {
            "kind": kind,
            "logical_time": logical_time,
            "status": status,
            "quorum": quorum,
            "strict": strict,
            "observed_sources": sorted(observed),
            "dissenting_sources": sorted(dissenting),
            "missing_sources": sorted(missing),
            "canonical_payload": (
                None
                if getattr(decision, "canonical_payload", None) is None
                else list(decision.canonical_payload)
            ),
            "representative_source": representative_source,
            "policy_digest": policy_digest,
        }
        decision_digest = _digest(decision_payload)

        details = {
            "event_kind": kind,
            "logical_time": logical_time,
            "decision_status": status,
            "policy_digest": policy_digest,
            "decision_digest": decision_digest,
            "quorum": quorum,
            "strict": strict,
            "observed_sources": list(sorted(observed)),
            "dissenting_sources": list(sorted(dissenting)),
            "missing_sources": list(sorted(missing)),
        }
        if status == "AUTHORIZED":
            details["representative_source"] = representative_source
            path.append("evidence_authorized", actor, evidence_ref=decision_ref, details=details)
        else:
            details["reason"] = _nonempty(refusal_reason, "refusal_reason")
            path.append("evidence_refused", actor, evidence_ref=decision_ref, details=details)

        return ECPUDecisionRecord(
            event_kind=kind,
            logical_time=logical_time,
            status=status,
            policy_digest=policy_digest,
            decision_digest=decision_digest,
            representative_source=representative_source,
            observed_sources=tuple(sorted(observed)),
            dissenting_sources=tuple(sorted(dissenting)),
            missing_sources=tuple(sorted(missing)),
        )

    def record_application_commit(
        self,
        path: ObservationPath,
        kind: str,
        logical_time: int,
        checkpoint_path: str | Path,
        *,
        checkpoint_ref: str,
        actor: str = "ecpu-vm-commit",
    ) -> ECPUApplicationRecord:
        """Commit through E-CPU and verify the durable receiver-side application.

        The method requires an intent with application_required=True. It verifies
        the finalized authority marker, representative/apply marker, complete
        receiver-side consumption, absence of unresolved commit intents, the VM's
        idempotence receipt, and actual register readback before appending applied.
        """
        if not isinstance(path, ObservationPath):
            raise TypeError("path must be an ObservationPath")
        if path.status != "evidence_authorized":
            raise ValueError("E-CPU commit requires a path with evidence_authorized")
        if not path.intent.application_required:
            raise ValueError("E-CPU commit adapter requires intent.application_required=True")
        _nonempty(kind, "kind")
        _nonempty(checkpoint_ref, "checkpoint_ref")
        if isinstance(logical_time, bool) or not isinstance(logical_time, int) or logical_time < 0:
            raise ValueError("logical_time must be a non-negative integer")

        authorization_details = path.events[-1].details
        if (
            authorization_details.get("event_kind") != kind
            or authorization_details.get("logical_time") != logical_time
            or authorization_details.get("decision_status") != "AUTHORIZED"
        ):
            raise ValueError("path authorization receipt does not match the requested E-CPU event")

        decision = self.coordinator.commit_event(kind, logical_time, checkpoint_path)
        if getattr(decision, "status", None) != "AUTHORIZED":
            raise ValueError("E-CPU commit did not return an AUTHORIZED event")

        coordinator_snapshot = self.coordinator.snapshot()
        if not isinstance(coordinator_snapshot, Mapping):
            raise ValueError("E-CPU coordinator snapshot must be a mapping")
        event_links = _event_entry(coordinator_snapshot.get("links"), kind, logical_time, "evidence links")
        source_links = event_links.get("sources")
        if not isinstance(source_links, (list, tuple)) or not source_links:
            raise ValueError("E-CPU event has no source evidence links")
        links_by_source = {}
        for link in source_links:
            if not isinstance(link, Mapping):
                raise ValueError("E-CPU source evidence link is malformed")
            source = _nonempty(link.get("source"), "evidence link source")
            if source in links_by_source:
                raise ValueError("E-CPU event contains duplicate source links")
            links_by_source[source] = dict(link)

        representative_event = _event_entry(
            coordinator_snapshot.get("representatives"), kind, logical_time, "representative"
        )
        representative_link = representative_event.get("link")
        if not isinstance(representative_link, Mapping):
            raise ValueError("E-CPU representative link is malformed")
        representative_link = dict(representative_link)
        representative_source = _nonempty(
            representative_link.get("source"), "representative source"
        )
        if links_by_source.get(representative_source) != representative_link:
            raise ValueError("E-CPU representative is not one of the event's exact evidence links")

        applied_event = _event_entry(coordinator_snapshot.get("applied"), kind, logical_time, "applied marker")
        applied_link = applied_event.get("link")
        if not isinstance(applied_link, Mapping) or dict(applied_link) != representative_link:
            raise ValueError("E-CPU applied marker does not match the authorized representative")

        consumed_event = _event_entry(coordinator_snapshot.get("consumed"), kind, logical_time, "consumed marker")
        consumed_sources = consumed_event.get("sources")
        if not isinstance(consumed_sources, (list, tuple)):
            raise ValueError("E-CPU consumed marker sources are malformed")
        if len(set(consumed_sources)) != len(consumed_sources):
            raise ValueError("E-CPU consumed marker contains duplicate sources")
        if set(consumed_sources) != set(links_by_source):
            raise ValueError("E-CPU receiver has not consumed/ACKed every event source")

        consume_intents = coordinator_snapshot.get("consume_intents")
        if not isinstance(consume_intents, (list, tuple)):
            raise ValueError("E-CPU consume_intents snapshot must be a sequence")
        for item in consume_intents:
            if not isinstance(item, Mapping) or item.get("kind") != kind or item.get("logical_time") != logical_time:
                continue
            pending_links = item.get("links")
            if not isinstance(pending_links, (list, tuple)):
                raise ValueError("E-CPU event consume-intent links are malformed")
            if pending_links:
                raise ValueError("E-CPU event retains unresolved consume intents")

        apply_intents = coordinator_snapshot.get("apply_intents")
        if not isinstance(apply_intents, (list, tuple)):
            raise ValueError("E-CPU apply_intents snapshot must be a sequence")
        if any(
            isinstance(item, Mapping)
            and item.get("kind") == kind
            and item.get("logical_time") == logical_time
            for item in apply_intents
        ):
            raise ValueError("E-CPU event retains an unresolved apply intent")

        consensus = coordinator_snapshot.get("policy_consensus")
        if not isinstance(consensus, Mapping):
            raise ValueError("E-CPU commit snapshot lacks policy consensus")
        finalized = _event_entry(consensus.get("finalized"), kind, logical_time, "finalized consensus")
        if finalized.get("status") != "AUTHORIZED":
            raise ValueError("E-CPU commit snapshot does not preserve AUTHORIZED finalization")
        policy = consensus.get("policy")
        if not isinstance(policy, Mapping):
            raise ValueError("E-CPU commit snapshot lacks authority policy")
        policy_digest = _digest(dict(policy))
        if policy_digest != authorization_details.get("policy_digest"):
            raise ValueError("E-CPU commit policy differs from the path authorization receipt")
        representative_source = _nonempty(representative_link.get("source"), "representative source")
        if representative_source != authorization_details.get("representative_source"):
            raise ValueError("E-CPU commit representative differs from the path authorization receipt")
        decision_payload = {
            "kind": kind,
            "logical_time": logical_time,
            "status": getattr(decision, "status", None),
            "quorum": getattr(decision, "quorum", None),
            "strict": getattr(decision, "strict", None),
            "observed_sources": sorted(getattr(decision, "observed_sources", ())),
            "dissenting_sources": sorted(getattr(decision, "dissenting_sources", ())),
            "missing_sources": sorted(getattr(decision, "missing_sources", ())),
            "canonical_payload": (
                None
                if getattr(decision, "canonical_payload", None) is None
                else list(decision.canonical_payload)
            ),
            "representative_source": representative_source,
            "policy_digest": policy_digest,
        }
        if _digest(decision_payload) != authorization_details.get("decision_digest"):
            raise ValueError("E-CPU commit decision differs from the path authorization receipt")

        target_pid = coordinator_snapshot.get("target_pid")
        register_prefix = _nonempty(coordinator_snapshot.get("register_prefix"), "register_prefix")
        if isinstance(target_pid, bool) or not isinstance(target_pid, int) or target_pid <= 0:
            raise ValueError("E-CPU target_pid must be positive")

        vm_snapshot = self.coordinator.vm.snapshot()
        if not isinstance(vm_snapshot, Mapping):
            raise ValueError("E-CPU VM snapshot must be a mapping")
        receipts = vm_snapshot.get("resolver_observation_receipts")
        if not isinstance(receipts, (list, tuple)):
            raise ValueError("E-CPU VM snapshot lacks observation idempotence receipts")
        payload = representative_link.get("payload")
        if not isinstance(payload, (list, tuple)):
            raise ValueError("E-CPU representative payload is malformed")
        sequence = representative_link.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
            raise ValueError("E-CPU representative sequence must be positive")
        receipt_match = any(
            isinstance(item, Mapping)
            and item.get("pid") == target_pid
            and item.get("source") == representative_source
            and item.get("sequence") == sequence
            and item.get("payload") == list(payload)
            for item in receipts
        )
        if not receipt_match:
            raise ValueError("E-CPU VM lacks the exact representative application receipt")

        observation = self.decode_observation(tuple(payload))
        if (
            getattr(observation, "kind", None) != kind
            or getattr(observation, "logical_time", None) != logical_time
            or getattr(observation, "source", None) != representative_source
        ):
            raise ValueError("decoded E-CPU representative observation identity mismatch")
        expected_registers = observation.register_values(register_prefix)
        if not isinstance(expected_registers, Mapping) or not expected_registers:
            raise ValueError("E-CPU representative projects no VM registers")
        task = self.coordinator.vm.scheduler.tasks.get(target_pid)
        if task is None or not callable(getattr(task.backend, "read_register", None)):
            raise ValueError("E-CPU target VM task does not expose register readback")

        actual_registers = {}
        for name, expected in expected_registers.items():
            _nonempty(name, "register name")
            if isinstance(expected, bool) or not isinstance(expected, int):
                raise ValueError("E-CPU register projection must contain strict integers")
            actual = task.backend.read_register(name)
            if actual != expected:
                raise ValueError(f"E-CPU VM register readback differs for {name}")
            actual_registers[name] = actual

        projection_digest = _digest(dict(sorted(actual_registers.items())))
        checkpoint_digest = self.coordinator.save_checkpoint(checkpoint_path)
        if not isinstance(checkpoint_digest, str) or _SHA256.fullmatch(checkpoint_digest) is None:
            raise ValueError("E-CPU checkpoint writer returned an invalid SHA-256 digest")

        path.append(
            "applied",
            actor,
            evidence_ref=checkpoint_ref,
            details={
                "application_id": f"{kind}:{logical_time}",
                "target_id": str(target_pid),
                "projection_digest": projection_digest,
                "register_prefix": register_prefix,
                "receiver_consumed_sources": sorted(links_by_source),
                "receiver_ack_emitted": True,
                "checkpoint_digest": checkpoint_digest,
            },
        )
        return ECPUApplicationRecord(
            event_kind=kind,
            logical_time=logical_time,
            target_pid=target_pid,
            representative_source=representative_source,
            representative_sequence=sequence,
            projection_digest=projection_digest,
            checkpoint_ref=checkpoint_ref,
            checkpoint_digest=checkpoint_digest,
        )
