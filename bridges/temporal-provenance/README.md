# Bridge: clock-domain-safe temporal provenance

**Status:** experimental portable temporal-observation contract and analyzer.  
**Purpose:** preserve local-clock coordinates, causal partial orders, scheduler order, and calendar readings as distinct evidence when encounters move between independent systems.

## Why this bridge exists

In-Formation-Space already carries encounter records and explicit causal relations. E-CPU also provides a typed `TemporalFrame` with process-local monotonic readings, local wall samples, vector-clock causal stamps, named scheduler ticks, and separate SystemEpoch coordinates. Virtual-Ground-Interpreter has separately explored event correspondence between streams whose clocks are independently transformed.

Those are related, but not interchangeable, claims:

- A local tick orders observations only within the clock that produced it.
- A monotonic reading can be subtracted only within the same actor and restore segment.
- A scheduler tick orders work only within the same scheduler.
- A vector clock can establish happens-before, equality, or concurrency when the stamps were actually captured.
- A wall timestamp is a calendar estimate. It does not establish causality or a cross-host event order.
- An event correspondence is a proposed match between records. It is not itself a causal edge.
- A missing causal stamp means **unobserved ordering**, not concurrent events.

The bridge makes these distinctions portable without importing E-CPU or VGI at runtime.

## Source and adaptation lineage

Inspected source revisions:

| Project | Revision | Material used |
| --- | --- | --- |
| [E-CPU](https://github.com/Kier73/E-CPU) | `800f94f83ffd6f527ed093c8d1c1e93e153c34f6` | Studied `mailcpu.temporal.TemporalFrame`, `MonotonicReading`, `CausalStamp`, and `SchedulerReading`; the JSON frame contract is compatible with `TemporalFrame.to_dict()`. |
| [Virtual-Ground-Interpreter](https://github.com/Kier73/Virtual-Ground-Interpreter) | `cedcc4540a9d75228cf83aaf21e1ba960fe8a555` | Studied the build-15/build-17 local-clock and cross-observer event-alignment experiments. Their event correspondence does not require timestamp synchronization and is not converted into a clock-difference edge here. |

This bridge is a **reimplementation of a small portable interchange and analysis contract**, not copied code. It has no runtime dependency on either project. The source repositories remain the authorities for their own runtime semantics.

## Record shape

An observation has this form:

```json
{
  "format": "in-formation.temporal-provenance/0.1",
  "event_id": "event-17",
  "local_counter": {
    "clock_id": "controller:C",
    "coordinate": 105,
    "unit": "tick"
  },
  "temporal_frame": null
}
```

At least one of `local_counter` or `temporal_frame` is required. The local-counter coordinate is deliberately opaque: the analyzer does not assume that a tick is a second, a nanosecond, or globally comparable.

An E-CPU-compatible temporal frame contains the exact field set emitted by `TemporalFrame.to_dict()`:

- `actor_id`;
- optional `monotonic` reading `(actor_id, segment, elapsed_ns)`;
- optional `wall` reading `(actor_id, utc_ns, sample_index)`;
- optional `causal` stamp `(actor_id, lamport, vector)`;
- optional `scheduler` reading `(scheduler_id, tick)`;
- separate `event_lambda`, `chronon_phase`, and `chemical_tau` coordinates.

The validator checks the actor binding, non-negative counters, vector-clock self component and Lamport bound, and the unit-circle constraint on chronon phase. The remaining SystemEpoch coordinates are retained but are not converted into physical time or used to order events.

The frame can be stored in an encounter envelope under a namespaced extension, for example:

```json
{
  "extensions": {
    "in-formation.temporal-provenance/0.1": {
      "format": "in-formation.temporal-provenance/0.1",
      "event_id": "event-17",
      "local_counter": null,
      "temporal_frame": {
        "actor_id": "receiver:1",
        "monotonic": null,
        "wall": null,
        "causal": {
          "actor_id": "receiver:1",
          "lamport": 2,
          "vector": {"controller:1": 1, "receiver:1": 1}
        },
        "scheduler": null,
        "event_lambda": null,
        "chronon_phase": null,
        "chemical_tau": null
      }
    }
  }
}
```

The example is illustrative. A producer should retain the actual frame emitted by its clock context rather than reconstructing one from prose.

## Comparison contract

The analyzer reports each domain independently for every pair of observations:

| Domain | Comparable only when | Result |
| --- | --- | --- |
| `local_counter` | Same `clock_id` and `unit` | before / after / equal; otherwise incomparable or unobserved |
| `causal` | Both vector stamps are present | before / after / equal / concurrent; absent is unobserved |
| `monotonic` | Same actor and same restore segment | before / after / equal; otherwise incomparable or unobserved |
| `scheduler` | Same scheduler ID | before / after / equal; otherwise incomparable or unobserved |
| `wall` | Never used by this analyzer | not_used |

Vector-clock comparison uses componentwise ordering over the union of actor IDs; an omitted component is zero. A relation of concurrent is therefore a positive result from two recorded vector stamps. It is not a synonym for “we do not know.”

No single topological order is emitted. Each domain gets its own directed edges, maximal events, cycle check, and weakly connected components. Events in separate components remain unordered by that domain. The analyzer does not merge local-counter, scheduler, and causal edges into one global timeline.

If both causal and monotonic readings exist for the same actor and segment and their directional orders disagree, the pair is flagged as `local_causal_disagreement`. The tool does not silently choose one clock.

## Reproduce

Run the standard-library tests:

    python -m unittest discover -s bridges/temporal-provenance -p 'test_*.py' -v

Analyze a JSON array (or an object with an `observations` array):

    python bridges/temporal-provenance/temporal_provenance.py \
      --input observations.json \
      --output temporal-analysis.json

Generate the split-clock relay example:

    python bridges/temporal-provenance/demonstration.py \
      --output results/temporal-provenance-example.json

The split-clock relay demonstration preserves controller ticks C100/C101/C105/C108 and sensor ticks S8/S11/S14. It derives within-stream order only, reports 12 cross-stream local-counter pairs as incomparable, and leaves all 21 causal comparisons unobserved because the packet contains no vector stamps. It does not retroactively invent clock synchronization or causal evidence.

A second, explicitly synthetic example shows the different result when vector stamps are actually captured: a receiver that has received a controller message is causally after that send, while an independent sensor event remains concurrent with both.

## Boundaries and next experiments

- Clock IDs and actor IDs are labels; this format does not authenticate their owners.
- No calibration or affine clock-fit model is inferred. A future calibration extension should carry anchor events, uncertainty bounds, validity intervals, and provenance, then prove order only when mapped intervals are disjoint.
- A VGI-style event correspondence can be added as a separate relation. It must not be treated as a causal edge or as a clock calibration unless a separate contract establishes that implication.
- The analyzer is pairwise (O(n^2)). It is intended for inspectable traces, not an unbounded event database.
- The vector-clock model assumes actor IDs are uniquely owned by one active writer. Split-brain actor identity invalidates its causal interpretation.
- Digests or encounter references do not authenticate a source, and this bridge does not fetch referenced artifacts.

The next useful experiment is to capture the same event stream through two E-CPU clock contexts, preserve the actual TemporalFrames, and verify that local durations remain endpoint-local while vector-clock stamps recover only message-mediated causal order.
