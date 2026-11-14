#!/usr/bin/env python3
"""CAG-003: independent receiver-side E-CPU admission and bounded VGI witness.

Do not confuse a VGI finite Z/8Z projection witness with a certificate for
the full integer CAG arithmetic graph or independent source authorization.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
import signed_ground as signed
import substrates as c2
import convergent_fabric as cag

RECEIPT_SCHEMA = "in-formation.cag003-receiver-authority/0.1"
OPERATOR = "cag003.reconstruct_captured_ground"
NODE = "cag003-independent-receiver"
VGI_SCHEMA = "in-formation.cag003-vgi-finite-projection/0.1"


class AdmissionError(ValueError):
    pass


def require(ok: bool, why: str) -> None:
    if not ok:
        raise AdmissionError(why)


def source_inputs(root: Path) -> dict[str, Any]:
    return {
        "source": cag.read(root / "source.json"),
        "blue": cag.read(root / "blue-route.json"),
        "amber": cag.read(root / "amber-route.json"),
        "trace": cag.read(root / "transport-trace.json"),
        "jetstream": c2.read_jsonl(root / "jetstream-arrivals.jsonl"),
        "libp2p": c2.read_jsonl(root / "libp2p-spool.jsonl"),
    }


def compute(value: Mapping[str, Any]) -> dict[str, Any]:
    # This exact deterministic function is the receiver-owned implementation,
    # not code sent by the publisher. All packets are re-validated here.
    report = c2.reconstruct(
        value["source"], value["blue"], value["amber"], value["trace"],
        value["jetstream"], value["libp2p"],
    )
    return {
        "value": report["reference"]["value"],
        "cag002_report_digest": report["report_digest"],
        "source_digest": report["source_digest"],
    }


def vgi_finite_projection(*, source_digest: str, expected_value: int) -> dict[str, Any]:
    from vgi import GroundTransitionSystem, GroundReconstructionVerifier, GroundReconstructionCertificate

    # A separate, declared finite cyclic Ground illustrates VGI replay and
    # the nonpromotion rule. The CAG integer graph is NOT reduced to a proof.
    observations = [
        {
            "source": f"s{i}",
            "action": "advance",
            "outcomes": [{"target": f"s{(i + 1) % 8}", "output": [(i + 1) % 8]}],
            "support_count": 1,
            "evidence": [f"cag003:declared-finite-projection:s{i}"],
        }
        for i in range(8)
    ]
    system = GroundTransitionSystem.from_dict({
        "format": "VGI-TransitionSystem-1",
        "states": [f"s{i}" for i in range(8)],
        "actions": ["advance"],
        "initial_state": "s0",
        "channels": ["signal8"],
        "observations": observations,
        "metadata": {"scope": "declared auxiliary Z/8Z projection, not integer CAG proof"},
    })
    verifier = GroundReconstructionVerifier()
    corpus = [tuple("advance" for _ in range(n)) for n in range(8)]
    certificate = verifier.certify(system, corpus, context_digest=source_digest)
    require(verifier.verify(system, certificate, context_digest=source_digest),
            "VGI finite projection certificate failed")
    return {
        "schema": VGI_SCHEMA,
        "status": "finite_projection_reconstruction_only",
        "source_context_digest": source_digest,
        "full_integer_value": expected_value,
        "projection_modulus": 8,
        "projected_value": expected_value % 8,
        "ground": system.to_dict(),
        "certificate": certificate.to_dict(),
        "claims_not_established": [
            "CAG arithmetic DAG equivalence to the auxiliary VGI Ground",
            "VGI source-observation consensus or remote publisher admission",
            "formal proof of the full unbounded integer computation",
        ],
    }


def verify_vgi_projection(evidence: Mapping[str, Any], *, source_digest: str,
                          expected_value: int) -> None:
    from vgi import GroundTransitionSystem, GroundReconstructionVerifier, GroundReconstructionCertificate
    require(evidence.get("schema") == VGI_SCHEMA
            and evidence.get("status") == "finite_projection_reconstruction_only"
            and evidence.get("source_context_digest") == source_digest
            and evidence.get("full_integer_value") == expected_value
            and evidence.get("projected_value") == expected_value % 8
            and evidence.get("projection_modulus") == 8,
            "VGI projection context differs from the signed source")
    system = GroundTransitionSystem.from_dict(evidence["ground"])
    cert = GroundReconstructionCertificate.from_dict(evidence["certificate"])
    require(GroundReconstructionVerifier().verify(system, cert, context_digest=source_digest),
            "VGI independent certificate replay failed")
    require(evidence == vgi_finite_projection(
        source_digest=source_digest, expected_value=expected_value),
        "VGI projection changed from the declared finite contract")


def admit(root: Path) -> dict[str, Any]:
    from mailcpu import (
        Capability, HeadlessOS, HypervisorAction, HypervisorPolicy,
        LexicalDecisionModel, OperatorRegistry, OperatorSpec, SystemIdentity,
        SystemSeed, SystemSeedEnvelope, VirtualBudget, VirtualGroundRef,
        VirtualLayerRuntime, VirtualLayerWorkload, VirtualOperatorRef,
    )

    origin = signed.verify_intent(
        root, signed.load(root / "signed-intent.json"),
        signed.load(root / "publisher-trust.json"),
    )
    operating_system = HeadlessOS()
    operating_system.hypervisor.classifier = LexicalDecisionModel()
    operating_system.hypervisor.policy = HypervisorPolicy(embedding_review_confidence=1.0)
    identity = SystemIdentity("cag003-local-host", 1)
    seed = SystemSeed.from_system(operating_system)
    envelope = SystemSeedEnvelope(identity, "receiver-owned", "cag003", seed)
    admission = operating_system.seed_admission.admit(envelope)
    require(admission.accepted, "receiver refused to admit its own E-CPU system Ground")
    ground = VirtualGroundRef.from_envelope(envelope)

    calls: list[str] = []
    registry = OperatorRegistry()
    def operator(value: Any, workload: Any) -> dict[str, Any]:
        calls.append(workload.workload_id)
        return compute(value)

    registry.register(
        OperatorSpec(
            operator_id=OPERATOR, version=1,
            description="Independently reconstruct pure finite CAG from signed transport history",
            input_kind="object", output_kind="object",
            substrates=("cpu",), required_rights=frozenset({"compute"}),
            base_energy=8, energy_per_byte=1, max_input_bytes=131072,
            max_output_bytes=4096, deterministic=True, effect_mode="pure",
        ),
        operator,
    )
    runtime = VirtualLayerRuntime(registry, NODE, frozenset({"cpu"}),
                                  max_bytes=262144, max_energy=1000000)
    workload = VirtualLayerWorkload(
        workload_id="cag003:" + origin["source_digest"][:24],
        system=identity, ground=ground,
        intention={"goal": {"equals": 44},
                   "source_commitment": origin["source_digest"]},
        operators=(VirtualOperatorRef(OPERATOR, 1, "cpu"),),
        input_value=source_inputs(root),
        budget=VirtualBudget(max_energy=600000, max_bytes=262144,
                             max_virtual_ticks=2000),
        logical_time=1, eligible_nodes=(NODE,), max_hops=1,
    )
    allowed_pid = operating_system.environment.kernel.spawn(
        "cag003-receiver-authorized",
        capabilities=(Capability("/virtual-layer/operators", frozenset({"compute"})),),
        parent_pid=operating_system.environment.init_pid,
    )
    denied_pid = operating_system.environment.kernel.spawn(
        "cag003-receiver-denied",
        capabilities=(Capability("/unrelated", frozenset({"read"})),),
        parent_pid=operating_system.environment.init_pid,
    )
    first = runtime.execute_operator(
        operating_system, allowed_pid, "signed-origin", "cag003", 1,
        workload.logical_time, workload, OPERATOR)
    require(first.action is HypervisorAction.ALLOW and first.executed and not first.replayed,
            "E-CPU did not authorize exactly one initial local computation")
    require(first.effect is not None and first.effect["result"]["value"] == 44
            and first.effect["result"]["source_digest"] == origin["source_digest"]
            and first.effect["result"]["cag002_report_digest"] == origin["report_digest"],
            "E-CPU effect is not bound to signed source")
    replay = runtime.execute_operator(
        operating_system, allowed_pid, "signed-origin", "cag003", 1,
        workload.logical_time, workload, OPERATOR)
    require(replay.action is HypervisorAction.ALLOW and replay.replayed
            and replay.effect == first.effect and len(calls) == 1,
            "same semantic operation invoked twice or returned a different effect")
    denied = runtime.execute_operator(
        operating_system, denied_pid, "signed-origin", "cag003", 2,
        workload.logical_time, workload, OPERATOR)
    require(denied.action is HypervisorAction.DENY
            and not denied.executed and denied.effect is None and len(calls) == 1,
            "missing receiver capability did not deny or handler ran on refused request")
    require(operating_system.environment.kernel.journal.verify(),
            "receiver kernel journal did not validate")
    vgi = vgi_finite_projection(source_digest=origin["source_digest"], expected_value=44)
    core = {
        "schema": RECEIPT_SCHEMA,
        "status": "signed_source_receiver_locally_admitted",
        "publisher": origin,
        "ecpu": {
            "runtime": "mailcpu.VirtualLayerRuntime via HeadlessOS Hypervisor",
            "receiver_ground": ground.to_dict(),
            "workload_digest": workload.digest,
            "operator_contract_digest": registry.specs()[0].digest,
            "first_action": first.action.value,
            "first_executed": first.executed,
            "first_effect": first.effect,
            "replayed": replay.replayed,
            "denied_action": denied.action.value,
            "denied_executed": denied.executed,
            "handler_invocations": len(calls),
            "journal_verified": True,
        },
        "vgi": vgi,
        "claims_not_established": [
            "Two independently operated real network providers",
            "Independently administered publisher trust anchor",
            "VGI proof of the full integer CAG DAG",
            "Distributed atomic execution or arbitrary exactly-once external effects",
        ],
    }
    return {**core, "receipt_digest": cag.sha(core)}


def verify_receipt(root: Path) -> dict[str, Any]:
    original = cag.read(root / "admission-report.json")
    require(original.get("schema") == RECEIPT_SCHEMA, "receiver receipt schema invalid")
    core = {k: v for k, v in original.items() if k != "receipt_digest"}
    require(original.get("receipt_digest") == cag.sha(core), "receiver receipt digest mismatch")
    origin = signed.verify_intent(
        root, signed.load(root / "signed-intent.json"),
        signed.load(root / "publisher-trust.json"),
    )
    require(original.get("publisher") == origin, "receiver source authentication receipt differs")
    expected = compute(source_inputs(root))
    ecpu = original.get("ecpu", {})
    require(ecpu.get("first_action") == "allow"
            and ecpu.get("first_executed") is True
            and ecpu.get("replayed") is True
            and ecpu.get("denied_action") == "deny"
            and ecpu.get("denied_executed") is False
            and ecpu.get("handler_invocations") == 1
            and ecpu.get("journal_verified") is True,
            "receiver Hypervisor admission/denial/replay claims missing")
    require(ecpu.get("first_effect", {}).get("result") == expected
            and expected["cag002_report_digest"] == origin["report_digest"],
            "receiver's reported effect disagrees with independently reconstructed Ground")
    verify_vgi_projection(original["vgi"], source_digest=origin["source_digest"],
                          expected_value=expected["value"])
    return {
        "status": "signed_source_and_receiver_transcript_reconstructed",
        "receipt_digest": original["receipt_digest"],
        "source_digest": origin["source_digest"],
        "value": expected["value"],
        "limitations": "Verifier checks attested receiver report and replays source arithmetic/VGI witness; it cannot independently observe internal Hypervisor invocation",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("admit", "verify"))
    p.add_argument("--directory", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == "admit":
            doc = admit(args.directory)
            cag.write(args.directory / "admission-report.json", doc)
        else:
            doc = verify_receipt(args.directory)
        print(json.dumps({"status": doc["status"],
                          "digest": doc.get("receipt_digest")}, sort_keys=True))
    except Exception as exc:
        # Public logs include bounded reason; source raw JWT/key never retained.
        p.exit(1, f"CAG-003 receiver fail closed: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
