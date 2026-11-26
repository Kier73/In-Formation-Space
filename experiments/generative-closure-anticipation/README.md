# GLA-003 — Anticipatory representation discovery

Follow-up to [GLA-002](../generative-closure-detours/README.md). Can an observer estimate the usefulness of a representation before constructing it?

## Local virtual observations

For the first-difference operator D with its first coordinate preserved, the transformed entry of E = D^r A (D^T)^c equals the truncated binomial stencil sum over a=0..min(r,i), b=0..min(c,j) of (-1)^(a+b) binom(r,a) binom(c,b) A[i-a,j-b]. Thus a coordinate of a depth-three candidate can be computed from a bounded local window without constructing intermediates. This is classical finite difference algebra. We sample 64 locations with replacement using a reproducible pseudorandom generator and use the same locations for all nine candidates. Compare observed nonzero frequency to exact root support. The estimated application cost is 2 n^2 times that frequency plus (r+c)(n-1).

## Policies and cost

Direct sparse baseline; exhaustive shared-state depth-three search; point-estimate probe; conservative confidence probe; and a free-information oracle (not executable without exact support knowledge). The oracle charges materialization and certification of the chosen candidate, but not the knowledge used to choose it. Probe policies gate impossible payback using a loose upper bound on savings. Rank candidates by estimated q-column savings minus acquisition cost, attempt at most one, and admit only if exact subsequent application savings cover the remaining certificate cost. Already-spent search cost is sunk; a failed probe can still lose money. The conservative policy adds sqrt(log(9/0.05)/(2*64)) to each estimated support fraction, clipped at one: a one-sided Hoeffding union bound under ideal IID uniform sampling. The deterministic PRNG experiment is not a proof of statistical coverage. No correctness claim depends on the statistical estimate.

Charge root and final encoding scans (2 n^2), four units per stencil summand (read, two multiplies, addition), n(n-1) per full difference, n^2 per support scan, n(n-1) per inverse integration and n^2 per coefficient comparison. Application cost is exact field-operation count for sparse application plus integration; indexing, allocation, PRNG, sorting and memory traffic are unpriced. Exhaustive reference shares intermediate states. Across horizons reference tables and probe samples are reused for measurement, but their full logical costs are charged independently per decision. Probe attempts construct the chosen representation directly, not by reading the exhaustive reference. The reference and extra stencil checks are validation work not charged to policies.

Four sizes, six seeds, ten families and five horizons. Includes depth-four (outside vocabulary), localized corruption, row permutation, random, sparse and identity controls. Synthetic families deliberately test the known vocabulary. One new RHS for each decision checked against direct arithmetic, plus inverse certificates and held-out stencil comparisons. No actual wall-clock speedup or unrestricted matrix-multiplication claim.

## Reproduction

`node experiment.js > results.json`

Executed the same function in a JS runtime: 3600 exact product checks, 1496 coefficient-level inverse certifications, and 17280 local stencil comparisons passed. Retained compact JSON contains per-decision results and aggregate means. The oracle is relative to a single chosen transform and the stated acquisition ledger, not all possible algorithms.

## Frontier

Observe whether a local stencil policy can be refined by adaptively allocating probes to competing candidates, or discover the stencil coefficients rather than specifying them. Use localized adversaries and stronger arithmetic baselines, count real runtime and memory, and explore learned recurrence operators under exact certificates. 
