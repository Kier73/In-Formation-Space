# RE-002 — Active response discrimination and observer-relative reconstruction

**Status:** synthetic exact-rational experiment; 13 new regression tests (21 including RE-001) pass locally under Python 3.13.5. All observations are generated from declared finite candidate models. No E-CPU deployment, VGI runtime, physical sensor, externally trained neural model, network transport, or genuine evidence admission is exercised.

## Question

When two systems appear to share response modes, **which permitted intervention distinguishes their generating laws, and which remaining differences are unobservable under the current observer contract?**

This continues [RE-001](README.md), rather than claiming a universal response metric. It draws on:

- [VGI Builds 14–17](https://github.com/Kier73/Virtual-Ground-Interpreter/tree/main/theory_development): event-interval shape, observer-dependent frequency/phase representations, and invariance only under explicitly declared symmetries.
- [In-Formation-Space observation-equivalence](../../bridges/observation-equivalence/README.md): finite observation partitions and refinement by distinguishability.
- [In-Formation-Space Trial 08](../description-to-realization/trials/trial-08-intervention-aware-attention/README.md): active intention must distinguish a plan from intervention; RE-002 explicitly resets after every impulse and does not model persistent intervention effects.
- [In-Formation-Space evidence-gated observation path](../../bridges/observation-path/README.md) and [E-CPU gated observation](https://github.com/Kier73/E-CPU/blob/main/mailcpu/gated_observation.py): refusal is not a negative measurement. RE-002's authority gate is an **injected mock**, not an implementation of either runtime.
- [E-CPU operational semantics](https://github.com/Kier73/E-CPU/blob/main/docs/OPERATIONAL_SEMANTICS_AND_STATE_SPACE.md): distinguish a portable observable relation from a particular implementation and its admissible observation.

## Controlled test systems

All systems have exact state evolution `x[k+1]=A x[k]+B_p u[k]` and observation `y[k]=C_o x[k]`, evaluated from **zero state**. An impulse on port `p` produces `h_p[k]=C_o A^k B_p`.

There are five declared hypotheses:

| Hypothesis | Hidden dynamics | Primary response under port `u` | Primary response under port `v` |
| --- | --- | --- | --- |
| `baseline` | poles `1/2`, `1/4` | `(1/2)^k` | `(1/4)^k` |
| `alternate_third` | poles `1/2`, `1/3` | `(1/2)^k` | `(1/3)^k` |
| `alternate_three_quarters` | poles `1/2`, `3/4` | `(1/2)^k` | `(3/4)^k` |
| `hidden_extra_mode` | baseline plus `7/8` mode | `(1/2)^k` | `(1/4)^k` (mode is primary-invisible) |
| `coordinate_alias` | similarity transform of baseline | `(1/2)^k` | `(1/4)^k` |

The `baseline` and `coordinate_alias` differ internally but are related by an exact invertible state-coordinate change, so they realize **identical responses to all input sequences** under both declared readouts. The hidden extra mode is driven by port `v` but unseen by the primary observer. An optional `auxiliary` readout sees that extra mode only in the `hidden_extra_mode` candidate.

The values above are **real decays**, not physical sound frequencies in hertz.

## Active observation policy

The candidate set is finite and known to the planner. For each declared probe, it calculates exact predicted response vectors and partitions the remaining candidate names by equality. The deterministic selection heuristic first minimizes the largest resulting equivalence class, then maximizes the number of groups and prefers lower-cost probes. It is **not** a globally optimal decision tree and has no calibrated candidate probabilities.

Three probes are offered:

- `primary_u`: inexpensive impulse through the original port; all five candidates return the same response.
- `secondary_v`: impulse through a second allowed port; separates the two alternative second-mode laws, but leaves `{baseline, coordinate_alias, hidden_extra_mode}` together.
- `auxiliary_v`: a second sensor observes the `v` impulse. This requires an explicit `auxiliary_read` authorization; it separates the extra hidden mode from the two-coordinate-equivalent baselines.

**Outcome:** The policy chooses `secondary_v` first, splitting five models into classes of sizes **1, 1, and 3**. Under a simulated denied authorization, the next selected probe is recorded as `evidence_refused`; **no observation is fabricated, and the three candidates remain**. Under authorization, the same probe yields `{baseline, coordinate_alias}` if the true model is baseline, or uniquely selects the hidden-mode candidate if that is the declared truth.

The policy cannot distinguish `baseline` from `coordinate_alias` even after the auxiliary readout. This is correct under the declared projections. A singleton conclusion is only **within the finite supplied candidate set**; it is not proof that no other implementation exists.

## Reconstructable law

Adding the primary impulse responses from ports `u` and `v` yields:

`h[k] = (1/2)^k + (1/4)^k`.

The RE-001 exact-rational solver recovers the same two-mode recurrence:

`h[k+2] = (3/4) h[k+1] - (1/8) h[k]`.

With only port `u`, the second mode cannot be inferred from the returned response. This is a restricted **controllability/observability** example: probe selection determines which generating relationships can be reconstructed, assuming a declared system class and consistent reset/clock indexing.

## Observer and temporal comparison

A response-distance matrix is computed across three chosen input traces. Under a common nonzero affine sensor transform `y'=a*y+b`, all squared pairwise response distances are multiplied by `a²`; normalizing by a nonzero reference distance therefore recovers the same matrix. A nonlinear squaring observation provides a negative control and **does not** preserve the normalized geometry.

A second synthetic control applies independent positive affine clock maps to a known irregular event sequence. Normalized inter-event interval shapes match exactly **when matching event IDs are supplied**. Without paired event IDs, the tool returns `unresolved_unpaired_event_ids`; it does not claim correspondence or causality. This preserves the VGI/IFS distinction between timing similarity, inferred event correspondence, and actual E-CPU temporal/causal evidence.

## Results and interpretation

The [deterministic machine report](active_resonance_report.json) records all candidate partitions, both denied and admitted auxiliary-read paths, the exact recurrence, cross-observer RDM check, and clock-comparison results.

**Supported for this finite fixture:** active input selection reveals a second dynamical mode missed by a single input; adding an admitted observation projection can reveal a previously invisible driven mode; the coordinate-equivalent realizations remain indistinguishable; and sensor/clock invariances hold under their stated affine transformations.

**Not established:** semantic equivalence in arbitrary systems; passive spectral matching as a unique system identifier; event matching without provenance; physical sensor calibration; a real E-CPU authority decision or host execution; distributed reconstruction; optimal policy for general POMDPs; or performance with noise/nonlinear dynamics.

## Run

From repository root:

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/active_resonance.py > /tmp/RE002_report.json
```

The Python module imports `Plant` and the exact solver from RE-001 in this same folder; no third-party packages are required.

## Next discriminating question

How can multiple genuinely independent hosts coordinate **authorized, cost-aware active probes** when their clocks, observation availability, and candidate models differ, while retaining enough provenance to validate predicted equivalence against subsequent actual outcomes? A natural next bridge is to carry the RE-002 probe partitions through the existing IFS evidence-gated observation path and E-CPU TemporalFrame machinery, with injected counterexamples for refused observations, incomplete event correspondence, noisy measurements and interventions that change the underlying state.
