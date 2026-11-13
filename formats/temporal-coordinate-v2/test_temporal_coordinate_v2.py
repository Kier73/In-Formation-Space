from __future__ import annotations

import hashlib
import json
import math
import struct
import unittest
from pathlib import Path

from formats.canonical_metadata_v1 import canonical_bytes
from formats.temporal_coordinate_v2 import (
    FRAME_SCHEMA,
    NUMERIC_SCHEMA,
    SPAN_SCHEMA,
    TemporalCoordinateError,
    decode_binary64,
    decode_integer,
    decode_operation_span_v2,
    decode_temporal_frame,
    encode_binary64,
    encode_integer,
    encode_operation_span_v2,
    encode_temporal_frame,
)

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads(
    (Path(__file__).resolve().parent / "vectors.json").read_text(encoding="utf-8")
)


def float_from_hex(value: str) -> float:
    return struct.unpack(">d", bytes.fromhex(value))[0]


class TemporalNumericV2Tests(unittest.TestCase):
    def test_arbitrary_width_integer_vectors_are_exact(self):
        for vector in VECTORS["integers"]:
            with self.subTest(vector=vector["name"]):
                encoded = encode_integer(int(vector["decimal"]))
                self.assertEqual(decode_integer(encoded), int(vector["decimal"]))
                self.assertEqual(encoded["schema"], NUMERIC_SCHEMA)
                canonical_bytes(encoded)

    def test_integer_envelope_rejects_noncanonical_decimal_tokens(self):
        for token in VECTORS["invalid_integer_tokens"]:
            with self.subTest(token=token):
                envelope = {
                    "format": "in-formation.temporal-numeric",
                    "schema": NUMERIC_SCHEMA,
                    "kind": "integer",
                    "encoding": "canonical-decimal-string",
                    "value": token,
                }
                with self.assertRaises(TemporalCoordinateError):
                    decode_integer(envelope)

    def test_binary64_vectors_preserve_every_bit(self):
        for vector in VECTORS["binary64"]:
            with self.subTest(vector=vector["name"]):
                value = float_from_hex(vector["be_hex"])
                encoded = encode_binary64(value)
                self.assertEqual(encoded["value"], vector["be_hex"])
                decoded = decode_binary64(encoded)
                self.assertEqual(struct.pack(">d", decoded).hex(), vector["be_hex"])
                canonical_bytes(encoded)

    def test_binary64_rejects_bad_hex_and_nonfinite_patterns(self):
        for vector in VECTORS["invalid_binary64_tokens"]:
            with self.subTest(vector=vector["name"]):
                envelope = {
                    "format": "in-formation.temporal-numeric",
                    "schema": NUMERIC_SCHEMA,
                    "kind": "binary64",
                    "encoding": "ieee754-binary64-be-hex",
                    "value": vector["be_hex"],
                }
                with self.assertRaises(TemporalCoordinateError):
                    decode_binary64(envelope)

    def test_chemical_tau_constraints_preserve_negative_zero(self):
        for vector in VECTORS["chemical_tau_cases"]:
            with self.subTest(vector=vector["name"]):
                # A non-finite value cannot be represented by a binary64 envelope.
                if vector["name"] == "infinity":
                    with self.assertRaises(TemporalCoordinateError):
                        encode_binary64(float_from_hex(vector["be_hex"]))
                    continue
                envelope = encode_binary64(float_from_hex(vector["be_hex"]))
                value = decode_binary64(envelope)
                if vector["accepted"]:
                    self.assertGreaterEqual(value, 0.0)
                    self.assertEqual(struct.pack(">d", value).hex(), vector["be_hex"])
                else:
                    self.assertLess(value, 0.0)

    def test_chronon_phase_unit_circle_cases(self):
        for vector in VECTORS["chronon_phase_cases"]:
            with self.subTest(vector=vector["name"]):
                phase = [
                    float_from_hex(vector["real_be_hex"]),
                    float_from_hex(vector["imag_be_hex"]),
                ]
                if vector["accepted"]:
                    wire = [encode_binary64(x) for x in phase]
                    decoded = [decode_binary64(x) for x in wire]
                    self.assertTrue(math.isclose(math.hypot(*decoded), 1.0, rel_tol=1e-9, abs_tol=1e-9))
                else:
                    with self.assertRaises(TemporalCoordinateError):
                        from formats.temporal_coordinate_v2 import _check_phase
                        _check_phase(phase)

    def test_full_temporal_frame_roundtrip_with_wide_counters_and_float_bits(self):
        actor = "host-α"
        other = "host-B"
        phase_value = float_from_hex("3fe6a09e667f3bcd")
        frame = {
            "actor_id": actor,
            "monotonic": {
                "actor_id": actor,
                "segment": 18446744073709551615,
                "elapsed_ns": 18446744073709551616000,
            },
            "wall": {
                "actor_id": actor,
                "utc_ns": -9223372036854775808,
                "sample_index": 9007199254740992,
            },
            "causal": {
                "actor_id": actor,
                "lamport": 18446744073709551616,
                "vector": {
                    actor: 18446744073709551616,
                    other: 18446744073709551615,
                },
            },
            "scheduler": {"scheduler_id": "mailcpu", "tick": 123456789012345678901234567890},
            "event_lambda": 9007199254740993,
            "chronon_phase": [phase_value, phase_value],
            "chemical_tau": -0.0,
        }
        wire = encode_temporal_frame(frame)
        self.assertEqual(wire["schema"], FRAME_SCHEMA)
        self.assertEqual(wire["numeric_profile"], NUMERIC_SCHEMA)
        self.assertEqual(wire["causal"]["vector"][0]["actor_id"], other)
        canonical_bytes(wire)
        restored = decode_temporal_frame(wire)
        self.assertEqual(restored["monotonic"]["elapsed_ns"], frame["monotonic"]["elapsed_ns"])
        self.assertEqual(restored["wall"]["utc_ns"], frame["wall"]["utc_ns"])
        self.assertEqual(restored["causal"], frame["causal"])
        self.assertEqual(restored["scheduler"], frame["scheduler"])
        self.assertEqual(struct.pack(">d", restored["chemical_tau"]).hex(), "8000000000000000")
        self.assertEqual(encode_temporal_frame(restored), wire)
        self.assertEqual(hashlib.sha256(canonical_bytes(wire)).hexdigest(), hashlib.sha256(canonical_bytes(encode_temporal_frame(restored))).hexdigest())

    def test_temporal_frame_rejects_actor_and_causal_inconsistency(self):
        actor = "host-a"
        frame = {
            "actor_id": actor,
            "monotonic": None,
            "wall": None,
            "causal": {
                "actor_id": actor,
                "lamport": 1,
                "vector": {"host-b": 1},
            },
            "scheduler": None,
            "event_lambda": None,
            "chronon_phase": None,
            "chemical_tau": None,
        }
        with self.assertRaises(TemporalCoordinateError):
            encode_temporal_frame(frame)
        frame["causal"]["vector"][actor] = 1
        frame["monotonic"] = {"actor_id": "another-host", "segment": 0, "elapsed_ns": 0}
        with self.assertRaises(TemporalCoordinateError):
            encode_temporal_frame(frame)

    def test_operation_span_v2_roundtrip_with_unsafe_nanoseconds(self):
        span = {
            "format": "in-formation.operation-span",
            "schema": "in-formation.operation-span/0.1",
            "attempt_id": "attempt-1",
            "span_id": "span-1",
            "operation_id": "host.prepare",
            "clock_actor_id": "host-a",
            "clock_segment_id": "0",
            "monotonic_start_ns": 18446744073709551616,
            "monotonic_end_ns": 18446744073709551999,
            "elapsed_ns": 383,
            "clock_status": "measured",
            "outcome": "succeeded",
            "exception_type": None,
            "context": {"role": "source_host"},
            "measurement_scope": "synchronous-call",
            "span_digest": "0" * 64,
        }
        wire = encode_operation_span_v2(span)
        self.assertEqual(wire["schema"], SPAN_SCHEMA)
        self.assertEqual(decode_integer(wire["monotonic_start_ns"]), span["monotonic_start_ns"])
        restored = decode_operation_span_v2(wire)
        self.assertEqual(restored["monotonic_start_ns"], span["monotonic_start_ns"])
        self.assertEqual(restored["monotonic_end_ns"], span["monotonic_end_ns"])
        self.assertEqual(restored["elapsed_ns"], span["elapsed_ns"])
        self.assertEqual(encode_operation_span_v2(restored), wire)

    def test_operation_span_rejects_mismatched_duration(self):
        span = {
            "format": "in-formation.operation-span",
            "schema": "in-formation.operation-span/0.1",
            "attempt_id": "attempt-1",
            "span_id": "span-1",
            "operation_id": "host.prepare",
            "clock_actor_id": "host-a",
            "clock_segment_id": "0",
            "monotonic_start_ns": 10,
            "monotonic_end_ns": 20,
            "elapsed_ns": 9,
            "clock_status": "measured",
            "outcome": "succeeded",
            "exception_type": None,
            "context": {},
            "measurement_scope": "synchronous-call",
            "span_digest": "0" * 64,
        }
        with self.assertRaises(TemporalCoordinateError):
            encode_operation_span_v2(span)


if __name__ == "__main__":
    unittest.main()
