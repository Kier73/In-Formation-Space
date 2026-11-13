# OPS-001: Operation-path sensitivity

Follow-up: [OPS-002 measured fork/join interventions](INTERVENTION-002.md)
compares these predictions with retained observations from real worker threads.

[OPS-003 shared-resource contention](CONTENTION-003.md) preserves both the
fork/join graph and a receipt-backed resource-order graph over the same spans.

## Question

Does reducing the duration of an operation on a longest declared dependency
path shorten that path's maximum cost? A representative critical path alone
does not answer this: an equally long competing branch may remain unchanged.

This experiment extends the [operation-path analyzer](../../bridges/observation-path/operation_path_criticality.py)
with explicit counterfactual duration reductions. It leaves the evidence spans,
trace, original report and their schemas unchanged.

## Construction and meaning

First reconstruct and validate the original same-clock operation path. Then
retain every declared edge and assign each operation its measured duration.
Use forward and backward dynamic programs to calculate:

- The maximum source-to-sink path cost and number of paths attaining it.
- Each node's maximum containing-path cost, gap from the global maximum, and
  number of maximum paths through it.
- Whether a node belongs to every maximum path.
- The benefit of setting each node's duration to zero, with edges retained.
- The maximum path cost under a supplied joint duration-reduction hypothesis.

For node v with weight w(v), the longest path through v is
`forward(v) + backward(v) - w(v)`. If this equals the global maximum,
its critical-path multiplicity is the product of the numbers of maximizing
prefixes and suffixes. The DAG property ensures those paths cannot share any
other node. Counts use Python arbitrary-precision integers.

Paths here are distinct source-to-sink node sequences. Zero-duration operations
and isolated nodes remain present. Adding a redundant transitive edge can
change the number of paths without changing the maximum cost; counts are about
the supplied graph representation, not independent physical causes.

The per-node full-removal analysis recomputes the maximum after each hypothetical
change. Its time cost is O(V(V+E)), excluding source validation, sorting, and
arbitrary-precision arithmetic; it does not enumerate paths. This initial
implementation favors inspectability over optimization for very large graphs.

## Exact synthetic examples

Two branches A and B feed a join J. Values below are integer nanoseconds in
synthetic fixtures, not timing observations from a running workload.

| Original A, B, J | Proposed reduction | Original maximum | New maximum | Benefit |
| --- | --- | --- | --- | --- |
| 10, 10, 5 | A by 10 | 15 | 15 | 0 |
| 10, 10, 5 | B by 10 | 15 | 15 | 0 |
| 10, 10, 5 | A and B each by 4 | 15 | 11 | 4 |
| 10, 10, 5 | J by 5 | 15 | 10 | 5 |
| 10, 8, 5 | A by 7 | 15 | 13 | 2 |

The first rows show complementary changes whose individual benefits are zero.
The last row shows a bottleneck switching to another path. Individual removal
benefits therefore must not be added to estimate joint improvement.

## Reproduce

From the repository root, using Python 3.11 or newer:

```sh
python -m unittest discover -s experiments/operation-path-sensitivity -v
python -m unittest discover -s bridges/observation-path -p test_operation_path_criticality.py -v
python experiments/operation-path-sensitivity/sensitivity.py --spans spans.json --trace trace.json --reductions reductions.json
```

The span array and trace use the existing bridge formats. `reductions.json` is
an object from operation span SHA-256 digest to nanoseconds removed. Omit it for
baseline sensitivity. Each reduction must be an integer in [0, original duration];
booleans, floats, unknown spans, and the enclosing root are rejected. JSON report
output goes to stdout. The Python API also reconstructs reports to detect
altered results even when their content digest has been recomputed.

## Verification and provenance

The implementation and its seven tests ran locally on Windows with Python
3.14.0 on 2026-11-13. All passed, including independent exhaustive enumeration
of source-to-sink paths for all 64 forward DAGs on four labeled nodes and all
16 binary-duration assignments: 1,024 cases, including all-zero durations.
The existing operation-path suite passed all 11 tests. The default local Python
lacked `jsonschema`; all 13 operation-span tests then passed using the available
Python 3.11.15 environment with that dependency. CI installs it explicitly and
runs all three suites.

The dependency files `operation_path_criticality.py`, `operation_spans.py`, and
the test fixture module `test_operation_path_criticality.py` were compared with
GitHub revision `a54a7cba4ef0cd637faa21bd622ff4a301fe37a2` and matched after
newline normalization. They are imported without modification. No code from
E-CPU or VGI is copied. The dedicated workflow covers Linux and Windows on
Python 3.11 and 3.14; consult its run results for CI evidence.

## What remains unknown

This is inference under a fixed-DAG model, not a measured acceleration. It does
not predict root elapsed time, resource scheduling, queueing, changed dataflow,
or changes to other operation durations. Missing dependency edges still matter.
Full removal is an idealized sensitivity probe, not a claim that an operation
can actually be eliminated. Synthetic fixture timestamps serialize the nodes
to satisfy evidence validation but never create undeclared dependency edges.

A useful next experiment is to compare these counterfactual rankings with
controlled interventions on a real fork/join workload, preserving both the
prediction and observed deviation rather than replacing one with the other.
