# TPP-001 — Tactile perception process: cross-medium expression

**Question.** Which observable relationships survive translations between bytes,
electrical/hydraulic port quantities, mechanical motion and sensor encodings?
Which relationships fail when the observer changes the question or performs a
new intervention?

This is an experiment, not a new universal grammar. Its name describes the
process being studied: tactile interaction, observation, translation and
continuation.

## Relation to existing work

- [Observation equivalence](../../bridges/observation-equivalence/README.md)
  already distinguishes current-output agreement from transition congruence.
- [RE-004](../response-equivalence/RE004_README.md) already demonstrates why
  effect attribution can remain ambiguous after an apparent match.
- [Trial 08](../description-to-realization/trials/trial-08-intervention-aware-attention/README.md)
  explores observations that alter the states being examined.

TPP-001 does **not** replace those abstractions. It adds explicit
effort-flow expressions, wire-to-action interpretation, calibrated sensor
readouts, independently reconstructed accounting, and shortest finite
distinguishing continuations within a tiny declared cross-medium model.

## Executable process

Four declared *synthetic* mechanisms move a one-dimensional load against
a fixed force of 4 N. Each action lasts one model second. For a fractional
drive command `u` in [0,1], the ideal electrical and hydraulic routes move
the load by `u` metres with `4u` joules of mechanical work.

| Route | Effort | Flow during drive | Input J | Physical distinction |
| --- | --- | --- | --- | --- |
| electrical | 12 V | `u/3` A | `4u` | ideal electrical-to-mechanical port |
| hydraulic | 8 Pa | `u/2` m³/s | `4u` | ideal pressure-to-mechanical port |
| resistive | 15 V | `u/3` A | `5u` | `u` J heat per drive |
| inertial | 18 V | `u/3` A | `6u` | stores `2u` J, released on idle |

These are **stipulated idealized equations**, not a measured motor, fluid
circuit or inertial mechanism. Pressures, cross sections, constraints,
stability, and real material loss models are not established by the fixture.
The one-second energy balance is checked exactly:

```
input_energy = mechanical_work + heat + delta_stored_energy
```

On an idle interval, the inertial route spends its stored energy moving
the load; the other routes do not. Every route uses a different affine
sensor calibration, so raw values are not comparable as lengths without
the declared calibration. The input action crosses either a canonical
text or a canonical JSON wire encoding.

## Observed finite probes

Run `tactile_process.py` for the complete deterministic record
retained in [results.json](results.json).

- Electrical and hydraulic routes yield **the same calibrated position**
  sequence `[1/2, 1/2, 3/4]` despite different raw sensor values.
- After a single `drive 1/2`, electrical and inertial routes both
  show position `1/2`. The shortest supplied position-only probe that
  distinguishes them is `drive 1/2; idle`: inertial reads `3/4`,
  electrical stays at `1/2`.
- A permitted energy-input observation distinguishes the same two routes
  on the first drive (`2` J versus `3` J).
- Resistive and electrical routes remain indistinguishable by position
  in all 14 tested action sequences of depth <= 3, but an energy
  observation immediately distinguishes them (`5/2` J vs `2` J).
- Electrical and hydraulic routes are **undetermined** after those
  14 finite probes, not asserted physically identical or universally
  equivalent. Model formulas can be inspected separately.

The bounded breadth-first search returns a shortest witness when it finds
one; exhausting its declared alphabet and horizon returns *undetermined*.
An independent exhaustive tiny-sequence oracle checks the first witness
depth in the tests.

## Independent reconstruction and evidence

`tactile_process.py` emits event records containing canonical input bytes,
per-step power and energy quantities, raw and calibrated observations,
modeled stored state, previous-event digests and a report head digest.

`independent_check.py` does not import the producer. It independently
parses the bytes, replays the declared equations, reconstructs sensor
calibrations, and validates each event and the hash chain. Tampering with
a reported reading, heat or stored energy **is refused even when all later
hashes are recomputed**.

This is *internal synthetic consistency*, not authenticated environmental
evidence. SHA-256 digests do not identify an observer or prove that an
external device actually moved. The model's calibrated readings are
simulated values, not empirical sensor measurements. Interventions are
authorized by the local fixture only. Public GitHub transport and OS-local
socket bytes are real interaction media, but neither establishes the
fixture's physical claims.

## Reproduce

From the repository root, with Python 3.11+ and no extra packages:

```bash
python -m unittest discover -s experiments/tactile-perception-process -p 'test_*.py' -v
python experiments/tactile-perception-process/tactile_process.py
```

The nine test methods cover the exact-rational energy balances over four
routes and two encodings, socketpair loopback transfer of actual command
bytes, independent reconstruction, a shortest-probe oracle, change of
observation contract, missing evidence, and rehashed adversarial records.

The initial development run used Python 3.13.5 in a local Linux container:
**9/9 tests passed**. The test runner includes a separate CI workflow on
Linux and Windows Python 3.11/3.13; its results are distinct evidence and
should be checked in GitHub Actions after a PR runs.

## Next physical connection

A practical next experiment would receive independently sourced observations
from a real actuator, calibrated current/pressure/position instruments, and
an explicit intervention authorization. Add source identity, clock and unit
uncertainty, independent calibration references, and a measured energy
budget. Keep missing or refused sensor values as *unknown*, not zero.
Test whether a model learned from one medium predicts a held-out physical
conversion without being supplied its complete transducer law.

**Hypothesis to investigate:** an observer-relative relation between controlled
perturbation and distinguishable response may survive some changes of medium.
**Not yet established:** that a universal invariant exists, that these
idealized transducer laws describe real machinery, or that a finite test
certifies unrestricted future behavior.
