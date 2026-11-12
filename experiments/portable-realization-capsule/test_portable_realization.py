from __future__ import annotations

import hashlib

import pytest

from portable_realization import (
    MAGIC,
    PREFIX,
    PortableRealizationError,
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

    with pytest.raises(PortableRealizationError, match="truncated"):
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
