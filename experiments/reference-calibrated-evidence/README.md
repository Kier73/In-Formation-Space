# RIV-009: Reference-calibrated evidence accumulation

**Status:** finite exact two-phase calibration experiment, version 0.1.  
**Question:** When the observer has access to known calibration standards, how does their evidence change the shared calibration belief used for a later unknown target?

## Relationship to RIV-007 and RIV-008

[RIV-007: Calibration-aware joint evidence](../calibration-aware-joint-evidence/README.md) shows why an observer must retain a joint posterior over the target hypothesis and a session-shared calibration profile. RIV-009 adds a reference phase before the target observations. Known standards update the calibration-profile prior; that posterior is then passed into RIV-007's joint target filter.

[RIV-008: Decision-value context acquisition](../decision-value-context-acquisition/README.md) asks which context observation is worth acquiring under a supplied decision-loss objective. RIV-009 answers a different question: given a supplied sequence of known-reference observations, what calibration posterior follows, and how does using it change the subsequent target policy?

RIV-009 deliberately reuses RIV-007's public build_report() and validate_report() functions for every target-phase filter. It checks the RIV-007 report format at import time and independently reconstructs every nested report. It does not fork the shared-calibration target update rule.

## Two phases, one calibration state

Let C be one calibration profile drawn from a finite prior. It remains fixed through both phases.

**Reference phase.** Each reference event supplies a known standard hypothesis h_j, a sensor type i_j, and an observed binary signal x_j. Under conditional independence:

\[
P(C=c\mid r_{1:m})\propto P(C=c)\prod_{j=1}^{m}P(x_j\mid h_j,c,i_j).
\]

Each event also carries a reference-standard reference and digest, an observation reference and digest, an event identifier, and an exact positive caller-declared cost. The sequence is retained in its received order; the final posterior is order-independent under the declared conditional-independence model, while the prefix trace shows each intermediate update.

**Target phase.** The target hypothesis H is unknown and begins with its declared prior, independent of the reference standards. The updated calibration posterior becomes the calibration prior for RIV-007's joint filter:

\[
b_0(h,c)=P(H=h)P(C=c\mid r_{1:m}).
\]

The target filter then updates the complete joint belief over (H,C) for the target sensor schedule. The same calibration profile is retained; it is not independently redrawn for each target reading.

## Fair policy comparison

Three target policies are constructed:

1. **Uncalibrated-prior policy:** use the original calibration prior and ignore the reference outcomes.
2. **Reference-conditioned Bayes policy:** use the exact posterior calibration distribution after the reference phase.
3. **MAP-profile plug-in policy:** collapse the calibration posterior onto its most probable profile, with lexical profile ID as a deterministic tie-break.

All three policies are evaluated against the **same** target world: the target hypothesis prior combined with the final reference-conditioned calibration posterior. This avoids comparing accuracy values whose hidden data-generating calibration assumptions differ. The MAP-profile comparator may assign zero probability to some target histories that remain possible in the evaluation world. For this explicit out-of-support case, the experiment declares fallback action A and reports the probability mass requiring that fallback.

For each reference prefix, the report records the posterior over calibration profiles, cumulative evidence probability, cumulative declared cost, and the corresponding target policy's accuracy in that same final evaluation world. The realized prefix-accuracy sequence is not asserted to be monotonic.

## Exact fixture

Two profiles have equal prior probability. The first sensor has response probabilities:

| Profile | P(signal A given standard A) | P(signal A given standard B) |
|---|---:|---:|
| profile-1 | 9/10 | 1/10 |
| profile-2 | 3/5 | 2/5 |

Two known A standards each produce signal A on sensor-1. With a prior of 1/2 per profile:

\[
P(C=profile\text{-}1\mid AA)=\frac{9}{13},\qquad
P(C=profile\text{-}2\mid AA)=\frac{4}{13}.
\]

The reference evidence probability is 117/200; total declared reference cost is 1. The unknown target then uses sensor schedule (sensor-1, sensor-2, sensor-3) with equal prior probability for target hypotheses A and B.

Evaluating each policy in the same reference-conditioned target world gives:

| Target policy | Exact expected MAP accuracy |
|---|---:|
| Uncalibrated-prior policy | 5119/6500 |
| Reference-conditioned Bayes policy | 21/26 |
| MAP-profile plug-in policy | 4981/6500 |

The reference-conditioned policy gains 131/6500 over the uncalibrated-prior policy and 269/6500 over the MAP-profile plug-in policy in this fixture. These are exact model-conditional expected accuracies, not measured sensor performance or a guarantee that every reference stream improves every task.

## Reproduction

From the repository root, run:

    python -m py_compile experiments/reference-calibrated-evidence/reference_calibrated_evidence.py
    python -m unittest discover -s experiments/reference-calibrated-evidence -p 'test_*.py' -v
    python experiments/reference-calibrated-evidence/example.py

The implementation uses Python's standard library and exact Fraction arithmetic. The workflow validates the published Draft 2020-12 JSON Schema, compiles the adapter and example, runs the focused tests, and executes the example.

## Provenance and adjacent systems

The bridge to [ObservationPath](../../bridges/observation-path/README.md) is conceptual in this version: RIV-009 retains reference-standard and raw-observation identities, but it does not dispatch a request, authenticate a source, authorize a quorum, or advance an ObservationPath lifecycle. The append-only [hypothesis-revision ledger](../../bridges/hypothesis-revision/README.md) remains the place for proposed model changes and explicit validation; a calibration posterior update is not automatic model revision.

VGI's [partial-attention implementation](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/vgi/partial_attention.py) evaluates counterfactual transition distinctions under worst-case or supplied scenario weights. RIV-009 instead updates a Bayesian calibration belief from explicitly supplied likelihoods. These are complementary semantics, not interchangeable scoring methods.

E-CPU's [Observed Orbit Pipeline](https://github.com/Kier73/E-CPU/blob/main/docs/OBSERVED_ORBIT_PIPELINE.md) preserves temporal/source evidence and distinct logical coordinates. RIV-009 does not use clock-coordinate calibration as a substitute for sensor-response calibration; reference evidence order is supplied explicitly, and no cross-clock inference is performed.

## Evidence scope and limitations

- The calibration family is discrete, supplied, finite, and fixed across the complete reference-plus-target session. Continuous uncertainty, intra-session drift, and residual dependence after conditioning on the profile are not modeled.
- Reference labels are treated as known standards. Their truth, chain of custody, authority, and physical measurement integrity are not authenticated by this experiment. SHA-256 binds supplied content; it is not a signature.
- Reference observations update the calibration-profile posterior only. The target-hypothesis prior is assumed independent of the known reference standards.
- Reference sensor types must occur in the target schedule in this version, because RIV-007 requires each profile to define exactly the sensor types in its target schedule.
- Costs are exact caller-declared values in one common unit. They are not measured latency, transport, admission, energy, or operation-span costs.
- The comparison is model-conditional expected accuracy evaluated under one declared reference-conditioned model. It is not empirical generalization to a physical sensor network.
- The MAP-profile plug-in policy has an explicit A fallback on target histories impossible under its single selected profile but possible under the evaluation posterior.
- RIV-007 retains its finite full-history enumeration cap. Exceeding it fails closed; no approximate inference is substituted.
- The adapter checks a specific RIV-007 report format. Future changes to that contract require an explicit adapter revision.

## Files

- reference_calibrated_evidence.py — reference likelihood update, prefix/cost trace, RIV-007 target-filter reuse, common-world policy evaluation, and report reconstruction.
- test_reference_calibrated_evidence.py — exact posterior, common-world policy comparisons, prefix behavior, impossible evidence, provenance validation, nested report reconstruction, and tamper tests.
- example.py — reproducible two-standard, three-sensor target example.
- reference-calibrated-evidence.schema.json — portable report schema.
- README.md — model, exact results, reuse boundaries, and evidence limitations.
