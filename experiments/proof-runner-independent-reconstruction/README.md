# Three-host independent proof-runner reconstruction

**Status:** protocol experiment; live multi-host workflow is defined separately from the offline fixture suite.  
**Question:** can a third, separately scheduled verifier reconstruct the chain from a route-authority checkpoint to an exact proof-action result using only retained artifacts and independently authenticated public keys?

## Why this follows the signed receipt experiment

The signed completion-receipt experiment (#108) connected one self-digested \`execution_authorized\` event to a request-correlated proof-action result. It deliberately left two questions to its caller:

1. Is the event actually in a valid route-ledger history, rather than merely a self-consistent event-shaped object?
2. Why should a third host trust the runner and authority public keys used to verify the signatures?

This experiment adds the missing reconstruction steps as distinct evidence layers:

- the authority host uses the repository's SQLiteRouteEpochLedgerStore and ProofActionRouteEpochLedger implementations to create a durable route history across separate OS processes: initial open, restart + ownership claim + request admission + execution authorization, then stale-generation replay and rejection;
- the authority signs a checkpoint that commits to the exact final ledger, every SQLite audit revision and intermediate ledger digest, the raw SQLite database bytes, all three process-phase records, the stale-owner rejection, the request, execution ticket, and runner identity;
- the runner host consumes the actual database and audit export, validates the authority signature and all bindings, produces the portable result envelope, then signs a completion receipt using the previously established receipt format;
- the independent verifier host receives the retained artifacts, verifies the authority and runner public-key artifacts against the protected GitHub workflow, independently replays the route ledger and every SQLite revision prefix in Go, and verifies both Ed25519 signatures and all request/result bindings;
- before producing its final report, the independent verifier host opens the transferred SQLite database using the repository's own SQLite adapter and checks that its stored current state and append-only audit exactly match the exported evidence.

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

## Durable local authority profile

The live authority producer uses the repository's `bridges/proof-attention/proof_action_route_epoch.py` and `sqlite_route_epoch_store.py` implementations directly. The expected four durable revisions are:

1. `opened`: owner generation 1;
2. `claimed`: a replacement owner takes generation 2;
3. `admitted`: the request digest and ReliableChannel sequence are committed under generation 2;
4. `execution_authorized`: the deterministic execution ticket is committed under that same generation.

The first event is committed by one process. A second process starts after the first exits, opens the same database through a new SQLite store object, and commits the remaining three events. A third process again reopens the database and attempts to admit a different attempt using the generation-1 owner token. The ledger returns rejection and retains no stale admission. These are separate OS processes on the same authority job's runner, not separate authority machines.

The SQLite audit history records the revision number, predecessor ledger digest, new ledger digest, actor ID, appended event digests, and a local UTC commit marker. The verifier does not merely trust those rows: it recomputes the ledger prefix after every revision from the actual ordered event list, verifies the per-revision event append index, checks the predecessor digest chain, and checks that the final prefix equals the exported ledger head. A separate process-level race test prepares two different valid claims from one SQLite revision and launches them as concurrent OS processes. Exactly one compare-and-swap should commit.

The Go replay profile remains intentionally narrow and fail-closed. It accepts one active route epoch with one open, one claim, one admission, and one execution authorization. It rejects unsupported events—including close/handoff—instead of treating a partial replay as a complete route-ledger verifier.

The authority signature authenticates the authority's checkpoint claim and commits to the raw SQLite database SHA-256, the revision history digest, the process-phase evidence, and the stale-owner outcome. It does **not** prove that the host was uncompromised when the database was created or signed, that the local filesystem was honest, or that SQLite offers multi-host linearizability. The existing SQLite adapter targets a single host with a local filesystem. It must not be promoted to a network filesystem or treated as a distributed consensus service.
## Canonicalization and implementation diversity

All evidence files use the repository's [Canonical Metadata Profile v1](../../formats/canonical-metadata-v1/README.md): safe integers only, ASCII object keys, Unicode scalar strings, sorted keys, compact UTF-8 JSON, and exactly one trailing LF. The independent verifier is written in Go and reuses the already-tested Go canonical metadata implementation from [IHP-004](../../bridges/observation-path/cross_language_verifier/). It does not call the Python receipt verifier.

The authority and runner signatures are independently checked with Go's standard-library `crypto/ed25519`. Each public-key document has a custom GitHub artifact-attestation predicate that commits to the exact file SHA-256, participant ID, role, key fingerprint, and complete host-identity record. The third host runs `gh attestation verify` with the exact predicate type, signer workflow, protected main ref, and self-hosted-runner denial, then compares the verified predicate with the downloaded key document. This prevents a validly attested key file from being silently paired with a different role or host record. The Go CLI's `--key-attestations-verified` flag is therefore a statement from the workflow orchestration layer; it must never be set by a caller that has not actually performed both checks.

Offline tests use deterministic, explicitly non-secret fixture keys. A fixture pass is not a live three-host execution. Live producer jobs use ephemeral generated keys and retain no private key files.

## What a successful independent reconstruction establishes

A successful third-host report establishes that, for the exact transferred artifacts:

- the complete supported route-ledger document has a valid digest and a replayable event chain;
- every exported SQLite revision digest reconstructs from the event prefix and append index;
- the signed SQLite database hash matches the exact transferred database bytes;
- the third host can reopen that database through the repository adapter and reproduce the exported head and revision audit;
- the generation-1 owner is rejected after a durable generation-2 claim;
- a separate concurrency test exercises two OS processes racing one expected CAS revision and observes one winner;
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
- that the three authority processes or the three GitHub-hosted workflow jobs used distinct physical servers, regions, power supplies, or administrative fault domains;
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
