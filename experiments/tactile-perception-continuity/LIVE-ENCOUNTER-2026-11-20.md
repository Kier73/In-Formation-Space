# TPP-007 — seven-day external-observation encounter, 2026-11-20 UTC

**Evidence class:** historical NOAA physical water-level observations and
separately computed tidal predictions, not independently calibrated sources
or an as-issued prospective forecast.

## Source capture and independent checking

- Public provider: NOAA CO-OPS, station **9414290**, datum **MLLW**,
  UTC/GMT, metric units, six-minute data.
- Fixed observation interval: **2026-11-13 through 2026-11-19**, both
  endpoints fully elapsed before retrieval.
- [GitHub Actions run 44685425942](https://github.com/Kier73/In-Formation-Space/actions/runs/44685425942),
  *all five jobs passed*: Linux/Windows Python 3.11 and 3.13 test matrix,
  real read-only seven-day provider encounter, producer replay, and
  **independent Decimal reconstruction** of original response bytes,
  daily corrections, all reported MAEs and provider-quality counts.
- Retained JSON: [tpp007-seven-day-provider-evidence](https://github.com/Kier73/In-Formation-Space/actions/runs/44685425942#artifacts),
  GitHub Actions artifact ID **14606875004**. This includes both complete
  source response bodies (base64), URLs, UTC retrieval times, digests,
  provider flags, the chosen correction and all reported comparisons.
  Actions artifacts eventually expire.
- Physical observation response: **125,718 bytes**, SHA-256
  `8a31edbda35209261cbba2cc1fa8d7e3955449fda2d928ac31287028bc74f79d`,
  retrieved `2026-11-20T06:06:18.028149+00:00`.
- Model prediction response: **63,696 bytes**, SHA-256
  `7bb2a2a473aac47a268991816aa7e23f06a12daaa7dbf7922bb60d514ad413f8`,
  retrieved `2026-11-20T06:06:18.402844+00:00`.
- Two HTTP request attempts, **189,414 received body bytes** in total
  (not TLS or complete on-wire traffic). Both source streams and all
  1,680 day/timestamp pairs were present.
- **All 1,680 observations were provider-preliminary (`q=p`)**. This is
  not independent physical measurement verification.

## Precommitted two-process comparison

Day one, **Nov 13**, was used solely for training a median residual:

```
frozen day-one correction = 553/1000 m = +0.553 m
```

Both comparisons for each later day were scored before that day's
measurement-derived correction could be used to change the prediction:

- **Frozen:** keep +0.553 m for all six held-out days.
- **One-day-lag:** use only the *previous completed day's* measured median
  residual for each day's prediction.

| Held-out day | Matched | Tide-model MAE (m) | Frozen MAE (m) | One-day-lag MAE (m) |
| --- | ---: | ---: | ---: | ---: |
| Nov 14 | 240 | 0.46899 | 0.08955 | 0.08955 |
| Nov 15 | 240 | 0.41112 | 0.14188 | 0.04442 |
| Nov 16 | 240 | 0.40185 | 0.15115 | 0.02135 |
| Nov 17 | 240 | 0.38248 | 0.17053 | 0.02272 |
| Nov 18 | 240 | 0.47363 | 0.10727 | 0.09027 |
| Nov 19 | 240 | 0.47560 | 0.07740 | 0.05021 |

All six days: complete matched evidence, **no missing-day imputation**.

### Weighted aggregate over 1,440 held-out observations

| Method | Exact MAE (m) | Approximate MAE (m) | Change relative to original model |
| --- | --- | ---: | ---: |
| Uncorrected tide prediction | `7841/18000` | 0.43561 | reference |
| Fixed Nov 13 correction | `44267/360000` | 0.12296 | **71.77% lower** |
| Strict previous-day correction | `4247/80000` | 0.05309 | **87.81% lower** |

**Every daily frozen and one-day-lag comparison improved on the uncorrected
NOAA prediction in this seven-day historical encounter.** The day-one
offset was not numerically constant over the week: next-day optimal
median residuals changed, so the strictly causal rolling correction
generally produced a smaller error than the static one.

## What remains unknown

The numerical stability of an additive correction over seven days has
been **observed for this single station and week**, with finite error.
The separate physical influences behind the residual are **not
identified**. Candidate mechanisms include atmospheric conditions,
tide-model structure, changing external context, reference/calibration
effects or combinations. The experiment did not measure those causes,
use a second instrument, archive original issue-time predictions, or
establish forecast skill beyond these historical observations.

The primary producer and [independent weekly checker](independent_weekly_check.py)
can separately reconstruct the retained calculations, but both operate
on data from the **same** provider. Bytes and SHA-256 are not sensor
signatures; NOAA preliminary status must not be upgraded.

## Reproduce

From repository root:

```bash
python -m unittest discover -s experiments/tactile-perception-continuity -p 'test_*.py' -v
python experiments/tactile-perception-continuity/seven_day_residual.py --live > tpp007-live.json
python experiments/tactile-perception-continuity/seven_day_residual.py --replay tpp007-live.json
python experiments/tactile-perception-continuity/independent_weekly_check.py tpp007-live.json
```

New requests can return revisions or a different seven-day window.
For the original source bytes, use the retained artifact associated with
the specified workflow run. Details and scope:
[TPP-007 design](README.md).
