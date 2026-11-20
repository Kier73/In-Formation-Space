# TPP-003 — read-only NOAA observation encounter (2026-11-20 UTC)

**Evidence type:** A real hosted HTTPS retrieval of *public provider-reported
physical water-level observations*, with two independently fetched unit
expressions. This is not an independent physical measurement or sensor
calibration.

## Observation and environment

- Source: [NOAA CO-OPS Data API](https://api.tidesandcurrents.noaa.gov/api/dev/),
  station `9414290` (San Francisco), product `water_level`, datum
  `MLLW`, timestamp reference GMT/UTC, `date=recent`.
- Host: GitHub Actions `ubuntu-latest`, Python 3.13.
- Hosted run: [44679470282](https://github.com/Kier73/In-Formation-Space/actions/runs/44679470282)
  on TPP-003 branch; real-public-read job **passed**.
- Exact retained report: Actions artifact
  [tpp003-noaa-read-only-observation](https://github.com/Kier73/In-Formation-Space/actions/runs/44679470282#artifacts)
  (artifact ID `14603871956`, uploaded 2026-11-20 UTC).
  Report contains base64 original provider response bytes and their parsed
  interpretations. Artifacts may expire; their digests below are durable.
- Metric retrieved at `2026-11-20T05:12:35.965813+00:00`.
  Response: **53,919 bytes**, SHA-256
  `8fd61923dff3b5c642728b2d5a2af7e8a3a6927cfecb8f9ea352ef0f6e66c5b8`.
- English retrieved at `2026-11-20T05:12:36.381918+00:00`.
  Response: **53,958 bytes**, SHA-256
  `1e464249d12cd09891cab62cbc161031f5e065c9653669f2f034809eb7d6990b`.
- The matched records cover
  `2026-11-17T05:12:00+00:00` through
  `2026-11-20T05:06:00+00:00`.

## Measured representation comparison

- Both requests returned data; **720** shared timestamps with nonmissing
  values.
- **720/720** pairs agreed after `ft * 0.3048` within the
  contract's **0.001 m** representation tolerance.
- Maximum observed absolute difference was **0.0005472 m**.
- No timestamp exceeded the specified tolerance; no paired provider-quality
  statuses disagreed.
- **All 720 values were labelled preliminary (`q=p`)** by NOAA, not
  `q=v` (provider-verified). The raw `f` flags and standard-deviation
  field `s` are retained, not converted to an accuracy guarantee.
- The separate `independent_replay.py` checker passed against the complete
  archived source bytes, including raw SHA-256, interpreted observations,
  context and resulting comparison. All five jobs in this run (four
  offline-matrix jobs and the live encounter) passed.

## What this establishes, and what it does not

The provider returned a set of water-level observations from a real
environmental monitoring service, and *two distinct numerical expressions*
(meters and feet) were consistent under a declared unit transformation,
timestamp, station and datum. The original payloads are sufficient for a
separate implementation to replay this claim.

This does **not** establish independent sensing: both representations
originate at the **same** NOAA service and likely the same underlying
instrument data. Preliminary data may be revised. Distinct response SHA-256
digests alone do not authenticate the physical source, and replaying bytes
cannot prove sensor calibration, physical correctness, causality, or a
universally invariant expression. The two requests were separated in time
and were not simultaneous atomic reads.

For re-execution:

```bash
python -m unittest discover -s experiments/tactile-perception-observations -p 'test_*.py' -v
python experiments/tactile-perception-observations/noaa_bridge.py --live --date recent > tpp003-live-report.json
python experiments/tactile-perception-observations/independent_replay.py tpp003-live-report.json
```

Related: [experiment documentation](README.md), [adapter](noaa_bridge.py),
[separate replay verifier](independent_replay.py).
