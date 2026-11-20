# TPP-007 × SGN-001: physical spectral admission

This experiment feeds [TPP-007](../tactile-perception-continuity/README.md)
original archived NOAA source bytes directly into the **existing**
[SGN-001](../spectral-ground-navigation/README.md)
`fit_spectral` and `test_report` code. It does not duplicate the spectral
navigator or introduce a new runtime operator.

## Fixed chronology

- **Train:** November 13–15, 2026 UTC, 720 six-minute samples.
- **Validation:** November 16–17 UTC, 480 samples. All clock, gauge, circle and
  rank selection happens here using only earlier training data.
- **Final untouched test:** November 18–19 UTC, 480 samples. SGN-001's
  `test_report` uses at most 120 target coordinates of this interval and
  performs no refitting.

There are two scalar lanes: (1) physical-minus-model water-level residual
and (2) the observed physical water level itself.

## Observation authority

The original TPP-007 workflow
[44685425942](https://github.com/Kier73/In-Formation-Space/actions/runs/44685425942)
retains `tpp007-live.json` in artifact
`tpp007-seven-day-provider-evidence` (ID `14606875004`).
The driver refuses a different SHA-256 even if it carries a newly recomputed
checksum, refuses missing or extra timestamps, and refuses missing provenance.

These provider values are preliminary; neither the checksum nor a GitHub artifact
independently authenticates a physical instrument. The NOAA tidal predictions
were fetched after the observed dates. This is a retrospective scientific
comparison and **not** a measured prospective forecast.

The local independent equation reproduction found that both residual and
water-level fits qualified on model-selection validation but **failed** the
out-of-sample SGN test. The executable CI driver is authoritative for its own
output at the version recorded in a given run; floating-point/LAPACK selection
at near-ties can vary across hosts.

A failed out-of-sample result is marked `refused_after_independent_test`
even when the original SGN model's shorter validation status was `qualified`.
Do not treat such a model as an executable Ground on a receiving host.

## Reproduce

With NumPy installed, from repository root:

```bash
python -m unittest discover -s experiments/tpp007-sgn001 -p 'test_*.py' -v
python experiments/tpp007-sgn001/qualify_archived_tpp.py \
  --archive ./tpp007-live.json --output ./tpp007-sgn001-result.json
```

Download the exact archived JSON from the Actions artifact above. The
companion workflow downloads that artifact, reruns the original SGN code and
uploads the JSON result. GitHub Actions artifacts expire; the two source SHA-256
identities above and TPP-007's retained design remain important when
reacquiring observations, but revised provider bytes are **not** identical
to the originally witnessed record.

## Integration next

A portable receipt should carry the selected mathematical law, typed
coordinate, numeric profile and original SHA-256, **plus a local receiving-host
authority binding and final-test refusal status**. A self-recomputed checksum
does not independently authorize a transported law. Wire this through
existing VGI and E-CPU authorities only after the mainline conformance audit.
