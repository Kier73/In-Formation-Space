# RRE-001 — Rainfall rhythm ecology

2026-11-25. A deliberately independent exploration of ecology, not an extension of the computational research programme.

## Question and prior work

Can equal seasonal precipitation produce different plant composition solely through temporal repackaging? This is an established ecological research question, not a claim of novel discovery. For empirical motivation see [Deconstructing precipitation variability](https://doi.org/10.1111/1365-2745.13724), [Intra-annual rainfall regime shifts competitive interactions](https://doi.org/10.1890/12-0651.1), and [Disentangling the Effects of Precipitation Amount and Frequency on the Performance of 14 Grassland Species](https://doi.org/10.1371/journal.pone.0162310). These papers are context, not calibration data for this model.

## Experiment

A 240-day season gets exactly 360 mm of rain, delivered at periods 1, 3, 6, 12, 24, 40 days; the event is 1.5 times the period in mm. All integer starting phases are enumerated. Soil begins dry, populations begin with equal relative shares. Two water stores: upper capacity C and lower capacity 45 mm. Rain fills the upper store, then the lower, with excess lost as runoff; evaporation subtracts up to E from upper water and drainage removes fraction D from lower water each day. Then plant uptake competes for available water. Shallow uptake demand is 1.6 f S/(S+2), deep upper demand is 0.4 (1-f) S/(S+2), deep lower demand is 1.2 (1-f) L/(L+3), where S,L denote remaining upper and lower water and f is the shallow relative share. Upper demand is capped proportionally if necessary. Growth factors are exp(0.1 times realized uptake per share), with deep strategy incurring an additional 0.015 daily log-growth cost. Relative shares are normalized each day; this represents fixed total biomass, not absolute vegetation productivity. Parameters are illustrative choices, not estimated measurements.

The baseline is C=12, E=1.2, D=0.05. Full factorial sweep: C=6,12,24; E=0.6,1.2,1.8; D=0.015,0.05,0.12. Each soil cell averages every phase of every period (86 seasonal runs; 2,322 across the factorial, plus 86 duplicate baseline and 75 initial-share sensitivity runs). The code checks equal rainfall, nonnegative water, valid shares and daily/seasonal water balance.

## Observations from the simulated system

| Period (days) | Rain per event (mm) | Mean deep share (%) | Total plant uptake (mm) |
|---:|---:|---:|---:|
| 1 | 1.5 | 0.008867 | 71.84 |
| 3 | 4.5 | 0.000214 | 120.85 |
| 6 | 9 | 0.000024 | 149.87 |
| 12 | 18 | 58.53 | 152.84 |
| 24 | 36 | 99.76 | 162.85 |
| 40 | 60 | 99.89 | 139.68 |

Across all 27 soil settings, 24-day rain increases deep share relative to daily rain (range +1.52 to nearly +100 percentage points). Among sampled periods, deep share peaks at 24 days for 10 settings and 40 days for 17 settings. Maximum absolute water balance residual across the sweep is 1.319e-12 mm. For initial shallow shares 10%, 50%, 90%, the 24-day final deep shares are 99.93%, 99.76%, 99.53% respectively.

The companion controls independently re-express the core recurrence in shorter code (same author/session, not independent external replication), check agreement for baseline period 24, then deliberately change the mechanism. With 100 mm upper storage, 24-day rainfall yields deep share about 0.000003% instead of 99.76%, lower than the daily treatment (0.008867%). With 95% daily deep drainage, the 24-day share is just 0.0615%. With identical rooting/growth strategies, every tested schedule preserves 50:50 exactly within tolerance. More intermittent rain is not universally favorable to deeper-rooted plants even in the toy system.

The baseline 40-day schedule yields slightly more deep dominance than 24 days but lower total plant uptake, higher drainage and nonzero runoff; relative dominance and ecosystem water capture are not interchangeable. Total uptake is not a measured proxy for biomass in this fixed-share model.

## Reproduction

```sh
node experiment.mjs > reproduced.json
node controls.mjs > reproduced-controls.json
diff -u results.json reproduced.json
diff -u controls.json reproduced-controls.json
```

The JavaScript functions were executed directly in a hosted JS isolate on 2026-11-25; the checked-in files are the serialized functions with JSON output statements. Node CLI commands and repository-wide CI were not run in that environment. Minor floating-point differences across engines are possible; compare with tolerance if necessary. Raw outputs: [results.json](results.json), [controls.json](controls.json).

## Open questions and limitations

This is not a calibrated vegetation, soil physics or climate model. Instant overflow replaces realistic infiltration; no hydraulic redistribution, explicit rooting profiles, phenology, nutrient limitation, temperature, stochastic weather, absolute biomass or recruitment. The growth and maintenance choices favor shallow roots without deep water, so a reversal is conditional on the assumed mechanisms. The sweep is a sensitivity grid, not a population of sampled real soils and not a statistical confidence interval.

A next experiment should compare equal-frequency equal-total clustered and evenly spaced storm schedules (separating timing from size), add explicit infiltration rates and root distributions, and test against open field time series without tuning and testing on the same plots. A separate interesting direction is multi-season coexistence and drought carryover rather than single-season dominance. Neither is required to continue the wider repository's other work.
