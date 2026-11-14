"""CAG-004 hosted roles: SHN-001 internal loci and a distinct E-CPU receiver.

The implementation does not consider a virtual port to be a physical CPU.
External transport is GitHub Actions artifact handoff, not a real chip port.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract as c


def origin(directory: Path) -> dict[str, Any]:
    signed = c.read(directory / "signed-intent.json")
    trust = c.read(directory / "issuer-trust.json")
    return c.verify_intent(signed, trust)


def run_internal(directory: Path) -> dict[str, Any]:
    from mailcpu.self_hosted_port_network import SelfHostedPortNetwork
    statement = origin(directory)
    observations = []
    for job in statement["jobs"]:
        for ports in (1, 2):
            started = time.perf_counter_ns()
            chip = SelfHostedPortNetwork(ports, queue_limit=2)
            chip.submit(job["job_id"], job["coordinate"])
            phases = []
            # Each in-flight message must survive snapshot/restore with exactly
            # the same packet, FIFO and journal. No external network is used.
            while True:
                checkpoint = chip.snapshot()
                chip = SelfHostedPortNetwork.from_snapshot(checkpoint)
                c.require(chip.snapshot() == checkpoint, "internal checkpoint changed during restore")
                phases.append(chip.phase)
                if chip.phase == "done":
                    break
                chip.step()
            report = chip.report()
            report["semantic_result_digest"] = c.semantic_result(
                job, report["observed_value"], statement)
            report["restored_phases"] = phases
            report["local_elapsed_ns"] = time.perf_counter_ns() - started
            observations.append(report)
    result = c.seal_report({
        "schema": c.INTERNAL_SCHEMA,
        "source_digest": c.digest(statement),
        "shn_revision": c.SHN_REFERENCE,
        "execution_domain": "one E-CPU interpreter, internal OwnedNetworkFabric",
        "observations": observations,
    })
    c.persist(directory / "internal-report.json", result)
    return result


def run_receiver(directory: Path) -> dict[str, Any]:
    from mailcpu import (
        Capability, HeadlessOS, HypervisorAction, HypervisorPolicy,
        LexicalDecisionModel, OperatorRegistry, OperatorSpec, SystemIdentity,
        SystemSeed, SystemSeedEnvelope, VirtualBudget, VirtualGroundRef,
        VirtualLayerRuntime, VirtualLayerWorkload, VirtualOperatorRef,
    )
    statement = origin(directory)
    os_host = HeadlessOS()
    os_host.hypervisor.classifier = LexicalDecisionModel()
    os_host.hypervisor.policy = HypervisorPolicy(embedding_review_confidence=1.0)
    identity = SystemIdentity("cag004-receiver", 1)
    seed = SystemSeed.from_system(os_host)
    envelope = SystemSeedEnvelope(identity, "receiver-owned", "cag004", seed)
    admission = os_host.seed_admission.admit(envelope)
    c.require(admission.accepted, "E-CPU receiver refused own Ground")
    ground = VirtualGroundRef.from_envelope(envelope)
    invocations: list[str] = []
    registry = OperatorRegistry()
    def local_handler(value: Any, workload: Any) -> int:
        # Operator implementation is installed on the receiver, never
        # downloaded or provided as executable source by the sender.
        invocations.append(workload.workload_id)
        c.require(type(value["coordinate"]) is int, "untyped coordinate")
        return c.observed_at(value["coordinate"])

    registry.register(
        OperatorSpec(
            operator_id="cag004.affine_coordinate", version=1,
            description="Receiver-owned finite affine orbit evaluation",
            input_kind="object", output_kind="integer",
            substrates=("cpu",), required_rights=frozenset({"compute"}),
            base_energy=8, energy_per_byte=1,
            max_input_bytes=2048, max_output_bytes=128,
            deterministic=True, effect_mode="pure",
        ), local_handler,
    )
    runtime = VirtualLayerRuntime(registry, "cag004-receiver", frozenset({"cpu"}))
    permitted = os_host.environment.kernel.spawn(
        "cag004-authorized-receiver",
        capabilities=(Capability("/virtual-layer/operators", frozenset({"compute"})),),
        parent_pid=os_host.environment.init_pid,
    )
    refused = os_host.environment.kernel.spawn(
        "cag004-unprivileged-receiver",
        capabilities=(Capability("/elsewhere", frozenset({"read"})),),
        parent_pid=os_host.environment.init_pid,
    )
    observations = []
    for number, job in enumerate(statement["jobs"], 1):
        workload = VirtualLayerWorkload(
            workload_id=f"cag004-{job['job_id']}",
            system=identity, ground=ground,
            intention={"goal": {"equals": c.observed_at(job["coordinate"])},
                       "source_digest": c.digest(statement)},
            operators=(VirtualOperatorRef("cag004.affine_coordinate", 1, "cpu"),),
            input_value={"job_id": job["job_id"], "coordinate": job["coordinate"]},
            budget=VirtualBudget(max_energy=10000, max_bytes=4096,
                                 max_virtual_ticks=100),
            logical_time=number, eligible_nodes=("cag004-receiver",), max_hops=1,
        )
        started = time.perf_counter_ns()
        initial = runtime.execute_operator(
            os_host, permitted, "signed-orbit-source", "artifact-route",
            number, workload.logical_time, workload, "cag004.affine_coordinate")
        c.require(initial.action is HypervisorAction.ALLOW
                  and initial.executed and not initial.replayed,
                  "E-CPU capability did not admit first pure operation")
        c.require(initial.effect["result"] == c.observed_at(job["coordinate"]),
                  "receiver-local result differs from independent orbit")
        replay = runtime.execute_operator(
            os_host, permitted, "signed-orbit-source", "artifact-route",
            number, workload.logical_time, workload, "cag004.affine_coordinate")
        c.require(replay.action is HypervisorAction.ALLOW
                  and replay.replayed and replay.effect == initial.effect,
                  "E-CPU exact event did not replay cached effect")
        denied = runtime.execute_operator(
            os_host, refused, "signed-orbit-source", "artifact-route",
            number + 100, workload.logical_time, workload, "cag004.affine_coordinate")
        c.require(denied.action is HypervisorAction.DENY
                  and not denied.executed and denied.effect is None,
                  "unprivileged process executed protected pure operator")
        c.require(len(invocations) == number, "replayed/denied handler executed again")
        observations.append({
            "job_id": job["job_id"],
            "coordinate": job["coordinate"],
            "observed_value": initial.effect["result"],
            "semantic_result_digest": c.semantic_result(
                job, initial.effect["result"], statement),
            "workload_digest": workload.digest,
            "operator_contract_digest": registry.specs()[0].digest,
            "hypervisor_allow": True, "hypervisor_replayed": True,
            "hypervisor_denied": True, "handler_invocations": 1,
            "receiver_journal_verified": os_host.environment.kernel.journal.verify(),
            "receiver_local_elapsed_ns": time.perf_counter_ns() - started,
        })
    result = c.seal_report({
        "schema": c.EXTERNAL_SCHEMA,
        "source_digest": c.digest(statement),
        "ecpu_revision": c.ECPU_RECEIVER_REFERENCE,
        "execution_domain": "independent GitHub-hosted E-CPU Hypervisor receiver",
        "external_link_claim": "GitHub Actions artifact transfer, physical byte rate not measured",
        "observations": observations,
    })
    c.persist(directory / "receiver-report.json", result)
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("internal", "receiver"))
    p.add_argument("--directory", type=Path, required=True)
    args = p.parse_args()
    try:
        report = run_internal(args.directory) if args.command == "internal" else run_receiver(args.directory)
        print(json.dumps({"status": "observed",
                          "role": args.command,
                          "report_digest": report["report_digest"],
                          "results": [x["observed_value"] for x in report["observations"]]},
                         sort_keys=True))
    except Exception as exc:
        p.exit(1, f"CAG-004 host failed closed: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
