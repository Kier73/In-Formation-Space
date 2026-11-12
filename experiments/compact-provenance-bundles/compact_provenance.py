"""Compressed standalone headers and shared-provenance capsule bundles."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from collections.abc import Mapping, Sequence
from typing import Any

from portable_realization import (
    MAGIC as RAW_MAGIC,
    PREFIX as RAW_PREFIX,
    SCHEMA as RAW_SCHEMA,
    VERSION as RAW_VERSION,
    PortableRealizationError,
    decode_capsule,
    encode_capsule,
)


COMPRESSED_MAGIC = b"IFSPRCZ1"
COMPRESSED_VERSION = 1
COMPRESSED_PREFIX = struct.Struct("<8sHII")
BUNDLE_MAGIC = b"IFSPRB01"
BUNDLE_VERSION = 1
BUNDLE_PREFIX = struct.Struct("<8sHII")
ENTRY_PREFIX = struct.Struct("<II")
BUNDLE_SCHEMA = "in-formation-space.portable-realization-bundle.v1"
MAX_HEADER_BYTES = 16 * 1024 * 1024
MAX_CAPSULE_COUNT = 100_000


class CompactProvenanceError(ValueError):
    """Raised when a compressed capsule or provenance bundle is invalid."""


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
        raise CompactProvenanceError("metadata is not canonical JSON data") from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CompactProvenanceError(f"{field} must be an object")
    return value


def encode_compressed_capsule(raw_capsule: bytes, *, level: int = 9) -> bytes:
    """Compress only the canonical metadata header; preserve exact payload bytes."""
    try:
        header, payload = decode_capsule(raw_capsule)
    except PortableRealizationError as exc:
        raise CompactProvenanceError("raw capsule failed validation before compression") from exc
    if type(level) is not int or level < 0 or level > 9:
        raise CompactProvenanceError("zlib compression level must be between 0 and 9")

    header_bytes = _canonical(header)
    compressed = zlib.compress(header_bytes, level=level)
    prefix = COMPRESSED_PREFIX.pack(
        COMPRESSED_MAGIC,
        COMPRESSED_VERSION,
        len(header_bytes),
        len(compressed),
    )
    return prefix + compressed + payload


def decode_compressed_capsule(compact_capsule: bytes) -> bytes:
    """Inflate the header, rebuild a PRC-001 capsule, and run its full validator."""
    if not isinstance(compact_capsule, bytes) or len(compact_capsule) < COMPRESSED_PREFIX.size:
        raise CompactProvenanceError("compressed capsule is truncated")
    magic, version, raw_header_length, compressed_header_length = COMPRESSED_PREFIX.unpack_from(
        compact_capsule, 0
    )
    if magic != COMPRESSED_MAGIC:
        raise CompactProvenanceError("compressed capsule magic does not match")
    if version != COMPRESSED_VERSION:
        raise CompactProvenanceError("unsupported compressed capsule version")
    if raw_header_length <= 0 or raw_header_length > MAX_HEADER_BYTES:
        raise CompactProvenanceError("uncompressed capsule header length is invalid")
    compressed_start = COMPRESSED_PREFIX.size
    compressed_end = compressed_start + compressed_header_length
    if compressed_header_length <= 0 or compressed_end > len(compact_capsule):
        raise CompactProvenanceError("compressed capsule header is truncated")

    compressed = compact_capsule[compressed_start:compressed_end]
    payload = compact_capsule[compressed_end:]
    inflater = zlib.decompressobj()
    try:
        header_bytes = inflater.decompress(compressed, MAX_HEADER_BYTES + 1)
        header_bytes += inflater.flush()
    except zlib.error as exc:
        raise CompactProvenanceError("compressed capsule header is corrupt") from exc
    if (
        not inflater.eof
        or inflater.unused_data
        or inflater.unconsumed_tail
        or len(header_bytes) != raw_header_length
        or len(header_bytes) > MAX_HEADER_BYTES
    ):
        raise CompactProvenanceError("compressed capsule header length or framing mismatch")
    try:
        header = json.loads(header_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CompactProvenanceError("inflated capsule header is not JSON") from exc
    if _canonical(header) != header_bytes:
        raise CompactProvenanceError("inflated capsule header is not canonical")

    raw = (
        RAW_PREFIX.pack(RAW_MAGIC, RAW_VERSION, len(header_bytes))
        + header_bytes
        + payload
    )
    try:
        decode_capsule(raw)
    except PortableRealizationError as exc:
        raise CompactProvenanceError("inflated capsule failed PRC-001 validation") from exc
    return raw


def _shared_manifest(headers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not headers:
        raise CompactProvenanceError("bundle requires at least one capsule")

    first = headers[0]
    source = _mapping(first.get("source"), "source")
    realization = _mapping(first.get("realization"), "realization")
    toolchain = _mapping(first.get("toolchain"), "toolchain")

    shared = {
        "source_repository": source.get("repository"),
        "source_revision": source.get("revision"),
        "realization_repository": realization.get("repository"),
        "realization_revision": realization.get("revision"),
        "toolchain": dict(toolchain),
    }
    codec_schemas: dict[str, str] = {}
    for header in headers:
        src = _mapping(header.get("source"), "source")
        real = _mapping(header.get("realization"), "realization")
        current_toolchain = _mapping(header.get("toolchain"), "toolchain")
        if (
            src.get("repository") != shared["source_repository"]
            or src.get("revision") != shared["source_revision"]
            or real.get("repository") != shared["realization_repository"]
            or real.get("revision") != shared["realization_revision"]
            or dict(current_toolchain) != shared["toolchain"]
        ):
            raise CompactProvenanceError(
                "capsules do not share source and toolchain provenance"
            )
        codec = _mapping(header.get("codec"), "codec")
        name, schema = codec.get("name"), codec.get("schema")
        if not isinstance(name, str) or not isinstance(schema, str):
            raise CompactProvenanceError("capsule codec metadata is invalid")
        if name in codec_schemas and codec_schemas[name] != schema:
            raise CompactProvenanceError("codec schema differs within provenance bundle")
        codec_schemas[name] = schema

    if (
        toolchain.get("ifs_revision") != shared["source_revision"]
        or toolchain.get("ecpu_revision") != shared["realization_revision"]
    ):
        raise CompactProvenanceError("shared manifest revisions contradict toolchain pins")
    shared["codec_schemas"] = dict(sorted(codec_schemas.items()))
    return {
        "schema": BUNDLE_SCHEMA,
        "version": BUNDLE_VERSION,
        "shared": shared,
    }


def _seal_manifest(core: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = dict(core)
    return {**unsigned, "manifest_sha256": _sha(_canonical(unsigned))}


def _verify_manifest(manifest: Any) -> dict[str, Any]:
    data = dict(_mapping(manifest, "manifest"))
    supplied = data.pop("manifest_sha256", None)
    if (
        data.get("schema") != BUNDLE_SCHEMA
        or data.get("version") != BUNDLE_VERSION
        or supplied != _sha(_canonical(data))
    ):
        raise CompactProvenanceError("bundle manifest identity or digest mismatch")
    shared = _mapping(data.get("shared"), "manifest.shared")
    for key in (
        "source_repository",
        "source_revision",
        "realization_repository",
        "realization_revision",
    ):
        if not isinstance(shared.get(key), str) or not shared[key]:
            raise CompactProvenanceError(f"manifest.shared.{key} is invalid")
    toolchain = _mapping(shared.get("toolchain"), "manifest.shared.toolchain")
    for key in ("ifs_revision", "ecpu_revision", "vgi_revision"):
        if not isinstance(toolchain.get(key), str) or not toolchain[key]:
            raise CompactProvenanceError(f"manifest toolchain {key} is invalid")
    codecs = _mapping(shared.get("codec_schemas"), "manifest.shared.codec_schemas")
    if not codecs or any(not isinstance(k, str) or not isinstance(v, str) for k, v in codecs.items()):
        raise CompactProvenanceError("manifest codec schema registry is invalid")
    return {**data, "manifest_sha256": supplied}


def _local_entry(header: Mapping[str, Any], manifest_sha: str) -> dict[str, Any]:
    source = _mapping(header.get("source"), "source")
    realization = _mapping(header.get("realization"), "realization")
    codec = _mapping(header.get("codec"), "codec")
    verification = _mapping(header.get("verification"), "verification")
    payload = _mapping(header.get("payload"), "payload")
    core = {
        "schema": "in-formation-space.portable-realization-bundle-entry.v1",
        "version": 1,
        "manifest_sha256": manifest_sha,
        "source": {
            "kind": source["kind"],
            "ground_digest": source["ground_digest"],
            "program_digest": source["program_digest"],
        },
        "realization": {
            "compiler_route": realization["compiler_route"],
            "dense_model_digest": realization["dense_model_digest"],
            "sparse_model_digest": realization["sparse_model_digest"],
            "encoding": realization["encoding"],
        },
        "interface": dict(_mapping(header.get("interface"), "interface")),
        "codec": {"name": codec["name"], "schema": codec["schema"]},
        "verification": dict(verification),
        "payload": dict(payload),
        "standalone_capsule_sha256": header["capsule_sha256"],
    }
    capsule_sha = _sha(_canonical(core))
    with_capsule_sha = {**core, "capsule_sha256": capsule_sha}
    return {
        **with_capsule_sha,
        "header_sha256": _sha(_canonical(with_capsule_sha)),
    }


def encode_bundle(raw_capsules: Sequence[bytes]) -> bytes:
    """Bundle PRC-001 capsules while storing invariant provenance only once."""
    if not isinstance(raw_capsules, Sequence) or isinstance(raw_capsules, (str, bytes)):
        raise CompactProvenanceError("raw_capsules must be a sequence of standalone capsule bytes")
    if not raw_capsules or len(raw_capsules) > MAX_CAPSULE_COUNT:
        raise CompactProvenanceError("bundle capsule count is out of range")

    decoded = [decode_capsule(item) for item in raw_capsules]
    headers = [item[0] for item in decoded]
    payloads = [item[1] for item in decoded]
    manifest = _seal_manifest(_shared_manifest(headers))
    manifest_bytes = _canonical(manifest)
    manifest_sha = manifest["manifest_sha256"]

    out = bytearray(
        BUNDLE_PREFIX.pack(
            BUNDLE_MAGIC,
            BUNDLE_VERSION,
            len(manifest_bytes),
            len(raw_capsules),
        )
    )
    out.extend(manifest_bytes)

    for header, payload in zip(headers, payloads):
        local_header = _local_entry(header, manifest_sha)
        header_bytes = _canonical(local_header)
        out.extend(ENTRY_PREFIX.pack(len(header_bytes), len(payload)))
        out.extend(header_bytes)
        out.extend(payload)

    bundle_digest = hashlib.sha256(out).digest()
    out.extend(bundle_digest)
    return bytes(out)


def decode_bundle(bundle: bytes) -> tuple[dict[str, Any], list[bytes]]:
    """Validate shared manifest and entries, then reconstruct standalone capsules."""
    if not isinstance(bundle, bytes) or len(bundle) < BUNDLE_PREFIX.size + 32:
        raise CompactProvenanceError("bundle is truncated")
    magic, version, manifest_length, count = BUNDLE_PREFIX.unpack_from(bundle, 0)
    if magic != BUNDLE_MAGIC:
        raise CompactProvenanceError("bundle magic does not match")
    if version != BUNDLE_VERSION:
        raise CompactProvenanceError("unsupported bundle version")
    if count <= 0 or count > MAX_CAPSULE_COUNT or manifest_length <= 0 or manifest_length > MAX_HEADER_BYTES:
        raise CompactProvenanceError("bundle manifest length or entry count is invalid")

    supplied_bundle_digest = bundle[-32:]
    if hashlib.sha256(bundle[:-32]).digest() != supplied_bundle_digest:
        raise CompactProvenanceError("bundle SHA-256 mismatch")

    cursor = BUNDLE_PREFIX.size
    manifest_end = cursor + manifest_length
    if manifest_end > len(bundle) - 32:
        raise CompactProvenanceError("bundle manifest is truncated")
    manifest_bytes = bundle[cursor:manifest_end]
    try:
        manifest_json = json.loads(manifest_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CompactProvenanceError("bundle manifest is not JSON") from exc
    if _canonical(manifest_json) != manifest_bytes:
        raise CompactProvenanceError("bundle manifest is not canonical")
    manifest = _verify_manifest(manifest_json)
    shared = manifest["shared"]
    manifest_sha = manifest["manifest_sha256"]
    cursor = manifest_end
    restored_capsules: list[bytes] = []

    for _ in range(count):
        if cursor + ENTRY_PREFIX.size > len(bundle) - 32:
            raise CompactProvenanceError("bundle entry prefix is truncated")
        header_length, payload_length = ENTRY_PREFIX.unpack_from(bundle, cursor)
        cursor += ENTRY_PREFIX.size
        header_end = cursor + header_length
        payload_end = header_end + payload_length
        if (
            header_length <= 0
            or header_length > MAX_HEADER_BYTES
            or payload_end > len(bundle) - 32
        ):
            raise CompactProvenanceError("bundle entry lengths are invalid")
        header_bytes = bundle[cursor:header_end]
        payload = bundle[header_end:payload_end]
        cursor = payload_end
        try:
            entry = json.loads(header_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CompactProvenanceError("bundle entry header is not JSON") from exc
        if _canonical(entry) != header_bytes:
            raise CompactProvenanceError("bundle entry header is not canonical")
        entry = dict(_mapping(entry, "bundle entry"))

        supplied_header_sha = entry.pop("header_sha256", None)
        if supplied_header_sha != _sha(_canonical(entry)):
            raise CompactProvenanceError("bundle entry header SHA-256 mismatch")
        supplied_capsule_sha = entry.pop("capsule_sha256", None)
        if supplied_capsule_sha != _sha(_canonical(entry)):
            raise CompactProvenanceError("bundle entry capsule identity digest mismatch")

        if (
            entry.get("schema") != "in-formation-space.portable-realization-bundle-entry.v1"
            or entry.get("version") != 1
            or entry.get("manifest_sha256") != manifest_sha
        ):
            raise CompactProvenanceError("bundle entry does not reference this manifest")
        source = dict(_mapping(entry.get("source"), "entry.source"))
        realization = dict(_mapping(entry.get("realization"), "entry.realization"))
        codec = dict(_mapping(entry.get("codec"), "entry.codec"))
        receipt = dict(_mapping(entry.get("verification"), "entry.verification"))
        interface = dict(_mapping(entry.get("interface"), "entry.interface"))
        payload_descriptor = dict(_mapping(entry.get("payload"), "entry.payload"))

        codec_name = codec.get("name")
        codec_schema = codec.get("schema")
        if shared["codec_schemas"].get(codec_name) != codec_schema:
            raise CompactProvenanceError("bundle entry codec schema is not registered in shared manifest")
        if (
            payload_descriptor.get("byte_length") != len(payload)
            or payload_descriptor.get("sha256") != _sha(payload)
        ):
            raise CompactProvenanceError("bundle entry payload length or digest mismatch")

        full_source = {
            "repository": shared["source_repository"],
            "revision": shared["source_revision"],
            **source,
        }
        full_realization = {
            "repository": shared["realization_repository"],
            "revision": shared["realization_revision"],
            **realization,
        }
        codec_with_digest = {
            **codec,
            "payload_sha256": payload_descriptor["sha256"],
        }
        receipt_without_digest = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        raw_capsule = encode_capsule(
            payload,
            source=full_source,
            realization=full_realization,
            interface=interface,
            codec=codec_with_digest,
            verification=receipt_without_digest,
            toolchain=shared["toolchain"],
        )
        raw_header, raw_payload = decode_capsule(raw_capsule)
        if (
            raw_payload != payload
            or raw_header["capsule_sha256"] != entry.get("standalone_capsule_sha256")
        ):
            raise CompactProvenanceError("bundle entry did not reconstruct its standalone capsule identity")
        restored_capsules.append(raw_capsule)

    if cursor != len(bundle) - 32:
        raise CompactProvenanceError("bundle contains trailing or unassigned bytes")
    return manifest, restored_capsules
