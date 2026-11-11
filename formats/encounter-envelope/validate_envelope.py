#!/usr/bin/env python3
"""Validation utility for In-Formation Encounter Envelope (experimental 0.1).

Validates encounter records against the structural constraints of schema.json
using only Python's standard library.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple


SCHEMA_FORMAT = "in-formation.encounter/0.1"
SUPPORTED_DIGEST_ALGORITHMS = {"sha256"}


def parse_rfc3339(timestamp_str: str) -> bool:
    """Check if string is a valid RFC 3339 date-time with an explicit timezone."""
    if not isinstance(timestamp_str, str) or not timestamp_str.strip():
        return False
    normalized = timestamp_str.replace("Z", "+00:00") if timestamp_str.endswith("Z") else timestamp_str
    try:
        dt = datetime.datetime.fromisoformat(normalized)
        # RFC 3339 requires an explicit timezone offset
        return dt.tzinfo is not None
    except (ValueError, TypeError):
        return False


def validate_encounter(doc: Any) -> Tuple[bool, List[str]]:
    """Validate a Python dict against the encounter-envelope 0.1 schema rules.

    Returns:
        (is_valid, error_list)
    """
    errors: List[str] = []

    if not isinstance(doc, dict):
        return False, ["Envelope root must be a JSON object."]

    # Required top-level fields: format, id, source, payload
    for req in ("format", "id", "source", "payload"):
        if req not in doc:
            errors.append(f"Missing required root field: '{req}'.")

    # format check
    if "format" in doc and doc["format"] != SCHEMA_FORMAT:
        errors.append(f"Field 'format' must be '{SCHEMA_FORMAT}', got '{doc.get('format')}'.")

    # id check
    if "id" in doc:
        if not isinstance(doc["id"], str) or len(doc["id"].strip()) == 0:
            errors.append("Field 'id' must be a non-empty string.")

    # observed_at check
    if "observed_at" in doc and doc["observed_at"] is not None:
        if not parse_rfc3339(doc["observed_at"]):
            errors.append(
                f"Field 'observed_at' must be a valid RFC 3339 date-time with timezone or null, got '{doc['observed_at']}'."
            )

    # recorded_at check
    if "recorded_at" in doc and doc["recorded_at"] is not None:
        if not parse_rfc3339(doc["recorded_at"]):
            errors.append(
                f"Field 'recorded_at' must be a valid RFC 3339 date-time with timezone or null, got '{doc['recorded_at']}'."
            )

    # source check
    if "source" in doc:
        src = doc["source"]
        if not isinstance(src, dict):
            errors.append("Field 'source' must be an object.")
        else:
            if "kind" not in src:
                errors.append("Field 'source' missing required property 'kind'.")
            elif not isinstance(src["kind"], str) or len(src["kind"].strip()) == 0:
                errors.append("Field 'source.kind' must be a non-empty string.")

    # payload check
    if "payload" in doc:
        payload = doc["payload"]
        if not isinstance(payload, dict):
            errors.append("Field 'payload' must be an object.")
        else:
            has_val = "value" in payload
            has_ref = "reference" in payload
            if has_val and has_ref:
                errors.append("Field 'payload' must have either 'value' or 'reference', but not both (oneOf).")
            elif not has_val and not has_ref:
                errors.append("Field 'payload' must contain either 'value' or 'reference'.")
            elif has_ref:
                if not isinstance(payload["reference"], str) or len(payload["reference"].strip()) == 0:
                    errors.append("Field 'payload.reference' must be a non-empty string.")

    # relations check
    if "relations" in doc and doc["relations"] is not None:
        rel = doc["relations"]
        if not isinstance(rel, list):
            errors.append("Field 'relations' must be an array.")
        else:
            for idx, r in enumerate(rel):
                if not isinstance(r, dict):
                    errors.append(f"relations[{idx}] must be an object.")
                    continue
                if "kind" not in r or not isinstance(r["kind"], str) or not r["kind"].strip():
                    errors.append(f"relations[{idx}] missing non-empty 'kind' string.")
                if "target" not in r or not isinstance(r["target"], str) or not r["target"].strip():
                    errors.append(f"relations[{idx}] missing non-empty 'target' string.")

    # integrity check
    if "integrity" in doc and doc["integrity"] is not None:
        integ = doc["integrity"]
        if not isinstance(integ, dict):
            errors.append("Field 'integrity' must be an object.")

    return len(errors) == 0, errors


def verify_digest(doc: dict, base_dir: Optional[Path] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Verify the digest of an encounter record.

    Returns:
        (status_code, expected_digest, computed_digest)
        status_code in: 'verified', 'mismatch', 'unsupported_algorithm', 'reference_missing', 'no_integrity'
    """
    if "integrity" not in doc or not isinstance(doc["integrity"], dict):
        return "no_integrity", None, None

    algo = doc["integrity"].get("algorithm")
    expected = doc["integrity"].get("digest")
    if not algo or not expected:
        return "no_integrity", None, None

    algo_norm = algo.lower()
    if algo_norm not in SUPPORTED_DIGEST_ALGORITHMS:
        return "unsupported_algorithm", expected, None

    # Get target bytes: either from inline payload.value or external reference
    payload = doc.get("payload", {})
    payload_bytes: Optional[bytes] = None

    if "value" in payload:
        val = payload["value"]
        if isinstance(val, str):
            payload_bytes = val.encode("utf-8")
        else:
            payload_bytes = json.dumps(val, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif "reference" in payload:
        ref_path_str = payload["reference"]
        ref_path = Path(ref_path_str)
        if not ref_path.is_absolute() and base_dir is not None:
            ref_path = base_dir / ref_path

        if ref_path.is_file():
            try:
                payload_bytes = ref_path.read_bytes()
            except Exception:
                return "reference_missing", expected, None
        else:
            return "reference_missing", expected, None

    if payload_bytes is None:
        return "reference_missing", expected, None

    if algo_norm == "sha256":
        computed = hashlib.sha256(payload_bytes).hexdigest()
        if computed == expected:
            return "verified", expected, computed
        return "mismatch", expected, computed

    return "unsupported_algorithm", expected, None


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <envelope-file.json> [envelope-file-2.json ...]")
        return 2

    overall_pass = True
    for path_str in sys.argv[1:]:
        p = Path(path_str)
        if not p.is_file():
            print(f"[FAIL] {path_str}: File not found.")
            overall_pass = False
            continue

        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            print(f"[FAIL] {path_str}: JSON parse error: {exc}")
            overall_pass = False
            continue

        valid, errors = validate_encounter(data)
        if valid:
            status_msg = f"[PASS] {path_str} (id: {data.get('id')})"
            digest_status, expected, computed = verify_digest(data, base_dir=p.parent)
            if digest_status == "verified":
                status_msg += f" [Digest verified: sha256:{computed[:8]}...]"
            elif digest_status == "mismatch":
                status_msg += f" [Digest MISMATCH: expected {expected[:8]}..., got {computed[:8]}...]"
                overall_pass = False
            elif digest_status == "unsupported_algorithm":
                algo = data.get("integrity", {}).get("algorithm")
                status_msg += f" [Digest unchecked: unsupported algorithm '{algo}']"
            elif digest_status == "reference_missing":
                ref = data.get("payload", {}).get("reference")
                status_msg += f" [Digest unchecked: referenced payload '{ref}' not found locally]"
            print(status_msg)
        else:
            print(f"[FAIL] {path_str}:")
            for err in errors:
                print(f"  - {err}")
            overall_pass = False

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
