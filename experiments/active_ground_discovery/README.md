# CLT-002 — Active Ground discovery

A retained law is a source of candidate predictions and hence of questions to ask. This experiment tests the distinction between **conditional identification** inside a declared family and **unrestricted source admission**. It is deliberately finite and exact.

## Experiment

Acquire a prior 8-state, 3-action law (24 observations) with increment, nonlinear Boolean fold and modular square-plus-one. Construct the candidate family by affine relabelings z ↦ sz+b mod 8 for odd s. A second family includes every single-cell mutation of those transported tables. Candidate tables are deduplicated. The actual target oracle calculates each requested cell directly, independently of candidate-table construction, without exposing its parameters to the learner. Target worlds use all 32 charts and 16 single-cell mutations; no unrestricted generalization claimed.

For version space V and unqueried cell i, count predictions n(i,v). Select i minimizing sum_v n(i,v)^2 (uniform-prior expected remaining version count times |V|). Filter on the actual observed value. Compare against the same family with fixed-order probing and against full table acquisition (24 observations per source). Record candidate-cell reads and construction writes separately; these are operation counts, not wall-clock or energy. Map insertion, hashing, bucket arithmetic, source evaluation, and runtime allocation are not included.

A singleton is **CONDITIONAL**, not authority. A receiver with no independently established family contract must audit all remaining cells; combined distinct observations are exactly 24. A deliberately hidden mutation produces the same active prefix and an incorrect singleton, then fails independent complete audit. Budget exhaustion preserves ambiguity. The one-edit atlas tests the cost of broadening the prior against misspecification.

Native bridge: CI checks out the pinned CLT-001 proposal and E-CPU source, independently verifies the actual marker quotient, exports its distance-indexed law and reruns the JS experiment using that prior. The local standalone experiment uses an independently written fixture law, not a native E-CPU checkout. No inherited admission from an open PR is asserted. No source-family attestation, remote execution or pretrained-model claims.

## Reproduce

```sh
node experiments/active_ground_discovery/clt002.js
```

Optional native bridge (see workflow). Reported local tool execution uses the same JS function as the committed Node entry point. Results are in results.json.

## Next

Pay the full cost of qualifying a family contract (e.g. proof of permitted chart transformations), compare active queries against direct acquisition across varying measurement/compute costs, and learn which prior families are worth retaining. For arbitrary finite laws, a missing cell can conceal an adversarial difference; fewer conditional probes cannot prove unrestricted equivalence. A broader family may remove the query advantage entirely.

Prior: [CLT-001 proposal](https://github.com/Kier73/In-Formation-Space/pull/380), pinned at 34ce68b87ac4c531e2e6f104710233c77c1defe6.
