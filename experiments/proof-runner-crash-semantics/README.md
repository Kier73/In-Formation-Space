# Proof-runner crash semantics

**Status:** executable reference experiment.  
**Question:** what can an execution ticket actually guarantee when a worker process or response path fails around the boundary between computation, an external effect, and durable result recording?

## Connection to the proof-action bridge

The proof-action route ledger commits an `execution_authorized` event before invoking the external runner. It derives an execution ID from the route epoch, attempt ID, and request digest. `ProofActionReliableWorker.execute_request()` passes that ticket to the runner and explicitly requires the runner to resume or deduplicate by the same ID after restart.

Relevant existing implementation:

- `bridges/proof-attention/proof_action_route_epoch.py` — `record_execution_authorization()` makes route admission and execution authorization part of the route authority's CAS history.
- `bridges/proof-attention/proof_action_reliable_channel.py` — `execute_request()` commits the ticket before calling the external runner.

That is a sound admission boundary, but it does not make the runner's own work and result persistence atomic. This experiment isolates that remaining contract without changing the production bridge or claiming to deploy a proof worker.

## The dual-write ambiguity

Suppose the runner first persists `started`, performs an irreversible effect in another system, then persists `completed` plus the result. Two crashes produce the same durable runner record (`started`):

1. The process dies after `started` but before the effect.
2. The effect commits, then the process dies before writing `completed`.

The runner cannot distinguish these cases from its own record alone. Retrying `started` avoids losing the first effect but duplicates the second. Skipping `started` avoids duplicating the second but loses the first.

| Recovery rule | Crash before effect | Crash after effect, before completion receipt |
| --- | ---: | ---: |
| Retry `started` | 1 effect | 2 effects |
| Skip `started` | 0 effects | 1 effect |

The exhaustive two-world fixture is in `nontransactional_recovery_outcomes()` and is checked by `test_nontransactional_started_state_is_ambiguous`.

## Two contracts that can close the gap

### Pure or replay-safe computation

`SQLitePureResultRunner` executes a deterministic, side-effect-free computation while holding a SQLite write transaction, then commits its result under a unique execution ID. If the process crashes before commit, the computation may run again. If it crashes after commit but before returning, the next process retrieves the committed result without recomputing.

Its guarantee is **once-only result publication**, not once-only computation. The compute callback must be pure/replay-safe; the class cannot enforce that property. The SQLite database is a local reference store, not a distributed authority.

### Provider-side idempotent effect

`SQLiteIdempotentEffectSink` models a provider that stores an effect and its idempotency receipt in one transaction. A repeated `(execution_id, command)` returns the original receipt and does not create another effect. Reusing the same ID with a different command is rejected. A simulated lost response after commit demonstrates that a retry recovers the provider's prior result.

This contract can be implemented by a real effect provider that supports idempotency keys or by a transaction that includes both the effect and receipt. A local SQLite wrapper cannot make an arbitrary external HTTP request, file write on another host, or physical action atomic.

## Reproduction

No third-party packages are required:

```bash
python -m unittest discover -s experiments/proof-runner-crash-semantics -p 'test_*.py' -v
```

The tests cover the two crash windows, post-commit response loss, conflicting ticket reuse, and concurrent retries through separate SQLite connections.

## Claim boundary

- The finite counterexample establishes the ambiguity of a non-transactional two-resource protocol under the stated failure model. It does not prove all possible distributed protocols impossible; atomic effect-provider idempotency, authoritative effect lookup, or a shared transaction changes the assumptions.
- SQLite `BEGIN IMMEDIATE`, a primary-key ticket, and one local transaction provide a single-database reference implementation. They do not establish multi-host consensus, authentication, remote worker honesty, or deployment durability beyond SQLite's documented local guarantees.
- The pure-runner result is scoped to deterministic, side-effect-free computation. It does not guarantee that CPU work executes only once.
- An `execution_authorized` event remains permission to accept a job, not evidence that the job completed or that a tactic succeeded. Kernel receipts remain separate.
