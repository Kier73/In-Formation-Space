# TPP-007 — Do observation-derived corrections survive longer time?

**Question:** A single historical correction improved a tide-model's next-day
water-level estimate in [TPP-006](../tactile-perception-prediction/README.md).
Does that same description remain useful across **six consecutive held-out
days**, or must it be reconstructed through new observations?

This experiment tests *time as part of the observation contract*. A
relationship can remain algebraically well-defined and yet lose predictive
usefulness as the external physical system continues evolving.

## Two physical-information paths

[NOAA CO-OPS](https://api.tidesandcurrents.noaa.gov/api/dev/) provides:

- six-minute `predictions`: tidal-model outputs (descriptive/computational);
- six-minute `water_level`: reported physical water-level measurements.

The experimental context fixes station `9414290`, datum `MLLW`,
units `metric`, UTC/GMT and seven **fully elapsed consecutive days**.
The default is the seven days ending yesterday, selected before any
provider reading is inspected.

Exactly **two batched public HTTPS requests** acquire the seven-day
prediction and observation histories. Both original bodies, request
contexts, UTC retrieval times, SHA-256 digests and entire data streams
are retained. The code verifies source endpoint, product, station,
datum, units, date span, finite decimal values, duplicate timestamps,
quality flags, and one-week bounds before computing any result.

This is historical retrospective evaluation: the NOAA predictions were
retrieved *after* the observed days, not archived as originally issued
before each day's measurement. Nothing here establishes prospective
forecast skill or independently authenticated sensor truth.

## Two non-leaking observer processes

Let the reported observation be `O_t` and model tide prediction be
`P_t`. Exact timestamp equality is required; no interpolation or
missing-value inference occurs.

On the **first** fully observed day, learn one exact-rational offset:

```
b0 = median(O_t - P_t, t on day 0)
```

For each subsequent day 1..6, evaluate the following predictions
*before using that day's observations to change either law*:

1. **Uncorrected baseline:** `P_t`.
2. **Frozen first-day correction:** `P_t + b0`, unchanged for six days.
3. **One-day-lag correction:** `P_t + b_(d-1)`, where `b_(d-1)` is
   the *previous completed day's* observed median residual.

The third process may update its information after a day has elapsed,
but cannot see that day's target values while it is being scored.
Compare exact-rational mean absolute error and record every day's
baseline, frozen-correction result and lagged-correction result separately.

A day requires at least 120 matched samples; unavailable or mismatched
data produce an explicit **undetermined** day. A missing day also
breaks the one-day-lag chain into the next day; it cannot silently reuse
an unobserved prior day's correction.

Aggregate metrics are computed only over declared evaluated samples.
The report states whether the entire seven-day window was complete
or partially undetermined. A single good day must not be presented
as a successful week.

## Evidence discipline

- Physical measurements have provider `p` (preliminary) and/or
  `v` (provider-verified) quality labels, which are retained per day.
  Neither label independently establishes instrument accuracy.
- Source bytes and SHA-256 commitments establish reproducible
  interpretation of received data, not physical source authentication.
- A tidal prediction is a model expression, not a measurement by an
  independent instrument.
- The frozen correction is a testable temporal description, not a
  causal claim about weather, pressure, sea level, or environmental
  perturbation.
- The one-day-lag correction is an **observer update policy**, not an
  intervention changing the ocean, nor an optimized weather forecast.
- Numerical error comparisons do not price provider CPU work,
  observation energy or real HTTP/TLS transport overhead.

The test is valuable if the frozen correction fails: it identifies
the operating time horizon beyond which the observed description
is not sufficient under this reference/context.

## Reproduce

From repository root, using only Python 3.11+ standard library:

```bash
python -m unittest discover -s experiments/tactile-perception-continuity -p 'test_*.py' -v
python experiments/tactile-perception-continuity/seven_day_residual.py --live > tpp007-live.json
python experiments/tactile-perception-continuity/seven_day_residual.py --replay tpp007-live.json
```

The optional `--start-day YYYYMMDD --end-day YYYYMMDD` specifies exactly
seven already-completed consecutive UTC days. Future and incomplete days
are refused. GitHub Actions runs a Linux/Windows Python 3.11/3.13
offline matrix plus one read-only public seven-day encounter.
Each run archives all original provider responses and its per-day
reconstruction report.

Fourteen offline tests include stable and drifting synthetic residual
families, explicit failures of a stale correction, no future-day
training leakage, incomplete-day refusal, missing prior-day renewal,
source-byte tampering and rehash counterexamples, source-reference,
station and timestamp checks, quality refusal, and independent replay.

## What to investigate next

If persistence varies across days, the next question is which measured
environmental distinction would make the observed response more
predictable. For example, additional weather observations could be
tested as explanatory covariates **without equating correlation with
causation**. That inquiry would require explicit source/datum alignment,
observation costs, held-out validation, and caution about selecting
explanations after inspecting outcomes.
