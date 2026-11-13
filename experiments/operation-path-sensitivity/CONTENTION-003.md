# OPS-003: Shared-resource dependencies and intervention value

## Question

Can an incomplete dependency graph appear accurate while missing the practical
value of an intervention? OPS-002 measured parallel blocking branches. Here the
same two branches must hold one shared `threading.Lock` while doing their work.
Their recorded work durations become serialized, so a resource-order edge
changes the modeled benefit of shortening either branch.

Both graph interpretations are retained over **the same spans**:

- `fork_join`: A-to-join and B-to-join, omitting the shared resource.
- `resource_order`: those edges plus the receipt-backed order between A and B.

The incomplete graph is not labeled mathematically wrong: it computes the
maximum cost of its declared paths correctly. The experiment tests whether
those declared paths explain intervention effects on the enclosing workload.
OPS-001 never promised to predict root elapsed time.

## Evidence and construction

Two worker threads cross a barrier, timestamp their request for the mutex,
acquire it, and measure the existing OPS-002 sleep operation **inside** the
critical section. Work spans exclude acquisition/waiting. The root span includes
release, worker scheduling, instrumentation and the final join operation.

Each worker appends a digest-linked receipt while holding the mutex. A receipt
binds its resource, attempt, process clock actor/segment, ordinal, exact work-span
digest, request timestamp, acquisition timestamp and release-pending marker.
The marker is sampled before release; it is not an actual release timestamp.
The request-to-acquisition interval includes waiting and scheduling and is not
an isolated measurement of lock contention.

Reconstruction requires two distinct branch receipts, exact identities, a valid
digest chain, enclosing root bounds, acquisition before work, work completion
before the release marker, and successive acquisition after the prior marker.
The join must follow the last marker. The receipt sequence supplies the edge;
timestamp order only checks its consistency. Missing receipts are rejected,
not replaced by timestamp sorting. This authenticates no physical event: the
receipts remain assertions made by the local harness.

Each of seven blocks runs a baseline followed by shuffled control, A-only,
B-only and joint interventions. Baseline sleeps are 80 ms per branch and 10 ms
for the join. Each shortened branch requests 20 ms. Both model predictions are
constructed from baseline evidence before executing that intervention.

Lock order may change across trials. The bundle records this rather than
pretending the orientation was preserved. For these two serialized work nodes,
the modeled duration is A+B+join in either order. That property does not apply
to arbitrary resource schedules.

## Exact oracle

For noiseless serialized weights A=80, B=80 and join=10:

| Intervention | Fork/join predicted path gain | Resource-order predicted path gain |
| --- | ---: | ---: |
| Control | 0 | 0 |
| A shortened by 60 | 0 | 60 |
| B shortened by 60 | 0 | 60 |
| Both shortened by 60 | 60 | 120 |

Tests verify this table for both A-first and B-first receipt order, and verify
that the baseline root slack changes from 80 to 0 when the edge is admitted.
These are synthetic exact checks, not timing measurements.

## Local observation, 2026-11-13

[Retained evidence](results/ops003-windows-local.json): Windows 11, Python
3.14.0, seven blocks, 35 measured trials and one excluded warm-up. Values below
are medians of seven paired differences, in milliseconds. Positive gain means
shorter duration. The raw artifact also retains signed ranges and all spans.

| Intervention | Fork/join predicted path gain | Resource-order predicted path gain | Observed resource-order path gain | Observed root gain |
| --- | ---: | ---: | ---: | ---: |
| Control | 0.000 | 0.000 | 0.213 | 0.245 |
| A only | 0.237 | 60.000 | 60.042 | 60.273 |
| B only | 0.000 | 60.000 | 59.848 | 60.034 |
| Both | 60.000 | 120.000 | 120.092 | 120.154 |

The fork/join model's own measured path gains were 0.201, 0.022 and 60.132 ms
for A, B and both respectively: fairly close to its predictions. Yet those
values leave about 60 ms of the observed root improvement unexplained. This is
a projection issue, not a failure of the longest-path algorithm. Adding the
resource evidence makes the serialized work explicit.

The same baseline spans have median root slack of 81.250 ms in the incomplete
graph and 0.910 ms in the resource-order graph. Slack is a defined remainder,
not a directly measured causal category. For each pair and each model,
`root gain = path gain + slack gain` remains exact; medians need not add.

Lock order changed relative to baseline in 17 of the 28 control/intervention
comparisons. This is recorded explicitly. The prediction agreement here relies
on the order-insensitive two-task sum, not guaranteed scheduling repeatability.

## Verification and reproduction

```sh
python -m unittest discover -s experiments/operation-path-sensitivity -v
python experiments/operation-path-sensitivity/contention.py --output results/ops003.json
python experiments/operation-path-sensitivity/contention.py --verify results/ops003.json
python experiments/operation-path-sensitivity/contention.py --verify experiments/operation-path-sensitivity/results/ops003-windows-local.json
```

All 23 local tests passed on Python 3.14.0: eight new contention tests plus the
15 existing sensitivity/intervention tests. New checks cover the exact oracle,
live evidence reconstruction with no timing threshold, missing receipts,
cross-trial/clock/resource substitution, duplicated spans, malformed coordinates,
broken/reordered but rehashed chains, dropped resource edges, and altered
predictions/analysis. A separate Python process reconstructed the local bundle.

The [contention workflow](../../.github/workflows/operation-path-contention.yml)
runs fresh seven-block Linux and Windows measurements, reconstructs each bundle
and uploads it. It requires consistent evidence, not a chosen performance result.
The existing OPS-001/002 workflows also run the expanded test suite.

Source baseline: In-Formation-Space
`0cc76672abc4bfe8808642898d13d61d24dcba30`. OPS-001, OPS-002 and the operation
span/path modules are imported unchanged. The bundle records exact local source
byte hashes; newline differences can change hashes across platforms. No code
from E-CPU or VGI is copied.

## Interpretation and next question

These are controlled blocking experiments on one process, not CPU benchmarks,
distributed resource admission, independent authority evidence or authenticated
execution. Baseline-first order, correlated paired samples, sleep overshoot,
and instrumentation remain relevant. Ranges are descriptive, not confidence
intervals. Root gain minus predicted path gain is a diagnostic discrepancy and
is never represented as a root-time prediction made by OPS-001.

The next useful question is how to distinguish missing resource order from a
changed operation boundary: if a span includes waiting, its duration can absorb
another operation's work. Measuring work-only and wait-inclusive boundaries
together would test whether a seemingly accurate cost model is portable under
intervention, or only compensating for missing structure.
