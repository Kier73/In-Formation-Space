import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  NUMERIC_SCHEMA,
  TemporalCoordinateError,
  decodeTemporalBinary64,
  decodeTemporalFrame,
  decodeTemporalInteger,
  decodeOperationSpanV2,
  encodeTemporalBinary64,
  encodeTemporalFrame,
  encodeTemporalInteger,
  encodeOperationSpanV2,
} from "./temporal_coordinate_v2.mjs";

const vectors = JSON.parse(readFileSync(new URL("./vectors.json", import.meta.url), "utf8"));

function doubleFromHex(hex) {
  return Buffer.from(hex, "hex").readDoubleBE(0);
}

function doubleHex(value) {
  const buffer = Buffer.allocUnsafe(8);
  buffer.writeDoubleBE(value, 0);
  return buffer.toString("hex");
}

test("arbitrary-width integer vectors round trip through canonical decimal strings", () => {
  for (const vector of vectors.integers) {
    const value = BigInt(vector.decimal);
    const encoded = encodeTemporalInteger(value);
    assert.equal(encoded.schema, NUMERIC_SCHEMA, vector.name);
    assert.equal(encoded.value, vector.decimal, vector.name);
    assert.equal(decodeTemporalInteger(encoded), value, vector.name);
  }
});

test("noncanonical integer tokens are rejected", () => {
  for (const token of vectors.invalid_integer_tokens) {
    assert.throws(() => decodeTemporalInteger({
      format: "in-formation.temporal-numeric",
      schema: NUMERIC_SCHEMA,
      kind: "integer",
      encoding: "canonical-decimal-string",
      value: token,
    }), TemporalCoordinateError, token);
  }
});

test("binary64 vectors preserve all bits including negative zero and subnormals", () => {
  for (const vector of vectors.binary64) {
    const value = doubleFromHex(vector.be_hex);
    const encoded = encodeTemporalBinary64(value);
    assert.equal(encoded.value, vector.be_hex, vector.name);
    assert.equal(doubleHex(decodeTemporalBinary64(encoded)), vector.be_hex, vector.name);
  }
});

test("malformed and nonfinite binary64 envelopes are rejected", () => {
  for (const vector of vectors.invalid_binary64_tokens) {
    assert.throws(() => decodeTemporalBinary64({
      format: "in-formation.temporal-numeric",
      schema: NUMERIC_SCHEMA,
      kind: "binary64",
      encoding: "ieee754-binary64-be-hex",
      value: vector.be_hex,
    }), TemporalCoordinateError, vector.name);
  }
});

test("full temporal frame round trips exact wide integers, unicode actors and float bits", () => {
  const actor = "host-α";
  const other = "host-B";
  const sqrtHalf = doubleFromHex("3fe6a09e667f3bcd");
  const frame = {
    actor_id: actor,
    monotonic: { actor_id: actor, segment: 18446744073709551615n, elapsed_ns: 18446744073709551616000n },
    wall: { actor_id: actor, utc_ns: -9223372036854775808n, sample_index: 9007199254740992n },
    causal: {
      actor_id: actor,
      lamport: 18446744073709551616n,
      vector: { [actor]: 18446744073709551616n, [other]: 18446744073709551615n },
    },
    scheduler: { scheduler_id: "mailcpu", tick: 123456789012345678901234567890n },
    event_lambda: 9007199254740993n,
    chronon_phase: [sqrtHalf, sqrtHalf],
    chemical_tau: -0,
  };
  const encoded = encodeTemporalFrame(frame);
  assert.equal(encoded.schema, "in-formation.temporal-frame/0.2");
  assert.deepEqual(encoded.causal.vector.map(item => item.actor_id), [other, actor]);
  const restored = decodeTemporalFrame(encoded);
  assert.equal(restored.monotonic.elapsed_ns, frame.monotonic.elapsed_ns);
  assert.equal(restored.wall.utc_ns, frame.wall.utc_ns);
  assert.equal(restored.causal.lamport, frame.causal.lamport);
  assert.equal(restored.scheduler.tick, frame.scheduler.tick);
  assert.equal(doubleHex(restored.chemical_tau), "8000000000000000");
  assert.deepEqual(encodeTemporalFrame(restored), encoded);
});

test("frame validation rejects missing own vector actor, invalid phase and negative chemical time", () => {
  const frame = {
    actor_id: "host-a",
    monotonic: null,
    wall: null,
    causal: { actor_id: "host-a", lamport: 1n, vector: { "host-b": 1n } },
    scheduler: null,
    event_lambda: null,
    chronon_phase: null,
    chemical_tau: null,
  };
  assert.throws(() => encodeTemporalFrame(frame), TemporalCoordinateError);
  frame.causal.vector["host-a"] = 1n;
  frame.chronon_phase = [1, 1];
  assert.throws(() => encodeTemporalFrame(frame), TemporalCoordinateError);
  frame.chronon_phase = null;
  frame.chemical_tau = -1;
  assert.throws(() => encodeTemporalFrame(frame), TemporalCoordinateError);
});

test("operation span v2 preserves unsafe nanosecond endpoints and validates digest", () => {
  const span = {
    format: "in-formation.operation-span",
    schema: "in-formation.operation-span/0.1",
    attempt_id: "attempt-1",
    span_id: "span-1",
    operation_id: "host.prepare",
    clock_actor_id: "host-a",
    clock_segment_id: "0",
    monotonic_start_ns: 18446744073709551616n,
    monotonic_end_ns: 18446744073709551999n,
    elapsed_ns: 383n,
    clock_status: "measured",
    outcome: "succeeded",
    exception_type: null,
    context: { role: "source_host" },
    measurement_scope: "synchronous-call",
    span_digest: "0".repeat(64),
  };
  const encoded = encodeOperationSpanV2(span);
  assert.equal(encoded.schema, "in-formation.operation-span/0.2");
  const decoded = decodeOperationSpanV2(encoded);
  assert.equal(decoded.monotonic_start_ns, span.monotonic_start_ns);
  assert.equal(decoded.monotonic_end_ns, span.monotonic_end_ns);
  assert.deepEqual(encodeOperationSpanV2(decoded), encoded);
  const tampered = { ...encoded, elapsed_ns: encodeTemporalInteger(382n) };
  assert.throws(() => decodeOperationSpanV2(tampered), TemporalCoordinateError);
});
