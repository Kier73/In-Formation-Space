# TCN-003 — An exact Gauss-cocycle for phase-aware long-distance transfer

**Status:** experimental implementation of established finite-field quadratic Gauss-sum/Weil representation mathematics, 20 November 2026. This is a direct continuation of [TCN-002](README.md), with the **missing central phase now explicitly retained**. It neither uses nor claims validation of the reported RH/GRH proof.

## Motivation

TCN-002 compacted any periodically scheduled chain of quadratic chirp–Fourier operators into a 2×2 symplectic matrix. That matrix determined a *projective* state: support, probabilities and relative phases. It **discarded global complex phase**. For one observation, global phase may be irrelevant. For a superposition of two different sources or computational pathways, discarded global phases alter interference, so adding projective rays would be mathematically incorrect.

TCN-003 resolves this for the declared family by discovering a small central extension whose scalar factors are **exactly fourth roots of unity**. The resulting operator can produce the **complete complex amplitude** of a basis-to-basis transition using an exact integer exponent modulo p, an exact exponent modulo 4, and a normalization flag. It also applies a long chain to **arbitrary supplied complex input vectors** without replaying each intermediate step.

## Fixed conventions and kernel

Work over the odd prime field F_p and write \(\omega=\exp(2\pi i/p)\). The positive-sign normalized Fourier operator and quadratic chirp remain

\[
(Fv)_y = p^{-1/2}\sum_x\omega^{xy}v_x,
\qquad (D_a v)_y=\omega^{ay^2}v_y.
\]

Their associated symplectic matrix is \(M_a=\begin{pmatrix}0&-1\\1&-2a\end{pmatrix}\), as in TCN-002. For a general \(M=\begin{pmatrix}A&B\\C&D\end{pmatrix}\in SL(2,F_p)\), choose the following **canonical** kernel:

If \(B\ne0\),

\[
K_M(y,x) = p^{-1/2}\;\omega^{(D y^2-2xy+A x^2)(2B)^{-1}}.
\]

If \(B=0\),

\[
K_M(y,x) = \mathbf 1_{y=Ax}\,\omega^{C y^2(2A)^{-1}}.
\]

All inverses above are in F_p, not floating-point division. The kernel convention gives \(K_J=F\) and \(K_{M_a}=D_aF\) without extra phases, but is only **projectively multiplicative**.

## Exact finite-field cocycle

Let \(M,N\in SL(2,F_p)\), \(b=M_{01}\), \(f=N_{01}\), \(B=(MN)_{01}\). When \(b,f,B\ne0\), the (0,0) entry of \(K_MK_N\) is a quadratic Gauss sum:

\[
\frac1p\sum_z\omega^{(B/(2bf))z^2}
= p^{-1/2}\,\chi\big(B/(2bf)\big)\,\epsilon_p,
\]

where \(\chi\) is the Legendre symbol and \(\epsilon_p=1\) for p congruent to 1 mod 4, or \(i\) for p congruent to 3 mod 4. The (0,0) entry of \(K_{MN}\) is \(1/\sqrt p\), so

\[
K_M K_N=\tau(M,N)K_{MN},\qquad
\tau(M,N)=\epsilon_p\chi(B/(2bf))\in\{\pm1,\pm i\}.
\]

When any of \(b,f,B\) is zero, the elementary delta/Gauss-sum calculation gives \(\tau(M,N)=1\). Symplectic covariance means the ratio computed at (0,0) is the **same scalar everywhere**, rather than being a coincidence at one matrix element. Direct numerical checks of independently constructed p×p matrices confirm the composition equation at random products over p=3,5,7,11,13,17,31.

Thus a transfer can be represented as \((M,q)\), meaning \(U=i^q K_M\), with exact composition

\[
(M,q)\star(N,r)=(MN,\;q+r+\operatorname{cocycle}(M,N)\pmod4).
\]

This is a closed, associative operator representation. Repeated squaring over these pairs costs \(O(L+\log n)\) 2×2 modular products for a periodic schedule of length L, and tracks **absolute phase**, unlike a symplectic-only power. The coefficient-level output remains normalized by 1 or 1/√p.

## Exact high-time amplitudes and arbitrary inputs

`ExactSchedule.navigate(n)` returns the full pair `(M, quadrant)` for a declared periodic quadratic schedule. `basis_amplitude(x,y)` returns a symbolic description:

- exact zero or nonzero support;
- phase \(i^q\omega^r\), with \(q\in Z_4\), \(r\in F_p\);
- magnitude 1 (permutation case) or 1/√p (general case).

Only `ExactAmplitude.complex_value()` evaluates a transcendental complex exponential for display. No floating-point spectral fitting, eigenvalue projection, or heuristic phase rounding is used to obtain the integer residues.

For an **arbitrary supplied** complex vector \(v\in\mathbb C^p\), the exact kernel gives

\[
(U_nv)_y = \sum_x \big(i^{q_n}K_{M_n}(y,x)\big)v_x.
\]

`apply_coordinate` evaluates **one** requested output in O(p) numerical operations after the O(log n) operator composition (or O(1) for a permutation). `apply_full` materializes all p outputs in O(p²) through this reference implementation. A more sophisticated FFT-based kernel application could reduce that full-output cost, and direct FFT may beat the current implementation for large p or short horizons. The input vector is **not compressed**; the method is an analytic operator shortcut for this specific family, not a universal state compressor.

The general input is processed by ordinary finite sums and complex arithmetic. Hence the *operator* and its basis kernels are exact finite-field symbolic objects, but arbitrary-complex-input output values are numerical approximations. The reported errors refer to comparison against independent repeated complex FFTs.

## Forward and inverse temporal navigation

The central extension has at most four times the period of the underlying symplectic operator. `full_period_bound()` computes an exact finite period using the order of the symplectic cycle plus the residual central quadrant. `find_exact_operator_coordinate` uses baby-step giant-step in the extended group to identify the **earliest full unitary** operator match. Its inverse search is not O(log n): it costs O(L√o) group products and O(√o) memory for extended cycle order o, plus order factoring.

The distinction is visible in the concrete p=101, period-three schedule (7,13,29):

| Step | Symplectic matrix | Scalar quadrant |
| --- | --- | ---: |
| 25 | ((19,67),(59,38)) | 2 (−1) |
| 178 | ((19,67),(59,38)) | 0 (+1) |
| 331 | ((19,67),(59,38)) | 2 (−1) |

Projectively these operators agree at all three steps, but the amplitude at steps 25 and 178 differs by a **minus sign**. The symplectic period bound is 153; the full unitary period bound is 306. In this example, n=10^100+123 also maps to the **full** operator at step 25, including its global phase.

## Adversarial evidence and reproduced measurements

From the repository root:

```bash
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/quadratic_transfer_grounds -p 'test_*.py' -v
OPENBLAS_NUM_THREADS=1 python experiments/quadratic_transfer_grounds/run_cocycle.py > tcn003-local.json
```

The extended local suite has **33 passing tests** (including the original 21). New tests cover direct *absolute* amplitudes across prime classes 1 and 3 mod 4; random noncommuting canonical-kernel compositions; algebraic operator inverses; phase-sensitive distinction of projective aliases; 101-digit exact phase residues; inverse full-unitary time coordinates; arbitrary dense complex inputs; cubic/nonquadratic inputs; exact 0/1/1/p probability; tampered-receipt recomputation; and malformed contracts. A deterministic CI matrix covers Python 3.11–3.13.

Illustrative measured local run (one host, three repetitions; do not transfer timing numbers to another machine or include discovery effort):

| Fixture | Outcome |
| --- | --- |
| n=10^100+123, p=101, schedule (7,13,29) | 491 modular products; full operator matrix ((19,67),(59,38)); central phase quadrant 2 |
| Exact single amplitude from x=33 to y=3 | \(-\omega^7/\sqrt{101}\), with exact integer phase residues (2,7) |
| Earliest identical **full** operator | Step 25; extended period bound 306 |
| p=127, **arbitrary** random normalized complex input, 4,096 steps | 20 modular products; max full-output difference vs repeated dense FFT ≈1.15e−13, one-coordinate difference ≈1.63e−14 |
| Single-host timing in preceding row | Direct 4,096 FFTs ≈103.8 ms median; build compact operator ≈0.165 ms; one target amplitude ≈0.039 ms; all 127 outputs ≈2.43 ms |
| p=31 **cubic-phase input**, 77 steps | full-output max difference ≈5.03e−15; all 31 input values retained |

The 101-digit query is a **mathematical recurrence** in a finite algebra, not observation of a process that physically evolved for that many steps. The reverse coordinate is an exact operator alias, not an occurrence time for an arbitrary goal in an external system.

## Reproducible receipts and authority mapping

`ExactSchedule.receipt(n,source,target)` binds the mathematical schedule, exact full operator, symbolic scalar amplitude, arithmetic counts, and a decimal index into canonical JSON plus SHA-256. `verify_receipt` independently recomputes all stated fields. Rehashing an altered scalar phase does not make an incorrect operator accepted. This is **consistency checking, not cryptographic authentication, external observation, authorization, or proof that a foreign host executed a state transition**.

Cross-project design relevance:

- E-CPU's `mailcpu/navigation_admission.py` governs authorized navigation. This module supplies a *candidate mathematical description*, not an execution grant.
- E-CPU's `mailcpu/law_certifier.py` distinguishes witnessed law / prefix / tape. This module assumes a schedule rather than proving it from an observed exterior.
- VGI's evidence-to-Ground discipline requires independent source links and explicit unknowns. Exact Gauss identities are mathematical assumptions; schedule correspondence needs separate witnesses.
- TCN-001's noisy partial-observation phase estimator can discover a *candidate* quadratic representation. To claim absolute phases from a fitted model, its global offset needs an independently calibrated phase witness. `bridge.py` deliberately carries only relative phase until such evidence exists.

## What to build next

For **nonquadratic transitions**, the operator itself leaves this finite Clifford family. The exact cocycle now makes it possible to combine multiple quadratic rays without incorrectly discarding their relative phases, but a sparse expansion may still grow to p modes or larger tensor ranks. The next investigation is to measure that expansion and its guard cost under cubic, piecewise, and adversarial phase oracles. This should compare against direct FFT and short algebraic solvers; no optimizer or physical-computation speedup may be claimed solely from a norm-preserving unitary.

## Provenance

Code in `cocycle.py` is newly written, using standard elementary finite-field Gauss-sum identities and a canonical quadratic kernel. Original independent reference tests use NumPy FFT and dense matrix products. General background: [qudit Clifford and Weil representations](https://link.springer.com/article/10.1007/s00220-021-04118-7), [finite-field Gauss sums](https://www.cambridge.org/core/books/abs/finite-fields/exponential-sums/60D3D9DC74D98A5DF17D7BF9D2019B34), and [quadratic Fourier/metaplectic operators](https://pmc.ncbi.nlm.nih.gov/articles/PMC7072060/). No external source code is imported or copied.
