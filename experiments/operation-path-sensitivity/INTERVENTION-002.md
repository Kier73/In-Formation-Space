# OPS-002: Measured fork/join interventions

## Question and protocol

Does OPS-001's predicted benefit survive an actual intervention on a blocking
fork/join workload? Two worker threads each request an 80 ms sleep. The main
thread waits for both, then requests a 10 ms join sleep. Interventions shorten
A, B, or both to 20 ms. An unchanged control measures ordinary run variation.
This is executable controlled waiting, not a CPU-performance benchmark.

One unretained warm-up initializes the pool. Each of seven measured blocks runs
a baseline first, then a seeded shuffle of control, A-only, B-only, and both.
Every prediction is constructed from that block's baseline **before** its
intervention executes. The requested 60 ms reduction is applied to the measured
baseline duration through OPS-001; later observed durations never set the
prediction. An infeasible reduction is rejected, not clipped.

Each trial retains four existing operation-span documents and the exact
A-to-join and B-to-join dependency trace. Worker barriers precede branch spans;
the enclosing root includes release, scheduling, recorder overhead and joining.
The threads use separate recorder instances sharing a single process clock
actor and segment. The recorder's mutable state is never shared between threads.

The evidence bundle retains the plan, seeded order, raw spans, predictions,
environment, source-file byte hashes, signed paired differences, descriptive
medians/ranges, and a content digest. `--verify` reconstructs all predictions and
analysis in a fresh process, checks the specified fork/join topology and delay
contexts, and rejects reused trial identities. These checks establish internal
consistency, not authenticated execution or physical provenance.

## Local observation, 2026-11-13

[Retained Windows evidence](results/ops002-windows-local.json): Python 3.14.0,
seven blocks, 35 measured trials plus the excluded warm-up. All values below
are milliseconds; positive gain means shorter duration. Ranges span the seven
paired observations and are not confidence intervals.

| Intervention | Median predicted path gain | Median observed path gain | Observed path gain range | Median root gain |
| --- | ---: | ---: | ---: | ---: |
| Unchanged control | 0.000 | -0.100 | -0.742 to 0.399 | 0.118 |
| A only | 0.146 | -0.022 | -0.589 to 0.272 | -0.012 |
| B only | 0.000 | 0.056 | -0.240 to 0.445 | -0.160 |
| Both | 60.000 | 59.811 | 59.280 to 60.451 | 59.932 |

The measured baseline branches are nearly equal, not exactly tied. Their small
duration differences explain the small nonzero A-only predictions. Single-branch
observations overlap the control range. The joint intervention produced a much
larger reduction in all seven observations; its median path prediction error
was -0.189 ms. This supports the modeled complementarity in this workload and
session without turning a small sample into a general performance guarantee.

For each pair, the report preserves the exact identity:

`root gain = dependency-path gain + root-slack gain`.

Slack is the remainder defined by the original analyzer, not a measured causal
category such as scheduling time. Medians of these components need not add.

## Reproduce and verify

From the repository root, with Python 3.11 or newer and no extra dependencies:

```sh
python -m unittest discover -s experiments/operation-path-sensitivity -v
python experiments/operation-path-sensitivity/intervention.py --output results/ops002.json
python experiments/operation-path-sensitivity/intervention.py --verify results/ops002.json
python experiments/operation-path-sensitivity/intervention.py --verify experiments/operation-path-sensitivity/results/ops002-windows-local.json
```

The local 15-test suite passed: eight intervention tests plus seven OPS-001
tests, including the 1,024-case exhaustive path oracle. Intervention tests cover
real-thread evidence reconstruction without asserting a speed threshold,
negative gains, invalid plans, missing edges, duplicate trials, changed order,
and self-consistently rehashed prediction/summary tampering. A separate CLI
process reconstructed the retained local bundle successfully.

The [dedicated workflow](../../.github/workflows/operation-path-intervention.yml)
runs fresh seven-block measurements on Linux and Windows, reconstructs each
bundle, and uploads the complete evidence. CI checks evidence consistency, not
whether a noisy performance number meets an expected improvement threshold.
Consult the workflow results for those observations rather than extrapolating
the local table to other hosts.

This builds on In-Formation-Space revision
`9e0dd5774c89d45ecf5aa665621d31dafbd3c6c4`, importing OPS-001 and the original
operation-span/path modules unchanged. No E-CPU or VGI code is copied.
The raw source hashes preserve the exact local file bytes; newline conversion
between platforms can change those hashes without changing Python behavior.

## Remaining questions

The baseline is always first, so time drift is not eliminated. Four comparisons
share each baseline and are correlated. Seeded ordering reduces systematic
variant-order bias without establishing a randomized causal estimate. OS sleep
overshoot, scheduling and instrumentation remain in the recorded durations.

Useful next work is to deliberately impose a shared resource constraint and
test when the fixed-DAG prediction fails. Serializing the branches under a lock
would introduce ordering that the original fork/join edges do not describe;
that experiment should record the new dependency evidence and compare both
models instead of attributing all deviation to timing noise.
