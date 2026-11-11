# Bridge: Adaptive policy execution through evidence paths

**Status:** experimental coordinator; transport remains adapter-supplied.  
**Connects:** Trial 06 (adaptive policy planning) and the Evidence-gated Observation Path.

## Purpose

Trial 06 constructs a decision tree from predicted observation outcomes. The observation-path bridge records what actually happens. This coordinator joins them without confusing prediction with execution.

## Lifecycle

1. begin_attempt() creates a planned request from the current policy node.
2. The external host adapter calls mark_dispatched() only after dispatch occurs.
3. The receiver adapter calls mark_admitted() only after admission occurs.
4. The sensor or transport adapter calls record_return() with an Encounter Envelope reference, payload digest, and canonicalization.
5. The interpreter calls interpret() with the interpreted branch value and an interpretation artifact reference.
6. The coordinator either resolves the query, records continued and exposes the next planned observation, or stops as unresolved model mismatch. When sender ACK confirmation is required, the path must first reach `sender_acknowledged`; partial ACK rounds remain `sender_ack_progress` and can be retried.

No transport or sensor operation is executed by this package. It only records claims after an external adapter reports them.

## E-CPU adapter boundary

The [E-CPU adapter map](ecpu-adapter-map.md) maps this coordinator and the evidence-path stages to existing E-CPU interfaces. The [dependency-injected adapter](../observation-path/ecpu_gated_adapter.py) verifies quorum finalization, receiver's durable VM commit, and sender-side ACK processing from E-CPU snapshots, pending sequences, and register readback. Partial sender ACK results remain explicit progress until all event sequences are cleared. No E-CPU runtime code is imported or modified by this bridge.

## Model-mismatch rule

The policy contains predicted outcome branches. If a real interpreted outcome matches none of them, the attempt ends as unresolved_model_mismatch. The raw return and interpretation references remain in the append-only path. The coordinator does not map the result to the nearest branch, discard it, or invent a query answer. This is where the observed system can teach us that the policy's hypothesis or observation model was incomplete. The [Append-only Hypothesis Revision bridge](../hypothesis-revision/README.md) records proposals motivated by these mismatches, preserves prior revisions, and requires explicit validation before an expanded model becomes active.

## Provenance and clocks

Each request attempt receives its own ObservationPath. The policy execution result holds all completed and current attempt records. Encounter Envelope references and digests are retained, but this coordinator does not fetch or validate the referenced envelope. The companion observation-path schema and CLI validate the record structure and lifecycle consistency; the CI workflow runs those checks and the coordinator tests.

Clock values remain labeled with their original clock domains; the coordinator performs no cross-clock alignment.

## Live runtime verification

The adapter has now been exercised against a pinned E-CPU checkout, not only stubs. The [live integration tests](../observation-path/ecpu_live_integration.py) and [run 172 receipt](../observation-path/results/live-ecpu-integration-run-172.json) document the actual transport, quorum, checkpoint, VM readback, and sender-ACK sequence.

## Construction and verification

- [Construction report](construction-report.md) records the lifecycle, evidence limits, and integrated CI result.
- [CI execution receipt](../observation-path/results/ci-run-112.json) records the run and test-suite counts.

## Implementation and tests

The coordinator deliberately lives beside its append-only path primitive so it can reuse the same request-attempt implementation:

- [adaptive_policy_execution.py](../observation-path/adaptive_policy_execution.py) — policy-tree coordinator over the evidence path ledger.
- [test_adaptive_policy_execution.py](../observation-path/test_adaptive_policy_execution.py) — adaptive branching, unexpected outcomes, rejection, timeout, and no-execution tests.
- [observation_path.py](../observation-path/observation_path.py) — lifecycle state machine used by each request attempt.

The CI workflow runs the observation-path and adaptive-coordinator test files as two separate suites. This directory is the conceptual entry point and index for the bridge, not the Python package directory.

## Reproduce

    python -m unittest discover -s bridges/observation-path -p 'test_*.py' -v

## Limits

The policy tree assumes deterministic predicted outcomes and a finite hypothesis set. Real observations may be stochastic or may expose a previously omitted hypothesis. A mismatch is therefore preserved as new evidence of model insufficiency, not treated as a code-path inconvenience. A production adapter must independently authenticate transport and Encounter Envelope evidence before reporting those stages.