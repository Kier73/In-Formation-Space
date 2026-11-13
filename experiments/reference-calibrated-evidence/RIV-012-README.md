# RIV-012: Evidence-gated execution of finite-horizon reference policies

**Status:** finite policy-prefix execution bridge, version 0.1.  
**Question:** How does a selected action in an adaptive RIV-011 policy become an authorized observation, advance exactly one branch, and produce the cumulative RIV-009 calibration belief?

## Policy is not evidence

RIV-011 returns an adaptive policy tree. A tree node names the next known-standard reading, and its two signal branches point to different posterior states and possible next actions. That is still only a plan.

RIV-012 creates a planned-only ObservationPath for the current node. The path is bound to:
- the RIV-011 policy report digest;
- the digest of the exact policy node;
- the current calibration posterior;
- the sequence of already interpreted reference signals;
- the remaining pathwise cost budget.

A path created from an earlier policy state cannot be replayed after a different signal has moved execution to another branch.

## One-step execution lifecycle

A path is accepted only when its events reconstruct through exactly:

planned → dispatched → admitted → returned → evidence_authorized → interpreted

The returned and interpreted events must agree on the policy report, state digest, node digest, signal prefix, candidate, sensor, known standard and standard digest. The signal must be an outcome declared reachable by that node. The ObservationPath itself enforces the structured AUTHORIZED decision contract.

Only after these checks does the adapter:
1. create the corresponding RIV-009 reference-observation row from the returned payload;
2. update the calibration posterior by following the selected policy branch;
3. replay all accumulated reference observations from the original RIV-011 calibration prior through RIV-009;
4. compare the cumulative RIV-009 posterior and target MAP accuracy with the current RIV-011 child node.

The output is an immutable policy-execution prefix. It records all paths, signal history, reference rows, evidence references, current posterior, remaining budget, next action and cumulative RIV-009 report. A caller can request the next planned path from that record's prior paths; the next action is resolved from the actual authorized signal history.

## Reproduction fixture

The example executes two synthetic fixture paths:
- first, sensor-0 against standard A returns signal A;
- second, the policy's child node chooses sensor-1 against standard A, which also returns signal A.

The example then rebuilds one cumulative RIV-009 report from both reference rows. Its paths use synthetic event references and fixture digests. They demonstrate the lifecycle contract; they are not physical sensor readings, real dispatch, verified standards, or authenticated quorum decisions.

## Reproduction

From the repository root:

    python -m py_compile experiments/reference-calibrated-evidence/finite_horizon_policy_execution.py
    python -m unittest discover -s experiments/reference-calibrated-evidence -p 'test_finite_horizon_policy_execution.py' -v
    python experiments/reference-calibrated-evidence/finite_horizon_policy_execution_example.py

The workflow validates the execution-record schema, compiles the ObservationPath and RIV-009/RIV-011 dependencies, runs branch-specific and multi-step replay tests, and executes the synthetic example.

## Evidence scope and limitations

- Path lifecycle, authority decision shape, and digest consistency are structurally reconstructed. Referenced dispatch, admission, Encounter, authority and interpretation artifacts are not fetched or cryptographically authenticated here.
- AUTHORIZED is a supplied lifecycle decision, not independent proof of source identity, quorum member identity, signer authenticity or the physical truth of the standard.
- The adapter accepts only known standards and signal outcomes A/B in the current RIV-011 model.
- Calibration remains discrete and fixed. Sensor likelihoods and independent conditional reference noise are supplied model assumptions.
- Cumulative RIV-009 inference is rebuilt from the original calibration prior and all accepted reference rows. Each prefix is kept separate; prior reports are not overwritten.
- This adapter does not revise the sensor model, source Ground, or hardware calibration. It changes only the admitted session belief under the declared model.
- The policy tree remains bounded by its original finite candidate set, horizon and pathwise budget.
- SHA-256 provides content identity and reconstruction, not authentication.

## Files

- finite_horizon_policy_execution.py — current-node plan creation, strict path reconstruction, branch update, cumulative RIV-009 report and immutable prefix record.
- test_finite_horizon_policy_execution.py — adaptive branching, multi-step replay, stale path rejection, authority, mismatch, tampering and schema tests.
- finite_horizon_policy_execution_example.py — reproducible two-step synthetic execution prefix.
- finite-horizon-policy-execution.schema.json — portable policy execution record schema.
