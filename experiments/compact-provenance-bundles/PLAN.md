# CPB-001 execution plan

## Question

Reduce repeated provenance cost while preserving exact standalone capsule identity and replay evidence.

## Procedure

1. Reuse PRC-001 capsule creation, verification receipts, and replay functions.
2. Reuse the 16 RCN-001 workloads, three E-CPU compiler routes, and six SRE-002 codecs.
3. Generate and replay every PRC-001 standalone capsule over its complete finite Boolean domain.
4. Compress only the canonical JSON header with zlib; decompress it, reconstruct the original raw capsule bytes, and replay again.
5. Build six bundles grouped by codec, each with one shared source/toolchain/codec manifest.
6. Build one global bundle containing all 288 capsules under one shared manifest.
7. Decode every bundle and require byte-for-byte reconstruction of the original standalone capsules.
8. Probe compressed-header/payload tampering and bundle outer-digest, entry-header, entry-payload, and manifest tampering.
9. Preserve per-codec and aggregate sizes, timings, exact byte identity, source pins, and evidence digests.

## Acceptance

All 288 compressed capsules must reconstruct and replay the exact PRC-001 capsule. All six per-codec bundles and the global bundle must reconstruct every original capsule byte-for-byte. Every compressed and bundled integrity probe must be rejected. Complete Boolean domains and Semantic TranslationContract comparisons must pass before and after compressed wrapping.

## Limitations

This is a finite benchmark of the 16 selected workloads. Zlib byte streams may vary across implementations, although decoded canonical metadata and payloads remain exact. Bundle-local entries require their shared manifest; a detached entry is not independently portable. SHA-256 does not provide origin authentication or execution authorization.

## First verified result

The pinned [CPB-001 workflow](https://github.com/Kier73/In-Formation-Space/actions/runs/43319093051) passed all focused tests, pre/post-compression semantic replay, per-encoding bundle reconstruction, global bundle reconstruction, and tamper rejection. It covered 16 workloads, 1,364 input rows, 288 capsules, and 49,104 pre/post-compression semantic comparisons. See the [retained measurement record](results/ci-run-43319093051.md).

The current shared-manifest bundle remains larger than header-compressed standalone capsules because local entry headers are still verbose JSON. CPB-002 should compare packed/compressed local entry metadata with a shared manifest and preserve random access.


## Final PR-head acceptance

The final pinned [CPB-001 workflow](https://github.com/Kier73/In-Formation-Space/actions/runs/43319482543) passed capsule/bundle/E-CPU tests, 49,104 pre/post-compression semantic comparisons, exact standalone reconstruction for all 288 bundle entries, and nested tamper rejection. See the [final-head evidence record](results/ci-run-43319482543.md).
