# Canonical Metadata Profile v1

**Format ID:** `canonical-metadata-v1`  
**Status:** shared normative format for the repository's portable metadata artifacts  
**Implementations exercised:** Python, Go, and Node.js

This profile defines a deliberately small JSON data model for records whose exact identity must be reconstructed by independent implementations. It is not a general-purpose JSON canonicalization standard and is not a claim of conformance to RFC 8785/JCS.

## Where it applies

- Portable Realization Capsule (PRC-001) metadata v1.
- The safe-integer metadata subset used by IHP-004 cross-language host evidence reconstruction.

The PRC application record remains at [CANONICAL-METADATA-V1.md](../../experiments/portable-realization-capsule/CANONICAL-METADATA-V1.md). IHP-004's application and evidence boundaries remain in its [experiment note](../../bridges/observation-path/cross_language_verifier/IHP-004-GO-CROSS-LANGUAGE-VERIFIER.md). Those documents define what each artifact means; this document is the shared source of truth for canonical metadata values and bytes.

## Data model

A v1 value is exactly one of:

- `null`;
- a Boolean;
- a Unicode string containing only Unicode scalar values (no unpaired surrogates);
- an integer in the inclusive range `-(2^53 - 1)` through `2^53 - 1`;
- an ordered array of v1 values;
- an object whose keys are ASCII strings and whose values are v1 values.

Floating-point values are not part of the profile. Decimal and exponent-form numeric tokens, negative zero, non-finite values, integers outside the safe range, non-ASCII object keys, invalid Unicode strings, duplicate object keys, and values outside the data model are rejected. A Boolean is not an integer for this purpose.

## Canonical encoding

For an accepted v1 object:

1. Encode as UTF-8 without a byte-order mark.
2. Sort object keys in ascending ASCII byte order. Array order is preserved.
3. Emit no insignificant whitespace: commas and colons have no surrounding spaces.
4. Encode strings as UTF-8 scalar values. Do not normalize Unicode and do not escape non-ASCII scalar values.
5. Escape quotation marks, reverse solidus, and control characters using the JSON string escapes emitted by the profile implementations. Do not escape solidus, or HTML-sensitive characters such as `<`, `>`, and `&`.
6. Emit integers in canonical base-10 form: `0` or an optional minus sign followed by a non-zero digit and then digits. No leading plus, leading zero, decimal point, exponent, or `-0` is permitted.
7. Reject duplicate object keys before accepting an artifact. Parsing and re-encoding must not silently resolve duplicate-key ambiguity.

A canonical file artifact is the canonical JSON bytes followed by **exactly one LF byte** (`0x0a`). CRLF, no final LF, multiple final LFs, a BOM, extra JSON values, or any other byte representation is not canonical.

## Digest layers

- An object digest is SHA-256 over canonical JSON bytes, excluding the terminating LF.
- An artifact-byte digest is SHA-256 over the exact canonical file bytes, including the one LF.
- Digests establish content identity and integrity only. They do not establish author identity, trust, authorization, source truth, or semantic correctness.

## Versioning

A need for floating-point metadata, non-ASCII object keys, integers outside the safe range, a different string-escaping rule, or another canonicalization algorithm requires an explicit new profile version. Implementations must reject unsupported profiles rather than silently widening v1.

## Differential conformance corpus

[**vectors.json**](vectors.json) is a shared corpus consumed by the Python, Go, and Node.js tests. It includes positive canonical artifacts and adversarial inputs for numeric lexical forms, safe-integer boundaries, Unicode, duplicate keys, key ordering, whitespace, escaping, framing, and root type.

Run the focused tests from the repository root:

```bash
python formats/canonical-metadata-v1/test_python.py
node formats/canonical-metadata-v1/test_node.mjs
(cd bridges/observation-path/cross_language_verifier && go test -count=1 -run TestSharedCanonicalMetadataV1Vectors ./...)
```

The corpus tests verify the same accept/reject decision and, for accepted cases, the exact canonical bytes and SHA-256 object digest. They do not prove that the profile itself is the only reasonable encoding or that all consumers have adopted it.
