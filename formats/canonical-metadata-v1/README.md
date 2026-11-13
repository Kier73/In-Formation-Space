# Canonical Metadata Profile v1

**Profile ID:** \`in-formation-space.canonical-metadata.v1\`  
**Status:** shared repository profile  
**Current adopters:** Portable Realization Capsule v1; IHP-004 Go reconstruction for the observed safe-integer operation-record subset.

## Purpose

Independent implementations must produce identical UTF-8 bytes before a digest can mean the same thing in different languages. This profile defines the structured metadata domain and byte encoding used by the repository's cross-language evidence and realization formats.

This is a deliberately restricted JSON profile. It is not full JSON Canonicalization Scheme (RFC 8785), because it excludes floating-point values and requires interoperable safe integers.

## Data model

A v1 metadata value is one of:

- \`null\`;
- a boolean;
- a Unicode string containing only valid Unicode scalar values;
- an integer in the inclusive range \`-(2^53 - 1)\` through \`2^53 - 1\`;
- an array of v1 metadata values;
- an object whose keys are ASCII strings and whose values are v1 metadata values.

Floating-point values are not part of the data model. Boolean values are not integers. Object keys outside ASCII are not permitted. Recursive values and values unsupported by JSON are not permitted.

These are format constraints, not language-specific implementation choices.

## Canonical encoding

Given a value in the v1 data model:

1. Encode the canonical document as UTF-8, without a byte-order mark.
2. Sort object keys in ascending ASCII/byte order.
3. Emit no insignificant whitespace: separators are comma and colon with no following spaces.
4. Emit non-ASCII string values as UTF-8 characters rather than converting them to JSON Unicode escape sequences.
5. Use standard JSON escaping for quotation marks, reverse solidus, and control characters.
6. Do not specially escape HTML-sensitive characters such as less-than, greater-than, or ampersand.
7. Preserve U+2028 and U+2029 as literal UTF-8 code points.
8. Reject duplicate object keys. A decoder that parses and then canonically re-encodes a document must compare the result with the exact input bytes; repeated keys cannot survive this equality check.
9. Reject any value outside the data model before computing identity digests.

Numeric tokens must be canonical base-10 safe integers. Fractional values, exponent notation, negative zero, and unsafe integers are rejected. A raw JSON document that parses to a valid value but uses a non-canonical representation is not itself a canonical document.

## Digest layers

An identity digest over a structured metadata value is SHA-256 over that value's canonical UTF-8 bytes. It does not include a trailing line-feed byte unless the containing format explicitly defines the digest over file bytes.

A file that stores one canonical metadata object uses the canonical bytes followed by exactly one LF byte. The file's artifact digest, when required, is SHA-256 over the exact file bytes including that LF. The object digest and artifact-byte digest are distinct identities.

Opaque binary payloads are not canonicalized by this profile; their digests are computed over their exact bytes.

## Conformance corpus

The shared test corpus is:

    formats/canonical-metadata-v1/test-vectors.json

It contains valid values with expected canonical UTF-8 strings and SHA-256 digests, values that must be rejected by the data model, and non-canonical JSON documents that may parse but must fail byte-for-byte canonical equality.

Independent implementations should consume the same corpus rather than translate examples into language-specific fixtures. This is intended to catch differences in:

- safe-integer parsing and serialization;
- object-key ordering;
- duplicate-key handling;
- negative zero and exponent notation;
- valid Unicode scalar strings and escaped Unicode;
- control-character escaping;
- line separators U+2028 and U+2029;
- solidus and HTML-character escaping.

## Adoption

- Portable Realization Capsule v1 adopts this profile for its header metadata.
- IHP-004 adopts this profile for the safe-integer record values emitted by the current IHP-001 hosts. IHP-001 v0.1 permits optional decimal temporal fields that the Go verifier deliberately rejects; IHP records need a versioned schema revision before the shared profile can be claimed for every v0.1-valid record.
- New formats should identify the profile ID in their own versioned schema or format document. They must not silently broaden the data model or substitute another canonicalization algorithm.

## Versioning

A future need for floating-point metadata, non-ASCII object keys, values outside the safe-integer range, or a different canonicalization algorithm requires an explicit profile version. A decoder must reject unsupported profile versions rather than silently normalizing them.
