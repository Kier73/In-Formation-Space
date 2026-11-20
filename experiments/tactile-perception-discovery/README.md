# TPP-002 — Tactile perception through blind transducer identification

**Question:** Can an observer extract a useful input/output relation by interacting with a system without being told its hidden coordinates, then test whether that relation survives translation to a different expression?

## Relationship to existing experiments

This continues [TPP-001](../tactile-perception-process/README.md), the [observation-equivalence bridge](../../bridges/observation-equivalence/README.md), and [RE-004 intervention ambiguity](../response-equivalence/RE004_README.md). It is not a replacement for those implementations.

TPP-001 supplied the equations used to compare four simulated ports. Here, the learner gets *observations* through independent OS subprocesses that respond to the existing canonical text/JSON drive and idle instructions. The exact-rational plant parameters are accessible to the test author in `discovery.py`, but the **learning algorithm never reads the fixture table**. It identifies composite input/output coefficients through the sensor's replies. This is an experiment in structural identifiability, not secure concealment from the code reader.

## Declared process

Each of six *synthetic* plants obeys, except for one deliberately nonlinear negative control:

```
x[t+1] = x[t] + a*u[t] + b*h[t]
h[t+1] = rho*h[t] + c*u[t]
y[t]   = g*x[t] + o
```

Here `x` is a modeled position, `h` an unobserved internal coordinate, and `y` the **uncalibrated raw sensor**. The nonlinear counterexample adds `u[t]^2` to the first equation. Every experiment starts from `x=h=0`. These are *given model-class assumptions*, not laws discovered from nature. The plant labels `electrical` and `hydraulic` refer to different synthetic expressions, **not measured electromechanical or fluid systems**.

The observer can infer a composite response law without knowing `g`, `a`, `b`, or `c`:

```
delta_y[t] = A*u[t] + z[t]
z[t+1]     = rho*z[t] + B*u[t]

A = g*a,  B = g*b*c,  z[t] = g*b*h[t]
```

When `A != 0`, the dimensionless ratio `B/A = (b*c)/a` is invariant under multiplicative changes of sensor gain `g`; `rho` is likewise gain-invariant **when the memory effect is observable**. Neither the separate factors of `b` and `c` nor hidden coordinate identity can be recovered from this port.

With a known reset and exactly four readings—initial, half-drive, idle, idle—the learner identifies `A`, `B`, and potentially `rho`. If `B=0`, `rho` is recorded as **unidentified**, never asserted to be zero.

## Observed output of the controlled experiment

| Experiment | Training observations | Held-out result |
| --- | ---: | --- |
| Electrical origin | 4 | Raw recurrence: `A=7`, `B=7/2`, `rho=1/2` |
| Hydraulic transfer | 2 target readings | Predicted six new steps exactly with `B/A=1/2`, `rho=1/2` |
| Slow-decay transfer | 2 target readings | Failed at the third step (second idle), despite identical first two predictions |
| Correction after disagreement | 2 additional target readings | Recovered `rho=3/4`, predicted six new steps exactly |
| Nonlinear negative control | 4 | Failed on the **first** held-out quarter-drive |
| Hidden-coordinate alias | 4 | Same available input/output law, despite different internal factors |
| Memoryless output | 4 | `B=0`; the hidden decay remains **unknown** |

The held-out sequence is quarter-drive, idle, idle, three-quarter-drive, one-third-drive, idle. Exact rationals are used throughout. Passing one test sequence is evidence for that sequence, not proof of all possible future actions. The experiment itself is deterministic, with no randomized test distribution.

### Expression does not imply physical identity

Two processes can preserve the same relationship at the chosen observational port while having different latent parameters. Conversely, a process that agrees on the immediate output can be distinguished by a later action. The transfer remains a *hypothesis* until independently challenged, and the failed prediction is kept as evidence alongside the corrected model.

The process uses **real local subprocesses and input/output pipes**; the returned observations are computed by stipulated mathematical fixtures. Nothing in this experiment measures a physical actuator, pressure, current, position, or thermodynamic expenditure.

Receipts contain per-request digests, ordered parent hashes, scope and refusal states. Hash consistency is not source authentication: a fabricated record can be rehashed without detection. A refused reading cannot support inference of zero.

## Reproduce

No additional Python packages are required. From the repository root:

```bash
python -m unittest discover -s experiments/tactile-perception-discovery -p "test_*.py" -v
python experiments/tactile-perception-discovery/discovery.py
```

The dedicated GitHub Actions workflow tests Python 3.11 and 3.13 on Linux and Windows, and publishes the deterministic subprocess-produced JSON report as a workflow artifact. The report is not a hardware receipt.

## Unresolved question

What is the **least** action-and-observation set needed to discover a transferable relationship under unknown sensor offset, gain, action scaling, internal memory and drift? This experiment assumes resettable plants and a fixed order-1 latent recurrence, so it does not yet address unknown model order, noise, uncertain timestamps, operating-range drift, signed physical observations, or real energy-flow equivalence. Those are useful next discriminating experiments, not claims already established.
