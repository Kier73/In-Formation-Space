# RIV-008: Decision-value context acquisition

**Status:** finite exact one-step value-of-information experiment, version 0.1.  
**Question:** Given a joint posterior over a target hypothesis and latent context, which candidate context observation best improves a declared decision, after accounting for observation cost?

## Relationship to RIV-006 through RIV-009

The shared evidence sequence constructs several distinct joint-belief models:

- [RIV-006: Context-switching evidence accumulation](../context-switching-evidence-accumulator/README.md) uses a hidden Markov operating regime that changes over time.
- [RIV-007: Calibration-aware joint evidence](../calibration-aware-joint-evidence/README.md) uses a discrete calibration profile drawn once and shared across a session.
- [RIV-009: Reference-calibrated evidence accumulation](../reference-calibrated-evidence/README.md) conditions the session-shared calibration prior on known reference standards before running the target filter.

These models preserve a joint posterior rather than discarding the association between the hypothesis and latent context. RIV-008 is deliberately model-agnostic at that boundary: it accepts a finite exact joint belief over a binary hypothesis and any finite set of context labels. The tests now construct input beliefs from all three upstream models, including the reference-conditioned target belief nested inside the RIV-009 report.

RIV-008 asks a different question from VGI's partial-probe minimax planner. VGI's planner chooses a worst-case policy to reduce unresolved attempt pairs. RIV-008 ranks one-step context-reading methods by their **expected reduction in Bayes decision loss**, using caller-supplied likelihoods, costs, and a declared task loss matrix. Neither objective is universally preferable; they answer different questions.

## Input contract

A joint belief is supplied as a finite list of exact probabilities:

```json
[
  {"hypothesis": "A", "context_state": "good",
   "probability": {"numerator": 1, "denominator": 4}},
  {"hypothesis": "A", "context_state": "degraded",
   "probability": {"numerator": 1, "denominator": 4}},
  {"hypothesis": "B", "context_state": "good",
   "probability": {"numerator": 1, "denominator": 4}},
  {"hypothesis": "B", "context_state": "degraded",
   "probability": {"numerator": 1, "denominator": 4}}
]
```

The probabilities must sum exactly to one. The belief document binds them to a source reference and source report digest; if an upstream state ID is supplied, it must equal the digest of the normalized joint-posterior rows. This establishes content identity, not authentication or independent validation of the upstream model.

Every candidate sensor declares:

- a unique `sensor_id` and context `dimension`;
- an exact positive rational `cost`;
- a finite set of outcome labels;
- one exact likelihood (P(omid H=h,Z=z)) for every candidate outcome and every joint state ((h,z)).

For each joint state, outcome likelihoods must sum exactly to one. Missing states, duplicate states or outcomes, floats, booleans used as numbers, and invalid probabilities are rejected. The candidate is modeled as a passive reading of the current context: it does not change the latent state or the target hypothesis during this one-step calculation.

## Decision value

The caller supplies a two-action loss matrix. By default it is symmetric zero-one classification loss:

[
L(a,h)=
egin{cases}
0 & a=h\
1 & a
e h.
end{cases}
]

At current belief (b(h,z)), the expected loss of action (a) is

[
R(amid b)=sum_{h,z} b(h,z)L(a,h).
]

The current Bayes decision risk is

[
R^*(b)=min_a R(amid b).
]

For a candidate sensor with outcome (o), its predictive probability is

[
P(omid b)=sum_{h,z}b(h,z)P(omid h,z).
]

For reachable outcomes, Bayes' rule gives

[
b_o(h,z)=
rac{b(h,z)P(omid h,z)}{P(omid b)}.
]

The one-step expected posterior risk and value of sample information are

[
mathbb{E}[R^*(b_O)]
=sum_{o:P(omid b)>0}P(omid b)R^*(b_o),
]

[
operatorname{EVSI}(s)
=R^*(b)-mathbb{E}[R^*(b_O)].
]

For nonnegative losses, EVSI must be nonnegative. The implementation asserts this invariant exactly. It also reports EVSI divided by the declared cost, the probability that the optimal action changes, and each outcome's complete posterior and risk contribution.

Candidates are ranked by exact EVSI/cost, then exact EVSI, then lower cost, then lexical sensor ID. A separate cost-versus-posterior-risk Pareto frontier retains candidates that are not dominated, so a caller can see trade-offs instead of only one winner. An optional cost budget filters eligibility without changing the underlying candidate scores.

## Exact RIV-006-derived example

The example takes a layer-two joint belief from the Markov-regime RIV-006 model. Its target-hypothesis posterior is

[
P(H=A)=rac12,
]

so the current symmetric Bayes risk is (1/2). The predictive probability that the next operating regime is good is (301/890). Four candidate context readers are evaluated:

| Candidate | Good outcome if context is good | Good outcome if degraded | Exact cost |
|---|---:|---:|---:|
| high-fidelity-context | 9/10 | 1/10 | 1 |
| budget-proxy | 2/3 | 1/3 | 1/2 |
| perfect-context-audit | 1 | 0 | 2 |
| blind-context | 1/2 | 1/2 | 1/4 |

Under the declared model and zero-one loss:

| Candidate | Expected posterior risk | EVSI | EVSI / cost |
|---|---:|---:|---:|
| high-fidelity-context | 413/890 | 16/445 | 16/445 |
| budget-proxy | 259/534 | 4/267 | 8/267 |
| perfect-context-audit | 81/178 | 4/89 | 2/89 |
| blind-context | 1/2 | 0 | 0 |

The high-fidelity reader wins on expected decision-risk reduction per unit cost. The perfect audit obtains more absolute information value than the budget proxy, but its cost is higher. Under a cost budget of (3/4), only the proxy and blind reader are eligible, and the proxy is selected. All four remain on the Pareto frontier for this fixture because lower risk comes with higher cost.

This is a constructed decision-value example, not measured sensor performance. The ranking follows from the supplied joint belief, likelihoods, losses, and costs.

## API

```python
from decision_value_acquisition import (
    build_joint_belief_document,
    build_report,
    validate_report,
)

belief = build_joint_belief_document(
    joint_posterior=upstream_joint_posterior,
    source_ref="artifact://joint-filter/report",
    source_report_digest=upstream_report_digest,
    source_state_id=upstream_state_id,
)

report = build_report(
    joint_belief=belief,
    candidate_sensors=candidate_context_readers,
    loss_matrix=None,     # defaults to symmetric zero-one classification loss
    cost_budget="3/4",
)
validate_report(report)
```

The report embeds the complete joint belief, candidate likelihood models, outcome branches, posterior beliefs, exact expected-risk contributions, ranking, and Pareto frontier. The published [JSON Schema](decision-value-acquisition.schema.json) defines its portable shape. Its validator rebuilds the result from those retained inputs. The digest detects content mutation; it does not authenticate the upstream report or candidate sensor source.

## Evidence scope and limitations

- This is **one-step expected value of sample information** for a fixed binary decision, not a multi-step policy or sequential stopping strategy.
- Candidate likelihoods are declared inputs. The experiment does not estimate sensor models from calibration data or establish their truth.
- The candidate reading is assumed passive: it does not alter the target hypothesis or latent context while being acquired.
- The belief and likelihood state spaces are finite and exact. Continuous calibration, unknown candidate likelihoods, correlated residual errors, and state evolution during measurement require richer models.
- Expected value depends on the declared loss matrix. A different task objective can change the ranking even with identical sensor models and posterior.
- Cost is a caller-supplied positive rational in a common declared unit. The experiment does not convert elapsed time, queue delay, transport cost, or energy into that unit.
- Expected-value ranking does not replace worst-case planning. A low-probability but high-consequence branch may motivate a separate robust or minimax criterion.
- The output is a proposal only. No measurement is dispatched, no ObservationPath is advanced, and no joint belief or transition model is revised.
- Digests provide content identity and reconstruction checks, not authentication of actors, sensors, sources, or execution receipts.

## Reproduction

From the repository root:

    python -m py_compile experiments/decision-value-context-acquisition/decision_value_acquisition.py experiments/decision-value-context-acquisition/example.py
    python -m unittest discover -s experiments/decision-value-context-acquisition -p 'test_*.py' -v
    python experiments/decision-value-context-acquisition/example.py

The implementation uses only the Python standard library and exact `Fraction` arithmetic. All probabilities, losses, and costs are validated as exact rationals; no floating-point approximation or sampling is used.

## Evidence-gated measurement execution

The [RIV-008 execution adapter](acquisition-execution.md) now binds the selected reader to a planned-only ObservationPath. It requires dispatch, receiver admission, return, explicit AUTHORIZED evidence, and exact interpretation before conditioning the joint posterior on the observed outcome.

A returned outcome outside the candidate model, or a declared outcome with zero predictive probability under the prior joint belief, is rejected as a model mismatch. A valid outcome creates a new immutable joint-belief snapshot and a measurement manifest bound to the full ObservationPath. It does not update the source Ground, likelihood model, or active attention policy.

The execution record also reports the *realized* Bayes decision-risk change for the observed branch. This is distinct from the non-negative expected value of sample information calculated before measurement: one outcome can increase the posterior decision risk even when the candidate has positive EVSI overall.

- [Execution implementation](acquisition_execution.py)
- [Execution tests](test_acquisition_execution.py)
- [Measurement record schema](decision-value-measurement.schema.json)
- [Execution evidence contract](acquisition-execution.md)

## Next discriminating step

The next extension is sequential acquisition: recompute candidate value after each authorized outcome, accounting for updated belief, remaining budget, and possible context-dependent measurement cost. That should be compared against finite-horizon dynamic programming and the existing VGI worst-case minimax policy, preserving their different objectives.
