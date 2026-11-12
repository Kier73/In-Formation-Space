# Compact Provenance and Capsule Bundles

**Experiment:** CPB-001 · Compressed standalone capsules and shared-provenance bundles  
**Status:** candidate; pinned cross-repository CI is the acceptance gate.

CPB-001 continues PRC-001. Its first result showed that the canonical metadata header averages about 2.5 KB per capsule. For compact binary model payloads, metadata can exceed the data itself. This experiment compares two exact ways to reduce that repeated cost without changing the underlying realization.

## Formats compared

1. **PRC-001 raw standalone capsule** — unchanged baseline, full canonical JSON header plus exact codec payload.
2. **Compressed standalone capsule** — zlib-compresses only the canonical JSON header; decompression reconstructs the exact PRC-001 capsule and invokes its original validator.
3. **Per-encoding shared-provenance bundle** — packages 48 standalone capsules of one codec under a single shared manifest.
4. **Global shared-provenance bundle** — packages all 288 workload/compiler/codec capsules under one common manifest.

The shared manifest stores invariant source repository/revision, realization repository/revision, toolchain pins, and codec schema registry once. Each entry retains its source Ground and typed-program digests, dense/sparse model identities, compiler route, interface, complete-domain verification receipt, codec identity, and exact payload digest.

A bundle is portable as a complete bundle. Extracting one local entry without its manifest is intentionally insufficient; the decoder uses the manifest to reconstruct the original standalone PRC-001 capsule and then runs the PRC-001 validator.

## Verification

CPB-001 reuses the exact 16 RCN-001 workloads and six SRE-002 codecs. Every standalone PRC-001 capsule is independently verified and replayed over the complete Boolean domain. It is then wrapped in the compressed standalone form, decoded, and its reconstructed PRC-001 bytes are replayed again.

All 288 raw capsules are then encoded into six per-encoding bundles and one global bundle. Every bundle decoder must reconstruct the exact original standalone capsule bytes. Header and payload tampering is probed in compressed standalone capsules. Bundle-level, entry-header and entry-payload tampering is probed with the outer bundle digest recomputed, requiring the inner integrity checks to reject it.

## Measurements

The runner records raw and compressed standalone sizes, raw/compressed header sizes, saved bytes, per-codec bundle sizes, global bundle size, shared manifest/entry overhead, exact byte reconstruction counts, integrity rejection, and local encode/decode timings.

## Evidence boundary

Zlib output is exact with respect to the decompressed canonical header and original payload, but compressed bytes may vary across zlib implementations or versions. Bundle entries depend on their manifest and are not standalone when detached. SHA-256 is integrity/identity, not authentication or authorization. Neither format is integrated into E-CPU transport, admission, durable storage, or remote execution yet.