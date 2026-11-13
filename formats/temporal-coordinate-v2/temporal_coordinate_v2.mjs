// Lossless temporal coordinate v2 codec. No unsafe integers or floating-point
// values are represented as ordinary JSON numbers on the wire.
import { createHash } from "node:crypto";

export const NUMERIC_SCHEMA = "in-formation.temporal-numeric/2.0";
const NUMERIC_FORMAT = "in-formation.temporal-numeric";
const INTEGER_ENCODING = "canonical-decimal-string";
const FLOAT_ENCODING = "ieee754-binary64-be-hex";
const FRAME_FORMAT = "in-formation.temporal-frame";
const FRAME_SCHEMA = "in-formation.temporal-frame/0.2";
const SPAN_FORMAT = "in-formation.operation-span";
const SPAN_SCHEMA = "in-formation.operation-span/0.2";

export class TemporalCoordinateError extends Error {
  constructor(message) {
    super(message);
    this.name = "TemporalCoordinateError";
  }
}

function reject(message) {
  throw new TemporalCoordinateError(message);
}
function exact(value, keys, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      Object.keys(value).length !== keys.length ||
      keys.some(key => !Object.hasOwn(value, key))) {
    reject(label + " must contain exactly " + keys.join(", "));
  }
  return value;
}
function integer(value, label, minimum = null) {
  if (typeof value !== "bigint") reject(label + " must be bigint");
  if (minimum !== null && value < minimum) reject(label + " must be non-negative");
  return value;
}
function unicodeScalarString(value) {
  return typeof value === "string" && !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value);
}
function text(value, label) {
  if (!unicodeScalarString(value) || !value.trim() || value.includes("\0")) {
    reject(label + " must be non-empty valid Unicode without NUL");
  }
  return value;
}
function envelope(kind, encoding, value) {
  return { format: NUMERIC_FORMAT, schema: NUMERIC_SCHEMA, kind, encoding, value };
}
function envelopeFields(value, kind, encoding) {
  const raw = exact(value, ["format", "schema", "kind", "encoding", "value"], "numeric envelope");
  if (raw.format !== NUMERIC_FORMAT || raw.schema !== NUMERIC_SCHEMA ||
      raw.kind !== kind || raw.encoding !== encoding) reject("numeric envelope profile mismatch");
  return raw.value;
}
export function encodeTemporalInteger(value) {
  return envelope("integer", INTEGER_ENCODING, integer(value, "integer").toString(10));
}
export function decodeTemporalInteger(value, minimum = null, maximum = null) {
  const token = envelopeFields(value, "integer", INTEGER_ENCODING);
  if (typeof token !== "string" || !/^(?:0|-?[1-9][0-9]*)$/.test(token)) {
    reject("non-canonical integer token");
  }
  const n = BigInt(token);
  if (minimum !== null && n < minimum) reject("integer below minimum");
  if (maximum !== null && n > maximum) reject("integer above maximum");
  return n;
}
function floatBytes(number) {
  const bytes = Buffer.alloc(8);
  bytes.writeDoubleBE(number, 0);
  return bytes.toString("hex");
}
export function encodeTemporalBinary64(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    reject("binary64 must be a finite number");
  }
  return envelope("binary64", FLOAT_ENCODING, floatBytes(value));
}
export function decodeTemporalBinary64(value) {
  const token = envelopeFields(value, "binary64", FLOAT_ENCODING);
  if (typeof token !== "string" || !/^[0-9a-f]{16}$/.test(token)) {
    reject("binary64 requires sixteen lowercase hex digits");
  }
  const n = Buffer.from(token, "hex").readDoubleBE(0);
  if (!Number.isFinite(n)) reject("binary64 must be finite");
  return n;
}
const sortUTF8 = (a, b) => Buffer.compare(Buffer.from(a, "utf8"), Buffer.from(b, "utf8"));

function checkPhase(values) {
  if (!Array.isArray(values) || values.length !== 2 ||
      values.some(v => typeof v !== "number" || !Number.isFinite(v)) ||
      Math.abs(Math.hypot(values[0], values[1]) - 1) > 1e-9) {
    reject("chronon phase must be a unit circle pair of finite binary64 values");
  }
}
function canonical(value, seen = new Set()) {
  if (value === null || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "string") {
    if (!unicodeScalarString(value)) reject("invalid Unicode scalar string in canonical metadata");
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) reject("canonical metadata forbids floats and unsafe integers");
    return JSON.stringify(value);
  }
  if (typeof value !== "object" || seen.has(value)) reject("unsupported or recursive canonical metadata");
  seen.add(value);
  let result;
  if (Array.isArray(value)) {
    result = "[" + value.map(v => canonical(v, seen)).join(",") + "]";
  } else {
    const keys = Object.keys(value);
    if (keys.some(key => !/^[\x00-\x7f]*$/.test(key))) reject("canonical object keys must be ASCII");
    result = "{" + keys.sort().map(key => JSON.stringify(key) + ":" + canonical(value[key], seen)).join(",") + "}";
  }
  seen.delete(value);
  return result;
}
const digest = value => createHash("sha256").update(canonical(value), "utf8").digest("hex");
const optionalInt = (value, label) => value === null ? null : encodeTemporalInteger(integer(value, label, 0n));
function actorBound(raw, actor, label, keys) {
  exact(raw, keys, label);
  if (text(raw.actor_id, label + ".actor_id") !== actor) reject(label + " actor mismatch");
}

export function encodeTemporalFrame(frame) {
  const src = exact(frame, ["actor_id", "monotonic", "wall", "causal", "scheduler",
    "event_lambda", "chronon_phase", "chemical_tau"], "temporal frame");
  const actor = text(src.actor_id, "frame.actor_id");
  const out = {
    format: FRAME_FORMAT, schema: FRAME_SCHEMA, numeric_profile: NUMERIC_SCHEMA,
    actor_id: actor, monotonic: null, wall: null, causal: null, scheduler: null,
    event_lambda: optionalInt(src.event_lambda, "event_lambda"),
    chronon_phase: null, chemical_tau: null,
  };
  if (src.monotonic !== null) {
    const m = src.monotonic;
    actorBound(m, actor, "monotonic", ["actor_id", "segment", "elapsed_ns"]);
    out.monotonic = { actor_id: actor,
      segment: encodeTemporalInteger(integer(m.segment, "segment", 0n)),
      elapsed_ns: encodeTemporalInteger(integer(m.elapsed_ns, "elapsed_ns", 0n)) };
  }
  if (src.wall !== null) {
    const w = src.wall;
    actorBound(w, actor, "wall", ["actor_id", "utc_ns", "sample_index"]);
    out.wall = { actor_id: actor,
      utc_ns: encodeTemporalInteger(integer(w.utc_ns, "utc_ns")),
      sample_index: encodeTemporalInteger(integer(w.sample_index, "sample_index", 0n)) };
  }
  if (src.causal !== null) {
    const c = src.causal;
    actorBound(c, actor, "causal", ["actor_id", "lamport", "vector"]);
    const lamport = integer(c.lamport, "lamport", 0n);
    if (!c.vector || typeof c.vector !== "object" || Array.isArray(c.vector)) reject("invalid causal vector");
    const actors = Object.keys(c.vector).sort(sortUTF8);
    if (!actors.length || !Object.hasOwn(c.vector, actor)) reject("causal vector must include its own actor");
    const entries = actors.map(id => {
      text(id, "causal vector actor");
      const counter = integer(c.vector[id], "causal counter", 0n);
      if (counter > lamport) reject("causal vector counter exceeds Lamport scalar");
      return { actor_id: id, counter: encodeTemporalInteger(counter) };
    });
    out.causal = { actor_id: actor, lamport: encodeTemporalInteger(lamport), vector: entries };
  }
  if (src.scheduler !== null) {
    const s = exact(src.scheduler, ["scheduler_id", "tick"], "scheduler");
    out.scheduler = { scheduler_id: text(s.scheduler_id, "scheduler_id"),
      tick: encodeTemporalInteger(integer(s.tick, "tick", 0n)) };
  }
  if (src.chronon_phase !== null) {
    checkPhase(src.chronon_phase);
    out.chronon_phase = src.chronon_phase.map(encodeTemporalBinary64);
  }
  if (src.chemical_tau !== null) {
    if (typeof src.chemical_tau !== "number" || !Number.isFinite(src.chemical_tau) ||
        src.chemical_tau < 0) reject("chemical_tau must be nonnegative finite number");
    out.chemical_tau = encodeTemporalBinary64(src.chemical_tau);
  }
  canonical(out);
  return out;
}

export function decodeTemporalFrame(frame) {
  const wire = exact(frame, ["format", "schema", "numeric_profile", "actor_id",
    "monotonic", "wall", "causal", "scheduler", "event_lambda", "chronon_phase", "chemical_tau"], "temporal frame v2");
  if (wire.format !== FRAME_FORMAT || wire.schema !== FRAME_SCHEMA ||
      wire.numeric_profile !== NUMERIC_SCHEMA) reject("temporal frame profile mismatch");
  const actor = text(wire.actor_id, "actor_id");
  const out = { actor_id: actor, monotonic: null, wall: null, causal: null,
    scheduler: null, event_lambda: null, chronon_phase: null, chemical_tau: null };
  if (wire.monotonic !== null) {
    const m = wire.monotonic;
    actorBound(m, actor, "monotonic", ["actor_id", "segment", "elapsed_ns"]);
    out.monotonic = { actor_id: actor,
      segment: decodeTemporalInteger(m.segment, 0n),
      elapsed_ns: decodeTemporalInteger(m.elapsed_ns, 0n) };
  }
  if (wire.wall !== null) {
    const w = wire.wall;
    actorBound(w, actor, "wall", ["actor_id", "utc_ns", "sample_index"]);
    out.wall = { actor_id: actor,
      utc_ns: decodeTemporalInteger(w.utc_ns),
      sample_index: decodeTemporalInteger(w.sample_index, 0n) };
  }
  if (wire.causal !== null) {
    const c = wire.causal;
    actorBound(c, actor, "causal", ["actor_id", "lamport", "vector"]);
    const lamport = decodeTemporalInteger(c.lamport, 0n);
    if (!Array.isArray(c.vector) || !c.vector.length) reject("empty causal vector");
    const vector = {};
    let previous = null;
    for (const entry of c.vector) {
      exact(entry, ["actor_id", "counter"], "causal vector entry");
      const id = text(entry.actor_id, "vector actor");
      if (previous !== null && sortUTF8(previous, id) >= 0) reject("causal vector not strictly UTF-8 sorted");
      const counter = decodeTemporalInteger(entry.counter, 0n);
      if (counter > lamport) reject("causal counter exceeds lamport");
      vector[id] = counter;
      previous = id;
    }
    if (!Object.hasOwn(vector, actor)) reject("causal vector must include own actor");
    out.causal = { actor_id: actor, lamport, vector };
  }
  if (wire.scheduler !== null) {
    const s = exact(wire.scheduler, ["scheduler_id", "tick"], "scheduler");
    out.scheduler = { scheduler_id: text(s.scheduler_id, "scheduler id"), tick: decodeTemporalInteger(s.tick, 0n) };
  }
  out.event_lambda = wire.event_lambda === null ? null : decodeTemporalInteger(wire.event_lambda, 0n);
  if (wire.chronon_phase !== null) {
    if (!Array.isArray(wire.chronon_phase) || wire.chronon_phase.length !== 2) reject("invalid phase shape");
    out.chronon_phase = wire.chronon_phase.map(decodeTemporalBinary64);
    checkPhase(out.chronon_phase);
  }
  if (wire.chemical_tau !== null) {
    out.chemical_tau = decodeTemporalBinary64(wire.chemical_tau);
    if (out.chemical_tau < 0) reject("chemical time cannot be negative");
  }
  canonical(wire);
  return out;
}

const SPAN_FIELDS = ["format", "schema", "attempt_id", "span_id", "operation_id",
  "clock_actor_id", "clock_segment_id", "monotonic_start_ns", "monotonic_end_ns",
  "elapsed_ns", "clock_status", "outcome", "exception_type", "context",
  "measurement_scope", "span_digest"];

function validateSpanTimes(raw, start, end, elapsed) {
  if (raw.clock_status === "measured") {
    if (end < start || elapsed === null || elapsed !== end - start) {
      reject("measured span endpoints and elapsed disagree");
    }
  } else if (raw.clock_status === "regressed") {
    if (elapsed !== null) reject("regressed span elapsed must be null");
  } else reject("unsupported span clock status");
}

export function encodeOperationSpanV2(span) {
  const src = exact(span, SPAN_FIELDS, "operation span");
  if (src.format !== SPAN_FORMAT ||
      !["in-formation.operation-span/0.1", SPAN_SCHEMA].includes(src.schema)) {
    reject("operation span format mismatch");
  }
  if (!src.context || typeof src.context !== "object" || Array.isArray(src.context)) {
    reject("operation span context must be an object");
  }
  const start = integer(src.monotonic_start_ns, "start", 0n);
  const end = integer(src.monotonic_end_ns, "end", 0n);
  const elapsed = src.elapsed_ns === null ? null : integer(src.elapsed_ns, "elapsed", 0n);
  validateSpanTimes(src, start, end, elapsed);
  const result = { ...src, schema: SPAN_SCHEMA,
    monotonic_start_ns: encodeTemporalInteger(start),
    monotonic_end_ns: encodeTemporalInteger(end),
    elapsed_ns: elapsed === null ? null : encodeTemporalInteger(elapsed) };
  const { span_digest: omitted, ...core } = result;
  result.span_digest = digest(core);
  return result;
}

export function decodeOperationSpanV2(span) {
  const src = exact(span, SPAN_FIELDS, "operation span v2");
  if (src.format !== SPAN_FORMAT || src.schema !== SPAN_SCHEMA) reject("span v2 profile mismatch");
  const { span_digest, ...core } = src;
  if (typeof span_digest !== "string" || digest(core) !== span_digest) reject("span v2 digest mismatch");
  const start = decodeTemporalInteger(src.monotonic_start_ns, 0n);
  const end = decodeTemporalInteger(src.monotonic_end_ns, 0n);
  const elapsed = src.elapsed_ns === null ? null : decodeTemporalInteger(src.elapsed_ns, 0n);
  validateSpanTimes(src, start, end, elapsed);
  return { ...src, monotonic_start_ns: start, monotonic_end_ns: end, elapsed_ns: elapsed };
}
