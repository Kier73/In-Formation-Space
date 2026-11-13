# RIV-016: Finite-horizon robust sequential acquisition

**Status:** finite exact dynamic programme, version 0.1.  
**Question:** When sensor-response likelihoods remain ambiguous and multiple measurements can be acquired adaptively, how should an observer choose a complete outcome-dependent policy without assigning probabilities to the possible models?

## Relationship to RIV-015

[RIV-015](README.md) chooses a single measurement and one outcome-to-action mapping under a finite unweighted likelihood ambiguity set. RIV-016 extends the same contract to a finite policy tree:

- a node can stop and decide A/B;
- or choose an unused sensor;
- each declared sensor outcome leads to a different child policy;
- all branches belong to one tree shared across every model scenario.

This is not repeated greedy one-step selection. It evaluates complete bounded policy trees with the same persistent ambiguity scenario over the full execution.

## A persistent model, not a branch-switching adversary

A crucial modelling choice is whether the same unknown likelihood model governs the entire run. RIV-016 adopts that *persistent-scenario* interpretation. If scenario m is the true model, it remains m after every outcome.

For a policy tree (pi), scenario m induces an expected terminal decision loss:

[
R_m(pi)=sum_{ellinmathrm{leaves}(pi)}
P_m(ell),L(a_ell,H).
]

The robust objective is applied **after the complete policy tree has been evaluated under each scenario**:

[
R_{mathrm{robust}}(pi)=max_{minmathcal M}R_m(pi).
]

The policy tree itself is selected to minimize this maximum, subject to the pathwise cost budget and measurement horizon.

This differs from a *rectangular* or stagewise adversary that may choose a different likelihood scenario after every outcome. That would be a different uncertainty model and can yield a more conservative value. RIV-016 does not silently switch to that interpretation.

## Scenario-specific mass vectors

The observer begins with a content-bound joint belief over hypothesis and finite context. At a node the dynamic programme carries one unnormalized mass vector per scenario:

[
w_m(h,z;,x_{1:t})
=P_m(x_{1:t},H=h,Z=z).
]

After selecting sensor s and observing outcome o, the child mass is:

[
w_m'(h,z)=w_m(h,z)P_m(omid h,z,s).
]

No probability is assigned to the scenario identity, and no scenario average is computed. The vector records the probability of this same observed prefix under each possible model.

At a terminal decision a, the scenario's contribution is simply:

[
R_m^{mathrm{node}}(a)=
sum_{h,z}w_m(h,z)L(a,h).
]

The child subpolicy risks are added branchwise for each fixed scenario. Only at the root is the maximum across scenarios taken.

A branch whose outcome has zero probability under **every** declared scenario becomes an explicit `model_mismatch_stop` node with disposition `stop_and_review`. The optimizer does not invent a new likelihood model for it.

## Resource contracts and Pareto pruning

Every candidate sensor has an exact positive caller-declared cost and may be used at most once on any path. The policy obeys:

- a finite maximum number of measurement acquisitions;
- a pathwise cost budget: no reachable policy path may exceed it;
- a finite DP-state cap;
- a finite Pareto-frontier cap;
- a finite branch-policy combination cap.

At each DP state, the implementation keeps policies that are not componentwise dominated across:

1. expected decision loss under every model scenario;
2. expected acquisition cost under every scenario;
3. maximum path cost;
4. maximum number of measurements on a path.

A policy that is better in one model but worse in another remains available. This preserves trade-offs rather than collapsing the ambiguity set to an average.

At the root the selected policy minimizes worst-case expected decision loss; ties prefer lower worst-case expected measurement cost, then lower maximum path cost, then fewer measurements, then deterministic canonical tree order. The report also exposes the full root Pareto frontier.

## Exact adaptive example

The fixture begins with (P(H=A)=P(H=B)=1/2), uses one declared likelihood model, and has three readers, each with cost (1/10):

| Reader | (P(yesmid H=A)) | (P(yesmid H=B)) |
|---|---:|---:|
| screen | 4/5 | 1/5 |
| reader-a | 9/10 | 2/5 |
| reader-b | 3/5 | 1/10 |

The pathwise budget is (1/5), and at most two readings may be acquired.

The selected tree is adaptive:

```text
screen
├── yes  -> reader-a -> terminal decision
└── no   -> reader-b -> terminal decision
```

After a “yes,” the screen shifts the target belief toward A and reader-a is the better remaining discrimination. After “no,” the belief shifts toward B and reader-b becomes the better follow-up. Both branches use one shared policy rule; neither is selected with knowledge of the hidden model.

The exact robust terminal risk is:

[
R_{mathrm{robust}}=rac{4}{25},
]

from a baseline risk (1/2), yielding robust loss reduction:

[
rac12-rac4{25}=rac{17}{50}.
]

The policy uses both measurements on every possible branch, so maximum path cost and scenario expected cost are both (1/5). This is a constructed finite fixture, not a measured sensor network.

## API

```python
from robust_sequential_acquisition import (
    build_report,
    validate_report,
)

report = build_report(
    joint_belief=joint_belief,
    candidate_sensors=candidates,
    model_scenarios=unweighted_likelihood_scenarios,
    path_cost_budget="1/5",
    max_measurements=2,
)
validate_report(report)
```

The report retains the complete joint belief, scenario likelihoods, candidate set, search caps, selected recursive policy tree, scenario-specific expected losses and costs, and root Pareto frontier. Its validator rebuilds the finite dynamic programme from those inputs.

## Reproduction

From the repository root:

    python -m py_compile experiments/robust-likelihood-acquisition/robust_sequential_acquisition.py
    python -m unittest discover -s experiments/robust-likelihood-acquisition -p 'test_robust_sequential_acquisition.py' -v
    python experiments/robust-likelihood-acquisition/robust_sequential_example.py

The implementation uses exact `Fraction` arithmetic. Search and frontier limits fail closed; no sampling or approximate policy is silently substituted.

## Evidence scope and limitations

- The model scenario is fixed across the entire policy-tree execution. A stagewise adversary that can switch scenarios after each outcome is outside this version.
- The finite ambiguity set is caller-supplied. The true model may lie outside it.
- No probability is assigned to model identity and scenario losses are not averaged.
- One tree maps observed outcome histories to sensor choices and terminal actions; it cannot observe the hidden scenario.
- The target/context joint prior and candidate likelihood tables are supplied assumptions. Uncertainty in the prior itself is not included in this version.
- The loss matrix is fixed. Different tasks can induce different policy trees.
- Sensors are passive readings and do not change the target/context state during acquisition.
- Each sensor may be used once per path; repeated readings of the same sensor are not represented as separate time-indexed actions.
- Costs are exact caller-supplied values, not measured dispatch, transport, receiver admission, quorum authority, interpretation, energy, or latency.
- The finite DP and Pareto frontier may grow rapidly. The implementation fails closed at declared limits.
- This is a policy proposal only. No sensor is dispatched, no ObservationPath is advanced, and no belief, Ground, or source model is revised.
- SHA-256 digests identify content and support reconstruction; they do not authenticate sources, likelihood truth, reviewers, or physical measurements.

## Next step

A subsequent execution bridge could bind each selected policy node to an ObservationPath and only advance one child after an authorized interpreted result. It must preserve the fixed-scenario semantics while retaining the actual returned evidence, and it must treat an outcome outside all declared branches as model mismatch rather than automatically refitting a model.
