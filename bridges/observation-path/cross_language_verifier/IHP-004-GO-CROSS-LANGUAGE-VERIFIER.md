# IHP-004: Go cross-language reconstruction of hosted operation evidence

**Experiment:** IHP-004  
**Status:** Go implementation, actual IHP-001 fixtures, regression tests, and a fifth-host workflow added on a review branch; live fifth-host execution pending  
**Format:** cross-language host reconstruction report v0.1  
**Input run:** [IHP-003 live run 43360810370](https://github.com/Kier73/In-Formation-Space/actions/runs/43360810370)

## Question

Can an independently authored implementation in another language reconstruct the IHP-001 source-to-receiver causal edge from the exact artifact bytes, without importing the Python validators or treating the Python report as its source of truth?

IHP-003 established implementation diversity between two Python implementations. IHP-004 adds a Go implementation using only the Go standard library. Its fifth hosted job receives the original source and receiver artifacts, independently reconstructs their record integrity and causal edge, and compares its evidence-bearing report projection with the separately generated IHP-003 Python report.

The Go implementation reads the original host records directly. The Python report is used only as a parity check after Go has reconstructed the edge; it is not an input to the reconstruction.

## Why this tests something different

A second implementation in the same language can still inherit language-runtime assumptions about parsing, numeric values, escaping, and serialization. A second implementation in a different language exposes those assumptions.

IHP-004 therefore tests two related questions:

1. Does Go independently reconstruct the same record, span, payload, handoff, and causal evidence?
2. Can a portable canonicalization rule be stated precisely enough that two runtimes compute the same digest from the same structured value?

The experiment deliberately does not hide an unresolved numeric-serialization problem behind a passing result.

## Portable canonical JSON profile used by IHP-004

IHP-004 adopts the same restricted data model now being exercised by the parallel PRC-001 cross-language receiver work in [Canonical Metadata Profile v1](https://github.com/Kier73/In-Formation-Space/blob/research/prc-cross-language-verifier/experiments/portable-realization-capsule/CANONICAL-METADATA-V1.md):

- Values may be null, booleans, Unicode strings containing only valid Unicode scalar values, integers, arrays, and objects.
- Integers must be in the interoperable safe range from -(2^53 - 1) through +(2^53 - 1). Floating-point values are not part of the profile.
- Object keys must be ASCII strings and are sorted in ascending ASCII/byte order.
- Insignificant whitespace is omitted.
- String values are encoded as UTF-8; non-ASCII characters remain UTF-8 rather than being converted to Unicode escape sequences.
- Standard JSON escaping is used for quotation marks, reverse solidus, and control characters. HTML-sensitive characters are not specially escaped.
- U+2028 and U+2029 remain literal UTF-8 code points.
- Duplicate object keys and values outside the data model are rejected.
- A file artifact is the canonical JSON bytes followed by exactly one LF byte. Object digests are SHA-256 over canonical JSON bytes without that trailing LF. Artifact-subject digests are SHA-256 over the exact file bytes, including the LF.

The Go parser uses json.Decoder.UseNumber() so numeric tokens are not first converted through binary floating point. It validates the safe-integer range, ASCII object keys, and Unicode scalar strings before encoding. Decimal, exponent-form, negative-zero, unsafe-integer, non-ASCII-key, or invalid-Unicode inputs are rejected rather than silently normalized differently from Python or JavaScript.

**Important scope of this profile:** the existing IHP-001 v0.1 JSON Schema allows decimal numbers in optional temporal fields such as chronon_phase and chemical_tau. The current Go implementation rejects those values anywhere in a record. It therefore verifies the observed safe-integer IHP-001 records, not every theoretically schema-valid v0.1 record. This is an explicit fail-closed subset, not a claim that the v0.1 format already has a complete cross-language number specification.

The parallel PRC-001 work has already formalized the same restrictions for its v1 metadata. The useful next step is to consolidate this common profile into one repository-level normative specification that IHP and PRC can both reference, rather than fork two canonicalization rules.

## Implementation and topology

The Go module lives at:

    bridges/observation-path/cross_language_verifier/

It has no third-party Go dependencies. The implementation is split into:

- canonical.go — canonical JSON bytes, number-domain checks, and SHA-256 helpers;
- record_validation.go — exact field, record, span, host, frame, and digest validation;
- reconstruct.go — artifact binding, handoff reconstruction, local clock endpoint checks, and vector-clock partial order;
- reports.go — Go report and attestation-predicate construction, plus parity comparison with the Python evidence projection;
- cmd/ihp004/ — command-line entry point;
- verifier_test.go — live evidence fixture tests and adversarial mutation tests.

The fifth hosted job is named cross_language_verifier_host. It runs only after source, receiver, primary verifier, and diverse Python verifier jobs have all succeeded on main. It downloads the exact source and receiver artifacts plus the IHP-003 Python report. Go reconstructs the host evidence directly, compares the evidence-bearing projection with the Python report, validates its own report and predicate schemas, attests its exact report bytes, and preserves the report as cross-language-host-reconstruction-report.

The primary Python verifier remains responsible for verifying the source and receiver Sigstore artifact attestations. The Go verifier does not re-verify those signatures. It provides a distinct language and implementation for content and causal reconstruction.

## Preserved live fixtures

The Go test corpus includes the exact source and receiver record files and the IHP-003 diverse report from run 43360810370. They are retained as reproducible fixtures, not treated as substitutes for the current run's signed artifacts.

Expected evidence identities:

| Evidence | Expected value |
|---|---|
| Source artifact SHA-256 | e238d820e2ee77863c4f8bc312ed639a47c47d2e7b5607da1951d1a6717f8856 |
| Receiver artifact SHA-256 | 37d4fce52c56d20f2bb0f0a58534d5ba92b21a391cc73d6d99d5226cb279e069 |
| Source record digest | 3b9195df4797e106ab3408ca55a832d5e5d142b7a28fcd5d2b8c1d8c775895df |
| Receiver record digest | 494795bf17a1927fc27fa3e4a6a1e32ea82e6bab1848a7751bb5d67e1c47100d |
| Source span digest | b1fbc7473a468d15af044500784e6552f98779e20c0dc32c82956191aab49d0e |
| Receiver span digest | 63f665ec0a4a9e53ecb08b86fbddecb9b83bfad21655d812d76aa726b1c196e3 |
| Handoff digest | 1a7155a5450d7ba07a783f54db3639ec7d451b6712419ebd5403dec251697e7e |

The Go tests require the actual fixture artifact hashes to match those values, recompute the record/span/payload/handoff digests, and require the same single strict causal edge as the Python diverse report.

## Verification suite

The Go regression suite covers:

- reconstruction of the actual preserved IHP-001 records and parity with the Python IHP-003 evidence projection;
- canonical UTF-8 strings, sorted keys, and non-escaped HTML characters;
- explicit rejection of decimal JSON number tokens;
- stale record digest rejection;
- altered payload and source-artifact binding rejection;
- concurrent vector clocks not being promoted to a causal edge;
- cross-run receiver rejection;
- noncanonical artifact byte rejection;
- report-predicate binding to exact report bytes and the verifier job identity.

Run locally:

    cd bridges/observation-path/cross_language_verifier
    go test -count=1 -v ./...

The command-line verifier on a GitHub Actions runner is:

    go run ./cmd/ihp004 verify \
      --source received-source/host-a.json \
      --receiver received-receiver/host-b.json \
      --python-report received-diverse/diverse-report.json \
      --report evidence/go-report.json \
      --predicate evidence/go-report.predicate.json

For local use, the command also requires a complete GitHub workflow identity in the GITHUB_* environment and RUNNER_* fields so that it cannot accidentally emit a report pretending to be the fifth hosted job.

The pull-request workflow runs the Go tests and validates both report schemas against outputs generated by those tests. The main-only workflow runs the fifth host against the signed, live artifacts from the current IHP-001 run.

## What a passing result would establish

A successful live fifth-host run would establish that:

- Go can independently parse the exact IHP-001 source and receiver artifact bytes;
- the Go implementation recomputes the same record, span, payload, and handoff digests;
- the Go implementation derives the same strict vector-clock edge and local monotonic endpoint constraints;
- the Go evidence-bearing report agrees with the IHP-003 Python diverse report on the underlying shared evidence;
- the Go report is bound to the fifth job's identity and exact report bytes through its own attestation.

This is a stronger test of implementation diversity than IHP-003 alone, and it also exposes a real serialization-contract gap.

## What it would not establish

A passing result would not establish:

- that the original source and receiver physically performed their claimed computations;
- that the Go verifier independently authenticated the source and receiver Sigstore signatures (the primary Python verifier does that);
- that the current Go implementation supports decimal-valued fields permitted by the broad v0.1 schema;
- that the JSON format description is free of common-mode conceptual mistakes;
- that the source and receiver jobs use independently attested physical hardware or fault domains;
- that the GitHub Actions artifact relay is E-CPU ReliableChannel or direct TCP/mTLS;
- a combined cross-host duration, network latency, or CPU time.

## Next discriminating step

The next research decision is to standardize numeric canonicalization in a versioned record format and add a differential corpus containing fractional numbers, exponent notation, negative zero, large integers, escaped Unicode, surrogate edge cases, and nested object keys. Every implementation should either produce the same canonical bytes and digest or reject the same input with an explicit reason.

Until that contract exists, IHP-004 remains deliberately limited to the integer-valued evidence domain observed in the live IHP-001 record pair.
