"""Bind exact sparse model payloads to portable source and verification receipts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import statistics
import struct
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
SRE002_PATH = ROOT / "experiments" / "sparse-encoding-landscape" / "run_experiment.py"
SPEC = importlib.util.spec_from_file_location("sre002_codecs", SRE002_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load the pinned SRE-002 codec implementation")
sre002 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sre002)

from portable_realization import (
    MAGIC,
    PREFIX,
    PortableRealizationError,
    decode_capsule,
    encode_capsule,
)

ENCODING_SCHEMAS = {
    "coo_json": "mailcpu.sparse-transition-relu.v1",
    "csr_json": "sre002.csr-json.v1",
    "rowmask_json": "sre002.rowmask-json.v1",
    "csr_binary": "sre002.csr-binary.v1",
    "rowmask_binary": "sre002.rowmask-binary.v1",
    "hybrid_binary": "sre002.hybrid-binary.v1",
}
ENCODINGS = tuple(ENCODING_SCHEMAS)


def digest(value: Any) -> str:
    return sre002.sha(value)


def bytes_digest(value: bytes) -> str:
    return sre002.sha_bytes(value)


def verify_capsule_tampering(capsule: bytes) -> dict[str, bool]:
    header_size = PREFIX.unpack_from(capsule, 0)[2]
    header_start = PREFIX.size
    payload_start = header_start + header_size
    header_bytes = bytearray(capsule[header_start:payload_start])
    payload = bytearray(capsule[payload_start:])

    # Change a source revision within the header without recomputing its digest.
    needle = b'"repository":"Kier73/In-Formation-Space"'
    replacement = b'"repository":"Kier73/Altered-Information-Space"'
    if needle not in header_bytes:
        raise AssertionError("capsule header source repository anchor missing")
    altered_header = bytes(header_bytes).replace(needle, replacement, 1)
    header_probe = capsule[:header_start] + altered_header + bytes(payload)

    # Change one payload byte without updating the payload descriptor.
    if not payload:
        raise AssertionError("capsule payload unexpectedly empty")
    payload[0] ^= 0x01
    payload_probe = capsule[:payload_start] + bytes(payload)

    results = {}
    for name, candidate in (
        ("header_tamper_rejected", header_probe),
        ("payload_tamper_rejected", payload_probe),
    ):
        try:
            decode_capsule(candidate)
        except PortableRealizationError:
            results[name] = True
        else:
            results[name] = False
            raise AssertionError(f"{name} failed")
    return results


def _expected_records(workload: Any, table: Any, inputs: list[tuple[int, ...]]) -> list[dict[str, Any]]:
    records = []
    for values in inputs:
        expected = tuple(workload.reference(values))
        if workload.program.evaluate(values) != expected:
            raise AssertionError(
                f"independent scalar reference differs from typed program: {workload.name}/{values}"
            )
        if table.row_for(values).outputs != expected:
            raise AssertionError(
                f"independent scalar reference differs from transition table: {workload.name}/{values}"
            )
        records.append({
            "inputs": list(values),
            "outputs": list(expected),
        })
    return records


def _make_verification_receipt(
    workload: Any,
    table: Any,
    compiler: str,
    encoding: str,
    expected_records: list[dict[str, Any]],
    case_records: list[dict[str, Any]],
    contract_digests: list[str],
) -> dict[str, Any]:
    return {
        "status": "verified-within-complete-finite-domain",
        "verification_method": (
            "independent scalar reference + typed transition program + complete transition table "
            "+ dense/sparse execution + E-CPU Semantic TranslationContract"
        ),
        "input_row_count": len(expected_records),
        "output_domain": "finite_boolean",
        "reference_outputs_sha256": digest(expected_records),
        "case_evidence_sha256": digest(case_records),
        "translation_contracts_sha256": digest(contract_digests),
        "typed_program_digest": workload.program.digest,
        "transition_table_digest": table.digest,
        "workload_id": workload.name,
        "compiler_route": compiler,
        "codec": encoding,
    }


def _interface(table: Any, sparse: Any) -> dict[str, Any]:
    return {
        "input_names": list(table.input_names),
        "output_names": list(table.output_names),
        "architecture": list(sparse.architecture),
        "domain": {
            "kind": "finite_boolean",
            "input_width": len(table.input_names),
            "output_width": len(table.output_names),
            "transition": "one total next-state output for every Boolean input assignment",
        },
    }


def _source(workload: Any, sparse: Any, ifs_revision: str) -> dict[str, Any]:
    return {
        "repository": "Kier73/In-Formation-Space",
        "revision": ifs_revision,
        "kind": sparse.source_kind,
        "ground_digest": sparse.source_digest,
        "program_digest": workload.program.digest,
    }


def _realization(
    compiler: str,
    dense: Any,
    sparse: Any,
    ecpu_revision: str,
    encoding: str,
) -> dict[str, Any]:
    return {
        "repository": "Kier73/E-CPU",
        "revision": ecpu_revision,
        "compiler_route": compiler,
        "dense_model_digest": dense.digest,
        "sparse_model_digest": sparse.digest,
        "encoding": encoding,
    }


def _toolchain(ifs_revision: str, ecpu_revision: str, vgi_revision: str) -> dict[str, str]:
    return {
        "ifs_revision": ifs_revision,
        "ecpu_revision": ecpu_revision,
        "vgi_revision": vgi_revision,
    }


def _verify_decoded_capsule(
    capsule: bytes,
    *,
    workload: Any,
    table: Any,
    compiler: str,
    encoding: str,
    dense: Any,
    original_sparse: Any,
    decoder: Callable[[bytes], Any],
    original_payload: bytes,
    expected_records: list[dict[str, Any]],
    contract: Any,
) -> dict[str, Any]:
    header, payload = decode_capsule(capsule)
    if payload != original_payload:
        raise AssertionError("capsule payload bytes changed")
    if header["codec"]["name"] != encoding:
        raise AssertionError("capsule codec identity changed")
    if header["realization"]["compiler_route"] != compiler:
        raise AssertionError("capsule compiler identity changed")
    if header["realization"]["sparse_model_digest"] != original_sparse.digest:
        raise AssertionError("capsule sparse model identity changed")
    if header["source"]["program_digest"] != workload.program.digest:
        raise AssertionError("capsule source program identity changed")
    if header["interface"] != _interface(table, original_sparse):
        raise AssertionError("capsule interface changed")

    decoded_sparse = decoder(payload)
    if decoded_sparse.digest != original_sparse.digest:
        raise AssertionError("capsule codec decoder reconstructed a different sparse model")
    if decoded_sparse.source_digest != header["source"]["ground_digest"]:
        raise AssertionError("capsule source Ground digest does not match decoded model")
    if decoded_sparse.source_model_digest != header["realization"]["dense_model_digest"]:
        raise AssertionError("capsule dense model digest does not match decoded model")

    case_records: list[dict[str, Any]] = []
    contract_digests: list[str] = []
    for row_index, expected_record in enumerate(expected_records):
        inputs = tuple(expected_record["inputs"])
        expected = tuple(expected_record["outputs"])
        dense_output = dense.predict(inputs)
        restored_output = decoded_sparse.predict(inputs)
        if dense_output != expected or restored_output != expected:
            raise AssertionError(
                f"decoded capsule output mismatch for {workload.name}/{compiler}/{encoding}/{row_index}"
            )
        comparison = sre002.compare_projected_observations(
            contract,
            case_payload={
                "program_digest": workload.program.digest,
                "table_digest": table.digest,
                "input_registers": dict(zip(table.input_names, inputs)),
            },
            source_observation=dict(zip(table.output_names, dense_output)),
            target_observation=dict(zip(table.output_names, restored_output)),
        )
        if not comparison.equivalent:
            raise AssertionError("capsule restore failed semantic TranslationContract")
        contract_digests.append(comparison.contract_digest)
        case_records.append({
            "row_index": row_index,
            "inputs": list(inputs),
            "outputs": list(expected),
            "restored_outputs": list(restored_output),
            "translation_contract_digest": comparison.contract_digest,
        })

    evidence_digest = digest(case_records)
    if evidence_digest != header["verification"]["case_evidence_sha256"]:
        raise AssertionError("capsule verification receipt evidence digest mismatch")
    if digest(contract_digests) != header["verification"]["translation_contracts_sha256"]:
        raise AssertionError("capsule verification receipt contract digest mismatch")
    if len(case_records) != header["verification"]["input_row_count"]:
        raise AssertionError("capsule verification receipt row count mismatch")

    return {
        "decoded_sparse_digest": decoded_sparse.digest,
        "restored_input_rows": len(case_records),
        "restored_case_evidence_sha256": evidence_digest,
        "capsule_sha256": header["capsule_sha256"],
        "header_sha256": header["header_sha256"],
    }


def verify_workload(
    workload: Any,
    *,
    ifs_revision: str,
    ecpu_revision: str,
    vgi_revision: str,
) -> dict[str, Any]:
    program = workload.program
    table = program.to_table()
    inputs = [tuple(row.inputs) for row in table.rows]
    expected_records = _expected_records(workload, table, inputs)
    route_results = []

    for compiler, dense in sre002.compile_models(program, table).items():
        sparse = sre002.SparseTransitionReLUNetwork.from_dense(dense)
        encoding_results = []

        for encoding, (payload, decoder, _encoder) in sre002.codec_table(sparse).items():
            if encoding not in ENCODING_SCHEMAS:
                raise AssertionError(f"unregistered codec schema: {encoding}")

            decoded_sparse = decoder(payload)
            if decoded_sparse.digest != sparse.digest:
                raise AssertionError("codec did not reconstruct the exact sparse model")
            contract = sre002.contract_for(
                workload, table, compiler, encoding, dense, decoded_sparse, payload
            )

            case_records: list[dict[str, Any]] = []
            contract_digests: list[str] = []
            for row_index, expected_record in enumerate(expected_records):
                inputs_tuple = tuple(expected_record["inputs"])
                expected = tuple(expected_record["outputs"])
                dense_output = dense.predict(inputs_tuple)
                sparse_output = decoded_sparse.predict(inputs_tuple)
                if dense_output != expected or sparse_output != expected:
                    raise AssertionError(
                        f"pre-capsule semantic mismatch: {workload.name}/{compiler}/{encoding}/{row_index}"
                    )
                comparison = sre002.compare_projected_observations(
                    contract,
                    case_payload={
                        "program_digest": program.digest,
                        "table_digest": table.digest,
                        "input_registers": dict(zip(table.input_names, inputs_tuple)),
                    },
                    source_observation=dict(zip(table.output_names, dense_output)),
                    target_observation=dict(zip(table.output_names, sparse_output)),
                )
                if not comparison.equivalent:
                    raise AssertionError("pre-capsule Semantic TranslationContract failed")
                contract_digests.append(comparison.contract_digest)
                case_records.append({
                    "row_index": row_index,
                    "inputs": list(inputs_tuple),
                    "outputs": list(expected),
                    "sparse_outputs": list(sparse_output),
                    "translation_contract_digest": comparison.contract_digest,
                })

            receipt = _make_verification_receipt(
                workload, table, compiler, encoding,
                expected_records, case_records, contract_digests,
            )
            capsule = encode_capsule(
                payload,
                source=_source(workload, decoded_sparse, ifs_revision),
                realization=_realization(
                    compiler, dense, decoded_sparse, ecpu_revision, encoding
                ),
                interface=_interface(table, decoded_sparse),
                codec={
                    "name": encoding,
                    "schema": ENCODING_SCHEMAS[encoding],
                    "payload_sha256": bytes_digest(payload),
                },
                verification=receipt,
                toolchain=_toolchain(ifs_revision, ecpu_revision, vgi_revision),
            )

            capsule_header, _ = decode_capsule(capsule)
            tamper = verify_capsule_tampering(capsule)
            restored = _verify_decoded_capsule(
                capsule,
                workload=workload,
                table=table,
                compiler=compiler,
                encoding=encoding,
                dense=dense,
                original_sparse=sparse,
                decoder=decoder,
                original_payload=payload,
                expected_records=expected_records,
                contract=contract,
            )
            header_size = PREFIX.unpack_from(capsule, 0)[2]
            overhead = len(capsule) - len(payload)

            encode_start = time.perf_counter_ns()
            encode_capsule(
                payload,
                source=_source(workload, decoded_sparse, ifs_revision),
                realization=_realization(
                    compiler, dense, decoded_sparse, ecpu_revision, encoding
                ),
                interface=_interface(table, decoded_sparse),
                codec={
                    "name": encoding,
                    "schema": ENCODING_SCHEMAS[encoding],
                    "payload_sha256": bytes_digest(payload),
                },
                verification=receipt,
                toolchain=_toolchain(ifs_revision, ecpu_revision, vgi_revision),
            )
            encode_ns = time.perf_counter_ns() - encode_start

            decode_samples: list[int] = []
            for _ in range(5):
                started = time.perf_counter_ns()
                decode_capsule(capsule)
                decode_samples.append(time.perf_counter_ns() - started)

            encoding_results.append({
                "encoding": encoding,
                "codec_schema": ENCODING_SCHEMAS[encoding],
                "inner_payload_bytes": len(payload),
                "capsule_bytes": len(capsule),
                "metadata_overhead_bytes": overhead,
                "header_json_bytes": header_size,
                "metadata_overhead_fraction": overhead / len(capsule),
                "inner_payload_sha256": bytes_digest(payload),
                "capsule_sha256": capsule_header["capsule_sha256"],
                "header_sha256": capsule_header["header_sha256"],
                "sparse_model_digest": decoded_sparse.digest,
                "verification_receipt_sha256": capsule_header["verification"]["receipt_sha256"],
                "verification_rows": restored["restored_input_rows"],
                "pre_capsule_semantic_comparisons": len(case_records),
                "post_capsule_semantic_comparisons": restored["restored_input_rows"],
                "case_evidence_sha256": restored["restored_case_evidence_sha256"],
                "header_tamper_rejected": tamper["header_tamper_rejected"],
                "payload_tamper_rejected": tamper["payload_tamper_rejected"],
                "capsule_encode_time_ns": encode_ns,
                "capsule_decode_timing": {
                    "sample_count": len(decode_samples),
                    "samples_ns": decode_samples,
                    "median_ns": int(statistics.median(decode_samples)),
                    "minimum_ns": min(decode_samples),
                    "maximum_ns": max(decode_samples),
                },
            })

        route_results.append({
            "compiler": compiler,
            "dense_model_digest": dense.digest,
            "sparse_model_digest": sparse.digest,
            "architecture": list(sparse.architecture),
            "source_ground_digest": sparse.source_digest,
            "input_width": len(table.input_names),
            "output_width": len(table.output_names),
            "complete_domain_rows": len(expected_records),
            "encodings": encoding_results,
        })

    return {
        "workload": workload.name,
        "family": workload.family,
        "program_digest": program.digest,
        "table_digest": table.digest,
        "complete_domain_rows": len(expected_records),
        "compiler_routes": route_results,
        "capsule_count": sum(len(item["encodings"]) for item in route_results),
        "pre_capsule_comparisons": (
            len(expected_records) * len(route_results) * len(ENCODINGS)
        ),
        "post_capsule_comparisons": (
            len(expected_records) * len(route_results) * len(ENCODINGS)
        ),
        "all_capsules_round_trip_and_replay_exactly": True,
    }


def run_experiment() -> dict[str, Any]:
    workloads = sre002.rcn.build_workloads()
    ifs_revision = os.environ.get("IFS_REVISION", "unspecified-local-checkout")
    ecpu_revision = os.environ.get("ECPU_REVISION", "unspecified-local-checkout")
    vgi_revision = os.environ.get("VGI_REVISION", "unspecified-local-checkout")

    results = [
        verify_workload(
            workload,
            ifs_revision=ifs_revision,
            ecpu_revision=ecpu_revision,
            vgi_revision=vgi_revision,
        )
        for workload in workloads
    ]
    encoding_records = [
        {
            **encoding,
            "workload": workload["workload"],
            "family": workload["family"],
            "compiler": route["compiler"],
        }
        for workload in results
        for route in workload["compiler_routes"]
        for encoding in route["encodings"]
    ]

    summaries = {}
    for encoding in ENCODINGS:
        selected = [item for item in encoding_records if item["encoding"] == encoding]
        inner = sum(item["inner_payload_bytes"] for item in selected)
        capsules = sum(item["capsule_bytes"] for item in selected)
        overhead = sum(item["metadata_overhead_bytes"] for item in selected)
        summaries[encoding] = {
            "capsule_count": len(selected),
            "inner_payload_bytes_sum": inner,
            "metadata_overhead_bytes_sum": overhead,
            "capsule_bytes_sum": capsules,
            "metadata_overhead_fraction": overhead / capsules if capsules else 0.0,
            "median_capsule_encode_ns": int(statistics.median(
                item["capsule_encode_time_ns"] for item in selected
            )),
            "median_capsule_decode_ns": int(statistics.median(
                item["capsule_decode_timing"]["median_ns"] for item in selected
            )),
            "header_tamper_rejections": sum(item["header_tamper_rejected"] for item in selected),
            "payload_tamper_rejections": sum(item["payload_tamper_rejected"] for item in selected),
            "capsules_with_complete_replay": sum(
                item["verification_rows"] == next(
                    workload["complete_domain_rows"]
                    for workload in results
                    if workload["workload"] == item["workload"]
                )
                for item in selected
            ),
        }

    capsule_count = sum(item["capsule_count"] for item in results)
    pre_comparisons = sum(item["pre_capsule_comparisons"] for item in results)
    post_comparisons = sum(item["post_capsule_comparisons"] for item in results)
    output = {
        "schema": "in-formation-space.portable-realization-capsules.prc001.v1",
        "experiment_id": "PRC-001",
        "status": "verified-within-complete-finite-domains",
        "source_revisions": {
            "ifs": ifs_revision,
            "ecpu": ecpu_revision,
            "vgi": vgi_revision,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "clock": {
                "implementation": time.get_clock_info("perf_counter").implementation,
                "monotonic": time.get_clock_info("perf_counter").monotonic,
                "resolution": time.get_clock_info("perf_counter").resolution,
            },
        },
        "workload_count": len(results),
        "complete_input_rows_verified": sum(item["complete_domain_rows"] for item in results),
        "compiler_model_pairs": sum(len(item["compiler_routes"]) for item in results),
        "encoding_count": len(ENCODINGS),
        "capsule_count": capsule_count,
        "pre_capsule_semantic_comparisons": pre_comparisons,
        "post_capsule_semantic_comparisons": post_comparisons,
        "total_semantic_comparisons": pre_comparisons + post_comparisons,
        "all_capsules_round_trip_and_replay_exactly": all(
            item["all_capsules_round_trip_and_replay_exactly"] for item in results
        ),
        "all_header_tampering_rejected": all(
            item["header_tamper_rejected"] for item in encoding_records
        ),
        "all_payload_tampering_rejected": all(
            item["payload_tamper_rejected"] for item in encoding_records
        ),
        "encoding_summaries": summaries,
        "capsule_evidence_digest": digest(encoding_records),
        "limitations": [
            "Verification is limited to the 16 selected RCN-001 workloads and their complete finite Boolean domains.",
            "The capsule binds payload bytes to source/model/interface/codec/toolchain/receipt metadata; it does not execute the contained model by itself.",
            "SHA-256 provides corruption and identity checks, not author authentication, authorization, or a digital signature.",
            "The verification receipt is an experiment record that is replayed by this runner; it is not a formal proof certificate.",
            "Capsules are not yet integrated into E-CPU communication, admission, durable storage, or remote execution.",
            "Header and capsule byte measurements are file-format sizes, not network throughput or resident memory.",
            "VGI is pinned as experiment context; the realization payload and executable decoder are currently E-CPU artifacts.",
        ],
        "workloads": results,
    }
    output["result_digest"] = digest(output)
    return output


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_experiment()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "experiment_id": result["experiment_id"],
        "status": result["status"],
        "workloads": result["workload_count"],
        "input_rows": result["complete_input_rows_verified"],
        "capsules": result["capsule_count"],
        "semantic_comparisons": result["total_semantic_comparisons"],
        "header_tamper_rejections": sum(v["header_tamper_rejections"] for v in result["encoding_summaries"].values()),
        "payload_tamper_rejections": sum(v["payload_tamper_rejections"] for v in result["encoding_summaries"].values()),
        "result_digest": result["result_digest"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
