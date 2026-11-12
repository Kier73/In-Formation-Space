"""E-CPU experiment: quorum authority, dissent, finalization, and late evidence.

Requires the exact pinned E-CPU checkout on PYTHONPATH and ECPU_ROOT.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

EXPERIMENT_ID = "ecpu-epistemic-authority-finalization-v1"
EXPERIMENT_SCHEMA = "in-formation.ecpu-epistemic-authority-finalization/0.1"
ECPU_REFERENCE_COMMIT = "800f94f83ffd6f527ed093c8d1c1e93e153c34f6"
SOURCES = ("S00", "S01", "S02", "S03")
QUORUM = 2
STRICT_LEVELS = (True, False)
DEFAULT_REPLICATES = 3

# Deterministic fixture values, not claims about external resolver truth.
SCENARIOS: dict[str, dict[str, str]] = {
    "partial_unanimous": {"S00": "hit", "S01": "hit"},
    "full_unanimous": {source: "hit" for source in SOURCES},
    "majority_dissent": {
        "S00": "hit", "S01": "hit", "S02": "hit", "S03": "miss"
    },
    "tied_split": {
        "S00": "hit", "S01": "hit", "S02": "miss", "S03": "miss"
    },
    "subquorum_partial": {"S00": "hit"},
}

EXPECTED = {
    (True, "partial_unanimous"): ("PENDING", "REFUSED"),
    (True, "full_unanimous"): ("QUORUM", "AUTHORIZED"),
    (True, "majority_dissent"): ("CONFLICT", "CONFLICT"),
    (True, "tied_split"): ("CONFLICT", "CONFLICT"),
    (True, "subquorum_partial"): ("PENDING", "REFUSED"),
    (False, "partial_unanimous"): ("QUORUM", "AUTHORIZED"),
    (False, "full_unanimous"): ("QUORUM", "AUTHORIZED"),
    (False, "majority_dissent"): ("QUORUM", "AUTHORIZED"),
    (False, "tied_split"): ("QUORUM", "AUTHORIZED"),
    (False, "subquorum_partial"): ("PENDING", "REFUSED"),
}

INTERPRETATION_LIMITS = [
    "This is a deterministic synthetic evidence fixture, not an external resolver benchmark.",
    "The E-CPU runtime is pinned to one exact commit and local durable mailbox transport.",
    "strict=False is evaluated as implemented by the pinned E-CPU consensus state machine; this is not a recommendation that permissive mode is safe.",
    "The tied two-versus-two condition tests deterministic tie resolution, not a statistically justified winner.",
    "The strict policy requires every configured source and treats any dissent as CONFLICT.",
    "Finalized events reject new consensus evidence; this experiment does not implement revision or supersession.",
    "Refused and conflicted events are not committed, so their pre-finalization data frames remain unconsumed in the durable mailbox.",
    "Only authorized events are VM-applied; the experiment does not revise an application after authorization.",
    "Three repetitions are for deterministic state-contract coverage, not confidence intervals.",
    "No information-per-cost ratio is computed and no adaptive policy is updated.",
]


def canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def matrix_conditions() -> list[dict[str, Any]]:
    return [
        {"strict": strict, "scenario": scenario, "quorum": QUORUM}
        for strict, scenario in itertools.product(STRICT_LEVELS, SCENARIOS)
    ]


def observation_for(
    mailcpu: Mapping[str, Any], source: str, value: str, logical_time: int = 1
) -> Any:
    """Build one typed fixture observation without asserting external sensor truth."""
    is_hit = value == "hit"
    return mailcpu["ResolverObservation"](
        source=source,
        domain="epistemic-fixture.invalid",
        record_type="TXT",
        logical_time=logical_time,
        status="NOERROR",
        hit=is_hit,
        ttl=60,
        value="alpha" if is_hit else "beta",
    )


def payload_signature(payload: tuple[Any, ...]) -> tuple[Any, ...]:
    """Remove source identity using E-CPU's canonical observation relation."""
    return payload[:2] + payload[3:]


def evidence_partition(
    values: Mapping[str, str], payloads: Mapping[str, tuple[Any, ...]]
) -> dict[str, Any]:
    groups: dict[tuple[Any, ...], list[str]] = {}
    for source, payload in payloads.items():
        groups.setdefault(payload_signature(payload), []).append(source)
    for sources in groups.values():
        sources.sort()
    ordered = sorted(
        groups.items(),
        key=lambda item: (-len(item[1]), tuple(repr(value) for value in item[0])),
    )
    if not ordered:
        winner_signature: tuple[Any, ...] | None = None
        winner_sources: list[str] = []
        winning_count = 0
        tied = False
    else:
        winner_signature, winner_sources_tuple = ordered[0]
        winner_sources = list(winner_sources_tuple)
        winning_count = len(winner_sources)
        tied = len(ordered) > 1 and len(ordered[1][1]) == winning_count
    observed = sorted(values)
    return {
        "groups": [
            {
                "sources": sources,
                "group_size": len(sources),
                "signature_digest": digest(list(signature)),
            }
            for signature, sources in ordered
        ],
        "winner_signature_digest": (
            digest(list(winner_signature)) if winner_signature is not None else None
        ),
        "winner_sources": winner_sources,
        "winning_count": winning_count,
        "tie_at_top": tied,
        "observed_sources": observed,
        "dissenting_sources": sorted(set(observed) - set(winner_sources)),
        "missing_sources": sorted(set(SOURCES) - set(observed)),
        "source_count": len(observed),
    }


def validate_condition(condition: Mapping[str, Any]) -> dict[str, Any]:
    if set(condition) != {"strict", "scenario", "quorum"}:
        raise ValueError("condition fields differ from the declared matrix")
    if type(condition["strict"]) is not bool:
        raise ValueError("strict must be a Boolean policy factor")
    if condition["scenario"] not in SCENARIOS:
        raise ValueError("scenario is outside the declared evidence patterns")
    if type(condition["quorum"]) is not int or condition["quorum"] != QUORUM:
        raise ValueError("quorum is outside the declared factor level")
    return {
        "strict": condition["strict"],
        "scenario": condition["scenario"],
        "quorum": condition["quorum"],
    }


def _read_register(vm: Any, pid: int, name: str) -> int:
    return vm.scheduler.tasks[pid].backend.read_register(name)


def _run_attempt(
    mailcpu: Mapping[str, Any],
    condition: Mapping[str, Any],
    replicate: int,
    condition_index: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    condition = validate_condition(condition)
    strict = condition["strict"]
    scenario = condition["scenario"]
    values = dict(SCENARIOS[scenario])
    observed_sources = sorted(values)
    missing_sources = sorted(set(SOURCES) - set(observed_sources))
    attempt_id = f"authority-{condition_index:02d}-replicate-{replicate:02d}"
    observation_id = f"{attempt_id}:resolver:1"

    with tempfile.TemporaryDirectory(prefix="ecpu-authority-finalization-") as temporary:
        root = Path(temporary)
        mailbox_path = root / "mailbox.jsonl"
        transport = mailcpu["DurableMailboxTransport"](mailbox_path)
        reliability_policy = mailcpu["ReliabilityPolicy"](
            lease_ticks=1, max_attempts=4, window_size=4
        )
        senders: dict[str, Any] = {}
        receivers: dict[str, Any] = {}
        for source in SOURCES:
            receiver_name = f"receiver-{source}"
            channel_name = f"authority-{source}"
            senders[source] = mailcpu["ReliableChannel"](
                transport, source, receiver_name, channel_name,
                reliability_policy, peer=receiver_name,
            )
            receivers[source] = mailcpu["ReliableChannel"](
                transport, receiver_name, receiver_name, channel_name,
                reliability_policy, peer=source,
            )

        vm = mailcpu["MailCPUVirtualMachine"]()
        pid = vm.spawn_program(
            mailcpu["Program"]((mailcpu["Instruction"](mailcpu["Op"].HALT),)),
            attempt_id,
        )
        policy = mailcpu["ObservationAuthorityPolicy"](
            "resolver", SOURCES, quorum=QUORUM, strict=strict
        )
        coordinator = mailcpu["GatedObservationCoordinator"](
            vm, policy, receivers, pid, "resolver"
        )

        payloads: dict[str, tuple[Any, ...]] = {}
        for source in observed_sources:
            observation = observation_for(mailcpu, source, values[source])
            payloads[source] = observation.to_payload()
            sequence = senders[source].send(payloads[source])
            if sequence != 1:
                raise AssertionError("fresh source channel did not begin at sequence one")

        admitted_links = coordinator.ingest_available()
        admitted_sources = sorted(link.source for link in admitted_links)
        if admitted_sources != observed_sources:
            raise AssertionError(
                f"intake mismatch: admitted {admitted_sources}, expected {observed_sources}"
            )

        evidence_records = []
        for link in admitted_links:
            evidence_records.append({
                "attempt_id": attempt_id,
                "observation_id": observation_id,
                "source": link.source,
                "channel": link.channel,
                "sequence": link.sequence,
                "synthetic_value": values[link.source],
                "payload_digest": hashlib.sha256(
                    canonical(list(link.payload)).encode("utf-8")
                ).hexdigest(),
                "event": {"kind": "resolver", "logical_time": 1},
                "authority_effect": "evidence_received_not_yet_authority",
            })

        partition = evidence_partition(values, payloads)
        predecision = coordinator.status("resolver", 1)
        expected_pre, expected_final = EXPECTED[(strict, scenario)]
        if predecision.status != expected_pre:
            raise AssertionError(
                f"pre-finalization mismatch for {(strict, scenario)}: "
                f"{predecision.status} != {expected_pre}"
            )
        if list(predecision.observed_sources) != partition["observed_sources"]:
            raise AssertionError("runtime observed-source list differs from evidence partition")
        if list(predecision.missing_sources) != partition["missing_sources"]:
            raise AssertionError("runtime missing-source list differs from evidence partition")
        if list(predecision.dissenting_sources) != partition["dissenting_sources"]:
            raise AssertionError("runtime dissenting-source list differs from evidence partition")

        finalized = coordinator.finalize_event("resolver", 1)
        if finalized.status != expected_final:
            raise AssertionError(
                f"finalization mismatch for {(strict, scenario)}: "
                f"{finalized.status} != {expected_final}"
            )

        representative_source = None
        representative_value = None
        ack_result: dict[str, tuple[int, ...]] = {}
        applied_count = 0
        consumed_sources: list[str] = []
        register_readback = None
        checkpoint_path = root / "authority.checkpoint"

        if finalized.status == "AUTHORIZED":
            authorized = coordinator.consensus.authorized_observation("resolver", 1)
            if authorized is None:
                raise AssertionError("authorized event has no representative observation")
            representative_source = authorized.source
            representative_value = "hit" if authorized.hit else "miss"
            commit_result = coordinator.commit_event("resolver", 1, checkpoint_path)
            ack_result = coordinator.process_acks(senders)
            if commit_result.status != "AUTHORIZED":
                raise AssertionError("authorized event failed to commit")
            state = coordinator.snapshot()
            applied_count = len(state["applied"])
            consumed_item = next(
                item for item in state["consumed"]
                if item["kind"] == "resolver" and item["logical_time"] == 1
            )
            consumed_sources = list(consumed_item["sources"])
            register_readback = _read_register(vm, pid, "resolver_hit")
            expected_register = int(authorized.hit)
            if register_readback != expected_register:
                raise AssertionError("VM register does not reflect authorized representative")
            expected_ack = {
                source: ([1] if source in observed_sources else [])
                for source in SOURCES
            }
            actual_ack = {source: list(ack_result[source]) for source in SOURCES}
            if actual_ack != expected_ack:
                raise AssertionError(f"ACK receipts differ from committed evidence: {actual_ack}")
            if consumed_sources != observed_sources:
                raise AssertionError("commit did not consume precisely the admitted evidence links")
        else:
            if coordinator.snapshot()["applied"]:
                raise AssertionError("non-authorized event unexpectedly changed VM application state")
            expected_pending = {
                source: ([1] if source in observed_sources else [])
                for source in SOURCES
            }
            actual_pending = {
                source: list(senders[source].pending_sequences())
                for source in SOURCES
            }
            if actual_pending != expected_pending:
                raise AssertionError("non-authorized event did not preserve sender evidence as pending")

        checkpoint_digest = coordinator.save_checkpoint(checkpoint_path)
        checkpoint_envelope = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        state_digest = hashlib.sha256(
            json.dumps(
                checkpoint_envelope["state"], sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        if checkpoint_digest != state_digest or checkpoint_envelope.get("digest") != state_digest:
            raise AssertionError("gated checkpoint digest is not independently reproducible")

        restored_mailbox_path = root / "restored-mailbox.jsonl"
        shutil.copyfile(mailbox_path, restored_mailbox_path)
        restored_transport = mailcpu["DurableMailboxTransport"](restored_mailbox_path)
        restored = mailcpu["load_gated_checkpoint"](
            checkpoint_path, {source: restored_transport for source in SOURCES}
        )
        restored_snapshot = restored.snapshot()
        original_snapshot = coordinator.snapshot()
        restore_matches = digest(restored_snapshot) == digest(original_snapshot)
        restored_status = restored.status("resolver", 1)
        if not restore_matches or restored_status.status != expected_final:
            raise AssertionError("checkpoint plus durable-mailbox replay changed finalized authority")
        if not transport.verify() or not restored_transport.verify():
            raise AssertionError("durable mailbox verification failed before late-evidence probe")

        # Missing-source cases exercise transport intake. Full-evidence cases
        # exercise consensus-level revision rejection because every source exists.
        late_transport_error: str | None = None
        late_transport_admitted: list[str] = []
        late_transport_attempted = False
        late_transport_queue_pending = 0
        direct_policy_rejected = False
        direct_policy_error: str | None = None

        if missing_sources:
            late_source = missing_sources[0]
            matching_source = partition["winner_sources"][0]
            late_value = values[matching_source]
            late_observation = observation_for(mailcpu, late_source, late_value)
            senders[late_source].send(late_observation.to_payload())
            late_transport_attempted = True
            try:
                newly_admitted = coordinator.ingest_available()
                late_transport_admitted = sorted(link.source for link in newly_admitted)
            except mailcpu["ObservationError"] as error:
                late_transport_error = f"{type(error).__name__}: {error}"
            late_transport_queue_pending = transport.pending(f"receiver-{late_source}")
            if late_source not in {
                source
                for item in coordinator.snapshot()["links"]
                if item["kind"] == "resolver" and item["logical_time"] == 1
                for source in (link["source"] for link in item["sources"])
            }:
                try:
                    coordinator.consensus.ingest(late_observation)
                except mailcpu["ObservationError"] as error:
                    direct_policy_rejected = True
                    direct_policy_error = f"{type(error).__name__}: {error}"
        else:
            late_source = partition["winner_sources"][0]
            old_value = values[late_source]
            late_value = "miss" if old_value == "hit" else "hit"
            late_observation = observation_for(mailcpu, late_source, late_value)
            try:
                coordinator.consensus.ingest(late_observation)
            except mailcpu["ObservationError"] as error:
                direct_policy_rejected = True
                direct_policy_error = f"{type(error).__name__}: {error}"

        after_late_snapshot = coordinator.snapshot()
        snapshot_unchanged_after_late = digest(after_late_snapshot) == digest(original_snapshot)
        post_late_status = coordinator.status("resolver", 1)
        if not direct_policy_rejected:
            raise AssertionError("consensus accepted a new observation after event finalization")
        if late_transport_admitted:
            raise AssertionError("late evidence was admitted after finalization")
        if post_late_status.status != expected_final or not snapshot_unchanged_after_late:
            raise AssertionError("late-evidence probe altered the finalized event")

        state = coordinator.snapshot()
        link_event = next(
            item for item in state["links"]
            if item["kind"] == "resolver" and item["logical_time"] == 1
        )
        applied_source = None
        if state["applied"]:
            applied_source = next(
                item["link"]["source"] for item in state["applied"]
                if item["kind"] == "resolver" and item["logical_time"] == 1
            )

        receipt = {
            "attempt_id": attempt_id,
            "observation_id": observation_id,
            **condition,
            "replicate": replicate,
            "source_count": len(SOURCES),
            "evidence_received_sources": observed_sources,
            "evidence_received_count": len(observed_sources),
            "evidence_partition": partition,
            "pre_finalization_status": predecision.status,
            "final_status": finalized.status,
            "expected_pre_finalization_status": expected_pre,
            "expected_final_status": expected_final,
            "representative_source": representative_source,
            "representative_value": representative_value,
            "applied_source": applied_source,
            "application_count": applied_count,
            "register_readback": register_readback,
            "consumed_sources": consumed_sources,
            "sender_acknowledged": {
                source: list(ack_result.get(source, ())) for source in SOURCES
            },
            "sender_pending_after_finalization": {
                source: list(senders[source].pending_sequences()) for source in SOURCES
            },
            "checkpoint_digest": checkpoint_digest,
            "checkpoint_state_digest": state_digest,
            "checkpoint_restore_matches": restore_matches,
            "restored_final_status": restored_status.status,
            "durable_log_verified": transport.verify(),
            "durable_log_sequence": transport.snapshot()["sequence"],
            "durable_log_head": transport.snapshot()["head_hex"],
            "late_evidence": {
                "source": late_source,
                "synthetic_value": late_value,
                "transport_attempted": late_transport_attempted,
                "transport_admitted_sources": late_transport_admitted,
                "transport_error": late_transport_error,
                "transport_queue_pending": late_transport_queue_pending,
                "direct_policy_rejected": direct_policy_rejected,
                "direct_policy_error": direct_policy_error,
                "late_source_already_present": late_source not in missing_sources,
                "post_late_status": post_late_status.status,
                "snapshot_unchanged": snapshot_unchanged_after_late,
            },
            "evidence_link_count_after_finalization": len(link_event["sources"]),
            "dissenting_sources_retained": partition["dissenting_sources"],
            "policy_authorized_despite_dissent": (
                finalized.status == "AUTHORIZED" and bool(partition["dissenting_sources"])
            ),
            "policy_authorized_despite_missing": (
                finalized.status == "AUTHORIZED" and bool(partition["missing_sources"])
            ),
        }
        validate_attempt_result(receipt)
        return receipt, evidence_records, {
            "attempt_id": attempt_id,
            "event": {"kind": "resolver", "logical_time": 1},
            "pre_finalization_status": predecision.status,
            "final_status": finalized.status,
            "evidence_partition": partition,
            "late_evidence": receipt["late_evidence"],
            "coordinator_snapshot_digest": digest(state),
            "checkpoint_digest": checkpoint_digest,
        }


def validate_attempt_result(record: Mapping[str, Any]) -> dict[str, Any]:
    strict = record["strict"]
    scenario = record["scenario"]
    if (strict, scenario) not in EXPECTED:
        raise ValueError("attempt is outside the declared policy/scenario matrix")
    expected_pre, expected_final = EXPECTED[(strict, scenario)]
    if record["pre_finalization_status"] != expected_pre:
        raise ValueError("pre-finalization status differs from declared contract")
    if record["final_status"] != expected_final:
        raise ValueError("final status differs from declared contract")
    partition = record["evidence_partition"]
    if record["evidence_received_sources"] != partition["observed_sources"]:
        raise ValueError("received evidence identities differ from evidence partition")
    if record["evidence_received_count"] != partition["source_count"]:
        raise ValueError("received evidence count differs from evidence partition")
    authorized = expected_final == "AUTHORIZED"
    if record["application_count"] != int(authorized):
        raise ValueError("VM application does not correspond exactly to authorization")
    if authorized:
        if record["representative_source"] not in partition["winner_sources"]:
            raise ValueError("applied representative is not in winning evidence group")
        if record["applied_source"] != record["representative_source"]:
            raise ValueError("VM applied link differs from authorized representative")
        if record["consumed_sources"] != partition["observed_sources"]:
            raise ValueError("authorized commit did not consume every admitted evidence link")
    else:
        if record["representative_source"] is not None or record["applied_source"] is not None:
            raise ValueError("non-authorized event unexpectedly acquired a representative")
        if record["consumed_sources"]:
            raise ValueError("non-authorized event unexpectedly consumed evidence")
    late = record["late_evidence"]
    if not late["direct_policy_rejected"] or late["transport_admitted_sources"]:
        raise ValueError("late evidence crossed finalized-event boundary")
    if not late["snapshot_unchanged"] or late["post_late_status"] != expected_final:
        raise ValueError("late-evidence attempt altered established authority")
    if not record["checkpoint_restore_matches"] or record["restored_final_status"] != expected_final:
        raise ValueError("finalized authority did not survive checkpoint restoration")
    if not record["durable_log_verified"]:
        raise ValueError("durable mailbox hash-chain replay failed")
    if record["policy_authorized_despite_dissent"] != (
        authorized and bool(partition["dissenting_sources"])
    ):
        raise ValueError("dissent/authorization relation is incorrectly recorded")
    if record["policy_authorized_despite_missing"] != (
        authorized and bool(partition["missing_sources"])
    ):
        raise ValueError("missing-source/authorization relation is incorrectly recorded")
    if record["evidence_link_count_after_finalization"] != partition["source_count"]:
        raise ValueError("evidence links changed after finalization")
    return dict(record)


def run_matrix(output_dir: str | Path, *, replicates: int = DEFAULT_REPLICATES) -> dict[str, Any]:
    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates < 3:
        raise ValueError("replicates must be an integer >= 3")
    root_text = os.environ.get("ECPU_ROOT", "")
    if not root_text:
        raise RuntimeError("ECPU_ROOT must identify the pinned E-CPU checkout")
    ecpu_root = Path(root_text).resolve()
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
        "DurableMailboxTransport", "MailCPUVirtualMachine", "Program",
        "Instruction", "Op", "ReliabilityPolicy", "ReliableChannel",
        "ObservationAuthorityPolicy", "ResolverObservation",
        "GatedObservationCoordinator", "ObservationError",
        "load_gated_checkpoint",
    )
    missing = [name for name in required if not hasattr(mailcpu, name)]
    if missing:
        raise RuntimeError(f"pinned E-CPU package lacks required APIs: {missing}")

    conditions = matrix_conditions()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    for condition_index, condition in enumerate(conditions):
        for replicate in range(replicates):
            receipt, evidence_records, trace_record = _run_attempt(
                vars(mailcpu), condition, replicate, condition_index
            )
            attempts.append(receipt)
            evidence.extend(evidence_records)
            trace.append(trace_record)

    counts = {
        status: sum(record["final_status"] == status for record in attempts)
        for status in ("AUTHORIZED", "CONFLICT", "REFUSED")
    }
    report_core = {
        "format": "in-formation.ecpu-epistemic-authority-finalization",
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
        "replicates_per_condition": replicates,
        "source_ids": list(SOURCES),
        "quorum": QUORUM,
        "strict_levels": list(STRICT_LEVELS),
        "scenario_ids": list(SCENARIOS),
        "condition_count": len(conditions),
        "attempt_count": len(attempts),
        "evidence_record_count": len(evidence),
        "final_status_counts": counts,
        "authorized_despite_dissent_count": sum(
            record["policy_authorized_despite_dissent"] for record in attempts
        ),
        "authorized_despite_missing_count": sum(
            record["policy_authorized_despite_missing"] for record in attempts
        ),
        "late_policy_rejection_count": sum(
            record["late_evidence"]["direct_policy_rejected"] for record in attempts
        ),
        "checkpoint_restore_success_count": sum(
            record["checkpoint_restore_matches"] for record in attempts
        ),
        "durable_log_verification_success_count": sum(
            record["durable_log_verified"] for record in attempts
        ),
        "attempt_results_digest": digest(attempts),
        "evidence_ledger_digest": digest(evidence),
        "trace_digest": digest(trace),
        "interpretation_limits": list(INTERPRETATION_LIMITS),
    }
    report = {**report_core, "report_digest": digest(report_core)}
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        schema_path = Path(__file__).with_name("run-manifest.schema.json")
        jsonschema.validate(
            report, json.loads(schema_path.read_text(encoding="utf-8"))
        )

    summary_core = {
        "format": "in-formation.ecpu-epistemic-authority-finalization-summary",
        "schema": "in-formation.ecpu-epistemic-authority-finalization-summary/0.1",
        "experiment_id": EXPERIMENT_ID,
        "matrix": {
            "condition_count": len(conditions),
            "attempt_count": len(attempts),
            "replicates_per_condition": replicates,
            "source_ids": list(SOURCES),
            "quorum": QUORUM,
            "strict_levels": list(STRICT_LEVELS),
            "scenario_ids": list(SCENARIOS),
        },
        "results": {
            "final_status_counts": counts,
            "authorized_despite_dissent_count": report["authorized_despite_dissent_count"],
            "authorized_despite_missing_count": report["authorized_despite_missing_count"],
            "late_policy_rejection_count": report["late_policy_rejection_count"],
            "checkpoint_restore_success_count": report["checkpoint_restore_success_count"],
            "durable_log_verification_success_count": report["durable_log_verification_success_count"],
            "tied_split_permissive_authorized_count": sum(
                record["scenario"] == "tied_split"
                and record["strict"] is False
                and record["final_status"] == "AUTHORIZED"
                for record in attempts
            ),
        },
        "digests": {
            "report_digest": report["report_digest"],
            "attempt_results_digest": report["attempt_results_digest"],
            "evidence_ledger_digest": report["evidence_ledger_digest"],
            "trace_digest": report["trace_digest"],
        },
        "interpretation_limits": list(INTERPRETATION_LIMITS),
    }
    summary = {**summary_core, "summary_digest": digest(summary_core)}
    documents = {
        "run-manifest.json": report,
        "summary.json": summary,
        "attempt-results.json": attempts,
        "evidence-ledger.json": evidence,
        "transition-trace.json": trace,
    }
    for name, document in documents.items():
        (output / name).write_text(
            json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if len(attempts) != len(conditions) * replicates:
        raise AssertionError("declared matrix did not complete")
    if not all(
        record["checkpoint_restore_matches"] and record["durable_log_verified"]
        for record in attempts
    ):
        raise AssertionError("checkpoint or durable-log verification failed")
    if not all(record["late_evidence"]["direct_policy_rejected"] for record in attempts):
        raise AssertionError("a late evidence proposal crossed finalization")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run E-CPU's quorum, dissent, finalization, and late-evidence matrix."
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
        "evidence_record_count": report["evidence_record_count"],
        "final_status_counts": report["final_status_counts"],
        "authorized_despite_dissent_count": report["authorized_despite_dissent_count"],
        "authorized_despite_missing_count": report["authorized_despite_missing_count"],
        "output_dir": str(Path(args.output_dir)),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
