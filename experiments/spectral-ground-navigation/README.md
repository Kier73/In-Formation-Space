# SGN-001 — Witnessed spectral-ground navigation

**Status:** executable research experiment. Separate algebraic and empirical routes. 20 November 2026.

## Question

When can a scalar observation be replaced with a small, fixed-dimensional transition law, such that reaching a specified distant coordinate means evaluating a power of that law rather than replaying all intermediate states? More importantly, **who is entitled to admit that shortcut, for what observable and horizon?**

This examines the suggested path **audit → gauge/warp → lift → spectral constraint → exponentiate**, with a necessary sixth activity: **independent, chronological disconfirmation**. The framing was prompted by two user-provided prototypes, `weilfit.py` (genus-two point counts over F_5, four-term recurrence) and `rootq.py` (character cancellation and path-quadric histogram probes). No source code from these attachments is copied; the algebraic fixture is independently implemented using its six reported point-count traces. The reported 20 November 2026 Alpöge/Claude RH/GRH proof claim is a **research premise for analogy only**, not a verified dependency of this experiment. SGN-001 neither proves RH nor applies the claimed Lean theorem.

Existing nearby IFS work: [Guarded Shortcut Trade-off](../guarded-shortcut-tradeoff/README.md) studies exact affine modular recurrence costs; [Logistic Map Coverage](../logistic-map-coverage/README.md) studies finite observer coverage. SGN-001 contributes **admission criteria for an inferred spectral law** rather than another modular speed benchmark.

## Two different authority paths

**A. Exact arithmetic from a declared algebraic family.** Assume a genus-two reciprocal characteristic polynomial of a Frobenius trace,

\[P(T)=T^4-e_1T^3+e_2T^2-qe_1T+q^2.\]

`ExactWeilGround.admit(q,s1,s2,witnesses)` obtains \(e_1=s_1\), \(e_2=(s_1^2-s_2)/2\), then independently checks \(s_3,\dots,s_6\) against Newton identities and the linear recurrence. Failing witness or integrality checks **refuses the shortcut**. Passing tests is conditional on the **declared Frobenius polynomial family**, which is not established by a finite sample. The genus-two Weil root-radius fact is a mathematical premise for genuine smooth curves, not a license to impose unit-circle spectra on arbitrary streams. Matrix powering uses Python *integers* modulo an arbitrary modulus and counts actual 4×4 modular products. The example supplied by `weilfit.py` gives \((e_1,e_2,e_3,e_4)=(2,6,10,25)\), \(s_{10^6}\pmod{2^{61}-1}=1187996290252243319\), with **29** modular matrix products. The six ground-truth traces were originally obtained by brute-force finite-field counts in the supplied prototype, and have not been independently re-counted here.

**B. Learned finite-horizon spectral approximation.** `fit_spectral(times,values)` holds out training, *model-selection validation*, and a distinct *final test*. Candidate physical-time clocks are `t`, `log(t)`, `t^1.5`; amplitude gauges are `1`, `sqrt(t)`, and `exp(-0.02t)`. The supplied data is normalized, regridded uniformly in candidate clock using **linear interpolation**, embedded in a Hankel delay space, compressed with truncated SVD, and fit with projected DMD. A candidate matrix is compared **both unconstrained** and with eigenvalues projected onto the unit circle while retaining eigenvectors; no unwhitened raw Procrustes rotation is used. Unitary/symplectic structure is not assumed without a matching validation advantage. Selection uses raw physical-unit validation RMSE relative to the better of a constant-last-value and constant-mean baseline; small complexity penalties break near ties. `test_report()` evaluates a withheld later window without refitting or choosing the model from it.

A useful validation result grants only the ability to call `predict(k)` **inside the validation-step range**. A requested larger horizon raises `ValueError` unless `allow_unwitnessed=True` is explicitly chosen; even then it is a *hypothesis*, not guaranteed prediction. Models that fail validation refuse predictions by default. A hidden regime change demonstrates why retrospective test evidence may overturn a previously qualified approximation. Some real sequences could look good on both blocks and fail immediately afterwards. This experiment cannot certify long-run dynamics from finite samples.

## What the byte pre-audit actually means

`cancellation_hint` reports maximum nonzero additive-character mass on a min-max quantized histogram plus lag-difference analogues. It is a **diagnostic, never an admission proof**. Permuting samples preserves the histogram-character statistic while radically changing transition structure. Even sophisticated square-root cancellation does not mathematically prove that a stream has no short generative rule (a pseudorandom-looking stream may have a compact generator). The supplied `rootq.py` also contains a path-chain histogram probe: the present experiment **does not implement that probe**, and cannot claim parity with its outputs.

## Reproduce

From this directory (Python ≥3.10, NumPy):

```bash
python -m pip install numpy
OPENBLAS_NUM_THREADS=1 python -m unittest -v test_navigator
OPENBLAS_NUM_THREADS=1 python run_experiment.py > run.json
```

`run_experiment.py` prints deterministic fixtures, proposed operator/gauge and rank, validation error/selection status, independent test error, and SHA-256 of the input to model selection. Machine-dependent NumPy/LAPACK rounding may change the selected model at near-ties; no timing benchmark is claimed. `run.json` is generated, not a tracked source of truth.

## Discriminating controls and open work

- **Algebraic negative control:** \(3^n+2^n\) does **not** satisfy the forced reciprocal Weil template; witness check rejects it.
- **Nonalgebraic controls:** logistic-map orbit \(x\mapsto4x(1-x)\) and seeded Gaussian noise lose to trivial forecast baselines on the validation window; no impossibility theorem follows.
- **Regime change:** an oscillator changing frequency *after validation* passes model selection then fails untouched test.
- **Dissipative case:** an exponentially decaying oscillator is admitted with *unconstrained* eigenvalues; forcing the critical circle is not universally legitimate.
- **Gauge warp:** chirp and logarithmically clocked oscillation recover strongly predictive stationary coordinates on finite windows. Warped interpolation introduces its own error and nonuniform effective sample density.
- **Future:** condition-number/phase-horizon uncertainty, exact spectral interval bounds, independent observation sources, irregular-sampling models without interpolation, dynamic switching, transient subspaces, model-size/MDL comparison, and integration with E-CPU/VGI evidence authority.

A finite-dimensional matrix always describes finitely many exponential-polynomial terms, but inability to fit one **cannot** be inferred from a cancellation test, a particular rank budget or a failed validation horizon. All results are observer- and task-relative.