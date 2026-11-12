"""Controlled fault/recovery matrix for E-CPU's reliable observation path.

Requires the pinned E-CPU checkout on PYTHONPATH and ECPU_ROOT:
    python experiments/ecpu-reliable-observation-recovery/run_recovery_matrix.py --output-dir results
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_DIR = ROOT / "bridges" / "observation-path"
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

from operation_spans import (
    OperationSpanRecorder,
    build_operation_cost_profiles,
    validate_operation_cost_profiles,
    validate_operation_span,
)

EXPERIMENT_ID = "ecpu-reliable-observation-recovery-v1"
EXPERIMENT_SCHEMA = "in-formation.ecpu-reliable-observation-recovery/0.1"
ECPU_REFERENCE_COMMIT = "800f94f83ffd6f527ed093c8d1c1e93e153c34f6"

# Independent, fully crossed factors. Every quorum value is feasible for every
# source-count value, so source-count and quorum width are not a joint factor.
SOURCE_COUNTS = (4, 8)
QUORUM_WIDTHS = (1, 2, 4)
DROP_FIRST_DATA_FRAME = (False, True)
DROP_FIRST_ACK = (False, True)
DEFAULT_REPLICATES = 3
MINIMUM_PROFILE_SAMPLES = 3
LOGICAL_TIME = 1
INTERPRETATION_LIMITS = [
    "This is a deterministic local fault-injection experiment, not a network emulator or deployment benchmark.",
    "FaultInjectingTransport wraps E-CPU's DurableMailboxTransport; dropped frames are omitted before durable enqueue.",
    "Only the first source is selected for injected loss; other source channels provide matching observations.",
    "The data-loss and ACK-loss factors are crossed independently; ACK drop indices account for the extra data retry send.",
    "The matrix waits for all configured sources before quorum finalization, even when quorum is lower than source count.",
    "All source observations agree by construction; this experiment does not test conflict or dissent semantics.",
    "Operation spans are synchronous monotonic wall durations, not CPU time.",
    "Three repetitions are a descriptive pilot threshold, not a confidence interval, stable percentile estimate, or causal law.",
    "A verified durable mailbox replay establishes local log integrity under this test, not multi-process crash recovery or remote durability.",
    "No information-per-cost ratio is computed and no adaptive attention policy is updated.",
]


def canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def matrix_conditions() -> list[dict[str, Any]]:
    return [
        {
            "source_count": source_count,
            "quorum": quorum,
            "drop_first_data_frame": drop_data,
            "drop_first_ack": drop_ack,
        }
        for source_count, quorum, drop_data, drop_ack in itertools.product(
            SOURCE_COUNTS, QUORUM_WIDTHS, DROP_FIRST_DATA_FRAME, DROP_FIRST_ACK
        )
    ]


def validate_condition(condition: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "source_count", "quorum", "drop_first_data_frame", "drop_first_ack"
    }
    if set(condition) != expected:
        raise ValueError("condition fields differ from the declared recovery matrix")
    source_count = condition["source_count"]
    quorum = condition["quorum"]
    if type(source_count) is not int or source_count not in SOURCE_COUNTS:
        raise ValueError("source_count is outside the declared factor levels")
    if type(quorum) is not int or quorum not in QUORUM_WIDTHS or quorum > source_count:
        raise ValueError("quorum is outside the feasible declared factor levels")
    for name in ("drop_first_data_frame", "drop_first_ack"):
        if type(condition[name]) is not bool:
            raise ValueError(f"{name} must be a Boolean factor")
    return {
        "source_count": source_count,
        "quorum": quorum,
        "drop_first_data_frame": condition["drop_first_data_frame"],
        "drop_first_ack": condition["drop_first_ack"],
    }


def fault_drop_indices(
    source: str,
    target_source: str,
    *,
    drop_first_data_frame: bool,
    drop_first_ack: bool,
) -> frozenset[int]:
    """Return send ordinals for one channel's wrapper, not global transport ordinals.

    The wrapper sees RDATA as send 1. Its first RACK is send 2 when data arrives
    immediately, or send 3 when the first RDATA is dropped and retransmitted.
    """
    if source != target_source:
        return frozenset()
    indices: set[int] = set()
    if drop_first_data_frame:
        indices.add(1)
    if drop_first_ack:
        indices.add(2 + int(drop_first_data_frame))
    return frozenset(indices)


def _measure(
    recorder: OperationSpanRecorder,
    *,
    attempt_id: str,
    span_id: str,
    operation_id: str,
    operation: Any,
    context: Mapping[str, Any],
) -> Any:
    return recorder.measure(
        attempt_id=attempt_id,
        span_id=span_id,
        operation_id=operation_id,
        operation=operation,
        context=dict(context),
    )


def _run_attempt(
    condition: Mapping[str, Any],
    replicate: int,
    recorder: OperationSpanRecorder,
    mailcpu: Mapping[str, Any],
    condition_index: int,
) -> dict[str, Any]:
    condition = validate_condition(condition)
    attempt_id = f"recovery-{condition_index:02d}-replicate-{replicate:02d}"
    observation_id = f"{attempt_id}:resolver:1"
    sources = tuple(f"S{index:02d}" for index in range(condition["source_count"]))
    target_source = sources[0]
    base_context = {
        **condition,
        "experiment_id": EXPERIMENT_ID,
        "workload_id": attempt_id,
        "observation_id": observation_id,
        "logical_time": LOGICAL_TIME,
        "replicate": replicate,
    }

    with tempfile.TemporaryDirectory(prefix="ecpu-observation-recovery-") as temporary:
        root = Path(temporary)
        durable = mailcpu["DurableMailboxTransport"](root / "mailbox.jsonl")
        transports = {}
        for source in sources:
            profile = mailcpu["FaultProfile"](
                drop_indices=fault_drop_indices(
                    source,
                    target_source,
                    drop_first_data_frame=condition["drop_first_data_frame"],
                    drop_first_ack=condition["drop_first_ack"],
                )
            )
            transports[source] = mailcpu["FaultInjectingTransport"](
                profile, inner=durable
            )

        vm = mailcpu["MailCPUVirtualMachine"]()
        pid = vm.spawn_program(
            mailcpu["Program"]((mailcpu["Instruction"](mailcpu["Op"].HALT),)),
            attempt_id,
        )
        senders = {}
        receivers = {}
        reliability_policy = mailcpu["ReliabilityPolicy"](
            lease_ticks=1, max_attempts=4, window_size=4
        )
        for source in sources:
            receiver_name = f"receiver-{source}"
            channel_name = f"recovery-{source}"
            senders[source] = mailcpu["ReliableChannel"](
                transports[source],
                source,
                receiver_name,
                channel_name,
                reliability_policy,
                peer=receiver_name,
            )
            receivers[source] = mailcpu["ReliableChannel"](
                transports[source],
                receiver_name,
                receiver_name,
                channel_name,
                reliability_policy,
                peer=source,
            )

        coordinator = mailcpu["GatedObservationCoordinator"](
            vm,
            mailcpu["ObservationAuthorityPolicy"](
                "resolver", sources, quorum=condition["quorum"], strict=True
            ),
            receivers,
            pid,
            "resolver",
        )

        def span_context(phase: str, **extra: Any) -> dict[str, Any]:
            return {**base_context, "phase": phase, **extra}

        send_sequences: dict[str, int] = {}
        for source in sources:
            observation = mailcpu["ResolverObservation"](
                source=source,
                domain="recovery-fixture.invalid",
                record_type="TXT",
                logical_time=LOGICAL_TIME,
                status="NOERROR",
                hit=True,
                ttl=300,
                value="controlled-recovery-observation",
            )
            sequence = _measure(
                recorder,
                attempt_id=attempt_id,
                span_id=f"send:{source}",
                operation_id="ecpu.ReliableChannel.send",
                operation=lambda sender=senders[source], payload=observation.to_payload():
                    sender.send(payload),
                context=span_context("initial_send", source=source),
            )
            if sequence != 1:
                raise AssertionError("each fresh sender must begin at reliable sequence 1")
            send_sequences[source] = sequence

        checkpoint_path = root / "receiver.checkpoint"
        checkpoint_counter = 0
        checkpoint_digests: list[str] = []
        original_save_checkpoint = coordinator.save_checkpoint

        def measured_save_checkpoint(path: str | Path) -> str:
            nonlocal checkpoint_counter
            checkpoint_counter += 1
            value = _measure(
                recorder,
                attempt_id=attempt_id,
                span_id=f"checkpoint:{checkpoint_counter}",
                operation_id="ecpu.GatedObservationCoordinator.save_checkpoint",
                operation=lambda: original_save_checkpoint(path),
                context=span_context("commit_checkpoint", checkpoint_index=checkpoint_counter),
            )
            checkpoint_digests.append(value)
            return value

        coordinator.save_checkpoint = measured_save_checkpoint

        first_links = _measure(
            recorder,
            attempt_id=attempt_id,
            span_id="ingest:initial",
            operation_id="ecpu.GatedObservationCoordinator.ingest_available",
            operation=coordinator.ingest_available,
            context=span_context("initial_intake"),
        )
        first_sources = sorted(link.source for link in first_links)
        expected_first = sorted(
            source for source in sources
            if not (condition["drop_first_data_frame"] and source == target_source)
        )
        if first_sources != expected_first:
            raise AssertionError(
                f"initial intake mismatch: observed {first_sources}, expected {expected_first}"
            )

        data_retry_count = 0
        data_recovery_links = 0
        if condition["drop_first_data_frame"]:
            failed = _measure(
                recorder,
                attempt_id=attempt_id,
                span_id="tick:data-retry",
                operation_id="ecpu.ReliableChannel.tick",
                operation=senders[target_source].tick,
                context=span_context("data_retry", source=target_source),
            )
            if failed:
                raise AssertionError("a retryable data loss was marked permanently failed")
            data_retry_count += 1
            recovered_links = _measure(
                recorder,
                attempt_id=attempt_id,
                span_id="ingest:data-retry",
                operation_id="ecpu.GatedObservationCoordinator.ingest_available",
                operation=coordinator.ingest_available,
                context=span_context("data_recovery_intake", source=target_source),
            )
            recovered_sources = sorted(link.source for link in recovered_links)
            if recovered_sources != [target_source]:
                raise AssertionError(
                    f"data retry did not restore exactly the missing source: {recovered_sources}"
                )
            data_recovery_links = len(recovered_links)

        all_links = coordinator.snapshot()["links"]
        if len(all_links) != 1:
            raise AssertionError("exactly one logical event should be retained")
        observed_sources = sorted(item["source"] for item in all_links[0]["sources"])
        if observed_sources != sorted(sources):
            raise AssertionError("the evidence links do not cover every configured source")

        decision = _measure(
            recorder,
            attempt_id=attempt_id,
            span_id="finalize",
            operation_id="ecpu.GatedObservationCoordinator.finalize_event",
            operation=lambda: coordinator.finalize_event("resolver", LOGICAL_TIME),
            context=span_context("finalize"),
        )
        if decision.status != "AUTHORIZED":
            raise AssertionError(f"matching observations failed quorum {condition['quorum']}: {decision.status}")

        commit_decision = _measure(
            recorder,
            attempt_id=attempt_id,
            span_id="commit",
            operation_id="ecpu.GatedObservationCoordinator.commit_event",
            operation=lambda: coordinator.commit_event("resolver", LOGICAL_TIME, checkpoint_path),
            context=span_context("commit"),
        )
        if commit_decision.status != "AUTHORIZED" or not checkpoint_path.exists():
            raise AssertionError("authorized event did not complete the durable VM/checkpoint path")

        initial_ack_result = _measure(
            recorder,
            attempt_id=attempt_id,
            span_id="acks:initial",
            operation_id="ecpu.GatedObservationCoordinator.process_acks",
            operation=lambda: coordinator.process_acks(senders),
            context=span_context("initial_ack_processing"),
        )
        pending_after_initial_acks = {
            source: list(senders[source].pending_sequences()) for source in sources
        }
        expected_pending = [1] if condition["drop_first_ack"] else []
        if pending_after_initial_acks[target_source] != expected_pending:
            raise AssertionError(
                "sender pending state does not match the injected ACK-loss condition"
            )
        for source in sources[1:]:
            if pending_after_initial_acks[source]:
                raise AssertionError(f"non-target sender {source} retained an unexpected pending frame")

        ack_retry_count = 0
        duplicate_cleanup_count = 0
        recovery_ack_result: dict[str, tuple[int, ...]] = {}
        if condition["drop_first_ack"]:
            failed = _measure(
                recorder,
                attempt_id=attempt_id,
                span_id="tick:ack-retry",
                operation_id="ecpu.ReliableChannel.tick",
                operation=senders[target_source].tick,
                context=span_context("ack_recovery_retry", source=target_source),
            )
            if failed:
                raise AssertionError("ACK retry was marked permanently failed")
            ack_retry_count += 1
            duplicate_links = _measure(
                recorder,
                attempt_id=attempt_id,
                span_id="ingest:duplicate-cleanup",
                operation_id="ecpu.GatedObservationCoordinator.ingest_available",
                operation=coordinator.ingest_available,
                context=span_context("duplicate_cleanup", source=target_source),
            )
            if duplicate_links:
                raise AssertionError("an already-applied reliable duplicate became new evidence")
            duplicate_cleanup_count += 1
            recovery_ack_result = _measure(
                recorder,
                attempt_id=attempt_id,
                span_id="acks:recovery",
                operation_id="ecpu.GatedObservationCoordinator.process_acks",
                operation=lambda: coordinator.process_acks(senders),
                context=span_context("recovery_ack_processing", source=target_source),
            )

        final_pending = {
            source: list(senders[source].pending_sequences()) for source in sources
        }
        if any(final_pending.values()):
            raise AssertionError(f"some sender sequences remain pending: {final_pending}")

        coordinator_state = coordinator.snapshot()
        if len(coordinator_state["applied"]) != 1:
            raise AssertionError("the representative observation was not applied exactly once")
        register_readback = vm.scheduler.tasks[pid].backend.read_register("resolver_hit")
        if register_readback != 1:
            raise AssertionError("VM register readback differs from the authorized hit observation")

        checkpoint_envelope = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint_state = checkpoint_envelope["state"]
        checkpoint_digest = hashlib.sha256(
            json.dumps(
                checkpoint_state, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        checkpoint_valid = checkpoint_digest == checkpoint_envelope.get("digest")
        if not checkpoint_valid:
            raise AssertionError("receiver checkpoint digest failed independent reconstruction")

        if not durable.verify():
            raise AssertionError("durable mailbox hash-chain replay did not reproduce live state")
        durable_state = durable.snapshot()

        fault_decisions = []
        for source, transport in transports.items():
            for item in transport.observations:
                fault_decisions.append({
                    "source": source,
                    "send_index": item.send_index,
                    "action": item.action,
                    "delay": item.delay,
                    "copies": item.copies,
                })
        injected_drops = sorted(
            (item["source"], item["send_index"])
            for item in fault_decisions if item["action"] == "drop"
        )
        expected_drops = sorted(
            (target_source, index)
            for index in fault_drop_indices(
                target_source,
                target_source,
                drop_first_data_frame=condition["drop_first_data_frame"],
                drop_first_ack=condition["drop_first_ack"],
            )
        )
        if injected_drops != expected_drops:
            raise AssertionError(
                f"fault schedule mismatch: actual {injected_drops}, expected {expected_drops}"
            )

        return {
            "attempt_id": attempt_id,
            "observation_id": observation_id,
            **condition,
            "replicate": replicate,
            "source_ids": list(sources),
            "initial_admitted_sources": first_sources,
            "admitted_source_count_after_recovery": len(observed_sources),
            "data_retry_count": data_retry_count,
            "data_recovery_link_count": data_recovery_links,
            "authorization_status": decision.status,
            "authorization_quorum": condition["quorum"],
            "initial_acknowledged": {
                source: list(initial_ack_result[source]) for source in sources
            },
            "pending_after_initial_acks": pending_after_initial_acks,
            "ack_retry_count": ack_retry_count,
            "duplicate_cleanup_count": duplicate_cleanup_count,
            "recovery_acknowledged": {
                source: list(recovery_ack_result.get(source, ())) for source in sources
            },
            "final_pending_sequences": final_pending,
            "application_count": len(coordinator_state["applied"]),
            "register_readback": register_readback,
            "checkpoint_call_count": checkpoint_counter,
            "checkpoint_digests": checkpoint_digests,
            "checkpoint_digest": checkpoint_envelope["digest"],
            "checkpoint_digest_reconstructed": checkpoint_valid,
            "durable_log_verified": True,
            "durable_log_sequence": durable_state["sequence"],
            "durable_log_head": durable_state["head_hex"],
            "fault_decisions": fault_decisions,
            "injected_drops": [
                {"source": source, "send_index": index}
                for source, index in injected_drops
            ],
        }


def build_cost_profile_matrix(
    conditions: list[dict[str, Any]],
    spans: list[dict[str, Any]],
    *,
    minimum_samples: int,
) -> dict[str, Any]:
    """Build independently reconstructible operation profiles per condition and phase.

    Intake, data recovery, duplicate cleanup, initial ACK handling, and recovery
    ACK handling are distinct workloads. They must not be blended into one
    operation distribution merely because they call the same method.
    """
    if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int) or minimum_samples < 1:
        raise ValueError("minimum_samples must be a positive integer")
    validated_spans = [validate_operation_span(span) for span in spans]
    phase_profiles = []
    matched_span_ids: set[tuple[str, str]] = set()
    for condition in conditions:
        selected = [
            span for span in validated_spans
            if all(span["context"].get(key) == value for key, value in condition.items())
        ]
        if not selected:
            raise ValueError("condition has no matching operation spans")
        phases = sorted({
            span["context"].get("phase")
            for span in selected
        })
        for phase in phases:
            if not isinstance(phase, str) or not phase:
                raise ValueError("every recovery span must declare a non-empty phase")
            phase_spans = [
                span for span in selected
                if span["context"].get("phase") == phase
            ]
            if len(phase_spans) < minimum_samples:
                raise ValueError(
                    f"condition phase {phase!r} has fewer than {minimum_samples} samples"
                )
            profile = build_operation_cost_profiles(
                phase_spans, minimum_samples=minimum_samples
            )
            validate_operation_cost_profiles(profile, phase_spans)
            phase_profiles.append({
                "condition": condition,
                "phase": phase,
                "span_count": len(phase_spans),
                "profile": profile,
            })
            matched_span_ids.update(
                (span["attempt_id"], span["span_id"]) for span in phase_spans
            )
    expected_span_ids = {
        (span["attempt_id"], span["span_id"]) for span in validated_spans
    }
    if matched_span_ids != expected_span_ids:
        raise ValueError("phase profiles do not partition the complete source-span set")
    core = {
        "format": "in-formation.ecpu-reliable-observation-recovery-cost-matrix",
        "schema": EXPERIMENT_SCHEMA,
        "minimum_samples": minimum_samples,
        "phase_profiles": phase_profiles,
        "policy_effect": "none",
        "interpretation": (
            "Profiles are partitioned by workload condition and explicit call phase; "
            "initial intake, data recovery, duplicate cleanup, initial ACK processing, "
            "and recovery ACK processing are never pooled."
        ),
    }
    return {**core, "profile_matrix_digest": digest(core)}


def validate_cost_profile_matrix(
    report: Mapping[str, Any],
    conditions: list[dict[str, Any]],
    spans: list[dict[str, Any]],
) -> dict[str, Any]:
    supplied = dict(report)
    supplied_digest = supplied.pop("profile_matrix_digest", None)
    if supplied_digest != digest(supplied):
        raise ValueError("cost profile matrix digest mismatch")
    rebuilt = build_cost_profile_matrix(
        conditions, spans, minimum_samples=int(supplied["minimum_samples"])
    )
    if rebuilt != dict(report):
        raise ValueError("cost profile matrix differs from reconstruction from raw spans")
    return dict(report)


def validate_attempt_result(record: Mapping[str, Any]) -> dict[str, Any]:
    source_count = record["source_count"]
    drop_data = record["drop_first_data_frame"]
    drop_ack = record["drop_first_ack"]
    if type(source_count) is not int or source_count not in SOURCE_COUNTS:
        raise ValueError("attempt source_count is outside the declared factor levels")
    if type(drop_data) is not bool or type(drop_ack) is not bool:
        raise ValueError("attempt fault flags must be Boolean")
    sources = [f"S{index:02d}" for index in range(source_count)]
    target = sources[0]
    if record["source_ids"] != sources:
        raise ValueError("attempt source identity list is not canonical")
    expected_initial = [source for source in sources if not (drop_data and source == target)]
    if record["initial_admitted_sources"] != expected_initial:
        raise ValueError("initial admitted source set does not match injected data loss")
    if record["authorization_status"] != "AUTHORIZED":
        raise ValueError("attempt is not authorized")
    if record["authorization_quorum"] != record["quorum"]:
        raise ValueError("recorded authorization quorum differs from configured quorum")
    if record["admitted_source_count_after_recovery"] != source_count:
        raise ValueError("attempt evidence source coverage is incomplete")
    if record["data_retry_count"] != int(drop_data):
        raise ValueError("data retry count does not match injected data loss")
    if record["data_recovery_link_count"] != int(drop_data):
        raise ValueError("data recovery link count does not match injected data loss")
    if record["ack_retry_count"] != int(drop_ack):
        raise ValueError("ACK retry count does not match injected ACK loss")
    if record["duplicate_cleanup_count"] != int(drop_ack):
        raise ValueError("duplicate cleanup count does not match injected ACK loss")

    expected_initial_acks = {
        source: ([] if source == target and drop_ack else [1])
        for source in sources
    }
    if record["initial_acknowledged"] != expected_initial_acks:
        raise ValueError("initial sender ACK receipts do not match the injected ACK schedule")
    expected_pending = {
        source: ([1] if source == target and drop_ack else [])
        for source in sources
    }
    if record["pending_after_initial_acks"] != expected_pending:
        raise ValueError("initial sender pending state does not match the ACK-loss schedule")
    expected_recovery_acks = {
        source: ([1] if source == target and drop_ack else [])
        for source in sources
    }
    if record["recovery_acknowledged"] != expected_recovery_acks:
        raise ValueError("recovery ACK receipts do not match the injected ACK schedule")
    if record["final_pending_sequences"] != {source: [] for source in sources}:
        raise ValueError("final sender pending sets are not all empty")

    expected_drops = [
        {"source": target, "send_index": index}
        for index in sorted(fault_drop_indices(
            target,
            target,
            drop_first_data_frame=drop_data,
            drop_first_ack=drop_ack,
        ))
    ]
    if record["injected_drops"] != expected_drops:
        raise ValueError("recorded injected drops differ from the declared fault schedule")
    if record["application_count"] != 1 or record["register_readback"] != 1:
        raise ValueError("logical observation was not applied exactly once")
    if record["checkpoint_call_count"] != 2 * source_count + 3:
        raise ValueError("checkpoint count does not match the coordinator's ordered consume/apply protocol")
    if len(record["checkpoint_digests"]) != record["checkpoint_call_count"]:
        raise ValueError("checkpoint digest count differs from measured checkpoint calls")
    if not record["checkpoint_digest_reconstructed"] or not record["durable_log_verified"]:
        raise ValueError("durable recovery evidence did not verify")
    if type(record["durable_log_sequence"]) is not int or record["durable_log_sequence"] <= 0:
        raise ValueError("durable mailbox log sequence is invalid")
    head = record["durable_log_head"]
    if type(head) is not str or len(head) != 64 or any(c not in "0123456789abcdef" for c in head):
        raise ValueError("durable mailbox hash-chain head is invalid")
    return dict(record)


def run_matrix(output_dir: str | Path, *, replicates: int = DEFAULT_REPLICATES) -> dict[str, Any]:
    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates < MINIMUM_PROFILE_SAMPLES:
        raise ValueError(f"replicates must be an integer >= {MINIMUM_PROFILE_SAMPLES}")
    ecpu_root_text = os.environ.get("ECPU_ROOT", "")
    if not ecpu_root_text:
        raise RuntimeError("ECPU_ROOT must identify the pinned E-CPU checkout")
    ecpu_root = Path(ecpu_root_text).resolve()
    if not ecpu_root.is_dir():
        raise RuntimeError(f"ECPU_ROOT is not a directory: {ecpu_root}")
    revision = subprocess.run(
        ["git", "-C", str(ecpu_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if revision != ECPU_REFERENCE_COMMIT:
        raise RuntimeError(
            f"E-CPU revision mismatch: expected {ECPU_REFERENCE_COMMIT}, got {revision}"
        )

    import mailcpu

    required = (
        "DurableMailboxTransport", "FaultInjectingTransport", "FaultProfile",
        "MailCPUVirtualMachine", "Program", "Instruction", "Op",
        "ReliabilityPolicy", "ReliableChannel", "GatedObservationCoordinator",
        "ObservationAuthorityPolicy", "ResolverObservation",
    )
    missing = [name for name in required if not hasattr(mailcpu, name)]
    if missing:
        raise RuntimeError(f"pinned E-CPU package lacks required APIs: {missing}")

    conditions = matrix_conditions()
    clock_actor_id = "ecpu-observation-recovery-process"
    clock_segment_id = (
        f"{os.environ.get('GITHUB_RUN_ID', 'local')}-{os.getpid()}-{time.monotonic_ns()}"
    )
    recorder = OperationSpanRecorder(
        clock_actor_id=clock_actor_id,
        clock_segment_id=clock_segment_id,
    )
    records = []
    for condition_index, condition in enumerate(conditions):
        for replicate in range(replicates):
            record = _run_attempt(
                condition, replicate, recorder, vars(mailcpu), condition_index
            )
            records.append(validate_attempt_result(record))

    spans = list(recorder.spans)
    for span in spans:
        validate_operation_span(span)
        context = span["context"]
        if context.get("experiment_id") != EXPERIMENT_ID:
            raise AssertionError("operation span lost experiment identity")
        if not context.get("observation_id") or not context.get("workload_id"):
            raise AssertionError("operation span lacks observation/workload correlation")

    profile_matrix = build_cost_profile_matrix(
        conditions, spans, minimum_samples=MINIMUM_PROFILE_SAMPLES
    )
    validate_cost_profile_matrix(profile_matrix, conditions, spans)

    expected_attempts = len(conditions) * replicates
    if len(records) != expected_attempts:
        raise AssertionError("recovery matrix did not complete its declared attempts")
    if len(spans) == 0:
        raise AssertionError("recovery matrix did not record any operation spans")

    report_core = {
        "format": "in-formation.ecpu-reliable-observation-recovery",
        "schema": EXPERIMENT_SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "ecpu_reference_commit": ECPU_REFERENCE_COMMIT,
        "python_version": platform.python_version(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_implementation": platform.python_implementation(),
        },
        "clock_actor_id": clock_actor_id,
        "clock_segment_id": clock_segment_id,
        "replicates_per_condition": replicates,
        "factor_levels": {
            "source_count": list(SOURCE_COUNTS),
            "quorum": list(QUORUM_WIDTHS),
            "drop_first_data_frame": list(DROP_FIRST_DATA_FRAME),
            "drop_first_ack": list(DROP_FIRST_ACK),
        },
        "condition_count": len(conditions),
        "attempt_count": len(records),
        "operation_span_count": len(spans),
        "application_count": sum(record["application_count"] for record in records),
        "data_retry_attempt_count": sum(record["data_retry_count"] for record in records),
        "ack_retry_attempt_count": sum(record["ack_retry_count"] for record in records),
        "duplicate_cleanup_count": sum(record["duplicate_cleanup_count"] for record in records),
        "all_attempts_authorized": all(
            record["authorization_status"] == "AUTHORIZED" for record in records
        ),
        "all_applications_exactly_once": all(
            record["application_count"] == 1 for record in records
        ),
        "all_senders_acknowledged": all(
            not any(record["final_pending_sequences"].values()) for record in records
        ),
        "all_durable_logs_verified": all(
            record["durable_log_verified"] for record in records
        ),
        "profile_matrix_digest": profile_matrix["profile_matrix_digest"],
        "phase_profile_count": len(profile_matrix["phase_profiles"]),
        "minimum_profile_samples": MINIMUM_PROFILE_SAMPLES,
        "interpretation_limits": list(INTERPRETATION_LIMITS),
    }
    report = {**report_core, "report_digest": digest(report_core)}
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        schema_path = Path(__file__).with_name("run-manifest.schema.json")
        schema_document = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(report, schema_document)
    if not all((
        report["all_attempts_authorized"],
        report["all_applications_exactly_once"],
        report["all_senders_acknowledged"],
        report["all_durable_logs_verified"],
    )):
        raise AssertionError("one or more recovery-matrix invariants failed")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    documents = {
        "run-manifest.json": report,
        "attempt-results.json": records,
        "operation-spans.json": {"spans": spans},
        "operation-cost-profiles.json": profile_matrix,
    }
    for name, document in documents.items():
        (output / name).write_text(
            json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run E-CPU's controlled reliable-observation loss/recovery matrix."
    )
    parser.add_argument("--output-dir", required=True, metavar="DIR")
    parser.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES)
    args = parser.parse_args(argv)
    try:
        report = run_matrix(args.output_dir, replicates=args.replicates)
    except (AssertionError, KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        parser.error(str(error))
        return 2
    print(json.dumps({
        "experiment_id": report["experiment_id"],
        "condition_count": report["condition_count"],
        "attempt_count": report["attempt_count"],
        "operation_span_count": report["operation_span_count"],
        "application_count": report["application_count"],
        "data_retry_attempt_count": report["data_retry_attempt_count"],
        "ack_retry_attempt_count": report["ack_retry_attempt_count"],
        "duplicate_cleanup_count": report["duplicate_cleanup_count"],
        "output_dir": str(Path(args.output_dir)),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
