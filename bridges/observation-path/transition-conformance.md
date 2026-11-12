# Transition conformance and model revision

**Status:** experimental evidence bridge for Trial 08  
**Connects:** [Trial 08: Intervention-aware attention](../../experiments/description-to-realization/trials/trial-08-intervention-aware-attention/README.md), the append-only observation path, and operation spans.

## Question

Trial 08 can plan over a supplied deterministic transition model. What happens when an actual probe is performed and an interpreted return plus before/after state witnesses become available?

This bridge compares one completed observation attempt with one model transition. It preserves the model prediction and the supplied observation separately. It does not treat a plan, dispatch, raw return, or elapsed-time sample as proof of a state transition.

## Required inputs

A conformance record binds:

- a fully validated Trial 08 model document and model reference;
- the probe identifier and the current state label;
- one append-only ObservationPath with `planned`, `dispatched`, `admitted`, `returned`, and `interpreted` stages in legal order;
- the raw return's Encounter Envelope reference, encounter ID, payload digest, and canonicalization;
- the exact value retained by the interpretation event;
- a before-state witness reference and SHA-256 digest;
- optionally, an after-state witness reference, digest, and declared next-state label.

The state witness values are references and labels supplied by the caller. This builder checks their shape and binds their digests into the record; it does not fetch, authenticate, or inspect the referenced artifacts. When an after-state witness is absent, only the visible outcome can be compared. The record will say `outcome_only_match` or `outcome_mismatch_state_unknown`; it will never claim full transition conformance.

## Conformance classifications

| Classification | Meaning |
|---|---|
| `matched` | Observed outcome and witnessed next state both match the model. |
| `outcome_mismatch` | The witnessed next state matches, but the visible outcome differs. |
| `next_state_mismatch` | The visible outcome matches, but the witnessed next state differs. |
| `transition_mismatch` | Both the outcome and next state differ. |
| `outcome_only_match` | Visible outcome matches, but no after-state witness was supplied. |
| `outcome_mismatch_state_unknown` | Visible outcome differs, but no after-state witness was supplied. |

A conformance document has a digest and can be independently rebuilt from the pinned model and the source ObservationPath using `validate_transition_conformance_record()`.

## Operation duration is not intervention cost

An optional operation span can be attached when it refers to the same attempt, completed successfully, and has a measured monotonic interval. Its scope, clock actor, clock segment, and elapsed nanoseconds are retained.

The operation span remains a performance measurement. It is not converted into the Trial 08 `intervention_cost`. That cost is a separate model quantity with units and semantics supplied by the model author. A calibration between elapsed duration and physical intervention impact would require a separate dimensional model and independent validation.

## Append-only model revision

`TransitionModelRevisionLedger` retains the initial Trial 08 model and later revisions. A complete mismatch with a witnessed next state can be proposed as a candidate override for one `(probe_id, current_state)` cell.

The lifecycle is explicit:

1. `propose_transition()` records a candidate and leaves the active model unchanged.
2. `validate_candidate()` records one caller-supplied result: `supported`, `rejected`, or `inconclusive`.
3. `activate_supported()` creates a new Trial 08 planner document only for selected candidates already marked supported.

Activation preserves the parent revision and all previous evidence. It updates only the candidate cell's observed outcome and next-state label. The parent's `intervention_cost` is preserved. Rejected and inconclusive candidates remain in the ledger and cannot be activated. A stale candidate based on an earlier model revision cannot be applied to a newer active revision.

The ledger's validation references and actor labels are retained as provenance claims; this module does not authenticate the reviewer or validation artifact. A digest protects content identity, not authorship or authority.

## Reproduce

From the repository root:

```bash
python -m py_compile bridges/observation-path/transition_conformance.py
python -m unittest discover -s bridges/observation-path -p 'test_transition_conformance.py' -v
```

The focused suite exercises lifecycle gating, full and partial comparisons, mismatch classifications, exact model reconstruction, optional operation spans, stale proposals, rejected/inconclusive proposals, and explicit supported activation.

## Limits and next experiments

This version assumes the Trial 08 finite state vocabulary and deterministic transition function. It does not add new world-state labels, infer stochastic distributions, model autonomous evolution, or learn intervention costs. State-space expansion and uncertainty-aware transition learning should be separate revision operations rather than implicit side effects of a mismatch.

A useful next experiment is to collect repeated, independently witnessed transitions for the same probe/state cell and test when their outcomes justify a deterministic model, a stochastic model, or a preserved unresolved disagreement.
