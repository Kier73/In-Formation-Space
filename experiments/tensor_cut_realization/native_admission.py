"""TCR-003 initial native-admission bridge for one pinned TCR-001 tensor cut.

This bounded bridge uses E-CPU's real VirtualLayerRuntime and HeadlessOS
Hypervisor. It does not transport work to another host or durably persist state.
Those remain separate TCR-003 stages, documented in TCR-003-HANDOFF.md.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import tensor_cut as tcr
from . import transit_tensor as tcr2

OPERATOR = "tcr.tensor_cut.partial"


class NativeAdmissionError(ValueError):
    pass


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def operator_spec():
    from mailcpu import OperatorSpec
    return OperatorSpec(
        operator_id=OPERATOR, version=1,
        description="Receiver-resident tensor cut numerical contribution",
        input_kind="object", output_kind="object", substrates=("cpu",),
        required_rights=frozenset({"compute"}),
        max_input_bytes=100_000, max_output_bytes=100_000,
        base_energy=2, energy_per_byte=1,
        deterministic=True, effect_mode="pure",
    )


class NativeCut:
    """Receiver owns its parameter arrays, Ground, pure handler and capability."""

    def __init__(self, packet: Path, *, grant_compute: bool = True):
        from mailcpu import (
            Capability, HeadlessOS, OperatorRegistry,
            SystemIdentity, SystemSeed, SystemSeedEnvelope, VirtualGroundRef,
            VirtualLayerRuntime,
        )
        from mailcpu.classifier import HypervisorPolicy, LexicalDecisionModel

        self.resident = tcr2.ResidentShard(Path(packet))
        self.manifest = self.resident.manifest
        self.index = self.resident.index
        self.node_id = f"tcr003-part-{self.index}"
        self.calls = 0
        self.system = HeadlessOS()
        self.system.hypervisor.classifier = LexicalDecisionModel()
        self.system.hypervisor.policy = HypervisorPolicy(embedding_review_confidence=1.0)
        self.identity = SystemIdentity(f"tcr003-system-{self.index}", 1)
        seed = SystemSeed.from_system(self.system)
        envelope = SystemSeedEnvelope(self.identity, "tensor-cut", "tcr003", seed)
        if not self.system.seed_admission.admit(envelope).accepted:
            raise NativeAdmissionError("receiver local Ground not admitted")
        self.ground = VirtualGroundRef.from_envelope(envelope)
        self.spec = operator_spec()
        registry = OperatorRegistry()
        registry.register(self.spec, self._pure_partial)
        self.runtime = VirtualLayerRuntime(registry, self.node_id, frozenset({"cpu"}))
        capability = (
            Capability("/virtual-layer/operators", frozenset({"compute"}))
            if grant_compute else Capability("/unrelated", frozenset({"read"}))
        )
        self.pid = self.system.environment.kernel.spawn(
            self.node_id, capabilities=(capability,),
            parent_pid=self.system.environment.init_pid,
        )

    def _pure_partial(self, value, workload):
        x, _ = tcr2.check_input(value, self.manifest, self.index)
        self.calls += 1  # Test-only diagnostic, absent from the semantic output.
        up = self.resident.up.astype(np.float64)
        bias = self.resident.ub.astype(np.float64)
        down = self.resident.down.astype(np.float64)
        y = tcr._activation(x @ up + bias, self.manifest["activation"]) @ down
        if not bool(np.isfinite(y).all()):
            raise NativeAdmissionError("nonfinite receiver result")
        return {"partial_hex": np.ascontiguousarray(y, dtype="<f8").tobytes().hex(),
                "output_digest": tcr._typed_digest(y)}

    def execute(self, request: dict, *, sequence: int = 1) -> dict:
        from mailcpu import VirtualBudget, VirtualLayerWorkload, VirtualOperatorRef
        from mailcpu.classifier import HypervisorAction

        # Sender requests cannot change the receiver's source/cut/activation policy.
        _, request_sha = tcr2.check_input(request, self.manifest, self.index)
        workload = VirtualLayerWorkload(
            workload_id="tcr003-" + request["request_id"],
            system=self.identity, ground=self.ground,
            intention={"goal": "tensor-cut partial", "source": self.manifest["digest"]},
            operators=(VirtualOperatorRef(OPERATOR, 1, "cpu", self.node_id),),
            input_value=request,
            budget=VirtualBudget(1_000_000, 400_000, 100_000),
            logical_time=17, eligible_nodes=(self.node_id,), max_hops=1,
        )
        native = self.runtime.execute_operator(
            self.system, self.pid, tcr2.ORIGIN, "tcr003.native",
            sequence, 17, workload, OPERATOR,
        )
        if native.action is not HypervisorAction.ALLOW or not native.executed:
            return {"accepted": False, "hypervisor_action": native.action.value,
                    "executed": bool(native.executed)}
        effect = native.effect
        if not isinstance(effect, dict) or effect.get("kind") != "virtual_layer.operator_result":
            raise NativeAdmissionError("no native E-CPU operator result")
        payload = effect["result"]
        if not isinstance(payload, dict) or set(payload) != {"partial_hex", "output_digest"}:
            raise NativeAdmissionError("unexpected native output schema")
        partition = self.manifest["partitions"][self.index]
        receipt = {
            "schema": tcr.RECEIPT_SCHEMA,
            "manifest_digest": self.manifest["digest"],
            "source_digest": self.manifest["source_digest"],
            "input_digest": self.manifest["input_digest"],
            "partition_id": self.index,
            "partition_tensor_digests": partition["tensor_digests"],
            "output_digest": payload["output_digest"],
            "output_shape": [self.manifest["probe_count"], self.manifest["output_dim"]],
            "arithmetic": self.manifest["arithmetic"], "status": "complete",
            "worker_trust": "unsigned artifact; no hardware or transport attestation",
        }
        if not self.system.environment.kernel.journal.verify():
            raise NativeAdmissionError("receiver journal failed")
        return {
            "accepted": True, "hypervisor_action": native.action.value,
            "native_replayed": bool(native.replayed),
            "operator_contract_digest": self.spec.digest,
            "ground_digest": _sha(self.ground.to_dict()),
            "event_fingerprint": native.fingerprint,
            "request_sha256": request_sha,
            "partial_hex": payload["partial_hex"],
            "receipt": receipt,
        }


def accept_partition(manifest: dict, request: dict, native_result: dict, directory: Path):
    """The native decision and ordinary TCR-001 numerical receipt are distinct."""
    if (native_result.get("accepted") is not True
            or native_result.get("hypervisor_action") != "allow"
            or native_result.get("operator_contract_digest") != operator_spec().digest):
        raise NativeAdmissionError("native operator admission not established")
    standard = {
        "schema": tcr2.RESPONSE, "request_id": request["request_id"],
        "accepted": True, "worker_id": tcr2.worker_name(request["partition_id"]),
        "request_sha256": native_result["request_sha256"],
        "receipt": native_result["receipt"],
        "partial_hex": native_result["partial_hex"],
        "replayed": bool(native_result["native_replayed"]),
        "receiver_compute_ns_local": 0,
    }
    return tcr2.accept_response(request, standard, manifest, directory)
