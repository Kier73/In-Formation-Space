from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from mailcpu.stateful_transition import StatefulTransitionRuntime
from mailcpu.transition_space import (
    SparseTransitionReLUNetwork,
    compile_live_compositional_transition_program,
    two_bit_counter_program,
)
from portable_realization import encode_capsule
from portable_stateful_checkpoint import (
    MAGIC,
    PREFIX,
    SCHEMA,
    VERSION,
    PortableStatefulCheckpointError,
    _canonical,
    _digest,
    decode_checkpoint,
    encode_checkpoint,
    restore_runtime,
)


ROOT = Path(__file__).resolve().parents[2]


def _scalar_counter(inputs):
    state_1, state_0, advance, reset = inputs
    if reset:
        return (0, 0)
    if advance:
        return (state_1 ^ state_0, 1 - state_0)
    return (state_1, state_0)


def _load_prc_runner():
    runner_path = ROOT / "experiments" / "portable-realization-capsule" / "run_experiment.py"
    spec = importlib.util.spec_from_file_location("psc001_prc_fixture", runner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _realization_capsule(program, reference_fn=None):
    prc = _load_prc_runner()
    workload = SimpleNamespace(
        name=program.name,
        program=program,
        reference=reference_fn or _scalar_counter,
    )
    table = program.to_table()
    inputs = [tuple(row.inputs) for row in table.rows]
    expected_records = prc._expected_records(workload, table, inputs)

    dense = compile_live_compositional_transition_program(program)
    sparse = SparseTransitionReLUNetwork.from_dense(dense)
    payload = prc.sre002.encode_hybrid_binary(sparse)
    encoding = "hybrid_binary"
    compiler = "live_dag"
    contract = prc.sre002.contract_for(
        workload, table, compiler, encoding, dense, sparse, payload
    )

    case_records = []
    contract_digests = []
    for row_index, record in enumerate(expected_records):
        input_vector = tuple(record["inputs"])
        expected = tuple(record["outputs"])
        dense_outputs = dense.predict(input_vector)
        sparse_outputs = sparse.predict(input_vector)
        assert dense_outputs == expected
        assert sparse_outputs == expected
        comparison = prc.sre002.compare_projected_observations(
            contract,
            case_payload={
                "program_digest": program.digest,
                "table_digest": table.digest,
                "input_registers": dict(zip(table.input_names, input_vector)),
            },
            source_observation=dict(zip(table.output_names, dense_outputs)),
            target_observation=dict(zip(table.output_names, sparse_outputs)),
        )
        assert comparison.equivalent
        contract_digests.append(comparison.contract_digest)
        case_records.append({
            "row_index": row_index,
            "inputs": list(input_vector),
            "outputs": list(expected),
            "restored_outputs": list(sparse_outputs),
            "translation_contract_digest": comparison.contract_digest,
        })

    receipt = prc._make_verification_receipt(
        workload,
        table,
        compiler,
        encoding,
        expected_records,
        case_records,
        contract_digests,
    )
    capsule = encode_capsule(
        payload,
        source=prc._source(workload, sparse, "test-ifs-revision"),
        realization=prc._realization(
            compiler, dense, sparse, "test-ecpu-revision", encoding
        ),
        interface=prc._interface(table, sparse),
        codec={
            "name": encoding,
            "schema": "sre002.hybrid-binary.v1",
            "payload_sha256": prc.bytes_digest(payload),
        },
        verification=receipt,
        toolchain=prc._toolchain(
            "test-ifs-revision", "test-ecpu-revision", "test-vgi-revision"
        ),
    )
    assert sparse.source_digest == program.digest
    assert sparse.digest
    return capsule, dense, sparse


def _build_runtime_and_capsules():
    baseline = two_bit_counter_program()
    revised = baseline.with_row_output(
        (0, 1, 1, 1),
        (1, 0),
        name="two-bit-counter.reset-exception.v1",
    )
    runtime = StatefulTransitionRuntime(baseline, (0, 1))

    first = runtime.step({"advance": 0, "reset": 0})
    assert first.state == (0, 1)
    revision_event = runtime.revise(revised)
    assert revision_event["tick"] == first.tick
    assert revision_event["state_preserved"] == [0, 1]
    second = runtime.step({"advance": 1, "reset": 1})
    assert second.state == (1, 0)
    third = runtime.step({"advance": 0, "reset": 0})
    assert third.state == (1, 0)
    assert runtime.tick == 3 and runtime.revision == 1

    def revised_scalar_counter(inputs):
        if tuple(inputs) == (0, 1, 1, 1):
            return (1, 0)
        return _scalar_counter(inputs)

    initial_capsule, initial_dense, initial_sparse = _realization_capsule(baseline)
    revised_capsule, revised_dense, revised_sparse = _realization_capsule(
        revised, revised_scalar_counter
    )
    assert runtime.model_digest == revised_dense.digest
    assert runtime.program_digest == revised.digest
    assert initial_sparse.source_digest == baseline.digest
    assert revised_sparse.source_digest == revised.digest
    return runtime, (initial_capsule, revised_capsule)


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for independent stateful checkpoint verification")
    return node


def test_portable_stateful_checkpoint_replays_revision_and_resumes_in_node():
    node = _node()
    runtime, capsules = _build_runtime_and_capsules()
    checkpoint = encode_checkpoint(
        runtime,
        capsules,
        resume_controls={"advance": 1, "reset": 0},
    )
    header = decode_checkpoint(checkpoint)
    assert header["schema"] == SCHEMA
    assert header["runtime"]["tick"] == 3
    assert header["runtime"]["revision"] == 1
    assert "current_model" not in header["runtime"]
    assert header["runtime"]["current_model_digest"] == runtime.model_digest
    assert len(header["realizations"]) == 2

    restored = restore_runtime(checkpoint)
    assert restored.snapshot() == runtime.snapshot()

    script = ROOT / "experiments" / "portable-realization-capsule" / "verify_capsule.mjs"
    with tempfile.TemporaryDirectory() as directory:
        checkpoint_path = Path(directory) / "two-bit-counter.psc"
        checkpoint_path.write_bytes(checkpoint)
        result = subprocess.run(
            [node, str(script), "--checkpoint", str(checkpoint_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)

        assert report["valid"] is True
        assert report["checkpoint_sha256"] == header["checkpoint_sha256"]
        assert report["event_count"] == 4
        assert report["step_count"] == 3
        assert report["revision_count"] == 1
        assert report["realization_count"] == 2
        assert report["exhaustive_model_rows"] == 32
        assert report["restored_state"] == [1, 0]
        assert report["restored_tick"] == 3
        assert report["restored_revision"] == 1
        assert report["restored_program_digest"] == runtime.program_digest
        assert report["restored_model_digest"] == runtime.model_digest
        assert report["resumed_state"] == [1, 1]
        assert report["resumed_tick"] == 4
        assert report["resumed_revision"] == 1

        resumed = restored.step(header["resume_controls"])
        assert list(resumed.state) == report["resumed_state"]
        assert resumed.tick == report["resumed_tick"]
        assert resumed.revision == report["resumed_revision"]
        assert resumed.event_digest == report["resumed_event_digest"]


def test_portable_stateful_checkpoint_rejects_corruption_and_semantic_event_forgery():
    node = _node()
    runtime, capsules = _build_runtime_and_capsules()
    checkpoint = encode_checkpoint(
        runtime,
        capsules,
        resume_controls={"advance": 1, "reset": 0},
    )
    header = decode_checkpoint(checkpoint)

    changed_bytes = bytearray(checkpoint)
    changed_bytes[-1] ^= 0x01
    with pytest.raises(PortableStatefulCheckpointError, match="checkpoint SHA-256"):
        restore_runtime(bytes(changed_bytes))

    forged = json.loads(json.dumps(header))
    last_event = forged["runtime"]["events"][-1]
    # Forge a self-consistent hash chain and terminal state, but not the
    # transition semantics of the active typed program / decoded model.
    last_event["outputs"] = [0, 0]
    last_event["state_after"] = [0, 0]
    event_payload = {
        key: value for key, value in last_event.items()
        if key != "event_digest"
    }
    last_event["event_digest"] = _digest(event_payload)
    forged["runtime"]["state"] = [0, 0]
    forged["runtime"]["chain_head_digest"] = last_event["event_digest"]
    core = {key: value for key, value in forged.items() if key != "checkpoint_sha256"}
    forged = {**core, "checkpoint_sha256": _digest(core)}
    raw = _canonical(forged)
    forged_checkpoint = PREFIX.pack(MAGIC, VERSION, len(raw)) + raw

    with pytest.raises(PortableStatefulCheckpointError, match="event differs from its replay"):
        restore_runtime(forged_checkpoint)

    script = ROOT / "experiments" / "portable-realization-capsule" / "verify_capsule.mjs"
    with tempfile.TemporaryDirectory() as directory:
        checkpoint_path = Path(directory) / "forged-state.psc"
        checkpoint_path.write_bytes(forged_checkpoint)
        result = subprocess.run(
            [node, str(script), "--checkpoint", str(checkpoint_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "step event does not match independent typed/model execution" in result.stderr
