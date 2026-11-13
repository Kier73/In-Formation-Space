# Three-host independent proof-runner reconstruction

**Status:** live three-job workflow with a single-host SQLite authority and a separate independent verifier; offline fixtures are test-only.  
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

The workflow uses three separate GitHub-hosted jobs in one run. The authority job itself runs three sequential, separately launched Python processes against one SQLite database on that job's local runner: one process opens the route, a second process reopens the database and claims/admit/authorizes, and a third process reopens it and demonstrates that the old owner-generation token is rejected. A separate process-level test launches two OS processes that race the same expected SQLite revision; exactly one CAS should win.

GitHub Actions artifacts transfer the database and retained evidence to the runner and verifier jobs. This does not claim that the three authority processes are three hosts, that SQLite is a multi-host consensus service, or that E-CPU ReliableChannel transported the artifacts. The third workflow job independently reads the transferred database; it is not the authority's transaction coordinator.

This experiment is complementary to [MOR-001: Multi-observer causal reconstruction](../multi-observer-causal-reconstruction/README.md), which examines independently produced temporal evidence and cross-host causal relations. Here the focus is whether a route authority can survive local process restart and whether a separate observer can reconstruct its durable history. Neither experiment alone establishes a general multi-host consensus authority.

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
The signed authority checkpoint is now format `in-formation.proof-action-route-ledger-attestation/0.2`; the reconstruction report is `in-formation.proof-runner-independent-reconstruction-report/0.2`. These versions include the SQLite database hash, the revision-history digest, process-phase evidence, and stale-owner rejection.

## Canonicalization and implementation diversity

All evidence files use the repository's [Canonical Metadata Profile v1](../../formats/canonical-metadata-v1/README.md): safe integers only, ASCII object keys, Unicode scalar strings, sorted keys, compact UTF-8 JSON, and exactly one trailing LF. The independent verifier is written in Go and reuses the already-tested Go canonical metadata implementation from [IHP-004](../../bridges/observation-path/cross_language_verifier/). It does not call the Python receipt verifier.

The authority and runner signatures are independently checked with Go's standard-library `crypto/ed25519`. Each public-key document has a custom GitHub artifact-attestation predicate that commits to the exact file SHA-256, participant ID, role, key fingerprint, and complete host-identity record. The third host runs `gh attestation verify` with the exact predicate type, signer workflow, protected main ref, and self-hosted-runner denial, then compares the verified predicate with the downloaded key document. This prevents a validly attested key file from being silently paired with a different role or host record. The Go CLI's `--key-attestations-verified` flag is therefore a statement from the workflow orchestration layer; it must never be set by a caller that has not actually performed both checks.

The third host separately emits `sqlite-authority-verification.json` after reopening the transferred database with the repository's Python adapter. The Go verifier does not accept a bare Boolean that claims this happened: it ingests that exact summary, checks its epoch, active owner, generation, revision count, and history digest against the ledger/audit reconstruction, and commits the summary's digest into the final report. The offline fixture deliberately marks `verified: false`; it tests the binding without claiming a real adapter reopen.

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

- multi-host consensus or linearizability; the live authority is SQLite on one GitHub-hosted machine, not a multi-host store adapter;
- that the authority host was uncompromised when the database and checkpoint were created; a privileged host actor could rewrite them before signing;
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

```bash
mkdir -p external
git clone https://github.com/Kier73/E-CPU external/E-CPU
git -C external/E-CPU checkout c82d795e6b7602cc3d6e8c41e8622820914f5cbf
git clone https://github.com/Kier73/Virtual-Ground-Interpreter external/Virtual-Ground-Interpreter
git -C external/Virtual-Ground-Interpreter checkout ac13c1bbd92dfd09f17de51adef7adb2d2088bf6
python -m pip install --no-deps external/Virtual-Ground-Interpreter/virtual_ground_interpreter
python -m pip install "cryptography>=42,<47" "jsonschema>=4,<5"
python -c "from vgi.proof import ProofGroundAdapter, VerifiedKernelReceipt"
export PYTHONPATH="bridges/proof-attention:external/E-CPU:."
python -m unittest discover \
  -s experiments/proof-runner-independent-reconstruction \
  -p 'test_*.py' -v

cd experiments/proof-runner-independent-reconstruction
go test -count=1 -v ./...
```

The tests use a deterministic, explicitly non-secret fixture for offline cross-language signature checks; its database bytes are a named stand-in, not a real SQLite file. Separate Python tests create a real temporary SQLite database, launch OS processes for restart and stale-owner replay, reopen the database, and race two OS-process CAS writers. Go adversarial cases include changed runner signatures, replaced runner keys, semantically broken but fully re-hashed admission chains, altered SQLite intermediate revisions, stale-owner process-evidence tampering, database-byte substitution, self-consistent result replacement, authority signature tampering, changed requests, and third-host identity reuse.
The live workflow file is \`.github/workflows/proof-runner-three-host-reconstruction.yml\`. The exact command and artifact names are recorded in that workflow.
