# Controlled E-CPU observation cost–information matrix

**Status:** pilot experiment; not a production benchmark or adaptive policy input.  
**Runtime:** E-CPU commit `800f94f83ffd6f527ed093c8d1c1e93e153c34f6`.  
**Purpose:** measure how controlled workload changes affect actual E-CPU observation-path call costs, while recording the informational result of each typed observation independently.

## Question

How do payload size, receiver mailbox backlog, source count, quorum width, and concurrent receiver activity affect the observed cost distribution of an E-CPU observation path? What did the observation distinguish under a separately declared hypothesis model?

The experiment uses E-CPU's actual `ReliableChannel`, `DurableMailboxTransport`, `GatedObservationCoordinator`, quorum finalization, VM commit, checkpoint writer, and sender ACK processing. It does not substitute a simulated coordinator for the main measured path.

## Workload matrix

The default matrix contains 24 conditions with three independent repetitions each (72 workload attempts):

| Factor | Levels |
| --- | --- |
| `ResolverObservation.value` UTF-8 bytes | 64, 1,024 |
| Initial receiver queue depth per source (including target frame) | 1, 3 |
| Source count / quorum | (2,2), (4,2), (4,4) |
| Concurrent independent receiver coordinators | 0, 2 |

All configured sources send a matching typed observation for each logical event. This is necessary for the strict policy to authorize the event even when the quorum threshold is less than the source count. An initial depth of 1 means the target is the only queued frame; a depth of 3 means two earlier backlog events precede the target. Each attempt ingests, finalizes, commits, checkpoints, and processes ACKs in FIFO order. Earlier events are consumed before the target event so the reliable receive cursor is respected.

The receiver-load factor synchronizes one or two independent E-CPU coordinator `ingest_available()` calls with the target observation's intake call. These background receivers use separate in-memory transports so they create concurrent receiver computation without adding their messages to the target's durable queue. This is a controlled same-process concurrency probe, not a distributed network or multi-host load test.

## Measurements

The span recorder surrounds actual synchronous call boundaries:

- `ReliableChannel.send()`
- `GatedObservationCoordinator.ingest_available()`
- `GatedObservationCoordinator.finalize_event()`
- `GatedObservationCoordinator.commit_event()`
- `GatedObservationCoordinator.save_checkpoint()` (each internal call is individually wrapped while the commit is running)
- `GatedObservationCoordinator.process_acks()`

Every span preserves attempt identity, explicit observation identity, workload condition, event phase, logical time, and clock actor/segment. The measured value is synchronous elapsed monotonic wall duration, including blocking and local scheduling; it is not CPU time.

The cost analyzer reconstructs profiles independently from the source spans. It partitions by the five workload factors and reports both:

1. `all_events`: the full queue-drain plus target path under that condition;
2. `target_event`: only call spans associated with the final requested observation.

This distinction matters for queue depth. E-CPU ingests one new event per source before the FIFO frame is consumed by the commit path. A deeper queue therefore adds earlier event work and gives the channel more queued records to validate, but the target event is still processed only after its predecessors. The raw spans retain `event_index` and `phase` so this can be inspected directly.

## Informational outcomes

Each typed ResolverObservation is accompanied by a separate evidence record and an `observation_outcome` document. The deterministic fixture model contains four hypotheses:

- two hypotheses predict `hit`;
- two hypotheses predict `miss`;
- the Boolean query is whether the result is a hit;
- prior masses are 0.40, 0.10, 0.30, and 0.20.

The model therefore has one bit of expected information gain and a modelled query-resolution probability of one. The actual hit/miss observation determines the realized posterior for that event. This is a declared synthetic hypothesis fixture used to exercise the information ledger; it is **not** a statement about a real DNS resolver, remote service, or external world. Its purpose is to test that real E-CPU observation delivery and application can be joined to a model-derived information record without deriving the latter from timing.

The experiment retains cost and information as separate artifacts. It does not compute an information-per-nanosecond score or modify an adaptive attention policy.

## Artifacts

The run writes:

- `run-manifest.json` — pinned runtime, platform, clock segment, matrix coverage, sample counts, and digest;
- `workload-results.json` — one result per attempt, including actual VM register readback and target outcome;
- `operation-spans.json` — raw synchronous call spans;
- `operation-cost-profiles.json` — independently reconstructed per-condition cost distributions;
- `observation-evidence.json` and `evidence/*.json` — source payloads, channel sequences, authority result, and evidence digests;
- `information-outcomes.json` — independently reconstructed information outcomes for each admitted event.

CI uploads these under the artifact name `ecpu-observation-cost-information-experiment`.


## First live CI pilot

The first full matrix completed successfully in [GitHub Actions Run 271](https://github.com/Kier73/In-Formation-Space/actions/runs/43130567381). Its `ecpu-observation-cost-information-experiment` artifact is retained by that run. The [checked-in summary receipt](results/live-ci-run-271-summary.json) records the artifact digest, run and E-CPU revisions, profile-matrix digest, and a compact view of the measured distributions.

**Observed coverage:** 24 conditions × 3 repetitions = 72 attempts; 2,448 operation spans; 144 evidence records and 144 information outcomes. Every sender ACK path completed. All six instrumented operation boundaries reached the three-sample descriptive threshold in the target-event profiles.

The following values are medians of condition-level target-event medians, in milliseconds. At each single-factor level, the 12 condition medians are equally weighted; these are not pooled per-call estimates.

| Operation | Payload 64 B | Payload 1,024 B | Queue depth 1 | Queue depth 3 | Receiver load 0 | Receiver load 2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `ingest_available()` | 0.1371 | 0.1430 | 0.1393 | 0.1390 | 0.1385 | 0.1396 |
| `commit_event()` | 34.8753 | 33.5270 | 33.5270 | 44.5605 | 34.3316 | 33.9628 |
| `save_checkpoint()` | 3.4164 | 3.0343 | 2.5650 | 3.5487 | 3.0531 | 3.4540 |
| `process_acks()` | 1.7651 | 1.6372 | 1.6372 | 1.6593 | 1.6848 | 1.6468 |

The initial signal is that queue depth is associated with higher target commit/checkpoint medians in this workload, whereas changing the observation value field from 64 to 1,024 bytes did not increase these medians. The same-process receiver-load condition produced similar medians to its no-background-call counterpart. These are descriptive contrasts, not causal conclusions.

The source/quorum factor is a **joint** design, not a full independent cross: (2 sources, quorum 2), (4, quorum 2), and (4, quorum 4). For target `commit_event()`, the corresponding medians of condition medians were 26.8335 ms, 41.4252 ms, and 39.1624 ms. The run cannot attribute those differences separately to source count or quorum width.

All 144 synthetic information outcomes report one bit of expected information gain and a modelled query-resolution probability of one. The 72 target outcomes were 48 hits and 24 misses, both of which resolved the fixture's Boolean query. This validates the distinction and reconstruction path between actual E-CPU observations and a declared model; it does not establish the model as external sensor truth.

The summary receipt's `summary_digest` is SHA-256 over all fields except itself. The run-manifest and cost-profile digests are retained separately. The source span/evidence/outcome artifacts remain available from the linked Actions run for independent re-analysis.


### Second workflow run

The same matrix was executed again in [Run 273](https://github.com/Kier73/In-Formation-Space/actions/runs/43130924950), using the same pinned E-CPU revision and a distinct process-local clock segment. It again completed 24 conditions, 72 attempts, 2,448 spans, 144 evidence records, and 144 information outcomes.

Across the 24 matched target-event condition medians, the median absolute run-to-run relative differences were 2.61% for `ingest_available()`, 2.53% for `commit_event()`, 1.91% for `save_checkpoint()`, and 4.78% for `process_acks()`. The [summary receipt](results/live-ci-run-271-summary.json) now records both runs, both artifact digests, the paired comparison method, and its limits.

This is a useful first check that the condition-level distributions are not wildly changing between two separate workflow/process segments. It is not a confidence interval, a claim of verified independent hardware, or proof of production repeatability. The next useful replication is across explicitly identified independent hosts and longer sample series.
## Reproduce

With E-CPU checked out at the pinned revision:

```bash
export ECPU_ROOT=external/E-CPU
export PYTHONPATH=external/E-CPU
python experiments/observation-cost-information/run_experiment.py \
  --output-dir experiments/observation-cost-information/results
python -m unittest discover \
  -s experiments/observation-cost-information -p 'test_*.py' -v
```

The runner checks the exact E-CPU revision before executing. Each output profile is rebuilt from its original source spans, and every information outcome is rebuilt from its retained prior model and observed branch. Evidence digests are checked against the experiment's local source records.

## Interpretation limits and next experiments

- The payload factor measures the UTF-8 byte length of the typed observation's `value` field, not the complete serialized frame.
- The durable transport is local. Filesystem, operating-system scheduling, Python runtime, and CI host effects remain in the measurements.
- The concurrency factor uses synchronized independent receiver coordinator calls in the same process. It does not model network latency, multi-host contention, or deployed receiver saturation.
- All senders agree by construction. Conflicting evidence, packet loss, retry, receiver refusal, partial ACK, and crash-recovery paths require separate controlled factors.
- Three repetitions are a pilot threshold for descriptive profiles, not enough to claim stable percentiles or causal laws. Compare raw spans and repeat on independent hosts/process segments before generalizing.
- The hit/miss hypothesis prior is fixed by the fixture. A real observation domain needs an independently specified, revisable hypothesis model and evidence provenance before informational outcomes can be treated as empirical.
- The matrix does not correct selection bias or define costs for observations that were never executed.

Promising next steps are: vary loss/retry and partial ACK state; separate durable-log size from observation payload size; repeat across independent process/host clock segments; and introduce a domain-grounded likelihood model only when the underlying observation semantics and calibration data exist.
