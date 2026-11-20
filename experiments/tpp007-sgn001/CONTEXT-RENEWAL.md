# TPP-007 × SGN-001: contextual renewal of a disconfirmed Ground

**Status:** executable, historical single-station research experiment, 2026-11-20.
**Question:** Can we detect that one observed relationship has shifted, prepare a replacement law without reading its target observations, and make the provisional/verified distinction portable across independent implementations?

This builds **inside the previously merged [TPP-007 × SGN-001](README.md) experiment**, instead of adding another executable engine. It also draws on existing IFS context-switching work ([RIV-006](../context-switching-evidence-accumulator/README.md)) and decision-value observation work ([RIV-008](../decision-value-context-acquisition/README.md)). Those are research analogies, **not** claims that the ocean has a diagnosed hidden Markov regime.

## Original evidence

- NOAA CO-OPS station `9414290`, datum `MLLW`, metric, UTC, six-minute data.
- Immutable archival TPP-007 workflow [44685425942](https://github.com/Kier73/In-Formation-Space/actions/runs/44685425942); artifact `tpp007-seven-day-provider-evidence`.
- Original SGN-001 validation and *failed* independent test: [run 44804847674](https://github.com/Kier73/In-Formation-Space/actions/runs/44804847674), artifact `tpp007-sgn001-qualification`.
- The Python producer and independent Node.js receiver refuse any different source-body SHA-256, archived source context, missing six-minute timestamp, quality omission, or replacement of the original SGN evidence report.
- A self-recomputed receipt checksum does **not** authenticate any source or authorize realization.

Both the physical observations and the NOAA model predictions were retrieved historically, after the observed dates. The 1,680 water-level observations are all provider-preliminary. This is not a prospective issue-time forecast or independently authenticated sensor experiment.

## Chronology and states

1. **Calibration, Nov 13–17:** compute each completed day's exact median of physical-minus-model residual; inspect only four adjacent median differences. Set the illustrative change threshold to `2 × median(absolute adjacent changes)`. All arithmetic is exact: original source decimals are converted to integral millimetres and half-millimetres are represented by twice-millimetre integers.
2. **Observation/possible renewal, Nov 18:** after this day ends, compare its daily median to Nov 17's median. Crossing the threshold makes Nov 18's completed-day median a **provisional** correction for Nov 19. There is no use of Nov 19 observations in this proposal.
3. **Independent historical scoring, Nov 19:** keep the proposed correction fixed and evaluate all 240 target samples. Retrospective corroboration requires both at least 15% less error than the uncorrected NOAA tide model and strictly lower error than the stale Nov 17 correction. These thresholds are part of the experiment's declared rule, not a statistically calibrated assurance bound.
4. **Authority:** the original spectral Ground remains `refused_after_independent_test`. The renewed correction is `provisional_not_admitted` before the target day and can become `historically_corrob_for_target_only` *after* that day. Neither state authorizes any later unobserved time. No new physical-execution capability is installed.

The algorithmic rule was chosen for this retrospective experiment after the dataset was available, so the triggering/corroboration results are an **exploratory case study**, not a preregistered or independently replicated forecasting evaluation.

## First observed result

| Measurement | Exact value |
| --- | ---: |
| Nov 13–17 adjacent day-median shifts (millimetres) | 97.5, 43.5, 11, 15 |
| Calibrated shift threshold | 0.0585 m |
| Nov 17 → Nov 18 measured median shift | 0.0645 m |
| Provisional correction for Nov 19 (Nov 18 median) | +0.4505 m |
| Nov 19 uncorrected NOAA MAE, 240 samples | 0.47559583 m |
| Nov 19 stale Nov 17-offset MAE | 0.09170417 m |
| Nov 19 provisional/renewed Nov 18-offset MAE | 0.05020833 m |

The provisional correction's Nov 19 MAE is ~45.25% lower than the stale-context comparator; it is also **exactly the existing TPP-007 one-day-lag method** for that day. The new result is in *independent source reconstruction and typed context/authority transitions*, not a newly discovered predictive algorithm. A better-scoring alternative on one day is not a certified physical law.

## Portable receiver

`context_renewal.py` produces a restricted canonical-JSON receipt (~2 KB) with:

- immutable source and predecessor SGN report identities,
- time and station references, exact calibration shifts, threshold and candidate,
- a target-independent provisional event,
- an exact target-score and historical-only disposition,
- an explicit refusal of unobserved future execution.

`verify_renewal.mjs` is an independent Node.js implementation, not an import of Python code or SGN. It reconstructs every relevant value from the original NOAA bytes and the pinned SGN output; it refuses recomputed digests of altered event fields, a changed prior report, and any attempt to set `executable_next_unobserved_day=true`.

This is separate-process, cross-language receipt verification. It does **not** involve E-CPU authenticated transport, quorum fences, VGI process execution, digital signatures, two independent instruments or verified physical cause. Existing [PRC-001](../portable-realization-capsule/README.md) provides complementary portable metadata concepts; a general reusable protocol must be designed and verified separately.

## Reproduce

Download the two exact evidence artifacts above; then, from repository root:

```bash
python -m unittest discover -s experiments/tpp007-sgn001 -p 'test_context_renewal.py' -v
python experiments/tpp007-sgn001/context_renewal.py \
  --archive ./tpp007-live.json \
  --spectral-report ./tpp007-sgn001-result.json \
  --output ./tpp007-context-renewal-receipt.json
node experiments/tpp007-sgn001/verify_renewal.mjs \
  ./tpp007-live.json ./tpp007-sgn001-result.json \
  ./tpp007-context-renewal-receipt.json

TPP007_ARCHIVE=./tpp007-live.json \
TPP007_SGN_REPORT=./tpp007-sgn001-result.json \
python -m unittest discover -s experiments/tpp007-sgn001 -p 'test_context_renewal.py' -v
```

The companion CI workflow retrieves both **unchanged** Actions artifacts, tests the Python and Node implementations and retains the portable receipt. Incomplete source evidence produces refusal, not an inferred observation.

## Next discriminating work

- Examine **multiple fully independent weeks and stations**, with the renewal policy frozen before inspecting each test interval. Report a distribution of false triggers, missed shifts, and forecast scores.
- Test evidence-cost-aware context measurement using RIV-008, with actual provider request/transport and observation costs rather than invented ones.
- Bind the typed receipt to E-CPU's *receiver-owned* admission and VGI's partial observation states only after E-CPU's mainline specification gates are reconciled.
