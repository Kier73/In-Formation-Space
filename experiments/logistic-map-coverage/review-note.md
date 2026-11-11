# Independent review: logistic-map coverage scan

**Status:** methodological review; original scan and encounter preserved.  
**Scope:** scan_coverage.py, results/analysis.md, and results/coverage-encounter.json.

## Summary

The scan is a useful first numerical exploration. It records a deterministic parameter grid, candidate periods, estimated widths of contiguous grid runs, and a coverage matrix over selected resolution and period budgets.

The reported values are evidence about that finite numerical procedure. They do not yet establish the exact measure of stable periodic windows, a plateau for all larger period budgets, or the measure of the full regular parameter set.

## What the current code measures

Let \(N\) be the number of parameter samples, \(W\) the transient warmup, \(\tau\) the return tolerance, and \(P_{\max}\) the period search ceiling.

The implementation:

1. samples \(r\) uniformly on the interval [3.5, 4.0];
2. iterates from the initial condition x=0.5 for W steps;
3. searches periods up to P_max for a single approximate return to the post-warmup state within tolerance tau;
4. computes a candidate cycle multiplier from that approximate orbit;
5. groups consecutive grid samples classified with the same stable candidate period;
6. sums the estimated widths of candidate runs meeting the requested width and period filters.

A more accurate name for the reported quantity is therefore a finite-grid estimate:

\[
\widehat C_{N,W,\tau}(\delta,P)
\]

It depends on the grid, initial condition, warmup, tolerance, maximum searched period, floating-point arithmetic, and candidate-window grouping procedure. It is not yet an independently certified value of the exact continuous-parameter coverage function.

## Limits affecting interpretation

### 1. A single near-return is a heuristic, not a cycle certificate

The classifier searches for one p-step return to x_base satisfying an absolute tolerance. A near recurrence in a transient or non-periodic orbit can satisfy a finite tolerance. The code does not require the return to persist over several further periods, compare multiple initial conditions, or certify the cycle for a whole parameter interval.

The multiplier is calculated from the first detected orbit segment. If the transient has not sufficiently converged, it may not accurately describe the eventual attracting cycle.

A more robust numerical classifier should check repeated p-step returns, use an explicit stability margin, and vary warmup and initial conditions. These measures would improve numerical evidence but still would not constitute a rigorous interval proof.

### 2. Grid runs are candidate intervals, not certified parameter windows

The start and end points are inferred from neighboring grid samples. The scanner does not solve for bifurcation boundaries or prove that every parameter between those approximated endpoints has the same stable attracting cycle.

The quoted widths are therefore discretized estimates. Calling them certified windows overstates the evidence.

### 3. An observed plateau is only a plateau over the tested budgets

The matrix samples P in {2, 4, 8, 16, 32, 64}, and the classifier never searches beyond period 64. Equality between the P<=32 and P<=64 columns shows no additional coverage was detected in that tested range. It does not prove that no wider qualifying windows occur at periods above 64, or that C(delta,P) is constant for every P>=32.

Use “observed plateau over the tested period budgets” rather than an unbounded statement about all larger P.

### 4. The uncovered fraction is not a measured chaotic or dead-zone fraction

The complement of the estimated coverage includes parameters for which this scanner did not identify a qualifying candidate run. That complement may contain chaotic behavior, higher-period cycles, cycles missed by the finite warmup or return tolerance, numerical misclassification, and windows that fail the chosen width or period constraints.

“Uncovered by this procedure at this resolution and period budget” is justified. “Dead zone” or “chaotic” requires additional evidence.

### 5. The denominator is the full parameter interval, not the regular set

The reported fraction is normalized by the width of [3.5, 4.0]. The scan does not independently identify the regular subset or measure its Lebesgue measure. It therefore cannot compare its coverage to “the measure of the whole regular set” or conclude that a stated proportion of the regular set remains uncovered.

### 6. External dynamical-systems claims need independent sourcing

The introductory claims about density of periodic windows and positive-measure chaotic parameter sets are not established by this scan. Their precise theorem statements, parameter domains, definitions of “regular,” and assumptions should be sourced and reviewed separately before being used as premises in a proof.

## Re-reading the recorded matrix

The encounter supports these finite observations for its Windows/Python run:

- 303 contiguous candidate runs were reported by the scan.
- Within the six tested resolution values, reported candidate coverage is non-increasing as delta increases.
- Within the six tested period budgets, reported candidate coverage is non-decreasing as P increases.
- The P<=32 and P<=64 columns are equal for each tested delta.
- The estimated coverage fraction of the entire sampled parameter domain ranges from 14.48% to 20.10% in the reported matrix.

These are properties of the recorded output. They do not, by themselves, establish the exact geometry or measure of all stable periodic windows.

## Recommended next experiment

A second scanner should keep the original run unchanged and compare:

1. warmup lengths such as 600, 2,000, and 10,000;
2. repeated return checks over at least three cycles;
3. multiple initial conditions;
4. several grid sizes, for example 25k, 50k, and 100k;
5. interval-boundary refinement around each candidate run;
6. explicit stability margins and candidate confidence labels.

Report candidate windows, uncertain boundary bands, and the sampled uncovered region separately. A rigorous coverage claim would require interval arithmetic or another proof-producing method that certifies orbit existence, stability, and parameter bounds across a whole interval.

## Disposition

Keep the existing scan, data, and original analysis as historical artifacts. Reclassify the result as exploratory finite-grid evidence. Do not discard the measured matrix; make its finite scope and numerical assumptions explicit before using it as a basis for further theory.
