# Logistic map coverage v2: stronger numerical screening

This is a second numerical pass over the original [Logistic Map Coverage Function experiment](README.md). It does not replace the original scan or turn numerical samples into formal interval certificates.

Compared with scan_coverage.py, v2:
- samples parameter-cell centers and assigns each detected run the corresponding cell-boundary interval;
- requires the candidate period to return repeatedly after its first approximate return;
- requires all configured initial conditions to identify the same candidate period;
- applies a non-zero stability margin;
- labels outputs as numerical candidate windows, not certified intervals;
- exposes sample count, period cap, and warmup as command-line options.

## Interpretation

A parameter returned with period zero means only that this procedure did not establish a stable candidate under the chosen finite settings. It does not mean the parameter is chaotic.

Agreement across initial conditions and repeated returns reduces some false positives. It does not prove an attracting cycle exists throughout the reported parameter interval. A proof-quality coverage calculation would require validated numerics, for example interval enclosures for the orbit, multiplier, and parameter boundaries.

## Files

- scan_coverage_v2.py — repeated-return, multi-initial-condition scanner.
- test_scan_coverage_v2.py — tests known stable periods, configuration guards, cell widths, and coverage monotonicity.
- review-note.md — independent limitations review of the original scan.

## Reproduce

    python -m unittest discover -s experiments/logistic-map-coverage -p 'test_scan_coverage_v2.py' -v
    python experiments/logistic-map-coverage/scan_coverage_v2.py --samples 20000 --json
