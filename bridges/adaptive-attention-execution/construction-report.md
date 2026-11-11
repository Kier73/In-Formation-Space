# Construction report: adaptive attention execution bridge

**Status:** experimental coordinator tested in integrated CI.  
**Connects:** Trial 06 adaptive policies and the evidence-gated observation path.

## Construction

The coordinator consumes a complete policy tree by its documented attributes rather than importing a particular planner package. It receives the available observation candidates, an attempt-ID prefix, a query label, a caller-supplied hypothesis-set digest function, and an optional plan reference.

At each non-terminal policy node it creates a new ObservationPath request intent. An external adapter then reports dispatch, receiver admission, and a returned Encounter Envelope reference. The interpreter supplies a branch value and interpretation artifact reference. The coordinator compares that interpreted value against the policy node's explicit branches.

Three outcomes are possible:

1. **Predicted terminal branch:** the request attempt closes as query_determined, recording the Boolean result, the remaining hypothesis-set digest, and its evidence basis.
2. **Predicted non-terminal branch:** the current attempt closes as continued, naming the next attempt and observation selected by the policy. A new request path must begin for that next observation.
3. **Unpredicted branch:** the attempt closes as unresolved. The raw return and interpretation references remain preserved, and the run stops with unresolved_model_mismatch. No nearest-branch or majority guess is made.

Dispatch failure, receiver rejection, return without admission, admitted timeout, and interpreter failure are separately recorded as terminal outcomes. None is converted into a negative sensor value.

## Evidence boundaries

The coordinator does not execute a transport or sensor action. It records stage claims only after an external adapter reports that the stage occurred. It stores Encounter Envelope references, payload digests, and canonicalization labels, but does not fetch or authenticate the referenced artifact. The observation-path validator checks the record shape and lifecycle consistency; the Encounter Envelope validator checks envelopes separately.

Clock values are stored together with their clock-domain labels. The coordinator performs no cross-clock arithmetic.

## Live E-CPU integration

The adapter has been run against E-CPU commit `800f94f83ffd6f527ed093c8d1c1e93e153c34f6` in In-Formation-Space GitHub Actions run 172. The live integration suite passed 2 tests:

- strict two-source quorum authorization, representative VM application, durable checkpoint restoration, and separate sender ACK processing;
- strict consensus conflict, terminal evidence refusal, unchanged VM state, and unconsumed/unacknowledged receiver frames.

The machine-readable [live integration receipt](../observation-path/results/live-ecpu-integration-run-172.json) preserves both repository SHAs and the exact tested operations.

## Verification

GitHub Actions run 112, commit 3c8d2ecdcd0bdedf746dcff4fd1813a73f4a6155, completed successfully on ubuntu-latest with Python 3.11.

Relevant suites:

- Observation-path lifecycle: 10 tests passed.
- Observation-path JSON Schema and lifecycle validator: 4 tests passed.
- Adaptive policy execution: 11 tests passed.

The execution test covers a two-observation policy that continues after the first interpreted value and resolves after the second; a result outside the predicted branches; planning without dispatch; receiver rejection; dispatch failure; unadmitted return; timeout; interpretation failure; missing next-observation candidate; and an already-resolved policy requiring no request.

The full integrated workflow ran 143 tests across the envelope, equivalence, observation path, six trials, guarded shortcut, and logistic-map experiments. All suites and the example path-record validation passed. The machine-readable encounter receipt is stored in the sibling observation-path results directory.

## Limits and next integration work

This is a protocol coordinator, not a live E-CPU or host adapter. A production adapter must bind the methods to actual transport calls, authenticate receiver admission, preserve the actual raw payload, validate the referenced Encounter Envelope, and supply a trustworthy interpretation artifact. The policy assumes deterministic predicted outcomes; any unexpected real outcome is deliberately treated as model mismatch and a reason to revise the hypothesis or observation model.