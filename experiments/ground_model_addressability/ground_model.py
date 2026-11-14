"""PNF-004: addressable neural law ranker inside native E-CPU authority.

The hand-designed 2->2 ReLU->1 ranker orders proposals, never certifies them.
Its two variable coefficients are decoded from admitted structural coordinates;
an M1 byte object binds the architecture, decoder and exact memory references.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from mailcpu import (Capability, HeadlessOS, OperatorRegistry, OperatorSpec,
                     ReplicatedMailboxNode, ReplicatedMailboxStore, SystemIdentity,
                     SystemSeed, SystemSeedEnvelope, VirtualBudget, VirtualGroundRef,
                     VirtualLayerRuntime, VirtualLayerWorkload, VirtualOperatorRef)
from mailcpu.checkpoint import load_checkpoint, save_checkpoint
from mailcpu.classifier import HypervisorPolicy, LexicalDecisionModel
from mailcpu.computational_objects import ComputationalObjectManifest, ComputationalObjectStore
from mailcpu.law_certifier import Law, fit_affine
from mailcpu.remote_memory import RemotePageStore
from mailcpu.virtual_layer import VirtualStructuralMemoryRef
from experiments.procedural_neural_formation.formation import Block, evaluate

OPERATOR = "pnf.ground_candidate_rank"
MEMORY = "pnf004.parameter-field"
CONTEXT = {"role": "neural-ranker-parameters", "decoder": "dyadic-ranker-v1"}
CONTRACT = {"schema": "ifs.addressable-ground-ranker.v1", "dimensions": [2, 2, 1],
            "activation": "relu", "input_encoder": "integer-residual-and-complexity-v1",
            "coefficient_decoder": "dyadic-ranker-v1", "variable_coefficients": 2,
            "fixed_parameters": {"up_weight": "identity-2", "up_bias": [0, 0], "down_bias": [0]},
            "down_weight_rules": ["-(1+(word%1024)/1024)", "-(1+(word%1024))/1048576"]}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def affine_at(a, c, modulus, x0, coordinate):
    """Independent binary composition reference, without E-CPU's navigator."""
    p, q, u, v = 1, 0, a % modulus, c % modulus
    while coordinate:
        if coordinate & 1:
            p, q = u * p % modulus, (u * q + v) % modulus
        u, v = u * u % modulus, (u * v + v) % modulus
        coordinate >>= 1
    return (p * x0 + q) % modulus


def backing(root):
    node = ReplicatedMailboxNode(ReplicatedMailboxStore(root / "mailbox.log", "pnf004"), quorum=1)
    return ComputationalObjectStore(RemotePageStore(root / "pages", node), max_object_bytes=65536)


def policy_for(proposal):
    # Receiver-owned benchmark policy. It authorizes only these explicit domains.
    return proposal.spec.domain in {"pnf004-parameter-field", "pnf004-observed-orbit"}


def descriptor(version):
    return {**CONTRACT, "parameters": [VirtualStructuralMemoryRef.from_version(
        name, version, coordinate).to_dict() for name, coordinate in (("error_weight", 10**12),
                                                                    ("cost_weight", 10**12 + 1))]}


class GroundModelHost:
    def __init__(self, root: Path, *, restored_policy=None, grant_compute=True, grant_read=True,
                 engine="addressed-scalar"):
        if engine not in {"addressed-scalar", "dense-reference"}:
            raise ValueError("unknown receiver inference engine")
        self.engine = engine
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = backing(self.root)
        self.calls = 0
        if restored_policy is None:
            self.system = HeadlessOS(structural_memory_admission_policy=policy_for)
            law = Law("lcg", {"a": 1664525, "c": 1013904223, "mod": 2**32, "x0": 31}, 1, "GROUND")
            witnesses = {i: affine_at(1664525, 1013904223, 2**32, 31, i) for i in (0, 1, 7, 19)}
            proposal = self.system.structural_memory.propose(MEMORY, law, witnesses,
                domain="pnf004-parameter-field", context=CONTEXT)
            version = self.system.structural_memory.admit(proposal.proposal_id, expected_revision=0)
            self.manifest = self.store.put_bytes(canonical(descriptor(version)), media_type="application/json")
            generation = 1
        else:
            if sha((self.root / "system.json").read_bytes()) != restored_policy["checkpoint_sha256"]:
                raise ValueError("external checkpoint pin mismatch")
            self.system = load_checkpoint(self.root / "system.json", structural_memory_admission_policy=policy_for)
            self.manifest = ComputationalObjectManifest.from_dict(restored_policy["manifest"])
            if self.manifest.manifest_digest != restored_policy["manifest_digest"]:
                raise ValueError("external manifest pin mismatch")
            if self.manifest.content_digest != restored_policy["model_digest"]:
                raise ValueError("external model pin mismatch")
            generation = restored_policy["next_generation"]
            if type(generation) is not int or generation < 2:
                raise ValueError("invalid receiver generation")
        model_bytes = self.store.read_bytes(self.manifest)
        self.model = json.loads(model_bytes)
        version = self.system.structural_memory.version_for_revision(MEMORY, 1)
        if self.model != descriptor(version) or canonical(self.model) != model_bytes:
            raise ValueError("model contract or pinned structural revision changed")
        self.model_digest = self.manifest.content_digest
        self.generation = generation
        self.references = tuple(VirtualStructuralMemoryRef.from_dict(r) for r in self.model["parameters"])
        self.system.hypervisor.classifier = LexicalDecisionModel()
        self.system.hypervisor.policy = HypervisorPolicy(embedding_review_confidence=1.0)
        self.identity = SystemIdentity("pnf004-observer", generation)
        envelope = SystemSeedEnvelope(self.identity, "ground-ranker", "pnf004", SystemSeed.from_system(self.system))
        if not self.system.seed_admission.admit(envelope).accepted:
            raise ValueError("execution Ground admission failed")
        self.ground = VirtualGroundRef.from_envelope(envelope)
        caps = []
        if grant_compute:
            caps.append(Capability("/virtual-layer/operators", frozenset({"compute"})))
        if grant_read:
            caps.append(Capability("/structural-memory/read", frozenset({"read"})))
        self.pid = self.system.environment.kernel.spawn("pnf004-ranker", capabilities=tuple(caps),
                                                      parent_pid=self.system.environment.init_pid)
        self.spec = OperatorSpec(operator_id=OPERATOR, version=1,
            description="Rank candidate Ground laws with addressed neural coefficients via " + self.engine,
            input_kind="object", output_kind="object", substrates=("cpu",),
            required_rights=frozenset({"compute"}), max_input_bytes=30000, max_output_bytes=10000,
            base_energy=2, energy_per_byte=1, deterministic=True, effect_mode="pure")
        registry = OperatorRegistry()
        registry.register(self.spec, self._infer)
        self.runtime = VirtualLayerRuntime(registry, "pnf004-local", frozenset({"cpu"}))

    def _infer(self, resolved, workload):
        features = resolved["input"]["features"]
        words = [resolved["structural_memory"][name]["value"] for name in ("error_weight", "cost_weight")]
        weights = [1 + (words[0] % 1024) / 1024, (1 + words[1] % 1024) / 1048576]
        self.calls += 1
        if self.engine == "dense-reference":
            model = Block(np.eye(2, dtype=np.float32), np.zeros(2, dtype=np.float32),
                          -np.asarray(weights, dtype=np.float32).reshape(2, 1), np.zeros(1, dtype=np.float32), "relu")
            scores = evaluate(model, np.asarray(features, dtype=np.float64))[:, 0].tolist()
        else:
            scores = [-(max(row[0], 0) * weights[0] + max(row[1], 0) * weights[1]) for row in features]
        return {"scores": scores, "model_digest": self.model_digest,
                "parameter_value_digests": [resolved["structural_memory"][name]["receipt"]["value_digest"]
                                             for name in ("error_weight", "cost_weight")]}

    def infer(self, features, sequence=1):
        if (not isinstance(features, list) or not 1 <= len(features) <= 8
                or any(not isinstance(row, list) or len(row) != 2 or
                       any(type(v) is not int or not 0 <= v <= 2**24 for v in row) for row in features)):
            raise ValueError("bounded integer feature rows required")
        workload = VirtualLayerWorkload(workload_id=f"pnf004-{sequence}", system=self.identity,
            ground=self.ground, intention={"goal": "rank candidate Ground laws", "model": self.model_digest},
            operators=(VirtualOperatorRef(OPERATOR, 1, "cpu", "pnf004-local", self.references),),
            input_value={"model_digest": self.model_digest, "features": features},
            budget=VirtualBudget(1000000, 100000, 100000), logical_time=17,
            eligible_nodes=("pnf004-local",), max_hops=1, schema_version=2)
        result = self.runtime.execute_operator(self.system, self.pid, "pnf004-task", f"pnf004-inference-{self.generation}",
                                               sequence, 17, workload, OPERATOR)
        if result.action.value != "allow" or not result.executed:
            return {"status": "denied", "action": result.action.value, "handler_calls": self.calls}
        return {"status": "executed", "replayed": result.replayed, "fingerprint": result.fingerprint,
                "result": result.effect["result"]}

    def save(self):
        save_checkpoint(self.system, self.root / "system.json")
        return {"checkpoint_sha256": sha((self.root / "system.json").read_bytes()),
                "manifest": self.manifest.to_dict(), "manifest_digest": self.manifest.manifest_digest,
                "model_digest": self.model_digest, "next_generation": self.generation + 1}


def candidates(training, modulus):
    if (not isinstance(training, list) or not 4 <= len(training) <= 32 or type(modulus) is not int
            or not 2 <= modulus <= 65536 or any(type(x) is not int or not 0 <= x < modulus for x in training)):
        raise ValueError("invalid orbit observations")
    step = (training[1] - training[0]) % modulus
    laws = [Law("int", {"x0": training[0], "step": step, "mod": modulus}, 1, "GROUND")]
    fitted = fit_affine(training[:4], modulus)
    if fitted is not None:
        laws.append(Law("lcg", {"x0": training[0], "a": fitted["a"], "c": fitted["c"], "mod": modulus}, 1, "GROUND"))
    features = [[sum(abs(law.navigate(i) - v) for i, v in enumerate(training)), index + 1]
                for index, law in enumerate(laws)]
    return laws, features


def task(host, observations, modulus, task_id, sequence):
    """Rank using training only; withheld observations independently gate admission."""
    if len(observations) != 16 or any(type(v) is not int or not 0 <= v < modulus for v in observations):
        raise ValueError("sixteen bounded integer observations required")
    laws, features = candidates(observations[:8], modulus)
    result = host.infer(features, sequence)
    if result["status"] != "executed":
        return result
    selected = max(range(len(laws)), key=lambda i: (result["result"]["scores"][i], -i))
    law = laws[selected]
    context = {"model_digest": host.model_digest, "observations_sha256": sha(canonical(observations))}
    memory_id = "pnf004.task." + task_id
    # This verifier sees all 16 observations, including the 8 withheld from ranking.
    current = host.system.structural_memory.active_version(memory_id)
    if current is None:
        proposal = host.system.structural_memory.propose(memory_id, law, dict(enumerate(observations)),
                                                        domain="pnf004-observed-orbit", context=context)
        version = host.system.structural_memory.admit(proposal.proposal_id, expected_revision=0)
    else:
        if (current.spec.family != law.family or current.spec.parameters != law.params
                or current.spec.context != context):
            raise ValueError("task identity conflicts with an admitted Ground")
        certificate = host.system.structural_memory.verifier.certify(current.spec, tuple(enumerate(observations)))
        if certificate.digest != current.certificate.digest:
            raise ValueError("restored witness evidence changed")
        version = current
    receipt = host.system.structural_memory.read_revision(memory_id, version.spec.revision, 10**12,
                                                          context=context)
    return {"status": "admitted", "family": law.family, "model_result": result["result"],
            "selected_index": selected, "candidate_count": len(laws), "features": features,
            "ground_spec_digest": version.spec.digest, "ground_revision": version.spec.revision,
            "verification_class": version.certificate.verification_class.value,
            "navigation_coordinate": 10**12, "navigation_value": receipt.value,
            "training_observations": 8, "withheld_observations": 8}
