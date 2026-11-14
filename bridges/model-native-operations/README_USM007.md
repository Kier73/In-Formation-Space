# USM-007 — Two competing receivers, one authorized model-result publication

**Status:** repository implementation and runnable experiment. The GitHub
Actions workflow must execute before any operational success claim.

## Research question

USM-005 established a proposed E-CPU receiver restart after Ground read
commit and before ReliableChannel ACK. USM-006 integrates E-CPU's existing
authenticated distributed recovery-lineage service. This experiment asks
a different, complementary question:

> Can two independently running replacement receiver processes both claim
> authority to publish the recovered model's result, or can one existing
> route-epoch authority ensure only one receives an execution ticket?

The implementation intentionally reuses In-Formation-Space's
`ProofActionRouteEpochLedger` and `SQLiteRouteEpochLedgerStore`.
No second ownership, CAS, lease, or journal algorithm is added.

## Real exercise across the repositories

The workflow uses two GitHub-hosted jobs.

The producer checks out the pinned E-CPU USM-006 commit and runs the actual
model-operated receiver hard-crash experiment. Its original and replacement
receivers use native E-CPU mTLS and ReliableChannel, while two separately
running authenticated recovery-lineage authority processes preserve their
journals. The complete recovery record is transferred as an artifact.

The observer job checks the recovered Ground using the IFS USM-003/005
independent source oracle and trace verifier. Only **after** that evidence
passes does it create a durable SQLite route ledger. The initial route
records the original model request and its exact digest. The adapter binds
the MailCPU prompt/call channel names and reliability policy into the
existing route schema.

Two separate Python subprocesses then race to claim the *same expected
owner generation*. Both read the original owner snapshot before a common
start gate. The existing SQLite `BEGIN IMMEDIATE` CAS serializes their
attempts. One claim may append generation 2; the other must refuse.

The winner alone may call
`ProofActionRouteEpochLedger.record_execution_authorization`, which
requires the original admitted model request and produces a stable,
deterministic execution ticket. The losing contender and the original
receiver must not get an execution authorization after the successful claim.

The experiment independently reopens the ledger, checks its append-only
audit history and requires exactly one claim and one execution authorization,
both binding the same model Ground receipt and source-trace digest. Its
output is a **logical publication** record. It deliberately does not execute
an arbitrary external effect.

## Local reproduction

The existing proof-attention route ledger imports E-CPU's reliable-channel
types, so install E-CPU from a compatible checkout before running this
experiment. The recovered source verifier itself remains Python standard
library and independently checks the mathematical source.

```bash
python -m unittest discover -s bridges/model-native-operations \
  -p 'test_model_route_fencing.py' -v

python bridges/model-native-operations/model_route_fencing.py demo \
  --source usm005-source.json --output usm007-fenced-model-result.json
```

The source file is the original JSON report from E-CPU USM-005 or the
`recovered_model` field of USM-006's report. The hosted workflow extracts
that input automatically.

## Invariants and adversarial cases

- Invalid or altered Ground result fails independent verification **before
  opening the route authority database**.
- Two independent claimant processes cannot both append ownership claims
  against one expected `owner_generation=1`.
- The losing claimant publishes no receipt or execution ticket.
- The original stale receiver cannot authorize an operation under its old
  owner generation after the claim.
- The native route ledger prohibits contradictory requests for the same
  admitted attempt ID, even if they arrive with a different channel sequence.
- The durable ledger history and execution ticket must match the recorded
  model-issued read and source oracle.

## What the result does and does not establish

This is **single-host, multi-process route ownership fencing** with SQLite
as an authoritative local database. It does **not** prove distributed
consensus, physical machine independence, or true network partition
fencing. The output explicitly reports
`remote_quorum_fencing_verified=false`.

It cannot enforce an external side effect that ignores the native execution
ticket, and it does not guarantee that a previously authorized runner will
cease work after later ownership changes. The stable ticket identifies
execution intent; an external sink must enforce deduplication and/or a
shared fencing authority at its own commit boundary.

E-CPU's fixed-membership `RecoveryLineageCoordinator` provides distinct
quorum-backed checkpoint authority, but does not alone give two competing
owner identities a shared linearizable publication right. IFS's existing
route-epoch authority provides that right for the single-host test. These
are **complementary authorities**, not substitutes for one another. A future
integration should place the ownership CAS behind authenticated E-CPU
authority participants or a quorum-backed, per-operation state service,
then test the effect publication against independently competing machines.

VGI remains relevant for verifying that a reconstructed Ground's
mathematical intention is preserved across changing context, observation
and hosting topology. USM-007 checks the **authorization to publish one
verified result**, not all mathematical interpretation equivalence.

## Existing work reused

- E-CPU `mailcpu.recovery_lineage_service` and
  `mailcpu.recovery_lineage_transport`: authenticated durable quorum.
- E-CPU `mailcpu.structural_memory`, `mailcpu.reliability`: admitted Ground,
  read receipt and communication checkpoint.
- IFS `bridges/model-native-operations/verify_recovered_model.py`: source
  oracle and reconstructable model/evidence trace.
- IFS `bridges/proof-attention/proof_action_route_epoch.py`: owner generation,
  per-request admission, execution authorization and stale-owner refusal.
- IFS `bridges/proof-attention/sqlite_route_epoch_store.py`: durable local
  CAS and append-only audit.
