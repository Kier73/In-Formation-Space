# Temporal Coordinate Wire Format v2

**Profile:** \`in-formation.temporal-coordinate.v2\`  
**Numeric envelope:** \`in-formation.temporal-numeric/2.0\`  
**Status:** experimental codec and conformance suite; not yet adopted by IHP records.

## Motivation

Canonical Metadata Profile v1 intentionally excludes floating-point JSON numbers and integers outside the interoperable safe-integer range. That is the right constraint for byte-identical JSON metadata, but E-CPU temporal coordinates include values that must not be rounded into that range:

- monotonic nanosecond readings and operation-span endpoints;
- signed UTC nanosecond timestamps;
- Lamport counters and vector-clock counters;
- scheduler ticks and event counters;
- binary64 chronon phase components;
- binary64 chemical-time values.

Relaxing canonical metadata v1 would weaken an already shared contract. Converting temporal coordinates to ordinary JSON numbers would make some large integers lose precision in JavaScript and make floating-point digests depend on language-specific formatting.

This v2 wire profile carries typed numeric payloads as canonical strings, so the surrounding record remains a valid Canonical Metadata v1 object.

## Typed numeric envelope

Every temporal numeric coordinate is encoded as an object with exactly these fields:

    {
      "format": "in-formation.temporal-numeric",
      "schema": "in-formation.temporal-numeric/2.0",
      "kind": "integer" | "binary64",
      "encoding": "canonical-decimal-string" | "ieee754-binary64-be-hex",
      "value": "..."
    }

### Arbitrary-width integer

For \`kind = "integer"\`:

- \`encoding\` is \`canonical-decimal-string\`;
- \`value\` is the base-10 representation of an arbitrary-width integer;
- grammar is \`0\` or an optional minus followed by a non-zero digit and then digits;
- no plus sign, leading zero, whitespace, decimal point, exponent, or negative zero is allowed;
- the decoded mathematical value is an exact integer and is never routed through binary floating point.

Field-level schemas determine signedness and constraints. For example, monotonic elapsed time, scheduler ticks, Lamport values, and vector counters are non-negative; UTC nanoseconds are signed.

### Binary64

For \`kind = "binary64"\`:

- \`encoding\` is \`ieee754-binary64-be-hex\`;
- \`value\` is exactly 16 lowercase hexadecimal digits;
- the digits represent the 8 IEEE-754 binary64 bytes in network (big-endian) order;
- NaN and positive/negative infinity are rejected;
- finite values round-trip bit-for-bit, including negative zero and subnormal values;
- semantic range checks occur after decoding. Chemical time must be numerically non-negative. Chronon phase must satisfy the E-CPU unit-circle check.

This is a bit-level transport encoding, not a decimal approximation. It does not imply that cross-host clocks share an epoch or that two clock domains can be compared.

## Temporal frame v2

A frame has the following shape:

    {
      "format": "in-formation.temporal-frame",
      "schema": "in-formation.temporal-frame/0.2",
      "numeric_profile": "in-formation.temporal-numeric/2.0",
      "actor_id": "...",
      "monotonic": null | {
        "actor_id": "...",
        "segment": <integer envelope>,
        "elapsed_ns": <integer envelope>
      },
      "wall": null | {
        "actor_id": "...",
        "utc_ns": <integer envelope>,
        "sample_index": <integer envelope>
      },
      "causal": null | {
        "actor_id": "...",
        "lamport": <integer envelope>,
        "vector": [
          {"actor_id": "...", "counter": <integer envelope>}
        ]
      },
      "scheduler": null | {
        "scheduler_id": "...",
        "tick": <integer envelope>
      },
      "event_lambda": null | <integer envelope>,
      "chronon_phase": null | [<binary64 envelope>, <binary64 envelope>],
      "chemical_tau": null | <binary64 envelope>
    }

Causal vector entries are an array rather than an object keyed by actor identity. This avoids imposing Canonical Metadata v1's ASCII object-key restriction on actor IDs. Entries are sorted by the UTF-8 byte sequence of \`actor_id\`; actor IDs must be valid Unicode scalar strings and unique. The stamp's own actor must appear in the vector. Each vector counter must be less than or equal to the Lamport scalar.

Every temporal coordinate remains separately typed. No conversion between wall, monotonic, causal, scheduler, event, chronon, or chemical time is defined.

## Operation span v2

Operation span v2 keeps the v0.1 semantic fields but uses typed integer envelopes for \`monotonic_start_ns\`, \`monotonic_end_ns\`, and non-null \`elapsed_ns\`. Its schema identifier is \`in-formation.operation-span/0.2\`. The span digest is SHA-256 over the canonical metadata v1 bytes of the v2 span object with \`span_digest\` omitted.

This prevents a valid monotonic timestamp from being rejected merely because it exceeds JavaScript's safe-integer range.

## Frame and span identity

- A temporal numeric envelope is itself ordinary Canonical Metadata v1.
- A frame digest, where a containing protocol needs one, is SHA-256 over the frame object's canonical metadata v1 bytes.
- A span digest is SHA-256 over the v2 span object's canonical metadata v1 bytes without the digest field.
- A record artifact is canonical metadata v1 bytes followed by exactly one LF byte.
- These digests identify serialized values; they do not authenticate authorship or prove that a process actually sampled a clock.

## Reversibility and validation rules

An implementation must satisfy all of the following:

1. Integer encode/decode is lossless for arbitrary-width signed integers.
2. Binary64 encode/decode preserves all 64 bits for finite IEEE-754 values.
3. Invalid numeric envelopes are rejected: unknown format/schema/kind/encoding, extra/missing properties, malformed decimal strings, wrong hex length/case, and non-finite bit patterns.
4. Integer field constraints are applied after exact decoding, never by coercing to floating point.
5. Frame validation preserves actor binding, clock-segment identity, vector uniqueness/order, causal self-entry, and Lamport/vector consistency.
6. Chronon phase is finite and remains within the E-CPU unit-circle tolerance.
7. Chemical time is finite and non-negative. Negative zero is accepted and preserved bit-for-bit because its numeric value is zero; it is not rewritten to positive zero.
8. Canonical Metadata v1 validation is applied to the enclosing v2 object before digesting it.

## Conformance vectors

The first codec corpus is \`formats/temporal-coordinate-v2/vectors.json\`. It includes arbitrary-width integer values, signed nanoseconds, safe-integer overflow, binary64 positive/negative zero, subnormals, extrema, a standard irrational value, phase pairs, and invalid numeric envelopes.

The same vectors are consumed by Python and Go tests. They are not application-level record fixtures. A later version can add Node.js once the E-CPU/JavaScript runtime has a stable typed-frame consumer.

## Adoption status and migration

IHP-001 v0.1 and IHP-004 currently remain unchanged. They continue to use the v0.1 record schema and fail closed on floating-point values or integers outside Canonical Metadata v1's safe range in the Go verifier.

Adopting v2 requires a new IHP operation-record schema revision that consistently upgrades:
- the source and receiver temporal frames;
- sender completion and receiver start frames inside handoff payloads/witnesses;
- operation-span monotonic endpoints and elapsed values;
- payload, handoff, span, and record digest calculation over the v2 wire objects.

A migration must not rewrite or reinterpret existing v0.1 digests. Both versions should remain independently decodable and explicitly identified.

## Non-goals

The v2 profile does not synchronize wall clocks, calibrate monotonic domains, infer cross-host duration, establish hardware identity, authenticate a producer, or prove the truth of a recorded operation. It only supplies lossless typed representations for temporal numeric coordinates.
