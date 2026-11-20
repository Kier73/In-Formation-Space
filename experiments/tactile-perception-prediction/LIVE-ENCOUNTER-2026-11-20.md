# TPP-006 — archived historical NOAA prediction/observation encounter

**Date collected:** 2026-11-20 UTC, GitHub-hosted read-only observation.
**Outcome:** A correction fitted on one historical day improved mean absolute
error on one later historical day. This is **not a prospective as-issued
forecast** or an independently authenticated physical measurement.

## Evidence and source contexts

- [GitHub Actions run 44683966378](https://github.com/Kier73/In-Formation-Space/actions/runs/44683966378):
  all **5 jobs passed** (Linux/Windows Python 3.11/3.13 offline tests and
  historical-public-encounter with complete byte-based replay).
- Artifact [tpp006-historical-prediction-observation](https://github.com/Kier73/In-Formation-Space/actions/runs/44683966378#artifacts),
  ID **14604873869**; contains raw source bytes (base64), input URLs,
  SHA-256 hashes, temporal contexts, provider quality, and reconstructed
  result. Artifacts eventually expire.
- Station 9414290 (San Francisco), datum MLLW, UTC/GMT, units meters.
- Training day: **2026-11-18**; held-out day: **2026-11-19**.
- Four bounded public API requests: two historical `water_level`
  observation requests and two `predictions` requests at six-minute
  intervals. The prediction data is supplied by a tidal model and is **not
  a separately instrumented physical sensor**.
- All 240 paired water-level observations on each day carried provider
  `q=p` (preliminary) quality. The observations and tidal predictions
  were separately fetched from the **same** provider.

| UTC day | Product | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Nov 18 | water_level | 18,039 | `12981e93bcb735f2c2ed3f47f2edbd13695ca2eeb1df8ced22a78d846ab078e0` |
| Nov 18 | predictions | 9,120 | `d20bd750f53c73443e81fdf553b42f2034eab9d63571d1480f4212636477c076` |
| Nov 19 | water_level | 18,047 | `679b4ba364f0d4e9e89ce78bc2a7cfdbe2e2b706d98a3b9b1c2febd06fb3c2c5` |
| Nov 19 | predictions | 9,113 | `81c2f40714c23ee4213aaa54c5b82b3e023587327b71074c1dc5012a113e1a8b` |

Original body total: **54,319 bytes** (does not include request headers,
TLS, network transport, or provider costs).

## Exact rational result

Fitting a **single constant median offset** from the Nov 18
observation-minus-model residuals produced:

```
training median residual correction = 901/2000 m = +0.4505 m
```

The correction was frozen before Nov 19 evaluation. No Nov 19
measurement was used for model identification.

| Assessment | Model-only MAE | Corrected MAE |
| --- | ---: | ---: |
| Training Nov 18 (240 matched) | `14209/30000` m (~0.47363 m) | `847/12000` m (~0.07058 m) |
| Held-out Nov 19 (240 matched) | `114143/240000` m (~0.47560 m) | `241/4800` m (~0.05021 m) |

Held-out MAE reduction: `34031/80000` m, approximately **89.44%** of
the original held-out model error. The maximum held-out absolute error
changed from `11/20` m to `199/2000` m.

**Important:** this two-day coincidence supports neither stationarity
over weeks nor a particular physical explanation. The discrepancy
could include provider-reference conventions, environmental effects,
model inadequacy or other unobserved context. A fixed residual fitted
to historical data is not an as-issued meteorological forecast.

## What is independently replayable

A separate parser reconstructs NOAA observation records from original
body bytes and validates timestamps, status, flags and source reference.
Prediction records have their own strict product, URL and timestamp
checks. The experiment computes the frozen correction and exact MAEs
from the reconstructed samples and refuses a modified result.

This verifies consistency between **retained bytes and derived claims**.
It does not establish cryptographic identity of the physical instrument,
independent data custody, physical correctness or the causal source of
the approximately 0.45-m persistent discrepancy.

## Next discriminating experiment

Extend the fixed correction over a substantially longer **predeclared
consecutive sequence of days**, without changing the correction, and
compare it with a strictly causal one-day-lag correction that can adapt
after each day is fully observed. Use the same NOAA station, datum,
UTC reference and provider quality gates. Record failures per day,
not just an average. If the relationship decays, that is important
evidence of missing physical context.

Reproduction: [code and method](README.md);
`python experiments/tactile-perception-prediction/residual_observer.py --live`
followed by `--replay` on the resulting JSON.
