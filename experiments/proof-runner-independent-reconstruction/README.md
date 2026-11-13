# Three-host independent proof-runner reconstruction

**Status:** protocol experiment; live multi-host workflow is defined separately from the offline fixture suite.  
**Question:** can a third, separately scheduled verifier reconstruct the chain from a route-authority checkpoint to an exact proof-action result using only retained artifacts and independently authenticated public keys?

## Why this follows the signed receipt experiment

The signed completion-receipt experiment (#108) connected one self-digested \`execution_authorized\` event to a request-correlated proof-action result. It deliberately left two questions to its caller:

1. Is the event actually in a valid route-ledger history, rather than merely a self-consistent event-shaped object?
2. Why should a third host trust the runner and authority public keys used to verify the signatures?

This experiment adds the missing reconstruction steps as distinct evidence layers:

- the authority host emits a hash-chained route-ledger checkpoint and signs a statement committing to its exact ledger digest, sequence, authorization event, request, execution ticket, and runner identity;
- the runner host consumes that checkpoint, produces the exact portable result envelope, and signs a completion receipt using the previously established receipt format;
- the independent verifier host receives only the retained artifacts, verifies the authority and runner public-key artifacts against the protected GitHub workflow, replays the supported route-ledger profile, then independently verifies both Ed25519 signatures and all request/result bindings.

The private signing keys are generated and held in process memory by their respective producer jobs. They are never written to disk or uploaded. Only public key documents are exported, and those documents are separately attested by their producing jobs.

## Three roles and evidence flow

\`\`\`text
Authority host
  route ledger + request
  Ed25519 checkpoint signature
  public authority key document
       | GitHub artifact storage
       v
Runner host
  verifies authority checkpoint and request
  exact result envelope + Ed25519 completion receipt
  public runner key document
       | GitHub artifact storage
       v
Independent verifier host
  verifies both public-key artifact attestations
  replays the ledger and verifies authority signature
  verifies request/result correlation and runner signature
  emits a reconstruction report
\`\`\`

The workflow uses three separate GitHub-hosted jobs in one run. GitHub Actions artifacts are the transfer mechanism. This does not claim direct E-CPU transport, separate cloud providers, independently attested physical machines, or independent administrative fault domains.

## Current ledger profile

The Go verifier is intentionally narrow and fail-closed. It currently accepts a single active route epoch containing:

- one \`opened\` event at owner generation 1;
- zero or more monotonic \`claimed\` owner-generation transitions;
- one \`admitted\` event binding an attempt, request digest, and reliable-channel sequence;
- one \`execution_authorized\` event binding the preceding admission, current owner generation, deterministic execution ticket, and runner ID.

It checks the outer ledger digest, contiguous event sequence, previous-event hash chain, each event self-digest, route digest, owner progression, admission-to-authorization linkage, and the deterministic ticket formula. It rejects unsupported event types—including \`closed\` handoff events—instead of treating a partial replay implementation as a complete route-ledger verifier. A later revision can add the full multi-epoch close/open replay rules from \`proof_action_route_epoch.py\`.

The authority signature authenticates a checkpoint claim under the authority key. It does not independently prove that an external compare-and-swap store was linearizable or that the authority recorded events honestly. This workflow's authority producer constructs a synthetic, single-request route-ledger example; it is not connected to a production E-CPU route authority or shared CAS store.

## Canonicalization and implementation diversity

All evidence files use the repository's [Canonical Metadata Profile v1](../../formats/canonical-metadata-v1/README.md): safe integers only, ASCII object keys, Unicode scalar strings, sorted keys, compact UTF-8 JSON, and exactly one trailing LF. The independent verifier is written in Go and reuses the already-tested Go canonical metadata implementation from [IHP-004](../../bridges/observation-path/cross_language_verifier/). It does not call the Python receipt verifier.

The authority and runner signatures are independently checked with Go's standard-library \`crypto/ed25519\`. The authority and runner public keys are accepted only after a separate \`gh attestation verify\` step pins the exact public-key artifact bytes to this repository's protected main workflow and denies self-hosted runners. The Go CLI's \`--key-attestations-verified\` flag is therefore a statement from the workflow orchestration layer; it must never be set by a caller that has not actually performed both checks.

Offline tests use deterministic, explicitly non-secret fixture keys. A fixture pass is not a live three-host execution. Live producer jobs use ephemeral generated keys and retain no private key files.

## What a successful independent reconstruction establishes

A successful third-host report establishes that, for the exact transferred artifacts:

- the complete supported route-ledger document has a valid digest and a replayable event chain;
- the admission event precedes and is exactly bound to the execution authorization;
- the execution ID matches the route epoch, attempt ID, and request digest;
- the authority signature verifies over the exact ledger checkpoint and its authorization/request bindings;
- the proof-action request digest is valid and matches the authorization;
- the proof-action result digest is valid and matches the exact request;
- the runner completion receipt verifies under the separately attested runner public key and commits to the exact result, proof trace, return evidence, and authorization event;
- the authority, runner, and verifier are distinct workflow job/actor identities for the same run.

The output preserves cross-host elapsed duration as unknown. No duration is inferred from independent runners' wall or monotonic clocks.

## What it does not establish

Even a successful live run does not establish:

- that the external production CAS authority was linearizable, or that the synthetic authority producer represented a live CAS commit;
- that the authority or runner behaved honestly or was uncompromised;
- that a Lean process actually ran, or that the returned tactic/proof trace is semantically valid;
- that theorem acceptance occurred; VGI's \`VerifiedKernelReceipt\` remains a separate trust boundary;
- that the result's Encounter source was fetched and authenticated independently;
- that E-CPU ReliableChannel, TCP, or mutual TLS transported the artifacts—the current workflow uses GitHub artifact storage;
- that jobs used distinct physical servers, regions, power supplies, or administrative fault domains;
- a network latency, CPU time, or combined cross-host elapsed duration.

A runner signature proves key possession and commitment to exact bytes. It does not prove computation.

## Reproduction

From the repository root:

\`\`\`bash
python -m pip install "cryptography>=42,<47"
python -m unittest discover \\
  -s experiments/proof-runner-independent-reconstruction \\
  -p 'test_host_evidence.py' -v

cd experiments/proof-runner-independent-reconstruction
go test -count=1 -v ./...
\`\`\`

The Go tests create their own deterministic Python fixture and verify it without importing the Python receipt verifier. Adversarial cases include changed runner signatures, replaced runner keys, semantically broken but fully re-hashed admission chains, self-consistent result replacement, authority signature tampering, changed requests, and third-host identity reuse.

The live workflow file is \`.github/workflows/proof-runner-three-host-reconstruction.yml\`. The exact command and artifact names are recorded in that workflow.
