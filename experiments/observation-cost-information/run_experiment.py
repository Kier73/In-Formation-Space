"""Controlled E-CPU observation workload matrix.

The matrix varies the size of the ResolverObservation.value field, preloaded
per-source queue depth, source count/quorum, and independent concurrent
receiver calls. It records synchronous E-CPU call spans and deterministic
fixture information outcomes as separate evidence streams.

Run with the pinned E-CPU checkout on PYTHONPATH and ECPU_ROOT set:
    python experiments/observation-cost-information/run_experiment.py --output-dir results
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
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_DIR = ROOT / "bridges" / "observation-path"
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

from observation_outcomes import build_observation_outcome, validate_observation_outcome
from operation_spans import (
    OperationSpanRecorder,
    build_operation_cost_profiles,
    validate_operation_cost_profiles,
    validate_operation_span,
)

EXPERIMENT_ID = "ecpu-observation-cost-information-v1"
EXPERIMENT_SCHEMA = "in-formation.ecpu-observation-cost-information/0.1"
ECPU_REFERENCE_COMMIT = "800f94f83ffd6f527ed093c8d1c1e93e153c34f6"
PAYLOAD_VALUE_BYTES = (64, 1024)
QUEUE_DEPTHS = (1, 3)
SOURCE_QUORUMS = ((2, 2), (4, 2), (4, 4))
RECEIVER_LOAD_WORKERS = (0, 2)
DEFAULT_REPLICATES = 3
MINIMUM_PROFILE_SAMPLES = 3
CONDITION_FIELDS = (
    "payload_value_bytes",
    "queue_depth_initial_per_source",
    "source_count",
    "quorum",
    "receiver_load_workers",
)
INTERPRETATION_LIMITS = [
    "The E-CPU runtime is pinned to the declared reference commit; results apply to this implementation and environment only.",
    "Payload size is the UTF-8 byte length of ResolverObservation.value, not the complete serialized transport frame.",
    "Queue depth is the number of preloaded typed observation frames per source before the first receiver intake call.",
    "Receiver load is a synchronized burst of independent in-process GatedObservationCoordinator.ingest_available() calls, not a production network or multi-host load test.",
    "The durable transport uses one local append-only mailbox log per workload attempt; results include local filesystem and host scheduling effects.",
    "All sources in one event supply matching canonical observations. The quorum factor changes the authority threshold while all configured sources are present.",
    "The hit/miss prior is a declared deterministic fixture model, not an empirical claim about an external resolver or world state.",
    "Information outcomes are computed from the fixture model and observed typed return. They are not derived from elapsed time or cost.",
    "Cost distributions are descriptive pilot measurements. They do not establish causal scaling laws, production capacity, or a calibrated adaptive policy.",
    "Wall duration around a synchronous call includes blocking and local scheduling; it is not CPU time.",
]


def canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def matrix_conditions() -> list[dict[str, int]]:
    conditions = []
    for payload_bytes, queue_depth, (source_count, quorum), receiver_load in itertools.product(
        PAYLOAD_VALUE_BYTES, QUEUE_DEPTHS, SOURCE_QUORUMS, RECEIVER_LOAD_WORKERS
    ):
        conditions.append({
            "payload_value_bytes": payload_bytes,
            "queue_depth_initial_per_source": queue_depth,
            "source_count": source_count,
            "quorum": quorum,
            "receiver_load_workers": receiver_load,
        })
    return conditions


def _condition_key(condition: Mapping[str, Any]) -> tuple[int, ...]:
    values = []
    for field in CONDITION_FIELDS:
        value = condition.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"span context requires non-negative integer {field}")
        values.append(value)
    if condition["source_count"] < 1 or not 1 <= condition["quorum"] <= condition["source_count"]:
        raise ValueError("source_count and quorum are inconsistent")
    if condition["queue_depth_initial_per_source"] < 1:
        raise ValueError("initial queue depth must include at least the target frame")
    if condition["payload_value_bytes"] < 4:
        raise ValueError("payload_value_bytes must fit the hit/miss marker")
    return tuple(values)


def _condition_document(key: tuple[int, ...]) -> dict[str, int]:
    return dict(zip(CONDITION_FIELDS, key))


def _value_for_outcome(outcome: str, byte_count: int) -> str:
    prefix = outcome + ":"
    if len(prefix.encode("utf-8")) > byte_count:
        raise ValueError("payload value is too small for its outcome prefix")
    return prefix + ("x" * (byte_count - len(prefix.encode("utf-8"))))


def _resolver_observation(ResolverObservation: Any, source: str, logical_time: int,
                          outcome: str, payload_value_bytes: int) -> Any:
    value = _value_for_outcome(outcome, payload_value_bytes)
    hit = outcome == "hit"
    return ResolverObservation(
        source=source,
        domain="resolver-fixture.invalid",
        record_type="TXT",
        logical_time=logical_time,
        status="NOERROR" if hit else "NXDOMAIN",
        hit=hit,
        ttl=300 if hit else 0,
        value=value,
    )


def _runtime(transport: Any, sources: Sequence[str], quorum: int, name: str,
             MailCPUVirtualMachine: Any, Program: Any, Instruction: Any, Op: Any,
             ReliableChannel: Any, GatedObservationCoordinator: Any,
             ObservationAuthorityPolicy: Any) -> tuple[Any, int, dict[str, Any], Any]:
    vm = MailCPUVirtualMachine()
    pid = vm.spawn_program(Program((Instruction(Op.HALT),)), name)
    senders = {}
    receivers = {}
    for source in sources:
        receiver_name = f"R-{source}"
        channel_name = f"gate-{source}"
        senders[source] = ReliableChannel(
            transport, source, receiver_name, channel_name, peer=receiver_name
        )
        receivers[source] = ReliableChannel(
            transport, receiver_name, receiver_name, channel_name, peer=source
        )
    coordinator = GatedObservationCoordinator(
        vm,
        ObservationAuthorityPolicy("resolver", tuple(sources), quorum=quorum, strict=True),
        receivers,
        pid,
        "resolver",
    )
    return vm, pid, senders, coordinator


def _background_receiver(payload_value_bytes: int, worker_index: int,
                         mailcpu: Mapping[str, Any]) -> Any:
    transport = mailcpu["InMemoryTransport"]()
    source = f"BG{worker_index}"
    vm, _pid, senders, coordinator = _runtime(
        transport, (source,), 1, f"background-receiver-{worker_index}",
        mailcpu["MailCPUVirtualMachine"], mailcpu["Program"], mailcpu["Instruction"],
        mailcpu["Op"], mailcpu["ReliableChannel"], mailcpu["GatedObservationCoordinator"],
        mailcpu["ObservationAuthorityPolicy"],
    )
    observation = _resolver_observation(
        mailcpu["ResolverObservation"], source, 9000 + worker_index, "miss", payload_value_bytes
    )
    senders[source].send(observation.to_payload())
    return coordinator


def _concurrent_receiver_intake(coordinators: Sequence[Any], primary_operation: Any) -> tuple[Any, int]:
    if not coordinators:
        return primary_operation(), 0
    barrier = threading.Barrier(len(coordinators) + 1)

    def receive_once(coordinator: Any) -> int:
        barrier.wait(timeout=15)
        links = coordinator.ingest_available()
        if len(links) != 1:
            raise AssertionError("background receiver did not admit exactly one observation")
        return len(links)

    with ThreadPoolExecutor(max_workers=len(coordinators)) as executor:
        futures = [executor.submit(receive_once, coordinator) for coordinator in coordinators]
        barrier.wait(timeout=15)
        try:
            primary_result = primary_operation()
        finally:
            background_counts = [future.result(timeout=30) for future in futures]
    return primary_result, sum(background_counts)


def _fixture_hypotheses() -> list[dict[str, Any]]:
    # Two hypotheses predict a hit and two predict a miss. The query is exactly
    # the hit predicate. This is an explicit controlled model, not sensor truth.
    return [
        {"hypothesis_id": "hit-primary", "prior_probability": 0.40,
         "predicted_outcome": "hit", "query_value": True},
        {"hypothesis_id": "hit-secondary", "prior_probability": 0.10,
         "predicted_outcome": "hit", "query_value": True},
        {"hypothesis_id": "miss-nxdomain", "prior_probability": 0.30,
         "predicted_outcome": "miss", "query_value": False},
        {"hypothesis_id": "miss-refused", "prior_probability": 0.20,
         "predicted_outcome": "miss", "query_value": False},
    ]



def build_cost_profile_matrix(
    spans: Sequence[Mapping[str, Any]],
    *,
    minimum_samples: int = MINIMUM_PROFILE_SAMPLES,
) -> dict[str, Any]:
    """Build separate, reconstructible operation profiles per workload condition."""
    if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int) or minimum_samples < 1:
        raise ValueError("minimum_samples must be a positive integer")
    grouped: dict[tuple[int, ...], list[dict[str, Any]]] = {}
    validated = [validate_operation_span(span) for span in spans]
    for span in validated:
        key = _condition_key(span["context"])
        grouped.setdefault(key, []).append(span)
    condition_profiles = []
    for key, condition_spans in sorted(grouped.items()):
        for scope in ("all_events", "target_event"):
            selected = [
                span for span in condition_spans
                if scope == "all_events" or span["context"].get("phase") == "target"
            ]
            if not selected:
                continue
            profile = build_operation_cost_profiles(
                selected, minimum_samples=minimum_samples
            )
            validate_operation_cost_profiles(profile, selected)
            condition_profiles.append({
                "condition": _condition_document(key),
                "scope": scope,
                "profile": profile,
            })
    core = {
        "experiment_id": EXPERIMENT_ID,
        "minimum_samples": minimum_samples,
        "condition_profiles": condition_profiles,
        "policy_effect": "none",
    }
    return {**core, "profile_matrix_digest": digest(core)}


def validate_cost_profile_matrix(
    report: Mapping[str, Any],
    spans: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Independently rebuild every condition profile from the original span records."""
    if not isinstance(report, Mapping):
        raise TypeError("cost profile matrix must be a mapping")
    supplied = dict(report)
    stated_digest = supplied.pop("profile_matrix_digest", None)
    if stated_digest != digest(supplied):
        raise ValueError("cost profile matrix digest does not match its contents")
    if supplied.get("experiment_id") != EXPERIMENT_ID or supplied.get("policy_effect") != "none":
        raise ValueError("unsupported cost profile matrix identity or policy effect")
    rebuilt = build_cost_profile_matrix(
        spans, minimum_samples=supplied.get("minimum_samples")
    )
    if rebuilt != dict(report):
        raise ValueError("cost profile matrix differs from independent reconstruction")
    return dict(report)


def run_matrix(output_dir: str | Path, *, replicates: int = DEFAULT_REPLICATES) -> dict[str, Any]:
    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates < MINIMUM_PROFILE_SAMPLES:
        raise ValueError(f"replicates must be at least {MINIMUM_PROFILE_SAMPLES}")
    try:
        from mailcpu import (
            DurableMailboxTransport,
            GatedObservationCoordinator,
            InMemoryTransport,
            Instruction,
            MailCPUVirtualMachine,
            Op,
            ObservationAuthorityPolicy,
            Program,
            ReliableChannel,
            ResolverObservation,
        )
    except ImportError as error:
        raise RuntimeError(
            "E-CPU must be checked out at the pinned revision and available on PYTHONPATH"
        ) from error

    mailcpu = {
        "DurableMailboxTransport": DurableMailboxTransport,
        "GatedObservationCoordinator": GatedObservationCoordinator,
        "InMemoryTransport": InMemoryTransport,
        "Instruction": Instruction,
        "MailCPUVirtualMachine": MailCPUVirtualMachine,
        "Op": Op,
        "ObservationAuthorityPolicy": ObservationAuthorityPolicy,
        "Program": Program,
        "ReliableChannel": ReliableChannel,
        "ResolverObservation": ResolverObservation,
    }

    ecpu_root = os.environ.get("ECPU_ROOT")
    if not ecpu_root:
        raise RuntimeError("ECPU_ROOT must identify the pinned E-CPU checkout")
    actual_revision = subprocess.check_output(
        ["git", "-C", ecpu_root, "rev-parse", "HEAD"], text=True
    ).strip()
    if actual_revision != ECPU_REFERENCE_COMMIT:
        raise RuntimeError(
            f"E-CPU revision mismatch: expected {ECPU_REFERENCE_COMMIT}, got {actual_revision}"
        )

    run_identity = os.environ.get("GITHUB_RUN_ID", f"local-{os.getpid()}")
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    clock_actor_id = "ecpu-observation-cost-matrix-process"
    clock_segment_id = f"{run_identity}-{run_attempt}"
    recorder = OperationSpanRecorder(
        clock_actor_id=clock_actor_id,
        clock_segment_id=clock_segment_id,
    )
    conditions = matrix_conditions()
    workload_results: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []
    information_outcomes: list[dict[str, Any]] = []
    output = Path(output_dir)
    evidence_dir = output / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    attempt_ordinal = 0
    for condition_index, condition in enumerate(conditions):
        payload_bytes = condition["payload_value_bytes"]
        queue_depth = condition["queue_depth_initial_per_source"]
        source_count = condition["source_count"]
        quorum = condition["quorum"]
        receiver_load = condition["receiver_load_workers"]
        sources = tuple(f"S{index}" for index in range(source_count))

        for replicate in range(replicates):
            attempt_ordinal += 1
            attempt_id = f"matrix-{condition_index:02d}-rep-{replicate:02d}"
            with tempfile.TemporaryDirectory(prefix="ecpu-observation-matrix-") as temporary:
                transport = DurableMailboxTransport(Path(temporary) / "mailbox.log")
                vm, pid, senders, coordinator = _runtime(
                    transport, sources, quorum, f"matrix-target-{attempt_ordinal}",
                    MailCPUVirtualMachine, Program, Instruction, Op, ReliableChannel,
                    GatedObservationCoordinator, ObservationAuthorityPolicy,
                )
                active_context: dict[str, Any] = {}
                checkpoint_index = 0
                original_save_checkpoint = coordinator.save_checkpoint

                def measured_save_checkpoint(checkpoint_path: str | Path) -> str:
                    nonlocal checkpoint_index
                    context = {
                        **active_context,
                        "boundary": "save_checkpoint",
                        "checkpoint_call_index": checkpoint_index,
                    }
                    span_id = f"checkpoint:{active_context['observation_id']}:{checkpoint_index}"
                    checkpoint_index += 1
                    result = recorder.measure(
                        attempt_id=attempt_id,
                        span_id=span_id,
                        operation_id="ecpu.GatedObservationCoordinator.save_checkpoint",
                        operation=lambda: original_save_checkpoint(checkpoint_path),
                        context=context,
                    )
                    coordinator._last_experiment_checkpoint_digest = result
                    return result

                coordinator.save_checkpoint = measured_save_checkpoint
                event_payloads: dict[int, dict[str, list[Any]]] = {}
                event_sequences: dict[int, dict[str, int]] = {}
                event_outcomes: dict[int, str] = {}
                event_logical_times: dict[int, int] = {}
                event_ids: dict[int, str] = {}

                def context_for(event_index: int, phase: str) -> dict[str, Any]:
                    logical_time = event_logical_times[event_index]
                    return {
                        **condition,
                        "experiment_id": EXPERIMENT_ID,
                        "workload_id": attempt_id,
                        "observation_id": event_ids[event_index],
                        "logical_time": logical_time,
                        "event_index": event_index,
                        "phase": phase,
                        "replicate": replicate,
                    }

                # Enqueue queue_depth frames per source, including the target.
                # Payload values match across sources within each logical event.
                for event_index in range(queue_depth):
                    logical_time = event_index + 1
                    event_logical_times[event_index] = logical_time
                    event_ids[event_index] = f"{attempt_id}:observation:{logical_time}"
                    outcome = "hit" if (replicate + event_index) % 2 == 0 else "miss"
                    event_outcomes[event_index] = outcome
                    phase = "target" if event_index == queue_depth - 1 else "queue_drain"
                    event_payloads[event_index] = {}
                    event_sequences[event_index] = {}
                    for source in sources:
                        observation = _resolver_observation(
                            ResolverObservation, source, logical_time, outcome, payload_bytes
                        )
                        context = {
                            **context_for(event_index, phase),
                            "source": source,
                            "receiver_queue_depth_before_send_per_source": event_index,
                        }
                        sequence = recorder.measure(
                            attempt_id=attempt_id,
                            span_id=f"send:{event_index}:{source}",
                            operation_id="ecpu.ReliableChannel.send",
                            operation=lambda sender=senders[source], payload=observation.to_payload():
                                sender.send(payload),
                            context=context,
                        )
                        event_payloads[event_index][source] = list(observation.to_payload())
                        event_sequences[event_index][source] = sequence

                attempt_outcome_digests = []
                checkpoint_digests: list[str] = []
                for event_index in range(queue_depth):
                    phase = "target" if event_index == queue_depth - 1 else "queue_drain"
                    active_context = context_for(event_index, phase)
                    logical_time = event_logical_times[event_index]
                    receiver_load_observations = 0

                    def intake() -> Any:
                        remaining_before_ingest = queue_depth - event_index
                        return recorder.measure(
                            attempt_id=attempt_id,
                            span_id=f"ingest:{event_index}",
                            operation_id="ecpu.GatedObservationCoordinator.ingest_available",
                            operation=coordinator.ingest_available,
                            context={
                                **active_context,
                                "receiver_queue_depth_before_ingest_per_source": remaining_before_ingest,
                                "receiver_queue_messages_before_ingest": remaining_before_ingest * source_count,
                            },
                        )

                    if phase == "target" and receiver_load:
                        background = [
                            _background_receiver(payload_bytes, index, mailcpu)
                            for index in range(receiver_load)
                        ]
                        links, receiver_load_observations = _concurrent_receiver_intake(
                            background, intake
                        )
                    else:
                        links = intake()
                    if len(links) != source_count:
                        raise AssertionError(
                            f"event {logical_time} admitted {len(links)} links; expected {source_count}"
                        )
                    if {link.source for link in links} != set(sources):
                        raise AssertionError("receiver intake source set differs from configured sources")

                    decision = recorder.measure(
                        attempt_id=attempt_id,
                        span_id=f"finalize:{event_index}",
                        operation_id="ecpu.GatedObservationCoordinator.finalize_event",
                        operation=lambda: coordinator.finalize_event("resolver", logical_time),
                        context=active_context,
                    )
                    if decision.status != "AUTHORIZED":
                        raise AssertionError(f"controlled matching event was not authorized: {decision.status}")

                    checkpoint_path = Path(temporary) / f"event-{logical_time}.checkpoint"
                    commit_decision = recorder.measure(
                        attempt_id=attempt_id,
                        span_id=f"commit:{event_index}",
                        operation_id="ecpu.GatedObservationCoordinator.commit_event",
                        operation=lambda: coordinator.commit_event("resolver", logical_time, checkpoint_path),
                        context=active_context,
                    )
                    if commit_decision.status != "AUTHORIZED" or not checkpoint_path.exists():
                        raise AssertionError("E-CPU commit did not complete its durable checkpoint path")

                    ack_result = recorder.measure(
                        attempt_id=attempt_id,
                        span_id=f"acks:{event_index}",
                        operation_id="ecpu.GatedObservationCoordinator.process_acks",
                        operation=lambda: coordinator.process_acks(senders),
                        context=active_context,
                    )
                    if set(ack_result) != set(sources):
                        raise AssertionError("sender ACK result omitted a configured source")
                    for source in sources:
                        acknowledged = ack_result[source]
                        sequence = event_sequences[event_index][source]
                        if sequence not in acknowledged or sequence in senders[source].pending_sequences():
                            raise AssertionError("current event ACK was not applied to its sender pending set")

                    representative = coordinator.consensus.authorized_observation("resolver", logical_time)
                    if representative is None:
                        raise AssertionError("authorized E-CPU event lost its representative observation")
                    observed_outcome = "hit" if representative.hit else "miss"
                    if observed_outcome != event_outcomes[event_index]:
                        raise AssertionError("E-CPU representative differs from controlled fixture input")
                    actual_register = vm.scheduler.tasks[pid].backend.read_register("resolver_hit")
                    if actual_register != int(representative.hit):
                        raise AssertionError("VM register readback differs from authorized observation")

                    source_records = [
                        {
                            "source": source,
                            "channel": f"gate-{source}",
                            "sequence": event_sequences[event_index][source],
                            "payload": event_payloads[event_index][source],
                        }
                        for source in sources
                    ]
                    evidence_core = {
                        "attempt_id": attempt_id,
                        "observation_id": event_ids[event_index],
                        "event": {"kind": "resolver", "logical_time": logical_time},
                        "source_observations": source_records,
                        "authority": {
                            "status": decision.status,
                            "quorum": quorum,
                            "strict": True,
                            "observed_sources": list(sources),
                        },
                    }
                    evidence_digest = digest(evidence_core)
                    evidence_record = {
                        **evidence_core,
                        "evidence_digest": evidence_digest,
                    }
                    evidence_records.append(evidence_record)
                    evidence_path = evidence_dir / f"{attempt_id}-event-{event_index}.json"
                    evidence_path.write_text(
                        json.dumps(evidence_record, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    outcome_document = build_observation_outcome(
                        attempt_id=attempt_id,
                        observation_id=event_ids[event_index],
                        evidence_ref=f"evidence/{evidence_path.name}",
                        evidence_digest=evidence_digest,
                        model_ref="fixture:resolver-hit-miss-v1",
                        prior_hypotheses=_fixture_hypotheses(),
                        observed_outcome=observed_outcome,
                    )
                    validate_observation_outcome(outcome_document)
                    information_outcomes.append(outcome_document)
                    attempt_outcome_digests.append(outcome_document["outcome_digest"])
                    if phase == "target":
                        target_analysis = outcome_document["analysis"]

                    # The measured checkpoint wrapper records every save within
                    # commit_event and retains the final digest for this event.
                    last_digest = getattr(coordinator, "_last_experiment_checkpoint_digest", None)
                    if last_digest is None:
                        raise AssertionError("checkpoint span did not expose a digest")
                    checkpoint_digests.append(last_digest)

                    if phase == "target":
                        target_receipt = {
                            "observation_id": event_ids[event_index],
                            "logical_time": logical_time,
                            "observed_outcome": observed_outcome,
                            "register_readback": actual_register,
                            "evidence_ref": f"evidence/{evidence_path.name}",
                            "evidence_digest": evidence_digest,
                            "outcome_digest": outcome_document["outcome_digest"],
                            "expected_information_gain_bits": target_analysis["expected_information_gain_bits"],
                            "expected_query_resolution_probability": target_analysis["expected_query_resolution_probability"],
                            "realized_entropy_change_bits": target_analysis["realized_entropy_change_bits"],
                            "receiver_load_observations": receiver_load_observations,
                            "checkpoint_digest": last_digest,
                        }

                workload_results.append({
                    "attempt_id": attempt_id,
                    **condition,
                    "replicate": replicate,
                    "queue_events": queue_depth,
                    "observation_outcome_digests": attempt_outcome_digests,
                    "target": target_receipt,
                    "all_senders_acknowledged": True,
                    "checkpoint_call_count": checkpoint_index,
                    "checkpoint_digests": checkpoint_digests,
                })

    spans = list(recorder.spans)
    for span in spans:
        validate_operation_span(span)
        context = span["context"]
        if context.get("experiment_id") != EXPERIMENT_ID:
            raise AssertionError("operation span lost experiment identity")
        if not context.get("observation_id") or not context.get("workload_id"):
            raise AssertionError("operation span lacks explicit observation/workload correlation")

    # Rebuild descriptive distributions separately by workload condition and
    # by target-only versus full queue-drain path. No cross-condition mixing.
    profile_report = build_cost_profile_matrix(
        spans, minimum_samples=MINIMUM_PROFILE_SAMPLES
    )
    validate_cost_profile_matrix(profile_report, spans)

    # Check the information layer and its raw evidence source independently.
    evidence_by_id = {
        (record["attempt_id"], record["observation_id"]): record
        for record in evidence_records
    }
    for outcome_document in information_outcomes:
        validate_observation_outcome(outcome_document)
        evidence = evidence_by_id[
            (outcome_document["attempt_id"], outcome_document["observation_id"])
        ]
        evidence_core = {key: value for key, value in evidence.items() if key != "evidence_digest"}
        if digest(evidence_core) != outcome_document["evidence_digest"]:
            raise AssertionError("information outcome evidence digest failed source reconstruction")

    report_core = {
        "format": "in-formation.ecpu-observation-cost-information",
        "schema": EXPERIMENT_SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "ecpu_reference_commit": ECPU_REFERENCE_COMMIT,
        "python_version": platform.python_version(),
        "platform": sys.platform,
        "clock_actor_id": clock_actor_id,
        "clock_segment_id": clock_segment_id,
        "replicates": replicates,
        "factor_levels": {
            "payload_value_bytes": list(PAYLOAD_VALUE_BYTES),
            "queue_depth_initial_per_source": list(QUEUE_DEPTHS),
            "source_quorum": [
                {"source_count": source_count, "quorum": quorum}
                for source_count, quorum in SOURCE_QUORUMS
            ],
            "receiver_load_workers": list(RECEIVER_LOAD_WORKERS),
        },
        "condition_count": len(conditions),
        "attempt_count": len(workload_results),
        "span_count": len(spans),
        "evidence_record_count": len(evidence_records),
        "information_outcome_count": len(information_outcomes),
        "profile_matrix_digest": profile_report["profile_matrix_digest"],
        "information_outcome_digests": sorted(
            item["outcome_digest"] for item in information_outcomes
        ),
        "minimum_profile_samples": MINIMUM_PROFILE_SAMPLES,
        "interpretation_limits": list(INTERPRETATION_LIMITS),
    }
    report = {**report_core, "report_digest": digest(report_core)}
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        manifest_schema = json.loads(
            (Path(__file__).with_name("run-manifest.schema.json")).read_text(encoding="utf-8")
        )
        jsonschema.validate(report, manifest_schema)
    output.mkdir(parents=True, exist_ok=True)
    documents = {
        "run-manifest.json": report,
        "workload-results.json": workload_results,
        "operation-spans.json": {"spans": spans},
        "operation-cost-profiles.json": profile_report,
        "observation-evidence.json": evidence_records,
        "information-outcomes.json": information_outcomes,
    }
    for filename, document in documents.items():
        (output / filename).write_text(
            json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if len(workload_results) != len(conditions) * replicates:
        raise AssertionError("workload matrix did not complete every condition/repetition")
    if len(recorder.spans) != len(spans):
        raise AssertionError("operation span count changed during output construction")
    if len(evidence_records) != len(information_outcomes):
        raise AssertionError("every information outcome must have one source evidence record")
    if len(profile_report["condition_profiles"]) != len(conditions) * 2:
        raise AssertionError("cost matrix did not preserve every condition and analysis scope")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a controlled E-CPU cost/information workload matrix."
    )
    parser.add_argument("--output-dir", required=True, metavar="DIR",
                        help="directory for raw spans, evidence, outcomes, and profiles")
    parser.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES,
                        help=f"independent repetitions per condition (minimum {MINIMUM_PROFILE_SAMPLES})")
    args = parser.parse_args(argv)
    try:
        report = run_matrix(args.output_dir, replicates=args.replicates)
        print(json.dumps({
            "experiment_id": report["experiment_id"],
            "condition_count": report["condition_count"],
            "attempt_count": report["attempt_count"],
            "span_count": report["span_count"],
            "information_outcome_count": report["information_outcome_count"],
            "output_dir": str(Path(args.output_dir)),
        }, sort_keys=True))
        return 0
    except (AssertionError, KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
