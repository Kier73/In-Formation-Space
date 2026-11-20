# TPP-006 — Prediction, observation, and the persistence of a correction

**Question:** When a model gives a prediction of a physical state, does a
simple correction inferred from earlier observations remain useful when the
physical system continues to evolve?

This experiment follows
[TPP-003 external observation](../tactile-perception-observations/README.md),
[TPP-004 inferred expression](../tactile-perception-calibration/README.md)
and [TPP-005 selective acquisition](../tactile-perception-acquisition/README.md).
The direction changes here: we no longer compare two equivalent numerical
expressions of the **same** measured quantity. We compare a *model prediction*
with the observation of the quantity it attempts to describe.

## External information paths

The read-only observer queries the
[NOAA CO-OPS Data API](https://api.tidesandcurrents.noaa.gov/api/dev/)
for two distinct, completed UTC days at station **9414290**:

- `product=predictions`, `interval=6`, units metric, datum `MLLW`:
  a **tide prediction** supplied by a model of tidal dynamics.
- `product=water_level`, units metric, datum `MLLW`:
  a **provider-reported water-level observation**, with preliminary or
  provider-verified flags, its sampled standard deviation and flags.

The NOAA tide prediction is **not an as-of forecast snapshot** stored
before the test day in this experiment: both historical predictions and
measurements are retrieved after the respective days have elapsed.
The prediction can capture astronomical tide dynamics while real observed
water level includes other influences. The experiment does not infer
those influences' causes, claim a weather forecast, or independently
validate NOAA's instruments.

All comparisons require **exactly matching** UTC timestamps, station,
datum, units and selected product. No interpolation, minute shifting,
default-value imputation or acceptance of an unmatched observation occurs.
Both unmodified original HTTP response bodies and content hashes are kept.

## Testable relationship

Let `P_t` be the NOAA model-predicted tide at timestamp `t`, and
`O_t` the provider's reported water level.

We define residual `r_t = O_t - P_t` and fit a one-parameter
observer-relative correction from **training-day observations only**:

```
b = median({O_t - P_t : t in training day})
predicted corrected height at t = P_t + b
```

The correction `b` is frozen before the next-day evaluation. With
at least 120 matched samples on *each* day, we compare the exact-rational
mean absolute errors:

```
MAE_baseline  = average(abs(O_t - P_t))
MAE_corrected = average(abs(O_t - (P_t + b)))
```

We record whether the frozen correction **improved**, **worsened**, or
**left unchanged** the later day's error. A correction inferred in one
context might fail to transfer when the material system or environment
changes. Such a failure is not discarded or automatically repaired.

This is one deliberately simple candidate relation, not an optimized
forecast system or universal physical invariant. No parameters are fitted
from the later day. Exact-rational calculations avoid floating-point
roundoff in model comparison, but input observations remain finite-precision
provider values with measurement uncertainty.

## Evidence and verification

- Four read-only HTTPS attempts: historical observation and tide prediction
  for the training day, and the same two products for a later held-out day.
- Each received body is archived in base64 with its request URL, UTC day,
  response-byte count, fetch time, and SHA-256 digest.
- The existing TPP-003 independent physical-observation replay verifies
  parsed water-level observations against original provider bytes.
- Predictions have a separate strict parser: six-minute timestamps, finite
  decimal values and duplicate rejection; the URL must declare the proper
  NOAA product, unit and datum.
- A replay function reconstructs the entire two-day inference and compares
  it to the retained outcome.
- Missing observations, invalid sources, mismatched reference frames and
  fewer than 120 matched timestamps result in explicit refusal or
  undetermined statuses, never an invented zero error.
- All results remain **one-provider claims**: content hashes and replay do
  not independently authenticate the real physical source or prove
  that observations are correct.

## Reproduction

Using Python 3.11 or newer with only standard-library modules, from
the repository root:

```bash
python -m unittest discover -s experiments/tactile-perception-prediction -p 'test_*.py' -v
python experiments/tactile-perception-prediction/residual_observer.py --live > tpp006-live.json
python experiments/tactile-perception-prediction/residual_observer.py --replay tpp006-live.json
```

The default live encounter requests two *fully elapsed* UTC days (two days
ago for training, yesterday for held-out). Two explicit historical
`--train-day YYYYMMDD --test-day YYYYMMDD` parameters are also
supported; reversed, same-day, future and incomplete dates are refused.

A GitHub Actions workflow checks offline fixtures across Linux and Windows
on Python 3.11/3.13, then independently attempts the four public HTTPS
requests and archives the complete source/assessment report. Successful
CI indicates *the program and evidence contracts ran*, not that its physical
correction succeeded. The outcome classification must be read separately.

The offline test suite deliberately includes both a scenario where the
correction improves and one where it worsens. It also checks future-data
separation, unavailable models, source-byte corruption, datum or station
mismatch, duplicate predictions, quality flags, and replay tampering.

## Further research

1. Revisit a **true as-issued forward prediction**, retaining its original
   issue-time and source identity before later measurements arrive.
2. Compare independently calibrated physical sensors rather than two
   data products of one provider.
3. Investigate residual dependencies on observed environmental context and
   the cost/benefit of requesting that context, without attributing causes
   from temporal correlation alone.
4. Introduce active physical interventions only with explicit authority,
   independently measured energy budgets and source-calibrated evidence.

The present experiment explores **the stability of a description against
continued physical observation**, not a claim that matter itself is
equivalent to its informational prediction.
