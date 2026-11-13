"""Shared Python implementation of Canonical Metadata Profile v1.

The profile is specified in formats/canonical-metadata-v1/README.md and its
cross-language fixtures live in test-vectors.json. This module centralizes
Python validation and serialization; Go and JavaScript remain independent
implementations of the same bytes.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

PROFILE_ID = "in-formation-space.canonical-metadata.v1"
MAX_SAFE_INTEGER = (1 << 53) - 1


class CanonicalMetadataError(ValueError):
    """A value or byte artifact is outside Canonical Metadata Profile v1."""


def validate_value(value: Any, field: str = "$", seen: set[int] | None = None) -> None:
    """Reject values that do not have one unambiguous v1 representation."""
    if value is None or type(value) is bool:
        return
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise CanonicalMetadataError(f"{field} contains invalid Unicode scalar data") from exc
        return
    if type(value) is int:
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalMetadataError(f"{field} is outside the interoperable safe-integer range")
        return
    if type(value) is float:
        raise CanonicalMetadataError(
            f"{field} floating-point values are not supported by canonical metadata v1"
        )

    if seen is None:
        seen = set()
    if isinstance(value, (list, tuple, Mapping)):
        identity = id(value)
        if identity in seen:
            raise CanonicalMetadataError(f"{field} contains a recursive value")
        seen.add(identity)
        try:
            if isinstance(value, Mapping):
                for key, member in value.items():
                    if type(key) is not str:
                        raise CanonicalMetadataError(f"{field} object keys must be strings")
                    try:
                        key.encode("utf-8")
                    except UnicodeEncodeError as exc:
                        raise CanonicalMetadataError(
                            f"{field} contains an invalid Unicode object key"
                        ) from exc
                    if not key.isascii():
                        raise CanonicalMetadataError(
                            f"{field} object keys must be ASCII for canonical metadata v1"
                        )
                    validate_value(member, f"{field}.{key}", seen)
            else:
                for index, member in enumerate(value):
                    validate_value(member, f"{field}[{index}]", seen)
        finally:
            seen.remove(identity)
        return
    raise CanonicalMetadataError(
        f"{field} contains a value unsupported by canonical metadata v1"
    )


def canonical_bytes(value: Any) -> bytes:
    """Return the compact, sorted, UTF-8 JSON bytes for one v1 value."""
    validate_value(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CanonicalMetadataError(
            "value cannot be represented as canonical metadata v1"
        ) from exc


def canonical_digest(value: Any) -> str:
    """SHA-256 of canonical JSON bytes, excluding a file-terminating LF."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def decode_canonical_document(raw: bytes) -> dict[str, Any]:
    """Decode a canonical v1 object artifact ending in exactly one LF byte.

    Duplicate keys, invalid UTF-8/Unicode, non-finite values, non-v1 values,
    non-canonical encodings, and non-object roots are rejected.
    """
    if not isinstance(raw, bytes):
        raise TypeError("raw canonical metadata must be bytes")
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise CanonicalMetadataError("artifact must end in exactly one LF byte")
    try:
        source = raw[:-1].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CanonicalMetadataError("artifact is not valid UTF-8") from exc

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, member in pairs:
            if key in result:
                raise CanonicalMetadataError(f"duplicate object key: {key!r}")
            result[key] = member
        return result

    def reject_constant(token: str) -> None:
        raise CanonicalMetadataError(
            f"non-finite JSON number is not permitted: {token}"
        )

    try:
        value = json.loads(
            source,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except CanonicalMetadataError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise CanonicalMetadataError(
            f"artifact is not valid canonical JSON: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise CanonicalMetadataError(
            "canonical metadata artifact root must be an object"
        )
    if canonical_bytes(value) + b"\n" != raw:
        raise CanonicalMetadataError(
            "artifact is not canonical JSON followed by exactly one LF"
        )
    return value
