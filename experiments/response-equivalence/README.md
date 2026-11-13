# RE-001 — Response equivalence is not generator identity

**Status:** reproducible, exact-rational synthetic experiment; eight local tests passed on Python 3.13.5. No external model, network, physical sensor, or deployment was used.

**Question:** when different representations exhibit the same response geometry, what part of the underlying generator can the observer reconstruct?

## Lineage

- [VGI Builds 07–19](https://github.com/Kier73/Virtual-Ground-Interpreter/tree/main/theory_development): response dissimilarity matrices, temporal/graph harmonics, observer quotients, and cases where shared similarity does not generalize.
- [IFS observation-equivalence](https://github.com/Kier73/In-Formation-Space/tree/main/bridges/observation-equivalence): current/future observational equivalence and quotienting by distinguishability.
- [IFS external-neural spectral study](https://github.com/Kier73/In-Formation-Space/tree/main/experiments/external_neural_structure_reading): singular spectra as representation descriptions, not functional identity.
- [E-CPU operational semantics](https://github.com/Kier73/E-CPU/blob/main/docs/OPERATIONAL_SEMANTICS_AND_STATE_SPACE.md): portable operation relation, concrete Ground/context, and declared observation contract.

## Model and experiment

A rational, zero-initial-state, discrete-time linear system has `x[t+1]=A x[t]+B u[t]` and `y[t]=C x[t]`. Its observable impulse sequence is `h[k]=C A^k B`. Different input sequences produce outputs by convolution with `h`.

The fixture begins with `A=diag(1/2,1/4)`, `B=(1,1)`, `C=(1,1)`, so:

`h[k] = (1/2)^k + (1/4)^k`.

Four alternatives test **different mechanisms**, not random proximity:

1. **Coordinate change:** an invertible similarity transform changes every state-space coordinate while preserving every zero-state input/output response.
2. **Hidden mode:** add an independently evolving mode with eigenvalue `7/8`, driven but never read out by `C`. Its response is *exactly indistinguishable* under the declared readout, although the realization is larger. A newly authorized sensor of that coordinate changes what is observable.
3. **Same modes, different readout:** leave `A` and `B` unchanged but use `C=(1,-1)`. Equal modal eigenvalues are insufficient for response equivalence.
4. **Delayed impostor:** add a length-seven shift chain whose first additional impulse coefficient occurs at `k=6`. All first six observations match; the seventh distinguishes the systems. Finite prefix equality is not global equivalence.

Five probe inputs produce ten pairwise squared response distances. An affine sensor transform `y' = 3y+2` multiplies these distances by `9`, so the normalized distance geometry is unchanged. This is a known calibration symmetry, not evidence that arbitrary nonlinear observer maps preserve geometry.

## Results

- Observed response recurrence, reconstructed from four rational impulse samples: `h[k+2] = (3/4) h[k+1] - (1/8) h[k]`.
- Exact 3×3 Hankel rank: `2` for both the two-state baseline and the three-state hidden-mode realization.
- Delayed system: exact 9×9 Hankel rank `9`, but its first six response coefficients match the baseline.
- The first response discrepancy for the same-poles/different-readout realization occurs at index `0`; the delayed realization at index `6`.
- 8/8 `unittest` checks passed. See `report.json` for machine-readable values.

## Interpretation

This identifies the minimal *observable* dynamical law for the selected system class; it does not identify a unique concrete internal implementation. The response signature induces an observer-relative equivalence class. For this fixture, the two modal roots are `1/2` and `1/4` (decaying real modes, not sinusoidal tones in hertz). An invisible mode may exist outside the observable quotient.

This is a controlled example of established system-identification and realization-theory principles, not a claim of a new universal semantic metric or a novel theorem. Tests are examples and regression checks; universal statements for these specific models rely on their stated algebraic construction. If the model class, time horizon, precision, sensor, allowable input family or reset assumptions change, the inference must be reconsidered.

**Next discriminator:** introduce independent observer transforms and real sensor noise, then evaluate whether active probing adds recoverable structure beyond static frequency/spectrum summaries while keeping causal correspondence, authority and observation admission separate.

## Reproduce

From this folder with Python 3.11+ (no third-party dependencies):

```bash
python -m unittest discover -v
python resonance_equivalence.py
```

No GitHub writes, external downloads, or physical measurements are required.

## Background

- [Minimal state-space realization](https://doi.org/10.1016/S0377-0427(00)00341-1): minimal realizations and change-of-basis equivalence.
- [MIT Signals, Systems and Inference, chapter 5](https://ocw.mit.edu/courses/6-011-introduction-to-communication-control-and-signal-processing-spring-2010/59a39b083dc3501a8e757bd16e46d6bc_MIT6_011S10_chap05.pdf): observability, hidden modes and transfer behavior.
- [Persistence of excitation](https://doi.org/10.1016/j.sysconle.2004.09.003): informative data needed for reconstruction.
