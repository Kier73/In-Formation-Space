#!/usr/bin/env python3
"""Comprehensive test suite for validate_envelope.py (positive & negative fixtures)."""

import json
import tempfile
from pathlib import Path
from validate_envelope import parse_rfc3339, validate_encounter, verify_digest


def test_rfc3339_timezone() -> None:
    # Valid RFC 3339
    assert parse_rfc3339("2026-11-11T20:30:00Z"), "Should accept 'Z' timezone"
    assert parse_rfc3339("2026-11-11T15:30:00-05:00"), "Should accept '-05:00' timezone"
    assert parse_rfc3339("2026-11-11T21:30:00.123456+00:00"), "Should accept microsecond timezone"

    # Naive / invalid datetimes
    assert not parse_rfc3339("2026-11-11T20:30:00"), "Should reject naive datetime without timezone"
    assert not parse_rfc3339("2026-11-11"), "Should reject date-only string"
    assert not parse_rfc3339("not-a-date"), "Should reject non-date string"


def test_validation_fixtures() -> None:
    base = {
        "format": "in-formation.encounter/0.1",
        "id": "test:001",
        "source": {"kind": "test"},
        "payload": {"value": "hello"},
    }

    # 1. Base valid
    v, err = validate_encounter(base)
    assert v, f"Base should be valid: {err}"

    # 2. Invalid format
    d = dict(base, format="wrong/0.1")
    v, err = validate_encounter(d)
    assert not v and any("format" in e for e in err), "Should reject wrong format"

    # 3. Missing source
    d = {k: v for k, v in base.items() if k != "source"}
    v, err = validate_encounter(d)
    assert not v and any("source" in e for e in err), "Should reject missing source"

    # 4. Naive recorded_at
    d = dict(base, recorded_at="2026-11-11T12:00:00")
    v, err = validate_encounter(d)
    assert not v and any("recorded_at" in e for e in err), "Should reject naive recorded_at"

    # 5. Valid recorded_at
    d = dict(base, recorded_at="2026-11-11T12:00:00Z")
    v, err = validate_encounter(d)
    assert v, f"Should accept RFC 3339 recorded_at: {err}"

    # 6. Both value and reference
    d = dict(base, payload={"value": "a", "reference": "b"})
    v, err = validate_encounter(d)
    assert not v and any("oneOf" in e for e in err), "Should reject both value and reference"

    # 7. Neither value nor reference
    d = dict(base, payload={"media_type": "text/plain"})
    v, err = validate_encounter(d)
    assert not v and any("contain either" in e for e in err), "Should reject empty payload"


def test_digest_verification() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        test_file = tmp_path / "payload.bin"
        test_file.write_bytes(b"sample-payload-bytes")
        correct_sha = "375aad76c3ae615bc390d3c2a12d47140f5f65c33bf55823c2439df7cb19458a"

        # 1. Valid file reference digest
        doc = {
            "format": "in-formation.encounter/0.1",
            "id": "test:ref",
            "source": {"kind": "test"},
            "payload": {"reference": "payload.bin"},
            "integrity": {"algorithm": "sha256", "digest": correct_sha},
        }
        status, exp, comp = verify_digest(doc, base_dir=tmp_path)
        assert status == "verified", f"Should verify file reference digest, got: {status}"

        # 2. Mismatched digest
        doc_bad = dict(doc, integrity={"algorithm": "sha256", "digest": "wrong"})
        status, exp, comp = verify_digest(doc_bad, base_dir=tmp_path)
        assert status == "mismatch", f"Should detect mismatch, got: {status}"

        # 3. Missing referenced file
        doc_missing = dict(doc, payload={"reference": "nonexistent.bin"})
        status, exp, comp = verify_digest(doc_missing, base_dir=tmp_path)
        assert status == "reference_missing", f"Should report reference_missing, got: {status}"

        # 4. Unsupported algorithm
        doc_unsupported = dict(doc, integrity={"algorithm": "sha512", "digest": "abc"})
        status, exp, comp = verify_digest(doc_unsupported, base_dir=tmp_path)
        assert status == "unsupported_algorithm", f"Should report unsupported_algorithm, got: {status}"


def main() -> None:
    test_rfc3339_timezone()
    test_validation_fixtures()
    test_digest_verification()
    print("[PASS] All validator positive and negative fixture tests passed cleanly!")


if __name__ == "__main__":
    main()
