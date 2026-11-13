# RIV-017: Evidence-gated execution of robust sequential policy trees

**Status:** finite policy-prefix execution bridge, version 0.1.  
**Question:** How can an adaptive RIV-016 policy tree advance from one node to another only after an actual observation has been returned, authorized, and interpreted?

## Relationship to RIV-015 and RIV-016

RIV-015 and RIV-016 select candidate measurement policies under a finite unweighted set of plausible sensor-response models. RIV-016's result is a tree, not a measurement record:

- a node names the sensor to use;
- its branches describe declared outcomes;
- each child selects the next action or a terminal decision.

RIV-017 binds one actual ObservationPath to the current policy node. A request remains a planned object until its lifecycle has been completed. A returned signal is not allowed to advance the tree by prose assertion alone.

## Policy-state binding

A planned ObservationPath is bound to a digest of:

- the exact validated RIV-016 report;
- the active policy node;
- the already interpreted sensor/outcome prefix;
- all unnormalized joint-state mass vectors, one per fixed model scenario;
- the remaining pathwise cost budget;
- the remaining measurement horizon;
- the sensors already used on this path.

The intent candidate is `robust-sequential-sensor:<sensor_id>`. The intent requires explicit authority, while application and sender ACK are disabled. The estimated cost must equal the exact cost on the active policy node when represented in the ObservationPath's numeric field.

The executor reconstructs every prior ObservationPath independently and recomputes the active node and execution-state digest. A path prepared for a different prefix, policy revision, candidate sensor, or budget is rejected.

## Required evidence lifecycle

Each executed observation must contain exactly:

1. `planned`
2. `dispatched`
3. `admitted`
4. `returned`
5. `evidence_authorized`
6. `interpreted`

The returned and interpreted event details bind the same report digest, state digest, node digest, outcome history prefix, sensor ID, dimension, exact policy cost, and scalar outcome. The scalar outcomes are compared by exact JSON type and value.

The path must include an explicit `evidence_authorized` event with `decision_status = AUTHORIZED` before interpretation. The module checks the authority event's declared fields and digest syntax, but it does not independently authenticate the authority service, source set, signatures, quorum, or trust root. Use the separate RIV-013/RIV-014 evidence bundle when that additional provenance layer is required.

## Scenario-aware branch advancement

RIV-016 keeps one unknown likelihood scenario fixed throughout policy execution. RIV-017 preserves that property.

For each scenario (m), the current state contains the unnormalized joint masses:

[
w_m(h,zmid x_{1:t}) =
P_m(x_{1:t},H=h,Z=z).
]

After an authorized interpreted outcome (o) from sensor (s), it updates:

[
w'_m(h,z)=w_m(h,z)P_m(omid h,z,s).
]

These masses stay separate. RIV-017 does not average scenario likelihoods, assign probabilities to scenario identity, or create a posterior over model identity. It also does not re-optimize the policy after each observation: it follows the exact child already selected by RIV-016.

The execution record exposes both unnormalized masses and scenario-conditioned joint posteriors where their normalizers are positive. A scenario for which the observed prefix has zero probability retains zero mass and no normalized posterior.

## Mismatch and stop handling

There are two distinct mismatch cases:

- **Undeclared outcome:** if the returned scalar is not one of the active node's branch labels, the executor raises `RobustPolicyExecutionMismatch`. The observation is not coerced, mapped to a nearby branch, or silently added to the policy. It should be retained as evidence for a separate model-review or revision proposal.
- **Declared outcome impossible under every scenario:** RIV-016 emits an explicit `model_mismatch_stop` child with `stop_and_review`. RIV-017 records the authorized observation and stops there. It does not invent a next likelihood model or posterior.

The executor also refuses paths beyond a terminal decision, paths whose costs exceed the policy budget, duplicate attempt IDs, and repeated use of a sensor that RIV-016 has already removed from that branch's available set.

## API

```python
from robust_policy_execution import (
    new_robust_policy_observation_path,
    build_robust_policy_execution_record,
    validate_robust_policy_execution_record,
)

planned = new_robust_policy_observation_path(
    policy_report=robust_policy_report,
    prior_observation_paths=previous_authorized_paths,
    attempt_id="attempt-001",
)

# The executor/transport/sensor/authority/interpreter append the actual events.
# Only then can the prefix be reconstructed:
record = build_robust_policy_execution_record(
    policy_report=robust_policy_report,
    observation_paths=previous_authorized_paths + [completed_path],
)
validate_robust_policy_execution_record(record)
```

The `robust_policy_execution_example.py` script intentionally stops after creating a planned-only ObservationPath. Synthetic completed paths appear in tests so lifecycle and branch semantics can be verified without representing those fixtures as external sensor observations.

## Reproduction

From the repository root:

    python -m py_compile experiments/robust-likelihood-acquisition/robust_policy_execution.py
    python -m unittest discover -s experiments/robust-likelihood-acquisition -p 'test_robust_policy_execution.py' -v
    python experiments/robust-likelihood-acquisition/robust_policy_execution_example.py

The JSON record contract is defined in [robust-policy-execution.schema.json](robust-policy-execution.schema.json). The focused workflow validates the schema, compiles the policy and execution modules, runs the exact branch/authority/mismatch tests, and runs the planned-only example.

## Evidence scope and limitations

- Each ObservationPath is independently reconstructed through its recorded lifecycle rules. Evidence URIs are references; this module does not fetch or authenticate their external artifacts.
- `AUTHORIZED` is checked as a structurally valid path decision, not as a cryptographically authenticated authority outcome. The module does not verify source identity, quorum membership, signer identity, trust-root validity, or signature revocation.
- Returned `payload_digest` is checked for SHA-256 syntax and bound into the execution manifest, but the raw payload is not fetched or independently reconstructed here. Inline Encounter Envelope integrity and per-source evidence binding are separate RIV-013 concerns.
- The finite likelihood ambiguity set may not contain the true sensor model. Authorization of a path does not establish model correctness.
- The reported scenario-conditioned masses are conditional on the supplied RIV-016 joint prior and likelihood tables; they are not posterior probabilities over model identity.
- Exact cost comes from the policy node. It is not measured dispatch, transport, receiver admission, authority, interpretation, energy, latency, or operation-span cost.
- No source likelihood model, joint prior, Ground, or policy tree is revised by this execution record.
- SHA-256 digests support content identity and deterministic reconstruction, not external authenticity or physical truth.

## Next step

A subsequent RIV-018 bridge can wrap each completed RIV-017 path in an inline Encounter Envelope, verify each source record, and append an Authority Lineage decision/receipt. That would compose RIV-013/RIV-014 provenance with robust adaptive execution without claiming the signed bundle makes the underlying likelihood model physically true.
