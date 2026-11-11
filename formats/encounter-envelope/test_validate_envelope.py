import hashlib
import json
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # Optional development dependency; runtime validator stays stdlib-only.
    Draft202012Validator = None
    FormatChecker = None

from validate_envelope import (
    compute_payload_digest,
    parse_iso8601,
    validate_encounter,
    verify_integrity,
)


def envelope(payload=None):
    return {
        "format": "in-formation.encounter/0.1",
        "id": "test:one",
        "source": {"kind": "test"},
        "payload": {"value": "hello"} if payload is None else payload,
    }


class TimestampTests(unittest.TestCase):
    def test_timezone_qualified_rfc3339_is_accepted(self):
        self.assertTrue(parse_iso8601("2026-11-11T20:30:00Z"))
        self.assertTrue(parse_iso8601("2026-11-11T15:30:00-05:00"))
        self.assertTrue(parse_iso8601("2026-11-11t20:30:00.125z"))

    def test_naive_and_non_rfc3339_forms_are_rejected(self):
        for value in (
            "2026-11-11T20:30:00",
            "2026-11-11 20:30:00Z",
            "not-a-date",
            "2026-13-11T20:30:00Z",
            "2026-11-11T20:30:60Z",
        ):
            with self.subTest(value=value):
                self.assertFalse(parse_iso8601(value))


class StructureTests(unittest.TestCase):
    def test_minimal_envelope_is_valid(self):
        self.assertEqual(validate_encounter(envelope()), (True, []))

    def test_payload_requires_exactly_one_of_value_or_reference(self):
        for payload in ({}, {"value": "x", "reference": "artifact.bin"}):
            with self.subTest(payload=payload):
                valid, errors = validate_encounter(envelope(payload))
                self.assertFalse(valid)
                self.assertTrue(errors)

    def test_reference_must_be_nonempty(self):
        valid, errors = validate_encounter(envelope({"reference": "  "}))
        self.assertFalse(valid)
        self.assertTrue(any("payload.reference" in error for error in errors))

    def test_relations_and_integrity_must_be_objects_or_arrays_as_specified(self):
        doc = envelope()
        doc["relations"] = None
        doc["integrity"] = None
        valid, errors = validate_encounter(doc)
        self.assertFalse(valid)
        self.assertTrue(any("relations" in error for error in errors))
        self.assertTrue(any("integrity" in error for error in errors))

    def test_optional_nested_fields_are_type_checked(self):
        doc = envelope()
        doc["source"]["capture_method"] = 4
        doc["payload"]["media_type"] = 7
        doc["extensions"] = []
        valid, errors = validate_encounter(doc)
        self.assertFalse(valid)
        self.assertEqual(len(errors), 3)

    def test_whitespace_only_id_is_rejected(self):
        doc = envelope()
        doc["id"] = "   "
        self.assertFalse(validate_encounter(doc)[0])

    def test_naive_timestamp_is_rejected_at_envelope_boundary(self):
        doc = envelope()
        doc["observed_at"] = "2026-11-11T20:30:00"
        self.assertFalse(validate_encounter(doc)[0])


class IntegrityTests(unittest.TestCase):
    def test_raw_utf8_digest(self):
        doc = envelope()
        expected = hashlib.sha256(b"hello").hexdigest()
        self.assertEqual(compute_payload_digest(doc, "sha256", "utf8-raw-v1"), expected)

    def test_json_digest_is_stable_for_key_order(self):
        first = envelope({"value": {"b": 2, "a": 1}})
        second = envelope({"value": {"a": 1, "b": 2}})
        a = compute_payload_digest(first, "sha256", "json-sort-keys-utf8-v1")
        b = compute_payload_digest(second, "sha256", "json-sort-keys-utf8-v1")
        self.assertEqual(a, b)

    def test_verified_integrity(self):
        doc = envelope()
        doc["integrity"] = {
            "algorithm": "sha256",
            "canonicalization": "utf8-raw-v1",
            "digest": hashlib.sha256(b"hello").hexdigest(),
        }
        self.assertEqual(verify_integrity(doc)[0], "VERIFIED")

    def test_mismatch_is_reported(self):
        doc = envelope()
        doc["integrity"] = {
            "algorithm": "sha256",
            "canonicalization": "utf8-raw-v1",
            "digest": "0" * 64,
        }
        self.assertEqual(verify_integrity(doc)[0], "MISMATCH")

    def test_unsupported_algorithm_is_explicit(self):
        doc = envelope()
        doc["integrity"] = {
            "algorithm": "sha512",
            "digest": "abc",
            "canonicalization": "utf8-raw-v1",
        }
        status, detail = verify_integrity(doc)
        self.assertEqual(status, "UNVERIFIED")
        self.assertIn("unsupported digest algorithm", detail)

    def test_reference_payload_is_not_claimed_verified(self):
        doc = envelope({"reference": "artifact.bin"})
        doc["integrity"] = {
            "algorithm": "sha256",
            "digest": "abc",
            "canonicalization": "utf8-raw-v1",
        }
        status, detail = verify_integrity(doc)
        self.assertEqual(status, "NOT_CHECKED")
        self.assertIn("not retrieved", detail)

    def test_missing_canonicalization_is_explicit(self):
        doc = envelope()
        doc["integrity"] = {"algorithm": "sha256", "digest": "abc"}
        status, detail = verify_integrity(doc)
        self.assertEqual(status, "UNVERIFIED")
        self.assertIn("canonicalization", detail)


class SchemaAgreementTests(unittest.TestCase):
    def test_shared_cases_agree_with_json_schema_when_available(self):
        if Draft202012Validator is None:
            self.skipTest("jsonschema is not installed; install it to run schema parity checks")
        schema_path = Path(__file__).with_name("schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())

        cases = [
            ("minimal", envelope(), True),
            ("nullable timestamps", {**envelope(), "observed_at": None, "recorded_at": None}, True),
            ("naive timestamp", {**envelope(), "observed_at": "2026-11-11T20:30:00"}, False),
            ("whitespace id", {**envelope(), "id": "   "}, False),
            ("null relations", {**envelope(), "relations": None}, False),
            ("both payload forms", envelope({"value": "x", "reference": "r"}), False),
            ("wrong optional type", {**envelope(), "extensions": []}, False),
        ]
        for name, doc, expected in cases:
            with self.subTest(name=name):
                schema_valid = validator.is_valid(doc)
                implementation_valid = validate_encounter(doc)[0]
                self.assertEqual(schema_valid, expected)
                self.assertEqual(implementation_valid, expected)


if __name__ == "__main__":
    unittest.main()
