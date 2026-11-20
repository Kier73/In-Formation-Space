# TPP-005 — actual selected-observation encounter, 2026-11-20 UTC

**Observation claim:** A read-only observer selected measurement times from
NOAA's English-unit observations *before* acquiring metric responses at
those times. Four readings were used to infer a model, four separately
requested readings tested it. This establishes only a finite provider-data
translation result, not independent metrological validation or an
intervention into the natural system.

## Reference and independently replayable evidence

- Public provider: [NOAA CO-OPS Data API](https://api.tidesandcurrents.noaa.gov/api/dev/).
- Monitoring station: **9414290** (San Francisco); observed quantity:
  water level; datum **MLLW**; GMT/UTC date **2026-11-19**.
- Read-only hosted run:
  [44682924873](https://github.com/Kier73/In-Formation-Space/actions/runs/44682924873).
  Five successful jobs: Linux/Windows Python 3.11/3.13 offline tests,
  plus live public observation and manifest replay on Linux.
- Artifact: [tpp005-selective-real-observation](https://github.com/Kier73/In-Formation-Space/actions/runs/44682924873#artifacts),
  GitHub Actions artifact ID **14605057912**. The JSON retains the exact
  original NOAA response bodies in base64 (input and all eight target
  responses), SHA-256 digests, source URLs, UTC provider flags, requests,
  input-only policy digest, fit, and subsequent predictions.
  Actions artifacts expire; the report can be reacquired using a new run,
  but new provider responses can change.
- Original English-source response: **18,062 bytes**, retrieved
  `2026-11-20T05:43:46.568213+00:00`;
  SHA-256 `150d8ca4dd8f33ba8cf9576e11e1cb6619adf134bbf40f3b34a3579d3908dfda`.
- 240 six-minute input readings, all provider-*preliminary* (`q=p`).
- Input-only observation-selection plan SHA-256:
  `3ac7f4e3fdaf299c8c06ac1b2e8245671dca2576c2e1feaaaca4dcc599102034`.

## Requests actually made

One complete English-unit day was retrieved. Four target metric timestamps
were selected from its input range (the two extrema and two interior
quantiles). Four other timestamps were chosen by a fixed chronological
challenge rule, **before** their metric values were retrieved.

| Purpose | Selected UTC time |
| --- | --- |
| Train | 2026-11-19 07:42 |
| Train | 2026-11-19 23:30 |
| Train | 2026-11-19 01:06 |
| Train | 2026-11-19 15:30 |
| Withheld challenge | 2026-11-19 03:00 |
| Withheld challenge | 2026-11-19 09:00 |
| Withheld challenge | 2026-11-19 14:54 |
| Withheld challenge | 2026-11-19 20:54 |

The eight separately addressed NOAA metric responses each contained two
six-minute provider records; only the exact requested timestamp was admitted
for its designated purpose. Their eight raw response bodies totalled
**1,980 bytes**. No missing or inconsistent quality flag was encountered
in the selected readings. No device was actuated.

## Observed inference and uncertainty

The exact-rational TPP-004 affine estimator, applied only to the four
preselected training pairs and a declared `0.001 m` output-expression
tolerance, produced:

```
possible slope a in [1363/4479, 1367/4479]
selected slope a = 455/1493
selected intercept b = -493/2986000 m
interval width  = 4/4479 (approx. 0.0008931)
```

**All four withheld observations** agreed with the selected model
within the tolerance; zero violations. Maximum held-out absolute residual:
`591/2986000 m`, approximately **0.000198 m**.

The two most separated input readings were 2.573 ft and 7.052 ft,
a spread of 4.479 ft. They yield the exact two-point worst-case
slope-width upper bound `4/4479`, compared with `4/4363`
for the chronological four-point comparator's two extreme inputs.
That is approximately a **2.59% lower bound value** for the
chosen two-point design. This is a mathematical bound conditioned on the
declared tolerance, **not** proof of a lower final statistical error or
better network performance.

## Information logistics: the important tradeoff

This experiment made **nine real HTTPS request attempts**:
one source-day request and eight targeted metric-window requests.

The sum of original retrieved HTTP response-body bytes was **20,042**
(18,062 source + 1,980 targets), excluding HTTP headers, TLS messages,
routing, TCP/IP overhead, and provider processing.

As a historical *non-simultaneous* comparison, TPP-004 requested both
full-day expressions for the same UTC day and retained
18,062 + 18,047 = **36,109** raw response-body bytes across **two**
requests. TPP-005's response-body total was about **44.5% lower**,
but it used **4.5 times as many requests**. These distinct executions
do not establish lower overall network cost, server-side cost, latency,
or energy consumption, and are not a controlled randomized comparison.

## Distinctions and further questions

1. Both representations were obtained from **one NOAA service** and
   presumably the same underlying physical instrumentation. They are
   not independent measurements or source-authenticated calibration.
2. All observed source readings were preliminary. A provider may revise
   them; the original response bytes are what this encounter preserves.
3. Finite model agreement is **not** a universal claim about sensor
   transformation, hidden dynamics or physical causality.
4. Selecting a small subset of responses is not the same as reducing the
   number of communication actions; the physical and informational
   resources must be accounted for separately.
5. This fixed selection policy is not asserted optimal for arbitrary
   sources or observer aims. Future work could explicitly measure
   end-to-end request cost, choose alternative provider interfaces, or
   introduce independent calibrated sensing and authorized intervention.

Reproduction: [TPP-005 code and instructions](README.md), with
`--live` for a fresh read-only encounter and `--replay` for independent
source-byte and manifest reconstruction.
