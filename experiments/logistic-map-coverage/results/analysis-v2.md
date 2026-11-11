# V2 numerical follow-up: repeated-return logistic coverage

**Execution:** GitHub Actions run 31  
**Commit:** a526f03925077fd450196016e80cd94e87e93f7e  
**Runner:** ubuntu-latest, Python 3.11.18  
**Scanner:** scan_coverage_v2.py  
**Encounter:** results/coverage-v2-ci-run-31.json

## Configuration

- Parameter interval: [3.5, 4.0]
- Cell-centered grid: 20,000 samples
- Transient warmup: 2,000 steps
- Initial conditions: 0.5 and 0.123456789
- Candidate period ceiling: 64
- Return tolerance: 1e-9
- Additional repeated returns after first candidate: 2
- Stability margin: 1e-6

The scanner completed in 6.37 seconds and returned 149 candidate windows.

## Coverage matrix

Fractions are normalized by the full parameter interval [3.5, 4.0] and computed from grouped numerical candidate cells.

| Resolution | P<=2 | P<=4 | P<=8 | P<=16 | P<=32 | P<=64 |
|---|---:|---:|---:|---:|---:|---:|
| 0.0002 | 0.0000 | 0.1123 | 0.1794 | 0.2002 | 0.2049 | 0.2049 |
| 0.0005 | 0.0000 | 0.1123 | 0.1765 | 0.1959 | 0.1974 | 0.1974 |
| 0.0010 | 0.0000 | 0.1109 | 0.1741 | 0.1908 | 0.1908 | 0.1908 |
| 0.0020 | 0.0000 | 0.1109 | 0.1741 | 0.1820 | 0.1820 | 0.1820 |
| 0.0050 | 0.0000 | 0.1109 | 0.1611 | 0.1611 | 0.1611 | 0.1611 |
| 0.0100 | 0.0000 | 0.1109 | 0.1494 | 0.1494 | 0.1494 | 0.1494 |

The observed plateau point within the tested budgets is P=32 for resolutions 0.0002 and 0.0005, P=16 for 0.0010 and 0.0020, and P=8 for 0.0050 and 0.0100.

## Comparison with the original scan

The original 50,000-point scan reported 303 candidate windows and coverage values of 20.10%, 19.29%, 18.47%, 17.63%, 15.63%, and 14.48% at the six respective resolutions.

V2 reports 149 candidate windows and 20.49%, 19.74%, 19.08%, 18.20%, 16.11%, and 14.94%.

The similar coverage magnitudes are an encouraging robustness signal, but this is **not a controlled convergence comparison**. The runs differ in grid size, cell placement, warmup, initial-condition count, tolerance, and cycle-return checks. The difference in candidate-window counts cannot be attributed to any one setting from these two runs alone.

## Verification

The successful CI job executed:
- 5 tests for the original scanner and coverage invariants;
- 6 tests for the repeated-return v2 classifier and coverage routine;
- the 20,000-sample v2 scan itself.

The v2 tests cover known period-1, period-2, and period-3 attractors; a parameter with no stable candidate under these settings; invalid configurations; cell-width accounting; and monotonicity of the coverage matrix.

## Interpretation

The stronger scan preserves the broad pattern seen in the initial run: detected candidate coverage increases with period budget and decreases with coarser resolution, and a plateau is observed over the tested period budgets through 64.

This result is still numerical. Repeated returns and multiple initial conditions reduce some heuristic failure modes but do not certify an attracting orbit on every point of a parameter interval. The complement of candidate coverage remains unclassified, not a measured chaotic set or dead-zone set. A rigorous next step would use validated interval arithmetic to bound orbit trajectories, cycle multipliers, and parameter boundaries.
