"""Bounded executable neural Ground with evidence-path operator observations.

Consumes the existing HFR typed graph and VGI ProofGround. Only a synthetic
parameter realization is evaluated: the source checkpoint's numerical payload
is never accessed, and local measurements never become kernel acceptance.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import numpy as np

from observation_path import ObservationIntent, ObservationPath
from vgi.neural_topology import build_neural_topology_proof_ground

SCHEMA = "in-formation.neural-executable-observation.v0.1"
RUNTIME_ID = "synthetic-numpy-reference.v0.1"
GENESIS = hashlib.sha256(b"neural-executable-observation-v0.1:genesis").hexdigest()
SUPPORTED = {
    "embedding.lookup", "tensor.add", "regularization.dropout",
    "normalization.layer_norm", "linear.affine",
    "attention.causal_scaled_dot_product", "activation.gelu_tanh",
}


class NeuralExecutionGroundError(ValueError):
    """The chosen observation is not valid for this bounded executable Ground."""


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise NeuralExecutionGroundError(f"non-canonical observation: {exc}") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _shape(shape: list[int | str], dimensions: Mapping[str, int]) -> tuple[int, ...]:
    result = []
    for item in shape:
        resolved = dimensions.get(item) if isinstance(item, str) else item
        if isinstance(resolved, bool) or not isinstance(resolved, int) or resolved <= 0:
            raise NeuralExecutionGroundError(f"unresolved or nonpositive dimension {item!r}")
        result.append(resolved)
    return tuple(result)


def _array_digest(array: np.ndarray) -> str:
    """Portable synthetic array identity includes dtype, shape, and little-endian bytes."""
    value = np.asarray(array)
    if value.dtype == np.dtype("float32"):
        normalized = np.ascontiguousarray(value.astype("<f4", copy=False))
        dtype = "F32"
    elif value.dtype == np.dtype("int64"):
        normalized = np.ascontiguousarray(value.astype("<i8", copy=False))
        dtype = "I64"
    elif value.dtype == np.dtype("bool"):
        normalized = np.ascontiguousarray(value.astype(np.bool_, copy=False))
        dtype = "BOOL"
    else:
        raise NeuralExecutionGroundError(f"unsupported array dtype {value.dtype}")
    header = _canonical({"dtype": dtype, "shape": list(value.shape)}).encode("utf-8")
    return hashlib.sha256(header + b"\x00" + normalized.tobytes(order="C")).hexdigest()


def _dtype_name(value: np.ndarray) -> str:
    mapping = {
        np.dtype("float32"): "F32",
        np.dtype("int64"): "I64",
        np.dtype("bool"): "BOOL",
    }
    try:
        return mapping[np.asarray(value).dtype]
    except KeyError as exc:
        raise NeuralExecutionGroundError("unsupported runtime dtype") from exc


def _describe(value: np.ndarray) -> dict[str, Any]:
    return {
        "dtype": _dtype_name(value),
        "shape": list(value.shape),
        "digest": _array_digest(value),
        "finite": bool(np.isfinite(value).all()),
    }


def _execute(operator: Mapping[str, Any], inputs: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Evaluate one family-interpreted primitive on synthetic inputs.

    This is an independently implemented prototype, not a measured original
    model. Evaluation mode is fixed; dropout is identity.
    """
    kind = operator["operator"]
    attributes = operator["attributes"]
    if kind == "embedding.lookup":
        result = inputs["table"][inputs["indices"]]
        values = {"embeddings": result}
    elif kind == "tensor.add":
        first, second = inputs.values()
        output_name = operator["outputs"][0]["name"]
        values = {output_name: first + second}
    elif kind == "regularization.dropout":
        values = {"output": inputs["value"]}
    elif kind == "normalization.layer_norm":
        value = inputs["value"]
        mean = np.mean(value, axis=-1, keepdims=True)
        variance = np.mean((value - mean) ** 2, axis=-1, keepdims=True)
        norm = (value - mean) / np.sqrt(variance + np.float32(attributes["epsilon"]))
        values = {"normalized": norm * inputs["scale"] + inputs["offset"]}
    elif kind == "linear.affine":
        data, weight = inputs["data"], inputs["weight"]
        layout = attributes["weight_layout"]
        if layout == "input_by_output":
            result = data @ weight
        elif layout == "output_by_input":
            result = data @ weight.T
        else:
            raise NeuralExecutionGroundError(f"unsupported weight layout {layout!r}")
        if "bias" in inputs:
            result = result + inputs["bias"]
        values = {operator["outputs"][0]["name"]: result}
    elif kind == "activation.gelu_tanh":
        value = inputs["value"]
        scaled = np.float32(math.sqrt(2.0 / math.pi))
        result = np.float32(0.5) * value * (
            1 + np.tanh(scaled * (value + np.float32(0.044715) * value**3))
        )
        values = {"output": result}
    elif kind == "attention.causal_scaled_dot_product":
        raw = inputs["fused_query_key_value"]
        if raw.ndim != 3:
            raise NeuralExecutionGroundError("synthetic attention expects [batch,sequence,3*hidden]")
        batch, sequence, width3 = raw.shape
        heads, head_width = attributes["head_count"], attributes["head_width"]
        if width3 != 3 * heads * head_width:
            raise NeuralExecutionGroundError("fused QKV width is inconsistent")
        qkv = raw.reshape(batch, sequence, 3, heads, head_width)
        q, k, v = [qkv[:, :, index].transpose(0, 2, 1, 3) for index in range(3)]
        scores = (q @ k.transpose(0, 1, 3, 2)) / np.float32(math.sqrt(head_width))
        causal = inputs["causal_mask"][..., :sequence, :sequence].astype(bool)
        if causal.shape != (1, 1, sequence, sequence):
            raise NeuralExecutionGroundError("synthetic causal mask has wrong dimensions")
        if not bool(np.all(causal[0, 0] == np.tril(np.ones((sequence, sequence), dtype=bool)))):
            raise NeuralExecutionGroundError("synthetic causal mask must be lower triangular")
        scores = np.where(causal, scores, -np.inf)
        exp = np.exp(scores - np.max(scores, axis=-1, keepdims=True))
        weights = exp / np.sum(exp, axis=-1, keepdims=True)
        context = (weights @ v).transpose(0, 2, 1, 3)
        values = {"context": context.reshape(batch, sequence, heads * head_width)}
    else:
        raise NeuralExecutionGroundError(f"unsupported executable primitive {kind!r}")

    return {key: np.asarray(value, dtype=np.float32) for key, value in values.items()}


class ExecutableNeuralGround:
    """VGI proof obligations plus a bounded, causal synthetic operator runner."""

    def __init__(
        self,
        graph: Mapping[str, Any],
        *,
        seed: int = 17,
        batch: int = 1,
        sequence: int = 2,
        max_elements: int = 120_000,
    ) -> None:
        if any(type(value) is not int for value in (seed, batch, sequence, max_elements)):
            raise NeuralExecutionGroundError("seed, batch, sequence and budget must be integers")
        if seed < 0 or batch <= 0 or sequence <= 0 or max_elements <= 0:
            raise NeuralExecutionGroundError("invalid seed, runtime dimensions or budget")
        # This independent VGI intake validates topology and creates *unverified*
        # obligations. No VerifiedKernelReceipt is produced by this adapter.
        self.package = build_neural_topology_proof_ground(graph)
        self.graph = json.loads(_canonical(dict(graph)))
        self.graph_digest = self.package.graph_digest
        self.seed = seed
        self.batch = batch
        self.sequence = sequence
        symbols = self.graph["dimension_symbols"]
        if sequence > symbols["sequence"]["maximum"]:
            raise NeuralExecutionGroundError("runtime sequence exceeds the declared context")
        self.dimensions = {name: entry["value"] for name, entry in symbols.items()
                           if entry["kind"] == "fixed"}
        self.dimensions.update({"batch": batch, "sequence": sequence})
        self.max_elements = max_elements
        self.operations = {item["id"]: item for item in self.graph["operations"]}
        if any(item["operator"] not in SUPPORTED for item in self.operations.values()):
            raise NeuralExecutionGroundError("graph contains operators without local synthetic evaluation")
        self.tensors = {item["name"]: item for item in self.graph["tensors"]}
        self.sources: dict[tuple[str, str], dict[str, Any]] = {}
        self.dependencies: dict[str, set[str]] = {key: set() for key in self.operations}
        self.consumers: dict[str, set[str]] = {key: set() for key in self.operations}
        self.outputs: dict[str, dict[str, Any]] = {}
        for edge in self.graph["edges"]:
            src, dst = edge["source"], edge["target"]
            if dst["kind"] == "graph_output":
                self.outputs[dst["name"]] = src
                continue
            key = (dst["operation"], dst["port"])
            if key in self.sources:
                raise NeuralExecutionGroundError("operation input has multiple producers")
            self.sources[key] = src
            if src["kind"] == "operation_output":
                a, b = src["operation"], dst["operation"]
                self.dependencies[b].add(a)
                self.consumers[a].add(b)

        # Fail closed *before allocation* for the 160-tensor GPT-2 graph or
        # any caller-provided runtime shape whose synthetic allocations exceed
        # the stated limit. The full source checkpoint is never loaded.
        tensor_count = sum(math.prod(_shape(item["shape"], self.dimensions))
                           for item in self.tensors.values())
        graph_input_count = sum(math.prod(_shape(item["shape"], self.dimensions))
                                for item in self.graph["inputs"])
        activation_count = sum(
            math.prod(_shape(port["shape"], self.dimensions))
            for operation in self.operations.values()
            for port in operation["outputs"]
        )
        # Attention uses [batch, heads, sequence, sequence] score, mask,
        # exponential and probability intermediates. Conservatively include
        # all attention scratch footprints in the preflight accounting.
        attention_scratch = sum(
            8 * batch * operation["attributes"]["head_count"] * sequence * sequence
            for operation in self.operations.values()
            if operation["operator"] == "attention.causal_scaled_dot_product"
        )
        required_elements = (
            tensor_count + graph_input_count + activation_count + attention_scratch
        )
        if required_elements > max_elements:
            raise NeuralExecutionGroundError(
                "synthetic realization would exceed element budget: "
                f"parameters={tensor_count}, graph_inputs={graph_input_count}, "
                f"activations={activation_count}, attention_scratch={attention_scratch}, "
                f"total={required_elements}, budget={max_elements}"
            )
        self._tensors: dict[str, np.ndarray] = {}
        self._runtime_inputs: dict[str, np.ndarray] = {}
        self._values: dict[tuple[str, str], np.ndarray] = {}
        self._completed: set[str] = set()
        self._records: list[dict[str, Any]] = []
        self._head = GENESIS
        self._status = "ready"

    @property
    def status(self) -> str:
        return self._status

    def _inputs(self) -> dict[str, np.ndarray]:
        if not self._runtime_inputs:
            vocab = self.dimensions["vocabulary"]
            ids = np.arange(self.batch * self.sequence, dtype=np.int64).reshape(self.batch, self.sequence)
            self._runtime_inputs = {
                "token_ids": ids % vocab,
                "position_ids": np.broadcast_to(
                    np.arange(self.sequence, dtype=np.int64), (self.batch, self.sequence)
                ).copy(),
            }
        return self._runtime_inputs

    def _tensor(self, name: str) -> np.ndarray:
        if name in self._tensors:
            return self._tensors[name]
        item = self.tensors[name]
        shape = _shape(item["shape"], self.dimensions)
        if math.prod(shape) > self.max_elements:
            raise NeuralExecutionGroundError("synthetic tensor would exceed element budget")
        dtype = item["dtype"]
        if name.rsplit(".", 2)[-2:] == ["attn", "bias"]:
            mask = np.tril(np.ones(shape[-2:], dtype=bool)).reshape(shape)
            value = mask if dtype == "BOOL" else mask.astype(np.float32)
        elif dtype == "F32":
            key = hashlib.sha256(f"{self.seed}:{name}".encode()).digest()
            rng = np.random.default_rng(int.from_bytes(key[:8], "big"))
            value = (rng.standard_normal(shape).astype(np.float32) * np.float32(0.08))
            if name.endswith(".ln_1.weight") or name.endswith(".ln_2.weight") or name == "ln_f.weight":
                value = 1 + value
        else:
            raise NeuralExecutionGroundError(f"unsupported synthetic tensor dtype {dtype!r}")
        self._tensors[name] = value
        return value

    def ready(self) -> tuple[str, ...]:
        if self._status not in ("ready", "partial"):
            return ()
        candidates = [
            name for name, dependencies in self.dependencies.items()
            if name not in self._completed and dependencies.issubset(self._completed)
        ]
        # Select the ready operation with the most downstream impact.
        # Measurements determine whether this greedy search continues;
        # it is NOT VGI's minimax TransitionGround policy.
        candidates.sort(key=lambda name: (-len(self.consumers[name]), name))
        return tuple(candidates)

    def _source(self, descriptor: Mapping[str, str]) -> np.ndarray:
        kind = descriptor["kind"]
        if kind == "tensor":
            return self._tensor(descriptor["name"])
        if kind == "graph_input":
            return self._inputs()[descriptor["name"]]
        if kind == "operation_output":
            return self._values[(descriptor["operation"], descriptor["port"])]
        raise NeuralExecutionGroundError(f"unsupported source endpoint {kind!r}")

    def step(self) -> dict[str, Any]:
        if self._status not in ("ready", "partial"):
            raise NeuralExecutionGroundError(f"cannot observe an execution in state {self._status}")
        choices = self.ready()
        if not choices:
            if len(self._completed) == len(self.operations):
                self._status = "complete"
            else:
                self._status = "blocked"
            raise NeuralExecutionGroundError("no executable operation remains")
        name = choices[0]
        operation = self.operations[name]
        obligation_key = f"operation:{name}"
        obligation_id = self.package.obligation_keys[obligation_key]
        if self.package.ground.kernel_status(obligation_id) != "unverified":
            raise NeuralExecutionGroundError("local numeric observation cannot overwrite kernel acceptance")

        inbound: dict[str, np.ndarray] = {}
        for port in operation["inputs"]:
            name_port = port["name"]
            source = self.sources[(name, name_port)]
            value = self._source(source)
            if _dtype_name(value) != port["dtype"] or list(value.shape) != list(
                _shape(port["shape"], self.dimensions)
            ):
                raise NeuralExecutionGroundError(f"typed input {name}.{name_port} differs from graph")
            inbound[name_port] = value
        input_refs = {
            port: {"source": dict(self.sources[(name, port)]), **_describe(value)}
            for port, value in inbound.items()
        }
        attempt_id = f"synthetic-neural:{len(self._records):04d}"
        proposal = {
            "graph_digest": self.graph_digest,
            "obligation_id": obligation_id,
            "operation_id": name,
            "operator": operation["operator"],
            "ready_candidates": list(choices),
            "input_refs": input_refs,
            "previous_head": self._head,
        }
        proposal_digest = _digest(proposal)
        intent = ObservationIntent(
            attempt_id=attempt_id,
            candidate_name=name,
            query="Does the synthetic numeric output satisfy this typed operator contract?",
            hypothesis_set_digest=proposal_digest,
            estimated_cost=float(max(1, math.prod(_shape(operation["outputs"][0]["shape"], self.dimensions)))),
            plan_ref=f"vgi-proof-obligation:{obligation_id}",
            authority_required=False,
        )
        path = ObservationPath(intent)
        path.append("dispatched", "local-sandbox", evidence_ref=f"local-dispatch:{proposal_digest}")
        path.append("admitted", "local-numpy-runtime", evidence_ref=f"local-admission:{proposal_digest}")

        produced = _execute(operation, inbound)
        output_refs = {}
        conforms = set(produced) == {item["name"] for item in operation["outputs"]}
        for port in operation["outputs"]:
            value = produced.get(port["name"])
            if value is None:
                conforms = False
                continue
            record = _describe(value)
            output_refs[port["name"]] = record
            if record["dtype"] != port["dtype"] or record["shape"] != list(_shape(port["shape"], self.dimensions)) or not record["finite"]:
                conforms = False
        payload_digest = _digest(output_refs)
        path.append(
            "returned", "local-numpy-runtime",
            evidence_ref=f"synthetic-result:{payload_digest}",
            details={
                "encounter_id": attempt_id,
                "payload_digest": payload_digest,
                "canonicalization": "synthetic-typed-array-digests-v1",
            },
        )
        path.append(
            "interpreted", "local-typed-interpreter",
            evidence_ref=f"typed-interpretation:{payload_digest}",
            details={
                "method": "dtype-shape-finite-check-v1",
                "matched": conforms,
                "operator": operation["operator"],
                "output_refs": output_refs,
                "source_parameters": "synthetic-not-observed",
            },
        )
        if conforms:
            path.append(
                "query_determined", "local-typed-interpreter",
                evidence_ref=f"local-query:{proposal_digest}",
                details={
                    "query_result": True, "hypothesis_set_digest": proposal_digest,
                    "basis": "locally executed synthetic arrays satisfy declared dtype/shape/finite contracts",
                },
            )
            for port, value in produced.items():
                self._values[(name, port)] = value
            self._completed.add(name)
            self._status = "complete" if len(self._completed) == len(self.operations) else "partial"
        else:
            path.append(
                "unresolved", "local-typed-interpreter",
                details={"reason": "synthetic numeric result did not satisfy typed port contract"},
            )
            self._status = "divergence"
        core = {
            "step_index": len(self._records),
            "proposal": proposal,
            "proposal_digest": proposal_digest,
            "observation_path": path.to_dict(),
            "outcome": "synthetic_type_shape_conforms" if conforms else "synthetic_divergence",
            "output_refs": output_refs,
            "previous_head": self._head,
        }
        record = {**core, "record_digest": _digest(core)}
        self._records.append(record)
        self._head = record["record_digest"]
        return json.loads(_canonical(record))

    def run(self, *, max_steps: int | None = None) -> dict[str, Any]:
        if max_steps is not None and (type(max_steps) is not int or max_steps < 0):
            raise NeuralExecutionGroundError("max_steps must be a non-negative integer")
        remaining = len(self.operations) - len(self._completed) if max_steps is None else max_steps
        for _ in range(remaining):
            if self._status in ("complete", "divergence", "blocked"):
                break
            self.step()
        return self.receipt()

    def receipt(self) -> dict[str, Any]:
        output_refs = {}
        if self._status == "complete":
            for name, source in self.outputs.items():
                output_refs[name] = _describe(self._source(source))
        core = {
            "schema": SCHEMA,
            "runtime_id": RUNTIME_ID,
            "graph_digest": self.graph_digest,
            "source_repository": self.package.source_repository,
            "source_revision": self.package.source_revision,
            "seed": self.seed,
            "runtime": {"batch": self.batch, "sequence": self.sequence,
                        "evaluation_mode": "dropout-identity", "max_elements": self.max_elements},
            "status": self._status,
            "observation_count": len(self._records),
            "operation_count": len(self.operations),
            "records": self._records,
            "record_head": self._head,
            "graph_output_refs": output_refs,
            "vgi_proof_ground": {
                "obligation_count": len(self.package.ground.obligations),
                "unverified_obligations": len(self.package.ground.unresolved_obligations()),
                "kernel_accepted_obligations": 0,
            },
            "evidence_policy": {
                "tensor_payload_bytes_read": 0,
                "parameter_origin": "synthetic-prng-not-source-checkpoint",
                "structural_topology": "family-interpreted-and-validated-by-VGI",
                "numerical_behavior": "local-synthetic-measurement-only",
                "authority": "no-external-authority-or-kernel-receipt",
                "ordering": "single-local-controller-sequence-no-cross-host-clock",
            },
        }
        return json.loads(_canonical({**core, "receipt_digest": _digest(core)}))


def verify_neural_observation_receipt(graph: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Reproduce the full synthetic trace and compare it byte-for-byte as JSON.

    This checks deterministic replay and record integrity, not independent
    numerical equivalence to any external model or runtime.
    """
    if not isinstance(receipt, Mapping) or receipt.get("schema") != SCHEMA:
        raise NeuralExecutionGroundError("invalid neural execution receipt schema")
    if "receipt_digest" not in receipt:
        raise NeuralExecutionGroundError("missing neural execution receipt digest")
    core = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    if _digest(core) != receipt["receipt_digest"]:
        raise NeuralExecutionGroundError("neural execution receipt digest differs")
    runtime = receipt.get("runtime")
    if not isinstance(runtime, Mapping) or runtime.get("evaluation_mode") != "dropout-identity":
        raise NeuralExecutionGroundError("unsupported runtime settings in receipt")
    session = ExecutableNeuralGround(
        graph,
        seed=receipt["seed"],
        batch=runtime["batch"],
        sequence=runtime["sequence"],
        max_elements=runtime["max_elements"],
    )
    rebuilt = session.run(max_steps=receipt["observation_count"])
    if _canonical(rebuilt) != _canonical(dict(receipt)):
        raise NeuralExecutionGroundError("neural execution receipt differs from deterministic replay")
    return rebuilt


__all__ = [
    "SCHEMA", "RUNTIME_ID", "NeuralExecutionGroundError",
    "ExecutableNeuralGround", "verify_neural_observation_receipt",
]
