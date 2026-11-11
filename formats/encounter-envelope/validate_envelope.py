#!/usr/bin/env python3
"""Validate an experimental In-Formation Encounter Envelope (0.1).

Structural validation uses only the Python standard library. Optional digest
verification is deliberately narrower: only SHA-256 and the named
canonicalization modes below are implemented. A reference is never fetched.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple


SCHEMA_FORMAT = "in-formation.encounter/0.1"
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
SUPPORTED_ALGORITHMS = {"sha256"}
SUPPORTED_CANONICALIZATIONS = {"utf8-raw-v1", "json-sort-keys-utf8-v1"}


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def parse_iso8601(timestamp_str: str) -> bool:
    """Return whether a string is a timezone-qualified RFC 3339 date-time.

    Python's fromisoformat accepts naive timestamps and non-RFC3339 forms,
    so a syntax check is performed before parsing. Leap-second notation (:60)
    is not accepted because Python's datetime implementation cannot validate it.
    """
    if not isinstance(timestamp_str, str) or not _RFC3339.fullmatch(timestamp_str):
        return False
    normalized = timestamp_str.replace("t", "T", 1)
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _check_optional_string(
    obj: dict, key: str, path: str, errors: List[str], *, nullable: bool = False
) -> None:
    if key not in obj:
        return
    value = obj[key]
    if nullable and value is None:
        return
    if not isinstance(value, str):
        expected = "a string or null" if nullable else "a string"
        errors.append(f"Field '{path}' must be {expected}.")


def validate_encounter(doc: Any) -> Tuple[bool, List[str]]:
    """Validate an envelope against the structural constraints of schema.json."""
    errors: List[str] = []
    if not isinstance(doc, dict):
        return False, ["Envelope root must be a JSON object."]

    for req in ("format", "id", "source", "payload"):
        if req not in doc:
            errors.append(f"Missing required root field: '{req}'.")

    if "format" in doc and doc["format"] != SCHEMA_FORMAT:
        errors.append(f"Field 'format' must be '{SCHEMA_FORMAT}', got '{doc.get('format')}'.")

    if "id" in doc and not _nonempty_string(doc["id"]):
        errors.append("Field 'id' must be a non-empty string.")

    for key in ("observed_at", "recorded_at"):
        if key in doc and doc[key] is not None and not parse_iso8601(doc[key]):
            errors.append(
                f"Field '{key}' must be a timezone-qualified RFC 3339 date-time or null, got '{doc[key]}'."
            )

    if "source" in doc:
        src = doc["source"]
        if not isinstance(src, dict):
            errors.append("Field 'source' must be an object.")
        else:
            if "kind" not in src:
                errors.append("Field 'source' missing required property 'kind'.")
            elif not _nonempty_string(src["kind"]):
                errors.append("Field 'source.kind' must be a non-empty string.")
            for key in ("name", "reference", "capture_method"):
                _check_optional_string(src, key, f"source.{key}", errors, nullable=True)

    if "context" in doc and not isinstance(doc["context"], dict):
        errors.append("Field 'context' must be an object.")

    if "payload" in doc:
        payload = doc["payload"]
        if not isinstance(payload, dict):
            errors.append("Field 'payload' must be an object.")
        else:
            has_val = "value" in payload
            has_ref = "reference" in payload
            if has_val == has_ref:
                if has_val:
                    errors.append("Field 'payload' must have either 'value' or 'reference', but not both (oneOf).")
                else:
                    errors.append("Field 'payload' must contain either 'value' or 'reference'.")
            elif has_ref and not _nonempty_string(payload["reference"]):
                errors.append("Field 'payload.reference' must be a non-empty string.")
            for key in ("media_type", "encoding", "digest"):
                _check_optional_string(payload, key, f"payload.{key}", errors)

    if "relations" in doc:
        rel = doc["relations"]
        if not isinstance(rel, list):
            errors.append("Field 'relations' must be an array.")
        else:
            for idx, item in enumerate(rel):
                if not isinstance(item, dict):
                    errors.append(f"relations[{idx}] must be an object.")
                    continue
                for key in ("kind", "target"):
                    if key not in item or not _nonempty_string(item[key]):
                        errors.append(f"relations[{idx}] missing non-empty '{key}' string.")
                _check_optional_string(item, "note", f"relations[{idx}].note", errors)

    if "integrity" in doc:
        integ = doc["integrity"]
        if not isinstance(integ, dict):
            errors.append("Field 'integrity' must be an object.")
        else:
            for key in ("algorithm", "digest", "canonicalization"):
                _check_optional_string(integ, key, f"integrity.{key}", errors)

    if "extensions" in doc and not isinstance(doc["extensions"], dict):
        errors.append("Field 'extensions' must be an object.")

    return len(errors) == 0, errors


def compute_payload_digest(
    doc: dict, algorithm: str = "sha256", canonicalization: Optional[str] = None
) -> Optional[str]:
    """Compute the digest of inline payload.value under a named byte contract.

    utf8-raw-v1 hashes a string's UTF-8 bytes without JSON quoting.
    json-sort-keys-utf8-v1 hashes compact JSON with sorted keys, UTF-8
    characters preserved, and non-finite numbers rejected. This is a local
    interchange contract, not a claim of RFC 8785/JCS compatibility.
    """
    if not isinstance(doc, dict) or not isinstance(doc.get("payload"), dict):
        raise ValueError("Envelope has no payload object.")
    payload = doc["payload"]
    if "value" not in payload:
        return None

    normalized_algorithm = algorithm.lower() if isinstance(algorithm, str) else ""
    if normalized_algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"Unsupported digest algorithm: {algorithm!r}.")
    if canonicalization not in SUPPORTED_CANONICALIZATIONS:
        raise ValueError(f"Unsupported or missing canonicalization: {canonicalization!r}.")

    value = payload["value"]
    if canonicalization == "utf8-raw-v1":
        if not isinstance(value, str):
            raise ValueError("utf8-raw-v1 requires payload.value to be a string.")
        payload_bytes = value.encode("utf-8")
    else:
        try:
            payload_bytes = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"payload.value cannot be serialized under json-sort-keys-utf8-v1: {exc}") from exc

    return hashlib.sha256(payload_bytes).hexdigest()


def verify_integrity(doc: dict) -> Tuple[str, str]:
    """Return (status, detail) for the optional integrity declaration."""
    integ = doc.get("integrity")
    if not isinstance(integ, dict):
        return "NOT_REQUESTED", "no integrity object"
    if "digest" not in integ and "algorithm" not in integ:
        return "NOT_REQUESTED", "integrity object contains no digest claim"
    if not _nonempty_string(integ.get("algorithm")) or not _nonempty_string(integ.get("digest")):
        return "UNVERIFIED", "integrity claim requires non-empty algorithm and digest"

    algorithm = integ["algorithm"]
    canonicalization = integ.get("canonicalization")
    if algorithm.lower() not in SUPPORTED_ALGORITHMS:
        return "UNVERIFIED", f"unsupported digest algorithm {algorithm!r}"
    if canonicalization not in SUPPORTED_CANONICALIZATIONS:
        return "UNVERIFIED", f"unsupported or missing canonicalization {canonicalization!r}"

    payload = doc.get("payload")
    if not isinstance(payload, dict):
        return "UNVERIFIED", "payload object is unavailable"
    if "reference" in payload:
        return "NOT_CHECKED", "payload is a reference; referenced bytes were not retrieved"
    if "value" not in payload:
        return "UNVERIFIED", "payload has no inline value to verify"

    try:
        actual = compute_payload_digest(doc, algorithm, canonicalization)
    except ValueError as exc:
        return "UNVERIFIED", str(exc)
    if actual != integ["digest"].lower():
        return "MISMATCH", f"expected {integ['digest']}, computed {actual}"
    return "VERIFIED", f"{algorithm}:{actual}"


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(f"Usage: {Path(sys.argv[0]).name} <envelope-file.json> [envelope-file-2.json ...]")
        return 2

    overall_pass = True
    for path_str in args:
        path = Path(path_str)
        if not path.is_file():
            print(f"[FAIL] {path_str}: File not found.")
            overall_pass = False
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"[FAIL] {path_str}: JSON read/parse error: {exc}")
            overall_pass = False
            continue

        valid, errors = validate_encounter(data)
        if not valid:
            print(f"[FAIL] {path_str}:")
            for error in errors:
                print(f"  - {error}")
            overall_pass = False
            continue

        print(f"[PASS] {path_str} (id: {data.get('id')})")
        status, detail = verify_integrity(data)
        if status == "VERIFIED":
            print(f"  [Digest verified] {detail}")
        elif status == "MISMATCH":
            print(f"  [Digest MISMATCH] {detail}")
            overall_pass = False
        elif status in {"UNVERIFIED", "NOT_CHECKED"}:
            print(f"  [Digest {status.lower()}] {detail}")
            overall_pass = False
        if isinstance(data.get("payload"), dict) and "digest" in data["payload"]:
            print("  [Payload digest declared] not checked; no corresponding integrity verification contract was supplied")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
