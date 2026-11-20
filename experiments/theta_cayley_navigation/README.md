# TCN-001 — Theta–Cayley Navigation: discovering a quadratic coordinate

**Status:** executable finite-field research experiment, 20 November 2026. Companion to [SGN-001](../spectral-ground-navigation/README.md), without changing its original tests or mathematical claims.

## The question

Can noisy, partial observations reveal a *change of representation* that turns a nonlinear-looking sequence into a unitary fixed transition, permits goal-directed inverse navigation, and carries evidence that says when **not** to claim the model describes the underlying system?

The exploration is inspired by the mathematical intuitions shared in the 20 November 2026 conversation, which mentioned a claimed Lean proof of RH/GRH and Stepanov/theta-chain arguments. **This experiment neither verifies nor imports the claimed proof**, and no result below depends on its validity. The transformation here is a classical quadratic-character matched filter, not a newly proved theta-lift theorem or a general optimizer.

## Mathematical construction: known family, unknown coefficients

Work over the odd prime field F_p. The observer receives complex measurements of a hypothesized hidden law, restricted to distinct indices in [0,p):

    psi(x) = exp(2*pi*i*(a*x*x+b*x+c)/p).

**Discovery.** For each possible quadratic coefficient `a'`, dechirp the observed coordinates by `exp(-2*pi*i*a'*x*x/p)`. Zero-pad unobserved samples; FFT the result over additive linear characters `b'`. The maximal modulus over **all p² pairs** estimates `a,b`. Quantize the phase of the matched sum to recover `c` as a pth-root candidate. This is a quadratic Fourier matching method. It costs p FFTs of length p, **O(p² log p)** per scan, not O(log p), and uses all supplied training observations. Noise can cause the discrete coefficients to be fitted incorrectly.

**Evidence.** The fit sees the training block only. A separate validation block tests complex phasor RMSE against a constant-phase baseline. Each permutation-null trial shuffles the training phase/index association and scans the *entire* p² family again, calibrating the look-elsewhere effect. These p-values are empirical and conditional on exchangeability. Qualification requires coherence, permutation significance, absolute validation error, and improvement over the baseline. Null probes do **not** prove incompressibility. A constant stream has perfect matching coherence but is not significant under a permutation test because shuffling it changes nothing; refusal means *not admitted by this policy*, not random.

**Cayley navigation.** Once `a` is known (as a model), the dechirped state

    z(x) = exp(-2*pi*i*a*x*x/p)*psi(x) = exp(2*pi*i*(b*x+c)/p)

satisfies `z(x+1)=U*z(x)` with `U=exp(2*pi*i*b/p)`. Let `S=(1-U)/(1+U)`; this scalar `S` is purely imaginary (skew-Hermitian), and `U=(1-S)/(1+S)` is exactly unitary in real arithmetic. For odd p, `U != -1`, so the Cayley transform exists. The implementation computes powers by repeated squaring with the exponent reduced mod p. Afterward it reapplies the chirp to obtain the requested model phase. Integer modular coordinate arithmetic avoids multiplying a floating angle by a huge time; floating roundoff remains possible. **O(log p) products after model discovery** does not mean O(log p) to learn the model, or certify a new physical observation.

**Goal addressing.** For a target relative phase `exp(2*pi*i*h/p)` (relative to fitted `c`), find candidates by solving

    a*x² + b*x = h (mod p).

A modular square-root algorithm (Tonelli–Shanks) handles odd prime p. The result is zero, one, two, or—in a constant degenerate law—every coordinate. These are exact solutions of **the fitted polynomial**, not independently verified target encounters. The fitted model is periodic mod p, so far-away coordinates are aliases, not new high-dimensional states.

## Falsification and controls

`test_theta_cayley.py` checks coefficient recovery from noisy partial observations; ordinary-FFT mismatch on a chirp; skew-Hermitian Cayley and unit modulus; huge-index navigation compared with independent direct *model* evaluation; exact target-coordinate inversion over every residue; modular square roots for primes p=5,13,17,41,127; linear-mode positive control; random-phase refusal; validation and final-test regime changes; a constant-stream permutation-null limitation; validation/train isolation; train/test overlap protection; malformed inputs; and a much cheaper **three-sample** algebraic baseline.

The **three-point baseline** is important: in the noiseless quadratic-root family, phases at x=0,1,2 already determine `(a,b,c)` by modular finite differences. The matched-filter scan is *not* an advance over that baseline there. Under noisy phase samples, naive quantization of three observations can fail while a globally coherent fit to many samples succeeds. That is a robustness-versus-cost trade, not a general quantum, metaplectic, or derivative-free optimization speedup.

An independent final block is never consulted during admission. A maliciously or naturally changing physical sequence can pass training+validation and then fail there. The test report states that failure; its earlier qualification cannot be promoted into a universal guarantee. `predict` and `navigate_cayley` refuse unwitnessed indices by default; explicit `allow_unwitnessed=True` is labeled a hypothesis.

## Reproduce

Requires Python >=3.10 and NumPy (no SciPy):

```bash
python -m pip install numpy
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/theta_cayley_navigation -p 'test_*.py' -v
OPENBLAS_NUM_THREADS=1 python experiments/theta_cayley_navigation/run_experiment.py > run.json
```

`run_experiment.py` emits deterministic evidence: fitted coefficients; exact matched-score and plain FFT comparisons; null-test significance; separate validation/test errors; large modular index and product count; inverse target coordinates; a shifted-test negative control; and the three-point baseline. The output is diagnostic, not an attached attestation from an independent host or a proof of RH.

## What a later contributor can extend

1. **Iterated transfers:** actually implement powers of `D_f F` and compare to this one-shot matched filter on *held-out objective families*. A norm-preserving transfer alone cannot guarantee a minimum-amplifying readout; evaluate conditional performance against classical FFT, enumeration, and a low-query algebraic solver. Squaring a dense transfer may negate any claimed operation savings.
2. **Multivariate quadratic forms:** recover a Hessian `A` over F_p^d with bounded observations, test chirp transformations under changes of basis, and account for the p^d representation cost and query selection.
3. **Observer/host integration:** produce immutable signed observation/transform/recovery receipts compatible with the E-CPU Ground authority and VGI's witness scope. A conditional synthetic polynomial witness is not yet that protocol.
4. **Spectral precision:** compare high-precision and modular-coordinate navigation; detect coefficient ambiguity and phase-estimation horizon under additive measurement noise.

### Attribution and intellectual context

Uses a new implementation from scratch of elementary Gauss-chirp matching, finite-field polynomial congruences, FFT, and Cayley parametrization. Adjacent repository work is [SGN-001](../spectral-ground-navigation/README.md), [Guarded Shortcut Trade-off](../guarded-shortcut-tradeoff/README.md), and [Logistic Map Coverage](../logistic-map-coverage/README.md). The resemblance to phase-separation/mixing optimization circuits (such as QAOA) is conceptual; we do not claim a quantum algorithm or quantum speedup. Source inspiration: user-shared exploratory notes dated 2026-11-20, not a reviewed research paper.

## Additional gauge-uncertainty experiment (finite seeds)

Run `OPENBLAS_NUM_THREADS=1 python experiments/theta_cayley_navigation/robustness_sweep.py` for 8 deterministic seeds at five additive complex noise levels. The recovered `(a,b)` pair and the rounded global offset `c` have different robustness. On the recorded local NumPy run:

| Complex noise sigma | Qualified / 8 | (a,b) exact / 8 | c exact / 8 | Final test corroborated / 8 |
| --- | ---: | ---: | ---: | ---: |
| 0 | 8 | 8 | 8 | 8 |
| 0.17 | 8 | 8 | 7 | 8 |
| 0.45 | 8 | 8 | 3 | 8 |
| 0.8 | 0 | 8 | 1 | 0 |
| 1.5 | 0 | 8 | 2 | 0 |

These are small, finite, in-family seeded synthetic trials, **not** statistical coverage guarantees. The meaningful finding: a phase coherence test and held-out RMSE can accept an approximate state model whose **absolute phase residue is wrong**. `goal_coordinates(h)` deliberately solves for *relative* phase h with respect to fitted c, so its roots depend only on `a,b`. An absolute-phase goal would require extra calibration/uncertainty accounting, and is not provided. The test suite explicitly rotates all observed phases by a common gauge angle and verifies that relative goal coordinates stay fixed while c shifts. At sigma 0.8 or higher, the regression policy refuses the model even when its inferred a,b happen to be correct, because quality is not witnessed strongly enough.
