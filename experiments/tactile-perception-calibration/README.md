# TPP-004 — Inferring an expression ratio from limited observations

**Question:** After observing two differently encoded measurements of the same
phenomenon, can a process discover a transferable numerical relation **without
being told the conversion**, then subject that relation to withheld observations?

This continues [TPP-003](../tactile-perception-observations/README.md).
The existing [observation-equivalence bridge](../../bridges/observation-equivalence/README.md)
already warns that finite output agreement is not universal transition
equivalence. Here the observation question is narrower: can we *identify an
unknown affine relation with finite precision*, then test it outside training?

## Mechanism

The program receives the raw provider-reported values at matching timestamps,
expressed as `x` in one unit and `y` in another. It does not read a
conversion table, sensor gain, or `0.3048` when fitting. The known
conversion constant is admitted only for a **post-fit audit**.

For a proposed affine map `y=a*x+b`, bounded by a stated measurement
**representation** error `epsilon`, the finite observation constraints are:

```
y_i - epsilon <= a * x_i + b <= y_i + epsilon
```

For all pairs with `x_j > x_i`, elimination of the unknown intercept `b`
gives exact rational inequalities:

```
(y_j - y_i - 2*epsilon) / (x_j - x_i) <= a
a <= (y_j - y_i + 2*epsilon) / (x_j - x_i)
```

Intersect these intervals with `a>=0`. The resulting interval describes
**every positive slope feasible under the declared tolerance for the supplied
training observations**. Pairwise interval overlap is sufficient because
all intercept feasibility sets are intervals on the real line. A central
slope and a feasible intercept are selected only for held-out prediction.
The full feasible interval is retained; the experiment never asserts a
single physically exact scale on the basis of finite-precision data.

An observationally consistent result is an *inference* within a model
class—not the unique physical law. A nonlinear, time-varying or
differently-datum system can contradict the affine hypothesis. The fit
reports explicit contradictory, underdetermined, or insufficient-variation
states rather than manufacturing a coefficient.

## Real observation source and withholding

[NOAA CO-OPS](https://api.tidesandcurrents.noaa.gov/api/dev/)
supplies water-level readings for station 9414290. Both representations
come from **the same provider**; their time, station, datum, quality
labels and original source bytes are preserved by [TPP-003](../tactile-perception-observations/README.md).

The fit replays and validates both original provider payloads with
TPP-003's independent source-byte checker. Importantly, it does *not*
consult TPP-003's precomputed cross-unit comparison, which uses the known
conversion and would leak the intended answer. Live acquisition requests
a **fixed, fully elapsed UTC day** (`begin_date=end_date`, yesterday at
execution time) for both unit expressions. During development, the moving
`date=recent` query returned 720 observations on one run but only **one**
on a later real GitHub runner. We preserve that insufficiency as an
observation, rather than assuming why the remote service behaved differently.
The next acquisition requests a fixed date to test whether that stabilizes
the observation window.

Training is selected by a predefined timestamp schedule: **every 100th
matched sample**, with all other timestamps withheld. This selection uses
no measured values. A 240-reading fixed day therefore supplies three
training observations, which is deliberately **insufficient** under the
four-reading minimum unless the sampling schedule is adjusted in advance.

The held-out predictions use only the inferred slope/intercept. The
predictive score is the exact rational maximum absolute residual and
the number of deviations beyond **1/1000 of the output unit**, including
the first counterexample timestamp. That tolerance is a *declared
representation criterion*, not a complete sensor uncertainty bound.
NOAA's provider preliminary/verified quality flags are not promoted to
independent physical confirmation.

## Reproduction

This experiment uses only Python 3.11+ standard library. From the repo root:

```bash
python -m unittest discover -s experiments/tactile-perception-calibration -p "test_*.py" -v
python experiments/tactile-perception-calibration/calibration.py --live > tpp004-live-report.json
python experiments/tactile-perception-calibration/calibration.py --replay tpp004-live-report.json
```

The live report contains both original NOAA response bodies in base64,
SHA-256 digests, interpreted values and the learned relation. The replay
command rechecks the source bytes, reruns identification and exactly compares
the retained inference. Four cross-platform offline CI jobs and a separate
bounded real HTTPS job retain results as a GitHub Actions artifact.

Offline counterexamples include a nonlinear withheld response, model-class
contradictions, missing or altered source bytes, misaligned quality status,
non-identifiable scale, and a counterexample deliberately inserted *after*
the selected training timestamps.

## Distinctions to retain

- A passing withheld test establishes agreement over that finite set, **not**
  independent accuracy of NOAA's instrument or a universal conversion proof.
- Distinct unit expressions of a single provider are not independent physical
  measurements.
- A nonzero slope interval is **epistemic uncertainty under the declared
  tolerance**, not an inferred probability distribution.
- A fitted intercept can depend on the chosen reference datum; matched
  coordinate reference is required before interpreting a scale.
- A physically exact relation might exist but remain unidentified from
  insufficient observations. Those cases are reported as undetermined.

**Next experiment:** select observations by expected reduction of the feasible
parameter region under observation cost, rather than the fixed 100th-sample
schedule, while refusing claims when the observer lacks calibration or
source authority.
