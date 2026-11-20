# TPP-004 — retained fixed-day source encounter, 2026-11-20 UTC

**Reproducible public observation, not independent instrument verification.**

## Observation window and source

- Fixed fully elapsed UTC day: **2026-11-19** (00:00–23:54 at 6-minute reporting intervals).
- NOAA CO-OPS public water level, station **9414290**, `MLLW`,
  two numerical expressions `metric` and `english`.
- 240 paired timestamps; all reported preliminary by the provider
  (`q=p`), not provider-verified.
- GitHub Actions live hosted run [44680678888](https://github.com/Kier73/In-Formation-Space/actions/runs/44680678888)
  (`live-public-expression`: passed).
- Raw source + derived results in Actions artifact
  [tpp004-observed-blind-calibration](https://github.com/Kier73/In-Formation-Space/actions/runs/44680678888#artifacts),
  artifact ID **14604465504**. The artifact contains complete source bytes
  (base64 in JSON) and a replayable inferred model. Artifacts may expire.
- First metric request: retrieved
  `2026-11-20T05:23:18.058360+00:00`, 18,047 bytes,
  raw SHA-256 `679b4ba364f0d4e9e89ce78bc2a7cfdbe2e2b706d98a3b9b1c2febd06fb3c2c5`.
- Second English request: retrieved
  `2026-11-20T05:23:18.312723+00:00`, 18,062 bytes,
  raw SHA-256 `150d8ca4dd8f33ba8cf9576e11e1cb6619adf134bbf40f3b34a3579d3908dfda`.
- Both decoded base64 bodies were checked against their recorded SHA-256.

## Predeclared sparse training and withheld observations

The algorithm replayed the source bytes with an implementation that does **not**
use a known conversion factor. It sampled every 32nd matched timestamp:
**8 training pairs**. The remaining **232 pairs** were held out.

From those eight observed values and a declared `1/1000` output-unit
representation tolerance, exact rational feasible-interval elimination found:

```
positive affine slope a in [1183/3888, 584/1913]
selected slope              4533671/14875488
selected offset            -950993/3718872000
```

All 232 withheld pairs agreed with the selected affine expression within
`1/1000 m`; **0 withheld violations**. Maximum absolute held-out residual:
`1532189/7437744000 m` (about **0.000206 m**).

Only *after* the fit and withheld validation, the known foot-to-meter constant
`381/1250 = 0.3048` was checked and found to lie inside the inferred feasible
interval. This is **not** an inference of the exact conversion constant.

The existing source adapter's known-unit comparison independently returned
240/240 pairs consistent within 0.001 m (maximum discrepancy 0.0005472 m);
it was not used in the TPP-004 fit.

## Important negative encounter

A separate live run using NOAA's moving `date=recent` query returned
**one paired timestamp**, even though an earlier TPP-003 run with nominally
the same query yielded hundreds. That run was correctly classified as
`undetermined` (insufficient training observations), not as a successful
identification. The fixed completed UTC-day query was introduced to
eliminate ambiguity in the requested observation interval. No unsupported
explanation for the observed change is asserted.

## Meaning of the evidence

- Two provider expressions, not two independent instruments.
- Preliminary provider data, not a metrological accuracy certificate.
- Finite held-out agreement under an **assumed affine model and 0.001 m
  representation tolerance**, not proof of a universal physical law.
- SHA-256 and replay validate retained bytes and derived interpretation, not
  physical instrument identity or external causality.
- All candidate slopes in the feasible interval remain viable under the
  chosen training observations; a central slope is used only for prediction.
- Different datum, altered quality status or missing original bytes are
  not silently admitted as equivalent observations.

Reproduce through [the experiment and source code](README.md) and the hosted
workflow. See also [TPP-003's independent NOAA source-byte replay](../tactile-perception-observations/independent_replay.py).
