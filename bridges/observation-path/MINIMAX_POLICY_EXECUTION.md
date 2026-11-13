# VGI minimax policy execution through ObservationPath

**Status:** experimental integration, version 0.1.

This adapter connects VGI's finite minimax partial-probe policy to the
existing append-only observation path. It reuses VGI's policy tree and the
existing `PartialProbeExecution`; it does not create a second probe ranker,
transport adapter, authority mechanism, or Ground representation.

## Execution boundary

A VGI policy is a finite counterfactual plan over caller-supplied probes and
declared outcomes. Scenario weights are metadata for this minimax objective;
the planner's worst-case objective does not use them. The scenario set is not
a claim that physical outcomes are exhaustive.

The coordinator follows one branch only after the host has reported the
actual request lifecycle:

```
planned -> dispatched -> admitted -> returned -> evidence_authorized
        -> [applied] -> [sender_ack_progress ... -> sender_acknowledged]
        -> interpreted -> exact policy branch
```

The host remains responsible for dispatch, receiver admission, return
artifacts, authority finalization, optional application, and optional sender
acknowledgement. `MinimaxPartialProbeExecution` only opens the attempt,
checks the declared gates, interprets the returned `TransitionOutcome`,
and selects the unique matching child branch.

An outcome outside the declared scenario set ends as `model_mismatch`.
It does not select a nearest branch, revise the Ground, or become a negative
measurement. For a matched outcome, the adapter independently constructs the
declared counterfactual child, builds the actual immutable Ground revision
through `PartialProbeExecution`, and checks their transition semantics agree.
Evidence and metadata are intentionally excluded from that semantic
comparison; the actual revision retains its own evidence references.

## Decision-time receipt

`build_decision_receipt(execution.to_dict(), policy.to_dict())` creates a
portable record containing the pinned VGI policy, initial Ground snapshot,
per-attempt ObservationPath events, selected branch, and a sealed event log.

For each branch decision the record separates:

- **Ground input frontier:** the evidence references already present in the
  Ground supplied to the planner.
- **Attempt availability:** the evidence references present in the complete
  current ObservationPath prefix.
- **Controller-declared use:** the request, admission, return, authority,
  optional application/ACK, and interpretation references declared as the
  basis for the branch decision.

The verifier reconstructs the branch from the exact interpreted outcome,
checks the path gates and Ground fingerprint chain, and recomputes the receipt
hash chain. Availability and declared use remain different claims. The record
does not prove that a reference influenced the controller's computation.

The receipt's hash chain protects content integrity after export. It does not
authenticate actors, prevent rollback by an untrusted host, prove that an
exported journal is complete, or establish a global order across hosts. This
version retains one controller's ordered attempt sequence and does not combine
clock values from separate domains.

## Minimal integration

The implementation is dependency-injected so the IFS adapter does not import
or duplicate VGI internals. The VGI caller supplies:

- `score_partial_probe` as `score_probe`;
- `counterfactual_probe_ground` as `counterfactual_ground`;
- the fixed VGI revision used to construct the policy.

After `begin_next()`, the host drives the returned attempt through the
existing path methods. Once the final required gate has been recorded, the
host passes the interpreted outcome to `complete_active()`. Repeat while the
coordinator is `ready`; it reports `complete` when the policy reaches a
terminal node.

A receipt is built only after there is no active attempt. Independent
reconstruction is available through `validate_decision_receipt(receipt)`.

## Verification

The focused test suite is
`test_minimax_policy_execution.py`. Its CI workflow checks out VGI at
`ac13c1bbd92dfd09f17de51adef7adb2d2088bf6` and exercises two-step policy
execution, authority gating, model mismatch, receipt reconstruction, and
tamper detection.

This is a finite reference integration. It does not itself demonstrate a
live remote sensor, multi-host causal reconstruction, credential isolation,
or independently authenticated receiver journals.
