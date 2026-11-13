from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from portable_realization import (
    MAGIC,
    PREFIX,
    PortableRealizationError,
    _canonical,
    decode_capsule,
    encode_capsule,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _arguments():
    payload = b"exact-realization-payload-v1"
    receipt = {
        "status": "verified-within-complete-finite-domain",
        "verification_method": "unit-test complete finite-domain replay",
        "input_row_count": 4,
        "output_domain": "finite_boolean",
        "reference_outputs_sha256": "1" * 64,
        "case_evidence_sha256": "2" * 64,
        "translation_contracts_sha256": "3" * 64,
        "typed_program_digest": "d" * 64,
        "transition_table_digest": "e" * 64,
        "workload_id": "two-input-test-ground",
        "compiler_route": "live_dag",
        "codec": "rowmask_binary",
    }
    return payload, {
        "source": {
            "repository": "Kier73/In-Formation-Space",
            "revision": "ifs-revision-abc123",
            "kind": "transition_program",
            "ground_digest": "a" * 64,
            "program_digest": "d" * 64,
        },
        "realization": {
            "repository": "Kier73/E-CPU",
            "revision": "ecpu-revision-def456",
            "compiler_route": "live_dag",
            "dense_model_digest": "b" * 64,
            "sparse_model_digest": "c" * 64,
            "encoding": "rowmask_binary",
        },
        "interface": {
            "input_names": ["input_a", "input_b"],
            "output_names": ["next_state"],
            "architecture": [2, 3, 1],
            "domain": {
                "kind": "finite_boolean",
                "input_width": 2,
                "output_width": 1,
            },
        },
        "codec": {
            "name": "rowmask_binary",
            "schema": "sre002.rowmask-binary.v1",
            "payload_sha256": _sha(payload),
        },
        "verification": receipt,
        "toolchain": {
            "ifs_revision": "ifs-revision-abc123",
            "ecpu_revision": "ecpu-revision-def456",
            "vgi_revision": "vgi-revision-ghi789",
        },
    }


def test_capsule_round_trip_preserves_all_metadata_and_payload():
    payload, arguments = _arguments()
    capsule = encode_capsule(payload, **arguments)
    header, restored_payload = decode_capsule(capsule)

    assert restored_payload == payload
    assert header["schema"] == "in-formation-space.portable-realization.v1"
    assert header["source"]["ground_digest"] == "a" * 64
    assert header["realization"]["sparse_model_digest"] == "c" * 64
    assert header["codec"]["name"] == "rowmask_binary"
    assert header["verification"]["input_row_count"] == 4
    assert header["payload"]["byte_length"] == len(payload)
    assert header["payload"]["sha256"] == _sha(payload)
    assert header["capsule_sha256"]
    assert header["header_sha256"]


def test_capsule_rejects_header_metadata_tampering():
    payload, arguments = _arguments()
    capsule = encode_capsule(payload, **arguments)
    header_size = PREFIX.unpack_from(capsule, 0)[2]
    start = PREFIX.size
    end = start + header_size
    header = capsule[start:end].replace(
        b'"repository":"Kier73/In-Formation-Space"',
        b'"repository":"Kier73/No-Formation-Space"',
        1,
    )
    assert len(header) == header_size
    tampered = capsule[:start] + header + capsule[end:]

    with pytest.raises(PortableRealizationError, match="header SHA-256"):
        decode_capsule(tampered)


def test_capsule_rejects_payload_tampering():
    payload, arguments = _arguments()
    capsule = encode_capsule(payload, **arguments)
    changed = bytearray(capsule)
    changed[-1] ^= 0x01

    with pytest.raises(PortableRealizationError, match="payload SHA-256"):
        decode_capsule(bytes(changed))


def test_capsule_rejects_truncation_and_wrong_magic():
    payload, arguments = _arguments()
    capsule = encode_capsule(payload, **arguments)

    with pytest.raises(PortableRealizationError, match="payload byte length mismatch"):
        decode_capsule(capsule[:-2])

    changed = b"BADMAGIC" + capsule[len(MAGIC):]
    with pytest.raises(PortableRealizationError, match="magic"):
        decode_capsule(changed)


def test_capsule_rejects_incomplete_verification_receipt():
    payload, arguments = _arguments()
    arguments["verification"]["input_row_count"] = 3

    with pytest.raises(PortableRealizationError, match="complete Boolean domain"):
        encode_capsule(payload, **arguments)


def test_capsule_rejects_interface_architecture_mismatch():
    payload, arguments = _arguments()
    arguments["interface"]["architecture"] = [3, 3, 1]

    with pytest.raises(PortableRealizationError, match="architecture"):
        encode_capsule(payload, **arguments)


def test_capsule_requires_digest_bound_nonempty_payload():
    _, arguments = _arguments()

    with pytest.raises(PortableRealizationError, match="non-empty"):
        encode_capsule(b"", **arguments)



@pytest.mark.parametrize(
    "mutation",
    [
        lambda args: args["verification"].__setitem__("measurement", 1.5),
        lambda args: args["verification"].__setitem__("unexpected_κ", "value"),
    ],
    ids=["floating-point-metadata", "non-ascii-object-key"],
)
def test_v1_canonical_metadata_rejects_nonportable_values(mutation):
    payload, arguments = _arguments()
    mutation(arguments)

    with pytest.raises(PortableRealizationError, match="canonical metadata v1"):
        encode_capsule(payload, **arguments)


def test_boolean_is_not_accepted_as_an_integer_field():
    payload, arguments = _arguments()
    arguments["interface"]["input_names"] = ["input_a"]
    arguments["interface"]["architecture"] = [1, 2, 1]
    arguments["interface"]["domain"]["input_width"] = True
    arguments["verification"]["input_row_count"] = 2

    with pytest.raises(
        PortableRealizationError,
        match="input_width must be an interoperable safe integer",
    ):
        encode_capsule(payload, **arguments)

    payload, arguments = _arguments()
    arguments["interface"]["input_names"] = ["input_a"]
    arguments["interface"]["architecture"] = [1, 2, 1]
    arguments["interface"]["domain"]["input_width"] = 1
    arguments["verification"]["input_row_count"] = True

    with pytest.raises(
        PortableRealizationError,
        match="input_row_count must be an interoperable safe integer",
    ):
        encode_capsule(payload, **arguments)


def test_independent_node_receiver_verifies_python_capsule_and_unicode_values():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the independent implementation check")

    payload, arguments = _arguments()
    arguments["verification"]["workload_id"] = "ground — λ\\nline\\u2028separator"
    capsule = encode_capsule(payload, **arguments)
    script = Path(__file__).with_name("verify_capsule.mjs")

    with tempfile.TemporaryDirectory() as directory:
        capsule_path = Path(directory) / "portable-realization.bin"
        capsule_path.write_bytes(capsule)
        result = subprocess.run(
            [node, str(script), str(capsule_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["valid"] is True
        assert report["capsule_sha256"] == decode_capsule(capsule)[0]["capsule_sha256"]
        assert report["payload_sha256"] == _sha(payload)
        assert report["codec"] == "rowmask_binary"

        capsule_path.write_bytes(capsule[:-1] + bytes([capsule[-1] ^ 1]))
        tampered = subprocess.run(
            [node, str(script), str(capsule_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert tampered.returncode != 0
        assert "payload SHA-256 mismatch" in tampered.stderr



def test_independent_node_receiver_decodes_and_replays_rowmask_binary_capsule():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the independent implementation check")

    import importlib.util

    root = Path(__file__).resolve().parents[2]
    runner_path = root / "experiments" / "portable-realization-capsule" / "run_experiment.py"
    spec = importlib.util.spec_from_file_location("prc_replay_fixture", runner_path)
    assert spec is not None and spec.loader is not None
    prc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prc)
    sre = prc.sre002

    workload = next(
        item for item in sre.rcn.build_workloads()
        if item.name == "parity-2"
    )
    table = workload.program.to_table()
    inputs = [tuple(row.inputs) for row in table.rows]
    expected_records = prc._expected_records(workload, table, inputs)

    dense = sre.compile_models(workload.program, table)["direct_dag"]
    sparse = sre.SparseTransitionReLUNetwork.from_dense(dense)
    payload = sre.encode_rowmask_binary(sparse)
    compiler = "direct_dag"
    contract_digests = ["0" * 64 for _ in expected_records]
    receipt = prc._make_verification_receipt(
        workload,
        table,
        compiler,
        "rowmask_binary",
        expected_records,
        expected_records,
        contract_digests,
    )
    capsule = encode_capsule(
        payload,
        source=prc._source(workload, sparse, "test-ifs-revision"),
        realization=prc._realization(
            compiler, dense, sparse, "test-ecpu-revision", "rowmask_binary"
        ),
        interface=prc._interface(table, sparse),
        codec={
            "name": "rowmask_binary",
            "schema": "sre002.rowmask-binary.v1",
            "payload_sha256": prc.bytes_digest(payload),
        },
        verification=receipt,
        toolchain=prc._toolchain(
            "test-ifs-revision", "test-ecpu-revision", "test-vgi-revision"
        ),
    )

    script = Path(__file__).with_name("verify_capsule.mjs")
    with tempfile.TemporaryDirectory() as directory:
        capsule_path = Path(directory) / "parity-2-rowmask.ifsp"
        reference_path = Path(directory) / "parity-2-reference.json"
        capsule_path.write_bytes(capsule)
        reference_path.write_text(
            json.dumps(expected_records, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        result = subprocess.run(
            [node, str(script), str(capsule_path), "--reference", str(reference_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["valid"] is True
        assert report["codec"] == "rowmask_binary"
        assert report["input_rows_replayed"] == 4
        assert report["semantic_comparisons"] == 4
        assert report["sparse_model_sha256"] == sparse.digest
        assert report["stored_parameter_count"] == sparse.stored_parameter_count

        altered = [dict(record) for record in expected_records]
        altered[0] = {
            "inputs": list(altered[0]["inputs"]),
            "outputs": [1 - altered[0]["outputs"][0]],
        }
        reference_path.write_text(
            json.dumps(altered, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        mismatch = subprocess.run(
            [node, str(script), str(capsule_path), "--reference", str(reference_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert mismatch.returncode != 0
        assert "reference digest" in mismatch.stderr



def test_independent_node_receiver_replays_float64_rowmask_coefficients():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the independent implementation check")

    import importlib.util

    root = Path(__file__).resolve().parents[2]
    runner_path = root / "experiments" / "portable-realization-capsule" / "run_experiment.py"
    spec = importlib.util.spec_from_file_location("prc_float64_replay_fixture", runner_path)
    assert spec is not None and spec.loader is not None
    prc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prc)
    sre = prc.sre002

    workload = next(
        item for item in sre.rcn.build_workloads()
        if item.name == "parity-2"
    )
    table = workload.program.to_table()
    inputs = [tuple(row.inputs) for row in table.rows]
    expected_records = prc._expected_records(workload, table, inputs)

    original_dense = sre.compile_models(workload.program, table)["direct_dag"]
    # ReLU positive homogeneity: scale the first hidden layer by 1/2 and
    # the next layer's incoming weights by 2. The represented function is
    # unchanged, but the first layer now requires exact float64 coefficients.
    scaled_weights = []
    scaled_biases = []
    for layer_index, matrix in enumerate(original_dense.weights):
        weight_scale = 0.5 if layer_index == 0 else 2.0 if layer_index == 1 else 1.0
        bias_scale = 0.5 if layer_index == 0 else 1.0
        scaled_weights.append([
            [weight * weight_scale for weight in row]
            for row in matrix
        ])
        scaled_biases.append([
            bias * bias_scale
            for bias in original_dense.biases[layer_index]
        ])
    scaled_dense = type(original_dense)(
        scaled_weights,
        scaled_biases,
        program_digest=workload.program.digest,
        input_names=table.input_names,
        output_names=table.output_names,
        architecture=original_dense.architecture,
    )
    sparse = sre.SparseTransitionReLUNetwork.from_dense(scaled_dense)
    payload = sre.encode_rowmask_binary(sparse)
    inner_header_size = int.from_bytes(payload[:4], "little")
    inner_header = json.loads(payload[4:4 + inner_header_size])
    assert inner_header["layers"][0]["weight_dtype"] == "f64"

    compiler = "direct_dag"
    receipt = prc._make_verification_receipt(
        workload,
        table,
        compiler,
        "rowmask_binary",
        expected_records,
        expected_records,
        ["0" * 64 for _ in expected_records],
    )
    capsule = encode_capsule(
        payload,
        source=prc._source(workload, sparse, "test-ifs-revision"),
        realization=prc._realization(
            compiler, scaled_dense, sparse, "test-ecpu-revision", "rowmask_binary"
        ),
        interface=prc._interface(table, sparse),
        codec={
            "name": "rowmask_binary",
            "schema": "sre002.rowmask-binary.v1",
            "payload_sha256": prc.bytes_digest(payload),
        },
        verification=receipt,
        toolchain=prc._toolchain(
            "test-ifs-revision", "test-ecpu-revision", "test-vgi-revision"
        ),
    )

    script = Path(__file__).with_name("verify_capsule.mjs")
    with tempfile.TemporaryDirectory() as directory:
        capsule_path = Path(directory) / "parity-2-rowmask-f64.ifsp"
        reference_path = Path(directory) / "parity-2-reference.json"
        capsule_path.write_bytes(capsule)
        reference_path.write_text(
            json.dumps(expected_records, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        result = subprocess.run(
            [node, str(script), str(capsule_path), "--reference", str(reference_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["valid"] is True
        assert report["codec"] == "rowmask_binary"
        assert report["input_rows_replayed"] == 4
        assert report["semantic_comparisons"] == 4
        assert report["sparse_model_sha256"] == sparse.digest
        assert report["stored_parameter_count"] == sparse.stored_parameter_count



def test_three_independent_binary_codecs_reconstruct_and_replay_same_stateful_counter():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the independent implementation check")

    from types import SimpleNamespace

    from mailcpu.transition_space import (
        SparseTransitionReLUNetwork,
        compile_live_compositional_transition_program,
        two_bit_counter_program,
    )

    root = Path(__file__).resolve().parents[2]
    runner_path = root / "experiments" / "portable-realization-capsule" / "run_experiment.py"
    spec = importlib.util.spec_from_file_location(
        "prc_hybrid_stateful_fixture", runner_path
    )
    assert spec is not None and spec.loader is not None
    prc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prc)
    sre = prc.sre002

    def scalar_counter(inputs):
        state_1, state_0, advance, reset = inputs
        if reset:
            return (0, 0)
        if advance:
            return (state_1 ^ state_0, 1 - state_0)
        return (state_1, state_0)

    program = two_bit_counter_program()
    table = program.to_table()
    workload = SimpleNamespace(
        name=program.name,
        program=program,
        reference=scalar_counter,
    )
    input_rows = [tuple(row.inputs) for row in table.rows]
    expected_records = prc._expected_records(workload, table, input_rows)

    compiled_dense = compile_live_compositional_transition_program(program)

    # Add one output-disconnected dense ReLU feature as a codec branch probe.
    # Its outgoing column is exactly zero, so the transition function is unchanged.
    weights = [
        [list(row) for row in layer]
        for layer in compiled_dense.weights
    ]
    biases = [list(layer) for layer in compiled_dense.biases]
    weights[0].append([1.0] * compiled_dense.architecture[0])
    biases[0].append(0.0)
    for row in weights[1]:
        row.append(0.0)
    architecture = (
        compiled_dense.architecture[0],
        compiled_dense.architecture[1] + 1,
        *compiled_dense.architecture[2:],
    )
    dense = type(compiled_dense)(
        weights,
        biases,
        program_digest=program.digest,
        input_names=table.input_names,
        output_names=table.output_names,
        architecture=architecture,
    )

    sparse = SparseTransitionReLUNetwork.from_dense(dense)
    payload = sre.encode_hybrid_binary(sparse)
    inner_header_length = int.from_bytes(payload[:4], "little")
    inner_header = json.loads(payload[4:4 + inner_header_length])
    assert inner_header["schema"] == "sre002.hybrid-binary.v1"
    total_rows = sum(layer["output_width"] for layer in inner_header["layers"])
    sparse_rows = sum(layer["sparse_row_count"] for layer in inner_header["layers"])
    assert 0 < sparse_rows < total_rows, "fixture should exercise both adaptive row modes"

    compiler = "live_dag"
    encoders = {
        "rowmask_binary": (
            sre.encode_rowmask_binary,
            "sre002.rowmask-binary.v1",
        ),
        "csr_binary": (
            sre.encode_csr_binary,
            "sre002.csr-binary.v1",
        ),
        "hybrid_binary": (
            sre.encode_hybrid_binary,
            "sre002.hybrid-binary.v1",
        ),
    }

    horizon = 4
    control_pairs = tuple(itertools.product((0, 1), repeat=2))
    trajectories = []
    for initial in itertools.product((0, 1), repeat=2):
        for controls in itertools.product(control_pairs, repeat=horizon):
            state = tuple(initial)
            expected_states = []
            for advance, reset in controls:
                state = scalar_counter((*state, advance, reset))
                expected_states.append(list(state))
            trajectories.append({
                "initial_state": list(initial),
                "controls": [list(pair) for pair in controls],
                "expected_states": expected_states,
            })
    assert len(trajectories) == 4 * (4 ** horizon)

    script = Path(__file__).with_name("verify_capsule.mjs")
    reports = []
    payload_digests = set()
    last_capsule_path = None
    last_reference_path = None
    last_trajectory_path = None

    with tempfile.TemporaryDirectory() as directory:
        reference_path = Path(directory) / "two-bit-counter-reference.json"
        trajectory_path = Path(directory) / "two-bit-counter-trajectories.json"
        reference_path.write_text(
            json.dumps(expected_records, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        trajectory_path.write_text(
            json.dumps(trajectories, separators=(",", ":")),
            encoding="utf-8",
        )

        for encoding, (encoder, codec_schema) in encoders.items():
            payload = encoder(sparse)
            payload_digests.add(prc.bytes_digest(payload))
            contract = sre.contract_for(
                workload, table, compiler, encoding, dense, sparse, payload
            )
            case_records = []
            contract_digests = []
            for row_index, record in enumerate(expected_records):
                inputs = tuple(record["inputs"])
                expected = tuple(record["outputs"])
                dense_outputs = dense.predict(inputs)
                sparse_outputs = sparse.predict(inputs)
                assert dense_outputs == expected
                assert sparse_outputs == expected
                comparison = sre.compare_projected_observations(
                    contract,
                    case_payload={
                        "program_digest": program.digest,
                        "table_digest": table.digest,
                        "input_registers": dict(zip(table.input_names, inputs)),
                    },
                    source_observation=dict(zip(table.output_names, dense_outputs)),
                    target_observation=dict(zip(table.output_names, sparse_outputs)),
                )
                assert comparison.equivalent
                contract_digests.append(comparison.contract_digest)
                case_records.append({
                    "row_index": row_index,
                    "inputs": list(inputs),
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
                    "schema": codec_schema,
                    "payload_sha256": prc.bytes_digest(payload),
                },
                verification=receipt,
                toolchain=prc._toolchain(
                    "test-ifs-revision", "test-ecpu-revision", "test-vgi-revision"
                ),
            )

            capsule_path = Path(directory) / f"two-bit-counter-{encoding}.ifsp"
            capsule_path.write_bytes(capsule)
            result = subprocess.run(
                [
                    node, str(script), str(capsule_path),
                    "--reference", str(reference_path),
                    "--trajectories", str(trajectory_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"{encoding}: {result.stderr}"
            report = json.loads(result.stdout)
            assert report["valid"] is True
            assert report["codec"] == encoding
            assert report["input_rows_replayed"] == 16
            assert report["semantic_comparisons"] == 16
            assert report["sparse_model_sha256"] == sparse.digest
            assert report["stored_parameter_count"] == sparse.stored_parameter_count
            assert report["trajectory_count"] == 1024
            assert report["trajectory_steps"] == 4096
            if encoding == "hybrid_binary":
                assert report["sparse_row_count"] == sparse_rows
                assert report["dense_row_count"] == total_rows - sparse_rows
            reports.append(report)

            last_capsule_path = capsule_path
            last_reference_path = reference_path
            last_trajectory_path = trajectory_path

        assert len(payload_digests) == 3, "the three binary codecs must have distinct payload bytes"
        assert {report["sparse_model_sha256"] for report in reports} == {sparse.digest}
        assert {report["stored_parameter_count"] for report in reports} == {
            sparse.stored_parameter_count
        }
        assert {report["trajectory_count"] for report in reports} == {1024}
        assert {report["trajectory_steps"] for report in reports} == {4096}

        altered_trajectories = [dict(item) for item in trajectories]
        altered_trajectories[0] = dict(altered_trajectories[0])
        altered_trajectories[0]["expected_states"] = [
            list(state) for state in altered_trajectories[0]["expected_states"]
        ]
        altered_trajectories[0]["expected_states"][0][0] ^= 1
        last_trajectory_path.write_text(
            json.dumps(altered_trajectories, separators=(",", ":")),
            encoding="utf-8",
        )
        mismatch = subprocess.run(
            [
                node, str(script), str(last_capsule_path),
                "--reference", str(last_reference_path),
                "--trajectories", str(last_trajectory_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert mismatch.returncode != 0
        assert "trajectory reference" in mismatch.stderr or "recurrent trajectory" in mismatch.stderr

