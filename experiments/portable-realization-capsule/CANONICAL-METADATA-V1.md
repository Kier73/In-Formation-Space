# Canonical Metadata Profile v1

**Applies to:** `in-formation-space.portable-realization.v1`  
**Status:** normative for PRC v1 metadata  
**Purpose:** byte-identical header reconstruction by independent implementations.

## Data model

A v1 metadata value is one of:

- null;
- a boolean;
- a Unicode string containing only valid Unicode scalar values;
- an integer in the inclusive range `-(2^53 - 1)` through `2^53 - 1`;
- an array of v1 metadata values;
- an object whose keys are ASCII strings and whose values are v1 metadata values.

Floating-point values are not part of v1 metadata. Object keys outside ASCII are not permitted. These are format constraints, not Python-only implementation details.

## Canonical encoding

1. Encode the JSON document as UTF-8.
2. Sort object keys in ascending ASCII/byte order.
3. Emit no insignificant whitespace: separators are comma and colon with no following spaces.
4. Emit non-ASCII string values as UTF-8 characters rather than converting them to JSON Unicode escape sequences.
5. Use standard JSON escaping for quotation marks, reverse solidus, and control characters.
6. Do not emit a byte-order mark.
7. Reject duplicate object keys. A decoder that parses JSON and re-encodes it canonically will detect duplicates because the re-encoded object cannot preserve repeated keys.
8. Reject any value outside the data model before computing identity digests.

Because object keys are ASCII and numbers are safe integers only, the ordering and numeric representation used by the Python encoder can be reproduced by the independent ECMAScript implementation in `verify_capsule.mjs`. String values are checked for valid Unicode scalar sequences before encoding.

## Digest layers

For a capsule:

- `receipt_sha256` is SHA-256 over the canonical receipt object with `receipt_sha256` omitted.
- `capsule_sha256` is SHA-256 over the canonical core object with both outer digest fields omitted.
- `header_sha256` is SHA-256 over the canonical header object with only `header_sha256` omitted; the `capsule_sha256` field remains included.
- `payload.sha256` is SHA-256 over the exact opaque payload bytes.

These digests establish content identity and integrity only. They do not establish author identity, trust, authorization, or semantic correctness.

## Versioning

A future need for floating-point metadata, non-ASCII object keys, a different canonicalization algorithm, or values outside the safe-integer range requires an explicit versioned profile. A decoder must reject unsupported profiles rather than silently normalizing them.
