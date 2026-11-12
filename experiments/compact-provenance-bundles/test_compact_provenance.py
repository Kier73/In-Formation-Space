from __future__ import annotations

import hashlib

import pytest

from portable_realization import encode_capsule
from compact_provenance import (
    BUNDLE_MAGIC,
    BUNDLE_PREFIX,
    ENTRY_PREFIX,
    COMPRESSED_PREFIX,
    CompactProvenanceError,
    decode_bundle,
    decode_compressed_capsule,
    encode_bundle,
    encode_compressed_capsule,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _capsule(index: int, encoding: str = "rowmask_binary", *, ecpu_revision: str = "ecpu-r1") -> bytes:
    payload = b"exact-payload-" + str(index).encode("ascii")
    program_digest = f"{index:064x}"
    receipt = {
        "status": "verified-within-complete-finite-domain",
        "verification_method": "test complete Boolean domain replay",
        "input_row_count": 4,
        "output_domain": "finite_boolean",
        "reference_outputs_sha256": f"{index + 1:064x}",
        "case_evidence_sha256": f"{index + 2:064x}",
        "translation_contracts_sha256": f"{index + 3:064x}",
        "typed_program_digest": program_digest,
        "transition_table_digest": f"{index + 4:064x}",
        "workload_id": f"ground-{index}",
        "compiler_route": "live_dag",
        "codec": encoding,
    }
    return encode_capsule(
        payload,
        source={
            "repository": "Kier73/In-Formation-Space",
            "revision": "ifs-r1",
            "kind": "transition_program",
            "ground_digest": f"{index + 5:064x}",
            "program_digest": program_digest,
        },
        realization={
            "repository": "Kier73/E-CPU",
            "revision": ecpu_revision,
            "compiler_route": "live_dag",
            "dense_model_digest": f"{index + 6:064x}",
            "sparse_model_digest": f"{index + 7:064x}",
            "encoding": encoding,
        },
        interface={
            "input_names": ["a", "b"],
            "output_names": ["next"],
            "architecture": [2, 3, 1],
            "domain": {"kind": "finite_boolean", "input_width": 2, "output_width": 1},
        },
        codec={
            "name": encoding,
            "schema": f"test-schema-{encoding}",
            "payload_sha256": _sha(payload),
        },
        verification=receipt,
        toolchain={
            "ifs_revision": "ifs-r1",
            "ecpu_revision": ecpu_revision,
            "vgi_revision": "vgi-r1",
        },
    )


def _refresh_bundle_digest(data: bytearray) -> bytes:
    return bytes(data[:-32]) + hashlib.sha256(data[:-32]).digest()


def test_compressed_standalone_capsule_round_trip_and_size_reduction():
    raw = _capsule(1)
    compact = encode_compressed_capsule(raw)
    restored = decode_compressed_capsule(compact)

    assert restored == raw
    assert len(compact) < len(raw)


def test_compressed_capsule_rejects_header_and_payload_changes():
    raw = _capsule(2)
    compact = encode_compressed_capsule(raw)
    magic, version, raw_len, compressed_len = COMPRESSED_PREFIX.unpack_from(compact, 0)
    compressed_start = COMPRESSED_PREFIX.size
    payload_start = compressed_start + compressed_len

    bad_header = bytearray(compact)
    bad_header[compressed_start + compressed_len // 2] ^= 0x01
    with pytest.raises(CompactProvenanceError):
        decode_compressed_capsule(bytes(bad_header))

    bad_payload = bytearray(compact)
    bad_payload[-1] ^= 0x01
    with pytest.raises(CompactProvenanceError):
        decode_compressed_capsule(bytes(bad_payload))


def test_bundle_round_trip_reconstructs_independent_standalone_capsules():
    capsules = [
        _capsule(10, "rowmask_binary"),
        _capsule(11, "csr_binary"),
        _capsule(12, "hybrid_binary"),
        _capsule(13, "coo_json"),
    ]
    bundle = encode_bundle(capsules)
    manifest, restored = decode_bundle(bundle)

    assert manifest["schema"] == "in-formation-space.portable-realization-bundle.v1"
    assert manifest["shared"]["codec_schemas"] == {
        "coo_json": "test-schema-coo_json",
        "csr_binary": "test-schema-csr_binary",
        "hybrid_binary": "test-schema-hybrid_binary",
        "rowmask_binary": "test-schema-rowmask_binary",
    }
    assert restored == capsules
    assert len(bundle) < sum(len(item) for item in capsules)


def test_bundle_rejects_mixed_toolchain_provenance():
    capsules = [_capsule(20), _capsule(21, ecpu_revision="ecpu-r2")]
    with pytest.raises(CompactProvenanceError, match="share source and toolchain"):
        encode_bundle(capsules)


def test_bundle_rejects_outer_digest_tampering():
    bundle = encode_bundle([_capsule(30), _capsule(31)])
    tampered = bytearray(bundle)
    tampered[-1] ^= 0x01
    with pytest.raises(CompactProvenanceError, match="bundle SHA-256"):
        decode_bundle(bytes(tampered))


def test_bundle_rejects_entry_payload_tampering_even_with_outer_digest_recomputed():
    bundle = bytearray(encode_bundle([_capsule(40), _capsule(41)]))
    _, _, manifest_length, _ = BUNDLE_PREFIX.unpack_from(bundle, 0)
    cursor = BUNDLE_PREFIX.size + manifest_length
    header_length, payload_length = ENTRY_PREFIX.unpack_from(bundle, cursor)
    payload_start = cursor + ENTRY_PREFIX.size + header_length
    bundle[payload_start] ^= 0x01
    tampered = _refresh_bundle_digest(bundle)

    with pytest.raises(CompactProvenanceError, match="payload length or digest"):
        decode_bundle(tampered)


def test_bundle_rejects_entry_header_tampering_even_with_outer_digest_recomputed():
    bundle = bytearray(encode_bundle([_capsule(50), _capsule(51)]))
    _, _, manifest_length, _ = BUNDLE_PREFIX.unpack_from(bundle, 0)
    cursor = BUNDLE_PREFIX.size + manifest_length
    header_length, _ = ENTRY_PREFIX.unpack_from(bundle, cursor)
    header_start = cursor + ENTRY_PREFIX.size
    header_end = header_start + header_length
    header = bytes(bundle[header_start:header_end])
    assert b"live_dag" in header
    changed = header.replace(b"live_dag", b"other_dag", 1)
    assert len(changed) == len(header)
    bundle[header_start:header_end] = changed
    tampered = _refresh_bundle_digest(bundle)

    with pytest.raises(CompactProvenanceError, match="header SHA-256"):
        decode_bundle(tampered)


def test_bundle_rejects_manifest_tampering_even_with_outer_digest_recomputed():
    bundle = bytearray(encode_bundle([_capsule(60), _capsule(61)]))
    _, _, manifest_length, _ = BUNDLE_PREFIX.unpack_from(bundle, 0)
    manifest_start = BUNDLE_PREFIX.size
    manifest_end = manifest_start + manifest_length
    manifest = bytes(bundle[manifest_start:manifest_end])
    assert b"Kier73/In-Formation-Space" in manifest
    changed = manifest.replace(
        b"Kier73/In-Formation-Space",
        b"Kier73/No-Formation-Space",
        1,
    )
    assert len(changed) == len(manifest)
    bundle[manifest_start:manifest_end] = changed
    tampered = _refresh_bundle_digest(bundle)

    with pytest.raises(CompactProvenanceError, match="manifest identity or digest"):
        decode_bundle(tampered)
