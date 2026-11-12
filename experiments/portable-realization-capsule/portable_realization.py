"""Self-contained, integrity-checked portable realization capsules.

The capsule binds an opaque exact realization payload to its source Ground,
model identity, interface, codec, toolchain revisions, and verification receipt.
SHA-256 protects integrity and identity; it does not authenticate an author.
"""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from typing import Any


MAGIC = b"IFSPRC01"
VERSION = 1
PREFIX = struct.Struct("<8sHI")
SCHEMA = "in-formation-space.portable-realization.v1"


class PortableRealizationError(ValueError):
    """Raised when a portable realization capsule is invalid or altered."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PortableRealizationError("capsule metadata is not canonical JSON data") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PortableRealizationError(f"{field} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise PortableRealizationError(f"{field} keys must be strings")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PortableRealizationError(f"{field} must be a non-empty string")
    return value


def _require_digest(value: Any, field: str) -> str:
    digest = _require_text(value, field)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise PortableRealizationError(f"{field} must be a lowercase SHA-256 digest")
    return digest


def _validate_core(core: Mapping[str, Any], payload: bytes) -> None:
    required = {
        "schema",
        "version",
        "source",
        "realization",
        "interface",
        "codec",
        "verification",
        "toolchain",
        "payload",
    }
    if set(core) != required:
        raise PortableRealizationError("capsule core fields do not match schema")

    if core["schema"] != SCHEMA or core["version"] != VERSION:
        raise PortableRealizationError("unsupported portable realization schema/version")

    source = _require_mapping(core["source"], "source")
    _require_text(source.get("repository"), "source.repository")
    _require_text(source.get("revision"), "source.revision")
    _require_text(source.get("kind"), "source.kind")
    _require_digest(source.get("ground_digest"), "source.ground_digest")

    realization = _require_mapping(core["realization"], "realization")
    _require_text(realization.get("repository"), "realization.repository")
    _require_text(realization.get("revision"), "realization.revision")
    _require_text(realization.get("compiler_route"), "realization.compiler_route")
    _require_digest(realization.get("dense_model_digest"), "realization.dense_model_digest")
    _require_digest(realization.get("sparse_model_digest"), "realization.sparse_model_digest")

    interface = _require_mapping(core["interface"], "interface")
    input_names = interface.get("input_names")
    output_names = interface.get("output_names")
    architecture = interface.get("architecture")
    domain = _require_mapping(interface.get("domain"), "interface.domain")
    if (
        not isinstance(input_names, list)
        or not input_names
        or any(not isinstance(item, str) or not item for item in input_names)
        or len(set(input_names)) != len(input_names)
    ):
        raise PortableRealizationError("interface.input_names must be unique non-empty strings")
    if (
        not isinstance(output_names, list)
        or not output_names
        or any(not isinstance(item, str) or not item for item in output_names)
        or len(set(output_names)) != len(output_names)
    ):
        raise PortableRealizationError("interface.output_names must be unique non-empty strings")
    if (
        not isinstance(architecture, list)
        or len(architecture) < 3
        or any(type(width) is not int or width < 1 for width in architecture)
        or architecture[0] != len(input_names)
        or architecture[-1] != len(output_names)
    ):
        raise PortableRealizationError("interface.architecture does not match its register names")
    if domain.get("kind") != "finite_boolean":
        raise PortableRealizationError("only finite_boolean interface domains are supported")
    if domain.get("input_width") != len(input_names):
        raise PortableRealizationError("interface domain width does not match input names")

    codec = _require_mapping(core["codec"], "codec")
    _require_text(codec.get("name"), "codec.name")
    _require_text(codec.get("schema"), "codec.schema")

    receipt = _require_mapping(core["verification"], "verification")
    if receipt.get("status") != "verified-within-complete-finite-domain":
        raise PortableRealizationError("capsule verification receipt is not complete")
    if receipt.get("input_row_count") != 2 ** len(input_names):
        raise PortableRealizationError("verification receipt does not cover the complete Boolean domain")
    if receipt.get("output_domain") != "finite_boolean":
        raise PortableRealizationError("verification receipt output domain is unsupported")
    _require_digest(receipt.get("reference_outputs_sha256"), "verification.reference_outputs_sha256")
    _require_digest(receipt.get("case_evidence_sha256"), "verification.case_evidence_sha256")
    _require_digest(receipt.get("translation_contracts_sha256"), "verification.translation_contracts_sha256")
    _require_digest(receipt.get("receipt_sha256"), "verification.receipt_sha256")
    receipt_unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt["receipt_sha256"] != _sha256(_canonical(receipt_unsigned)):
        raise PortableRealizationError("verification receipt digest mismatch")

    toolchain = _require_mapping(core["toolchain"], "toolchain")
    for key in ("ecpu_revision", "vgi_revision", "ifs_revision"):
        _require_text(toolchain.get(key), f"toolchain.{key}")

    payload_descriptor = _require_mapping(core["payload"], "payload")
    if payload_descriptor.get("byte_length") != len(payload):
        raise PortableRealizationError("payload byte length mismatch")
    if payload_descriptor.get("sha256") != _sha256(payload):
        raise PortableRealizationError("payload SHA-256 mismatch")


def encode_capsule(
    payload: bytes,
    *,
    source: Mapping[str, Any],
    realization: Mapping[str, Any],
    interface: Mapping[str, Any],
    codec: Mapping[str, Any],
    verification: Mapping[str, Any],
    toolchain: Mapping[str, Any],
) -> bytes:
    """Package an exact realization payload with its identity and evidence."""
    if not isinstance(payload, bytes) or not payload:
        raise PortableRealizationError("payload must be non-empty bytes")

    receipt = dict(_require_mapping(verification, "verification"))
    if "receipt_sha256" in receipt:
        raise PortableRealizationError("verification receipt digest is assigned by the capsule encoder")
    receipt["receipt_sha256"] = _sha256(_canonical(receipt))

    core = {
        "schema": SCHEMA,
        "version": VERSION,
        "source": dict(_require_mapping(source, "source")),
        "realization": dict(_require_mapping(realization, "realization")),
        "interface": dict(_require_mapping(interface, "interface")),
        "codec": dict(_require_mapping(codec, "codec")),
        "verification": receipt,
        "toolchain": dict(_require_mapping(toolchain, "toolchain")),
        "payload": {
            "byte_length": len(payload),
            "sha256": _sha256(payload),
        },
    }
    _validate_core(core, payload)

    capsule_digest = _sha256(_canonical(core))
    header_without_hash = {**core, "capsule_sha256": capsule_digest}
    header = {
        **header_without_hash,
        "header_sha256": _sha256(_canonical(header_without_hash)),
    }
    header_bytes = _canonical(header)
    prefix = PREFIX.pack(MAGIC, VERSION, len(header_bytes))
    return prefix + header_bytes + payload


def decode_capsule(capsule: bytes) -> tuple[dict[str, Any], bytes]:
    """Validate framing, canonical header, both digests, and return metadata/payload."""
    if not isinstance(capsule, bytes) or len(capsule) < PREFIX.size:
        raise PortableRealizationError("capsule is truncated")
    magic, version, header_length = PREFIX.unpack_from(capsule, 0)
    if magic != MAGIC:
        raise PortableRealizationError("capsule magic does not match")
    if version != VERSION:
        raise PortableRealizationError("unsupported capsule framing version")
    header_start = PREFIX.size
    payload_start = header_start + header_length
    if header_length <= 0 or payload_start > len(capsule):
        raise PortableRealizationError("capsule header is truncated")

    header_bytes = capsule[header_start:payload_start]
    try:
        header = json.loads(header_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PortableRealizationError("capsule header is not valid JSON") from exc
    if _canonical(header) != header_bytes:
        raise PortableRealizationError("capsule header is not canonical")

    if not isinstance(header, dict):
        raise PortableRealizationError("capsule header must be an object")
    header_hash = header.pop("header_sha256", None)
    if header_hash != _sha256(_canonical(header)):
        raise PortableRealizationError("capsule header SHA-256 mismatch")
    capsule_hash = header.pop("capsule_sha256", None)
    if capsule_hash != _sha256(_canonical({key: value for key, value in header.items()})):
        raise PortableRealizationError("capsule identity SHA-256 mismatch")

    payload = capsule[payload_start:]
    _validate_core(header, payload)
    # Restore derived integrity values for caller inspection.
    header["capsule_sha256"] = capsule_hash
    header["header_sha256"] = header_hash
    return header, payload
