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

`attach_to_encounter_envelope()` returns a copied envelope with the observation under the namespaced extension; `extract_from_encounter_envelope()` checks the extension and requires its `event_id` to match the envelope ID. The helper refuses to overwrite an existing temporal extension.

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

## Bounded affine clock calibration (separate experiment)

`clock_calibration.py` is an optional follow-on to temporal provenance. It does not rewrite the original observations or attach an alignment to a record unless a caller explicitly stores the resulting calibration. A calibration is a separate artifact with its own digest, anchors, model, and validity range.

### Anchor contract

A calibration anchor declares that one physical correlation event was observed at:

- an exact source-clock coordinate; and
- a bounded target-clock interval `[target_lower, target_upper]`.

Each anchor carries a unique ID, an explicit correlation basis (`shared_trigger`, `hardware_capture`, `common_capture`, or `controlled_intervention`), a witness reference, and a SHA-256 digest. Two or more anchors at distinct source coordinates are required.

The witness reference is a claim about where the correlation evidence can be inspected. Its digest is an integrity declaration only; this implementation does not retrieve, authenticate, or independently judge it. The caller must be able to defend the assertion that each source and target interval refers to the same physical event. Similarity-based event matching is not accepted as a calibration basis by this interface.

### Feasible-set model

The version-0.1 model assumes one positive affine relation over the declared validity range:

The v0.1 mapping assumes:

```
target = scale * source + offset
scale >= minimum_scale > 0
```

For every anchor, it requires:

```
target_lower <= scale * source_coordinate + offset <= target_upper
```

The implementation expresses these constraints as linear half-planes in the (scale, offset) plane, computes their feasible vertices, and retains the complete feasible region rather than choosing one best-fit line. The reported scale and offset bounds are projections of that region.

For a source coordinate inside the validity range, `map_source_interval()` evaluates `scale * source + offset` at every feasible vertex and returns the minimum and maximum target coordinates. This is a conservative feasible-set envelope. It is **not** a probability distribution, standard error, Bayesian posterior, or calibrated confidence interval.

`map_source_interval()` and `compare_cross_clock_intervals()` require the caller to repeat the calibration's source/target clock IDs and units. The request is rejected if a reading belongs to another clock segment or names a different unit; the calibration cannot be applied by matching a number alone.

`compare_cross_clock_intervals()` compares that mapped envelope to a target event's supplied interval:

- **before** only when every admissible mapped source coordinate is strictly earlier;
- **after** only when every admissible mapped source coordinate is strictly later;
- **overlap_unresolved** when the intervals overlap or even merely touch.

The comparison therefore yields a strict ordering only when every mapping allowed by the anchors agrees. It never chooses a convenient point estimate to force a timeline.

The calibration validity range must lie inside the observed anchor span. Version 0.1 refuses extrapolation outside that span. A non-affine or drifting clock may make the anchors infeasible; if they happen to fit within their uncertainty intervals, that demonstrates only consistency of this finite anchor set with the affine model, not that the model remains valid between or after the anchors.

### Reproduce

    python -m unittest discover -s bridges/temporal-provenance -p 'test_*.py' -v
    python bridges/temporal-provenance/clock_calibration.py --output results/clock-calibration-example.json

The synthetic example creates three shared-trigger anchor declarations. One source event maps strictly before a target interval; another overlaps its target interval and therefore remains unresolved. The artifact is a mathematical demonstration with synthetic witness references, not a physical calibration.

### Trust and semantic boundary

The calibration digest detects changes to the declared artifact. It does not authenticate the contributor, clock owner, trigger, witness artifact, or correlation event. The affine model and the uncertainty intervals are supplied assumptions. A production system should preserve original uncalibrated coordinates and record who/what admitted each anchor, the hardware or capture method, validity interval, calibration uncertainty semantics, and any drift or recalibration events.

A clock calibration can establish a bounded temporal relation under its assumptions. It cannot establish that one event caused another, that a controller's "accepted" or "completed" record means physical actuation, or that a sensor sample belongs to a particular command unless a separate correlation witness says so.

## Two-sided clock uncertainty (version 0.2)

The v0.1 calibration keeps a source reading exact and carries uncertainty on the target reading. Real captures can have uncertainty on both clocks. The opt-in v0.2 contract adds `build_interval_affine_calibration()`, `map_source_interval_bounds()`, and `compare_two_sided_cross_clock_intervals()` without changing or reinterpreting existing v0.1 artifacts.

Each v0.2 anchor carries two intervals:

- source clock: `[source_lower, source_upper]`;
- target clock: `[target_lower, target_upper]`.

The assertion is that the same declared correlation event is represented somewhere inside both intervals. The calibration assumes a positive affine mapping:

```
target = scale * source + offset
scale >= minimum_scale > 0
```

For each anchor, the mapped source interval must intersect the target interval. Because the scale is positive, this is equivalent to two linear constraints:

```
scale * source_lower + offset <= target_upper
scale * source_upper + offset >= target_lower
```

These become half-planes in the same two-dimensional scale/offset space. The builder intersects all of them, retains the full feasible vertex set, and refuses a calibration if there is no positive affine mapping satisfying every anchor. At least two source anchor intervals must be strictly separated so the feasible scale and offset remain bounded.

Query observations also carry source intervals. The mapper evaluates the lower source endpoint for the lower target bound and the upper source endpoint for the upper target bound across every feasible affine mapping. It rejects any query interval outside the declared anchor span. The clock ID and unit must match the calibration explicitly.

This is stronger than pretending one side of the synchronization capture is exact, but it remains an interval-consistency model. It does not assign probability to any point in the feasible set, prove the affine model is stationary, or validate the physical correlation claim. A wide source interval can legitimately make the result too broad to order an event; that uncertainty is retained rather than squeezed away.

### Reproduce the two-sided model

    python -m unittest discover -s bridges/temporal-provenance -p 'test_*.py' -v
    python bridges/temporal-provenance/clock_calibration_v2_demo.py --output results/clock-calibration-v2-example.json

The v0.2 tests cover exact point intervals (which collapse to the corresponding v0.1 style mapping), dual-sided uncertainty, interval intersection feasibility, non-monotone and non-affine rejection, source-clock/target-clock identity and unit checks, and unresolved results when mapped intervals overlap.

### Standards context

The [NTPv4 specification (RFC 5905)](https://www.rfc-editor.org/rfc/rfc5905.html) explicitly tracks clock dispersion and synchronization distance. Its synchronization-distance measure combines dispersion with half the round-trip delay to represent a maximum-error bound; dispersion also grows over time as clock-frequency tolerance accumulates. That is a useful standards precedent for treating time synchronization as an uncertainty-bearing estimate rather than an exact scalar. This bridge does not implement NTP, its peer-selection algorithm, or its synchronization-distance calculation. [RFC 5905](https://www.rfc-editor.org/rfc/rfc5905.html)

For the separate authenticity question, [Network Time Security (RFC 8915)](https://www.rfc-editor.org/rfc/rfc8915.html) specifies TLS-based key establishment and authenticated time-transfer packets for NTP. It illustrates that authenticated time-source identity is a distinct protocol obligation. The anchor witness references in this experiment are not NTS messages, are not authenticated by this code, and do not inherit NTS guarantees. [RFC 8915](https://www.rfc-editor.org/rfc/rfc8915.html)

## Boundaries and next experiments

- Clock IDs and actor IDs are labels; this format does not authenticate their owners.
- No calibration is inferred from event streams or similarity matches. The optional calibration artifact only evaluates explicit supplied anchors; it does not promote VGI-style correspondence into a causal edge or clock-synchronization witness.
- A VGI-style event correspondence can be added as a separate relation. It must not be treated as a causal edge or as a clock calibration unless a separate contract establishes that implication.
- The analyzer is pairwise (O(n^2)). It is intended for inspectable traces, not an unbounded event database.
- The vector-clock model assumes actor IDs are uniquely owned by one active writer. Split-brain actor identity invalidates its causal interpretation.
- Digests or encounter references do not authenticate a source, and this bridge does not fetch referenced artifacts.

The next useful experiment is to capture the same event stream through two E-CPU clock contexts, preserve the actual TemporalFrames, and verify that local durations remain endpoint-local while vector-clock stamps recover only message-mediated causal order.
