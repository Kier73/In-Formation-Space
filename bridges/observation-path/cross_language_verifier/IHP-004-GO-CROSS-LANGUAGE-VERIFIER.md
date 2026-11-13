# IHP-004: Go cross-language reconstruction of hosted operation evidence

**Experiment:** IHP-004  
**Status:** implemented; first live five-host execution passed on 2026-11-13T04:11:58Z  
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

## Shared Canonical Metadata Profile v1

IHP-004 and PRC-001 now share one repository-level contract: [Canonical Metadata Profile v1](../../../formats/canonical-metadata-v1/README.md). The shared implementation entry point is `formats/canonical_metadata_v1.py`; the Go and Node.js receivers independently implement the byte contract. Both Python call sites (the IHP diverse verifier and PRC capsule encoder) delegate to the shared validator and encoder.

The common [differential conformance corpus](../../../formats/canonical-metadata-v1/vectors.json) exercises accepted canonical bytes and adversarial rejection cases across Python, Go, and Node.js. It covers safe-integer boundaries, fractional and exponent-form numbers, negative zero, duplicate object keys, Unicode scalar validity, U+2028/U+2029, ASCII key ordering, escaping, whitespace, and exact one-LF artifact framing.

**IHP scope remains intentionally narrower than the full IHP-001 v0.1 schema:** the schema permits decimal-valued optional temporal fields such as `chronon_phase` and `chemical_tau`, but the current record/verifier path rejects them under this shared metadata profile. This is a fail-closed interoperability subset, not a claim that every schema-valid v0.1 record is currently supported. A future record-schema revision should adopt a versioned numeric representation for those values rather than weakening v1 inconsistently across runtimes.

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


## First live five-host execution

The first main-branch IHP-004 run completed successfully:

- **Run:** [Independent hosted-VM operation path #43363638666](https://github.com/Kier73/In-Formation-Space/actions/runs/43363638666)
- **Commit:** \`0c956b7888d80aa8ec0ca543365b982d28d8c59d\`
- **Workflow conclusion:** success
- **Source host:** success; produced and attested the source record.
- **Receiver host:** success; verified the source attestation, merged the sender causal stamp, and produced and attested the successor record.
- **Primary Python verifier:** success; verified the source and receiver input attestations, reconstructed the causal path, and attested its report.
- **Diverse Python verifier:** success; independently reconstructed the same evidence and attested its report.
- **Go cross-language verifier:** success; reconstructed directly from the exact source and receiver records, matched the Python diverse report's evidence projection, validated its report and predicate schemas, attested its report, and preserved its output.

The Go report is \`cross-language-host-reconstruction-report\`; its object-level \`report_digest\` is:

    237045c4e5fe9937241cba1dbd2e53dc6305091a973099d048dfbbeaa2218340

The primary and diverse Python reports have different report digests because they identify different verifier jobs and contain different report schemas. All three agree on the evidence-bearing causal reconstruction:

| Evidence | Primary Python | Diverse Python | Go |
|---|---|---|---|
| Source span digest | \`18d41be74e82ccf73c4948d2bbfec493e9a8bd6a45957aeee9c09fe06bfedbd7\` | same | same |
| Receiver span digest | \`a9d359d6fe9ad409583078de7262071ab014bc367d36e3d0ba63b41be86f7b00\` | same | same |
| Handoff digest | \`d71207a86d3c59e0bfd98c27b755dfcd7145e9edab1b53d882fab8cc79ed4523\` | same | same |
| Edge count | 1 | 1 | 1 |
| Sender Lamport | 1 | 1 | 1 |
| Receiver Lamport | 2 | 2 | 2 |
| Vector relation | before | before | before |

The sender vector contains only the source actor at counter 1. The receiver vector contains the source actor at counter 1 and the receiver actor at counter 1. All three implementations derive the same strict happens-before edge.

The new source artifact SHA-256 is:

    ea017830809e40290141e9e7eeb908a67fc90985b0fe91915256328c1b86335e

The new receiver artifact SHA-256 is:

    8ee6ad1ed8acd449fbbc7b0441aeca8fe60bfe9e39212ec9df4ac5cf5c346d25

The observed local synchronous-call durations are:

- source host: **225,116 ns** (approximately 0.225 ms);
- receiver host: **190,317 ns** (approximately 0.190 ms).

They are readings in separate process-local monotonic domains. All three reports retain \`combined_cross_host_elapsed_ns: null\`; no transport latency, CPU time, or end-to-end duration is inferred.

The run preserves five artifacts: \`source-host-evidence\`, \`receiver-host-evidence\`, \`independent-host-reconstruction-report\`, \`diverse-host-reconstruction-report\`, and \`cross-language-host-reconstruction-report\`.

This first live run establishes that three verifier implementations in two languages independently reconstruct the same causal edge from the same participant records, with the primary Python verifier additionally verifying the source and receiver Sigstore attestations. The Go job does not replace or duplicate that cryptographic input-verification responsibility.


## Second live execution after Canonical Metadata Profile v1 consolidation

After PR #98 consolidated the shared Python encoder, Node strict-document receiver, Go canonical writer, and 30-vector cross-runtime corpus, the full main-branch IHP workflow ran again successfully:

- **Run:** [Independent hosted-VM operation path #43365805836](https://github.com/Kier73/In-Formation-Space/actions/runs/43365805836)
- **Commit:** \`998d82f9685baaba3f94308096c82447ccbeef64\`
- **Workflow conclusion:** success
- **Source host:** success
- **Receiver host:** success
- **Primary Python verifier:** success, including both source/receiver Sigstore input attestations
- **Diverse Python verifier:** success
- **Go cross-language verifier:** success, using the consolidated canonical metadata implementation and the same Python report parity comparison

The three verifier reports agree on the following evidence for this second live record pair:

| Evidence | Value |
|---|---|
| Source artifact SHA-256 | \`75117f40bfa6e986205225ec1b5af15468b61643853602559a51a6ef19024661\` |
| Receiver artifact SHA-256 | \`e5483c258314851dc43ebaf654f1c4ef706fd066f1b705d2f49e3eeffc403159\` |
| Source record digest | \`bba190e667b5e1e55ccc27e01a1e57ccb35d50ccbe0abb3c8f5959ab998933c9\` |
| Receiver record digest | \`dc5656aa9f0b79657a1a2a2ac46f703392f8e2b367d110a03bfc2582b84c07ab\` |
| Source span digest | \`fe61e238d7103943bf5d3cbfdaa46fc5bec8a150ba1a02f2db397fe2750615da\` |
| Receiver span digest | \`d923f4e344c9ba5f1fef7fd9c4d0454f5a8e08e60cecfce53d9fa37b3ff2511e\` |
| Payload digest | \`0ad5d6ff3559bab4c5d3e3c76a33128a9e3737570a9a5db73ffd15fedfbc399b\` |
| Handoff digest | \`f0b859f5f97afa7e0391867624505d3bc69d6871d3fa59a0f85a00c3275a5888\` |
| Causal edge count | 1 |
| Sender Lamport / vector | 1 / \`{source: 1}\` |
| Receiver Lamport / vector | 2 / \`{source: 1, receiver: 1}\` |
| Vector relation | \`before\` |

The three report object digests are distinct because each names its verifier role and report schema:

- Primary Python: \`7cd2b0fb585705586751a8857533fe070ad12b9b70747ed3f205a53e616cb6ef\`
- Diverse Python: \`ea6185a5d95e805784b1f46ce0dbd695fad4769e8b91bb10803145e39c6c53cb\`
- Go: \`c65d20cf65e14d89a6964160354611d2f9589c60dc9e96d4f0ba21b8f2dabcc9\`

The observed local synchronous-call durations were **186,501 ns** on the source host and **209,530 ns** on the receiver host. They remain separate local monotonic measurements; all three reports retain \`combined_cross_host_elapsed_ns: null\`.

The second successful run demonstrates that the cross-language operation-path reconstruction still works after canonicalization was consolidated. The Go report is not merely passing a fixture or a standalone corpus test: it independently reconstructs the current source and receiver records and agrees with the separately generated Python evidence projection.

## What a passing result would establish

The successful first live fifth-host run established that:

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

The common canonicalization rule and first three-runtime differential corpus are now implemented. The next IHP-specific question is how to represent optional decimal-valued temporal coordinates without losing their semantics or introducing runtime-dependent numeric serialization. A versioned record-schema revision could use explicit exact-rational or decimal-string fields, with cross-language vectors for range, sign, precision, and round-trip behavior. Until that contract is designed and adopted, the current IHP safe-integer subset should continue to reject these fields rather than normalize them differently.
