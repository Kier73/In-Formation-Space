"""Compare compressed standalone capsules with shared-provenance bundles."""

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
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[2]
PRC001_DIR = ROOT / "experiments" / "portable-realization-capsule"
if str(PRC001_DIR) not in sys.path:
    sys.path.insert(0, str(PRC001_DIR))
PRC001_PATH = PRC001_DIR / "run_experiment.py"
SPEC = importlib.util.spec_from_file_location("prc001_reference", PRC001_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not import the verified PRC-001 capsule implementation")
prc001 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prc001)

from compact_provenance import (
    BUNDLE_MAGIC,
    BUNDLE_PREFIX,
    ENTRY_PREFIX,
    COMPRESSED_MAGIC,
    COMPRESSED_PREFIX,
    CompactProvenanceError,
    decode_bundle,
    decode_compressed_capsule,
    encode_bundle,
    encode_compressed_capsule,
)

sre002 = prc001.sre002
ENCODINGS = tuple(sre002.ENCODINGS)
TIMING_REPEATS = 3


def digest(value: Any) -> str:
    return sre002.sha(value)


def _measure(function: Callable[[], Any], repeats: int = TIMING_REPEATS) -> dict[str, Any]:
    first = function()
    samples = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        result = function()
        samples.append(time.perf_counter_ns() - started)
        if isinstance(first, bytes):
            if result != first:
                raise AssertionError("codec output changed between timing samples")
        else:
            if result != first:
                raise AssertionError("codec result changed between timing samples")
    return {
        "sample_count": len(samples),
        "samples_ns": samples,
        "median_ns": int(statistics.median(samples)),
        "minimum_ns": min(samples),
        "maximum_ns": max(samples),
    }


def _tamper_compressed_capsule(compact: bytes) -> dict[str, bool]:
    _, _, _, compressed_length = COMPRESSED_PREFIX.unpack_from(compact, 0)
    compressed_start = COMPRESSED_PREFIX.size
    payload_start = compressed_start + compressed_length
    if compressed_length <= 0 or payload_start >= len(compact):
        raise AssertionError("compressed standalone capsule framing is incomplete")

    header_probe = bytearray(compact)
    header_probe[compressed_start] ^= 0xFF
    payload_probe = bytearray(compact)
    payload_probe[payload_start] ^= 0x01

    checks = {}
    for label, candidate in (
        ("compressed_header_tamper_rejected", bytes(header_probe)),
        ("compressed_payload_tamper_rejected", bytes(payload_probe)),
    ):
        try:
            decode_compressed_capsule(candidate)
        except CompactProvenanceError:
            checks[label] = True
        else:
            raise AssertionError(f"{label} probe was accepted")
    return checks


def _tamper_bundle(bundle: bytes) -> dict[str, bool]:
    def must_reject(label: str, candidate: bytes) -> None:
        try:
            decode_bundle(candidate)
        except CompactProvenanceError:
            checks[label] = True
        else:
            raise AssertionError(f"bundle tampering probe {label} was accepted")

    checks: dict[str, bool] = {}

    outer = bytearray(bundle)
    outer[-1] ^= 0x01
    must_reject("bundle_outer_digest_rejected", bytes(outer))

    magic, version, manifest_length, count = BUNDLE_PREFIX.unpack_from(bundle, 0)
    cursor = BUNDLE_PREFIX.size
    manifest_end = cursor + manifest_length
    manifest = bundle[cursor:manifest_end]
    if count < 1:
        raise AssertionError("global bundle unexpectedly contains no capsules")
    cursor = manifest_end
    header_length, payload_length = ENTRY_PREFIX.unpack_from(bundle, cursor)
    header_start = cursor + ENTRY_PREFIX.size
    header_end = header_start + header_length
    header = bundle[header_start:header_end]
    payload_start = header_end

    if b"minterm" not in header:
        raise AssertionError("bundle entry header compiler anchor missing")
    changed_header = header.replace(b"minterm", b"evilxxx", 1)
    if len(changed_header) != len(header):
        raise AssertionError("bundle entry header tamper was not length preserving")
    header_probe = bytearray(bundle)
    header_probe[header_start:header_end] = changed_header
    header_probe = header_probe[:-32] + hashlib.sha256(header_probe[:-32]).digest()
    must_reject("bundle_entry_header_rejected", bytes(header_probe))

    payload_probe = bytearray(bundle)
    payload_probe[payload_start] ^= 0x01
    payload_probe = payload_probe[:-32] + hashlib.sha256(payload_probe[:-32]).digest()
    must_reject("bundle_entry_payload_rejected", bytes(payload_probe))

    source_anchor = b"Kier73/In-Formation-Space"
    source_replacement = b"Kier73/No-Formation-Space"
    if source_anchor not in manifest:
        raise AssertionError("bundle manifest source anchor missing")
    changed_manifest = manifest.replace(source_anchor, source_replacement, 1)
    manifest_probe = bytearray(bundle)
    manifest_probe[cursor:manifest_end] = changed_manifest
    manifest_probe = manifest_probe[:-32] + hashlib.sha256(manifest_probe[:-32]).digest()
    must_reject("bundle_manifest_rejected", bytes(manifest_probe))

    return checks


def _build_raw_capsule(
    workload: Any,
    table: Any,
    compiler: str,
    encoding: str,
    dense: Any,
    sparse: Any,
    payload: bytes,
    expected_records: list[dict[str, Any]],
    contract: Any,
    *,
    ifs_revision: str,
    ecpu_revision: str,
    vgi_revision: str,
) -> tuple[bytes, dict[str, Any]]:
    contract_digests: list[str] = []
    case_records: list[dict[str, Any]] = []
    for row_index, expected_record in enumerate(expected_records):
        inputs = tuple(expected_record["inputs"])
        expected = tuple(expected_record["outputs"])
        dense_output = dense.predict(inputs)
        sparse_output = sparse.predict(inputs)
        if dense_output != expected or sparse_output != expected:
            raise AssertionError(
                f"pre-capsule result differs: {workload.name}/{compiler}/{encoding}/{row_index}"
            )
        comparison = sre002.compare_projected_observations(
            contract,
            case_payload={
                "program_digest": workload.program.digest,
                "table_digest": table.digest,
                "input_registers": dict(zip(table.input_names, inputs)),
            },
            source_observation=dict(zip(table.output_names, dense_output)),
            target_observation=dict(zip(table.output_names, sparse_output)),
        )
        if not comparison.equivalent:
            raise AssertionError("pre-capsule semantic TranslationContract failed")
        contract_digests.append(comparison.contract_digest)
        case_records.append({
            "row_index": row_index,
            "inputs": list(inputs),
            "outputs": list(expected),
            "restored_outputs": list(sparse_output),
            "translation_contract_digest": comparison.contract_digest,
        })

    receipt = prc001._make_verification_receipt(
        workload,
        table,
        compiler,
        encoding,
        expected_records,
        case_records,
        contract_digests,
    )
    raw = prc001.encode_capsule(
        payload,
        source=prc001._source(workload, sparse, ifs_revision),
        realization=prc001._realization(compiler, dense, sparse, ecpu_revision, encoding),
        interface=prc001._interface(table, sparse),
        codec={
            "name": encoding,
            "schema": prc001.ENCODING_SCHEMAS[encoding],
            "payload_sha256": sre002.sha_bytes(payload),
        },
        verification=receipt,
        toolchain=prc001._toolchain(ifs_revision, ecpu_revision, vgi_revision),
    )
    return raw, {
        "case_evidence_sha256": digest(case_records),
        "translation_contracts_sha256": digest(contract_digests),
        "pre_capsule_comparisons": len(case_records),
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
    expected_records = prc001._expected_records(workload, table, inputs)
    route_results = []
    raw_records: list[dict[str, Any]] = []

    for compiler, dense in sre002.compile_models(program, table).items():
        sparse = sre002.SparseTransitionReLUNetwork.from_dense(dense)
        enc_results = []

        for encoding, (payload, decoder, _encoder) in sre002.codec_table(sparse).items():
            decoded_sparse = decoder(payload)
            if decoded_sparse.digest != sparse.digest:
                raise AssertionError("SRE-002 codec did not reconstruct sparse source model")
            contract = sre002.contract_for(
                workload, table, compiler, encoding, dense, decoded_sparse, payload
            )
            raw, initial_evidence = _build_raw_capsule(
                workload,
                table,
                compiler,
                encoding,
                dense,
                decoded_sparse,
                payload,
                expected_records,
                contract,
                ifs_revision=ifs_revision,
                ecpu_revision=ecpu_revision,
                vgi_revision=vgi_revision,
            )
            raw_header, raw_payload = prc001.decode_capsule(raw)
            if raw_payload != payload:
                raise AssertionError("standalone capsule changed its inner codec payload")

            compressed = encode_compressed_capsule(raw)
            restored_raw = decode_compressed_capsule(compressed)
            if restored_raw != raw:
                raise AssertionError("compressed standalone capsule did not restore exact PRC-001 bytes")
            replay = prc001._verify_decoded_capsule(
                restored_raw,
                workload=workload,
                table=table,
                compiler=compiler,
                encoding=encoding,
                dense=dense,
                original_sparse=decoded_sparse,
                decoder=decoder,
                original_payload=payload,
                expected_records=expected_records,
                contract=contract,
            )
            tamper = _tamper_compressed_capsule(compressed)

            raw_header_length = prc001.PREFIX.unpack_from(raw, 0)[2]
            compressed_header_length = COMPRESSED_PREFIX.unpack_from(compressed, 0)[3]
            compressed_prefix_bytes = COMPRESSED_PREFIX.size
            saved_bytes = len(raw) - len(compressed)

            compression_encode = _measure(lambda raw_item=raw: encode_compressed_capsule(raw_item))
            compression_decode = _measure(lambda compact=compressed: decode_compressed_capsule(compact))

            record = {
                "workload": workload.name,
                "family": workload.family,
                "compiler": compiler,
                "encoding": encoding,
                "raw_capsule_bytes": len(raw),
                "compressed_capsule_bytes": len(compressed),
                "raw_header_bytes": raw_header_length,
                "compressed_header_bytes": compressed_header_length,
                "compressed_framing_bytes": compressed_prefix_bytes,
                "compression_saved_bytes": saved_bytes,
                "compression_reduction_fraction": saved_bytes / len(raw) if raw else 0.0,
                "compressed_sha256": sre002.sha_bytes(compressed),
                "raw_capsule_sha256": raw_header["capsule_sha256"],
                "compressed_restore_capsule_sha256": replay["capsule_sha256"],
                "standalone_complete_replay_rows": replay["restored_input_rows"],
                "standalone_pre_capsule_comparisons": initial_evidence["pre_capsule_comparisons"],
                "standalone_post_compression_comparisons": replay["restored_input_rows"],
                "case_evidence_sha256": replay["restored_case_evidence_sha256"],
                **tamper,
                "compression_encode_timing": compression_encode,
                "compression_decode_timing": compression_decode,
            }
            enc_results.append(record)
            raw_records.append({
                "raw_capsule": raw,
                "record": record,
                "workload": workload.name,
                "compiler": compiler,
                "encoding": encoding,
            })

        route_results.append({
            "compiler": compiler,
            "dense_model_digest": dense.digest,
            "sparse_model_digest": sparse.digest,
            "complete_domain_rows": len(expected_records),
            "encodings": enc_results,
        })

    return {
        "workload": workload.name,
        "family": workload.family,
        "program_digest": program.digest,
        "table_digest": table.digest,
        "complete_domain_rows": len(expected_records),
        "compiler_routes": route_results,
        "capsule_count": len(raw_records),
        "pre_capsule_semantic_comparisons": (
            len(expected_records) * len(route_results) * len(ENCODINGS)
        ),
        "post_compression_semantic_comparisons": (
            len(expected_records) * len(route_results) * len(ENCODINGS)
        ),
        "all_compressed_capsules_replayed_exactly": True,
        "_raw_records": raw_records,
    }


def run_experiment() -> dict[str, Any]:
    ifs_revision = os.environ.get("IFS_REVISION", "unspecified-local-checkout")
    ecpu_revision = os.environ.get("ECPU_REVISION", "unspecified-local-checkout")
    vgi_revision = os.environ.get("VGI_REVISION", "unspecified-local-checkout")

    workload_results = [
        verify_workload(
            workload,
            ifs_revision=ifs_revision,
            ecpu_revision=ecpu_revision,
            vgi_revision=vgi_revision,
        )
        for workload in sre002.rcn.build_workloads()
    ]
    raw_records = [
        item
        for workload in workload_results
        for item in workload["_raw_records"]
    ]
    raw_capsules = [item["raw_capsule"] for item in raw_records]
    records = [item["record"] for item in raw_records]

    encoding_summaries = {}
    per_encoding_bundles = {}
    per_encoding_bundle_checks = {}
    for encoding in ENCODINGS:
        selected = [
            item for item in raw_records if item["encoding"] == encoding
        ]
        selected_raw = [item["raw_capsule"] for item in selected]
        raw_total = sum(len(item) for item in selected_raw)
        compressed_total = sum(item["record"]["compressed_capsule_bytes"] for item in selected)

        bundle_start = time.perf_counter_ns()
        bundle = encode_bundle(selected_raw)
        bundle_encode_ns = time.perf_counter_ns() - bundle_start
        decode_start = time.perf_counter_ns()
        manifest, restored = decode_bundle(bundle)
        bundle_decode_ns = time.perf_counter_ns() - decode_start
        if restored != selected_raw:
            raise AssertionError(f"per-encoding bundle changed standalone capsules: {encoding}")

        per_encoding_bundles[encoding] = bundle
        per_encoding_bundle_checks[encoding] = {
            "manifest_sha256": manifest["manifest_sha256"],
            "entry_count": len(restored),
            "byte_identical_capsule_reconstructions": len(restored),
            "bundle_sha256": sre002.sha_bytes(bundle),
            "bundle_encode_time_ns": bundle_encode_ns,
            "bundle_decode_time_ns": bundle_decode_ns,
        }
        encoding_summaries[encoding] = {
            "capsule_count": len(selected),
            "raw_standalone_bytes_sum": raw_total,
            "compressed_standalone_bytes_sum": compressed_total,
            "compressed_standalone_saved_bytes": raw_total - compressed_total,
            "compressed_standalone_reduction_fraction": (
                (raw_total - compressed_total) / raw_total if raw_total else 0.0
            ),
            "raw_header_bytes_sum": sum(item["record"]["raw_header_bytes"] for item in selected),
            "compressed_header_bytes_sum": sum(item["record"]["compressed_header_bytes"] for item in selected),
            "per_encoding_bundle_bytes": len(bundle),
            "bundle_manifest_and_entry_overhead_bytes": len(bundle) - sum(
                prc001.decode_capsule(item)[1].__len__() for item in selected_raw
            ),
            "bundle_saved_vs_raw_standalone_bytes": raw_total - len(bundle),
            "bundle_reduction_vs_raw_standalone": (
                (raw_total - len(bundle)) / raw_total if raw_total else 0.0
            ),
            "bundle_saved_vs_compressed_standalone_bytes": compressed_total - len(bundle),
            "bundle_reduction_vs_compressed_standalone": (
                (compressed_total - len(bundle)) / compressed_total if compressed_total else 0.0
            ),
            **per_encoding_bundle_checks[encoding],
            "median_compress_encode_ns": int(statistics.median(
                item["record"]["compression_encode_timing"]["median_ns"] for item in selected
            )),
            "median_compress_decode_ns": int(statistics.median(
                item["record"]["compression_decode_timing"]["median_ns"] for item in selected
            )),
            "compressed_header_tamper_rejections": sum(
                item["record"]["compressed_header_tamper_rejected"] for item in selected
            ),
            "compressed_payload_tamper_rejections": sum(
                item["record"]["compressed_payload_tamper_rejected"] for item in selected
            ),
        }

    global_bundle_start = time.perf_counter_ns()
    global_bundle = encode_bundle(raw_capsules)
    global_bundle_encode_ns = time.perf_counter_ns() - global_bundle_start
    global_decode_start = time.perf_counter_ns()
    global_manifest, global_restored = decode_bundle(global_bundle)
    global_bundle_decode_ns = time.perf_counter_ns() - global_decode_start
    if global_restored != raw_capsules:
        raise AssertionError("global bundle did not reconstruct every standalone capsule")
    global_tamper = _tamper_bundle(global_bundle)

    total_raw = sum(len(item) for item in raw_capsules)
    total_compressed = sum(item["record"]["compressed_capsule_bytes"] for item in raw_records)
    total_payload = sum(
        len(prc001.decode_capsule(item)[1]) for item in raw_capsules
    )
    total_bundle_metadata = len(global_bundle) - total_payload

    total_pre = sum(item["pre_capsule_semantic_comparisons"] for item in workload_results)
    total_post = sum(item["post_compression_semantic_comparisons"] for item in workload_results)

    result = {
        "schema": "in-formation-space.compact-provenance-bundles.cpb001.v1",
        "experiment_id": "CPB-001",
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
            "compression": "zlib header compression level 9; exact canonical JSON content",
            "timing_repeats": TIMING_REPEATS,
        },
        "workload_count": len(workload_results),
        "complete_input_rows_verified": sum(item["complete_domain_rows"] for item in workload_results),
        "compiler_model_pairs": sum(len(item["compiler_routes"]) for item in workload_results),
        "encoding_count": len(ENCODINGS),
        "capsule_count": len(raw_capsules),
        "pre_capsule_semantic_comparisons": total_pre,
        "post_compression_semantic_comparisons": total_post,
        "total_semantic_comparisons": total_pre + total_post,
        "compressed_capsules_restore_exact_standalone_bytes": all(
            item["record"]["raw_capsule_sha256"] == item["record"]["compressed_restore_capsule_sha256"]
            for item in raw_records
        ),
        "compressed_header_tampering_rejected": all(
            item["record"]["compressed_header_tamper_rejected"] for item in raw_records
        ),
        "compressed_payload_tampering_rejected": all(
            item["record"]["compressed_payload_tamper_rejected"] for item in raw_records
        ),
        "per_encoding_summaries": encoding_summaries,
        "global_bundle": {
            "capsule_count": len(global_restored),
            "bundle_bytes": len(global_bundle),
            "standalone_raw_bytes_sum": total_raw,
            "compressed_standalone_bytes_sum": total_compressed,
            "inner_payload_bytes_sum": total_payload,
            "shared_manifest_and_entry_overhead_bytes": total_bundle_metadata,
            "bundle_saved_vs_raw_standalone_bytes": total_raw - len(global_bundle),
            "bundle_reduction_vs_raw_standalone": (
                (total_raw - len(global_bundle)) / total_raw if total_raw else 0.0
            ),
            "bundle_saved_vs_compressed_standalone_bytes": total_compressed - len(global_bundle),
            "bundle_reduction_vs_compressed_standalone": (
                (total_compressed - len(global_bundle)) / total_compressed if total_compressed else 0.0
            ),
            "manifest_sha256": global_manifest["manifest_sha256"],
            "bundle_sha256": sre002.sha_bytes(global_bundle),
            "byte_identical_capsule_reconstructions": len(global_restored),
            "bundle_encode_time_ns": global_bundle_encode_ns,
            "bundle_decode_time_ns": global_bundle_decode_ns,
            **global_tamper,
        },
        "capsule_evidence_digest": digest(records),
        "limitations": [
            "Verification is limited to the 16 selected RCN-001 workloads and their complete finite Boolean domains.",
            "Zlib header compression preserves exact canonical JSON metadata and the exact inner codec payload; compressed output bytes may vary across zlib implementations/versions.",
            "Shared-manifest bundles are portable as bundles; an extracted local entry requires its referenced manifest to reconstruct its standalone capsule.",
            "Bundle decoding reconstructs byte-identical PRC-001 capsules whose verification receipts were replayed in this run.",
            "SHA-256 provides integrity and identity checks, not author authentication, authorization, or digital signatures.",
            "The bundle is not integrated into E-CPU transport, admission, durable storage, or remote execution.",
            "Payload/header/bundle bytes are serialization sizes, not resident memory or network throughput.",
        ],
        "workloads": [
            {key: value for key, value in item.items() if key != "_raw_records"}
            for item in workload_results
        ],
    }
    result["result_digest"] = digest(result)
    return result


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
        "capsules": result["capsule_count"],
        "workloads": result["workload_count"],
        "input_rows": result["complete_input_rows_verified"],
        "semantic_comparisons": result["total_semantic_comparisons"],
        "global_bundle_bytes": result["global_bundle"]["bundle_bytes"],
        "compressed_header_tamper_rejections": sum(
            summary["compressed_header_tamper_rejections"]
            for summary in result["per_encoding_summaries"].values()
        ),
        "compressed_payload_tamper_rejections": sum(
            summary["compressed_payload_tamper_rejections"]
            for summary in result["per_encoding_summaries"].values()
        ),
        "result_digest": result["result_digest"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
