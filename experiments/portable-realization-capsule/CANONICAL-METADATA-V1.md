# Canonical Metadata Profile v1

**Applies to:** `in-formation-space.portable-realization.v1`  
**Status:** normative for PRC v1 metadata

The canonical data model, UTF-8 byte encoding, numeric restrictions, object-key rules, artifact framing, and shared conformance vectors are defined in the repository-level [Canonical Metadata Profile v1](../../formats/canonical-metadata-v1/README.md).

PRC-001 uses that profile for its metadata header and all nested receipt, source, realization, interface, codec, verification, toolchain, and payload-descriptor objects. Its independent Node.js receiver and Python encoder are exercised by the shared [cross-runtime vector corpus](../../formats/canonical-metadata-v1/vectors.json), including the actual PRC encoder call site.

## Capsule digest layers

For a capsule:

- `receipt_sha256` is SHA-256 over the canonical receipt object with `receipt_sha256` omitted.
- `capsule_sha256` is SHA-256 over the canonical core object with both outer digest fields omitted.
- `header_sha256` is SHA-256 over the canonical header object with only `header_sha256` omitted; the `capsule_sha256` field remains included.
- `payload.sha256` is SHA-256 over the exact opaque payload bytes.

These digests establish content identity and integrity only. They do not establish author identity, trust, authorization, source truth, or semantic correctness.

## Versioning

A need for floating-point metadata, non-ASCII object keys, integers outside the safe-integer range, a different string-escaping rule, or another canonicalization algorithm requires an explicit new profile version. PRC v1 readers reject unsupported profiles rather than silently widening v1.
