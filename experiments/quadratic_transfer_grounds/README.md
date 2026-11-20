# TCN-002 — Composable quadratic transfer Grounds

**Status:** experimentally implemented. Python >=3.10, NumPy. 2026-11-20.

## Question

Can a *periodic chain* of quadratic Fourier/chirp operators be navigated to a remote coordinate and inverted back to its earliest equivalent time without storing the full vector or simulating all the intermediate states? Where, mathematically and empirically, does such a compact representation cease to exist?

**Answer for the declared finite-field family:** Yes, up to a common global phase, for basis-vector inputs and periodic schedules of **quadratic** diagonal phases over odd prime fields. We obtain exactly reproducible support, relative phase and rational probabilities from a 2×2 matrix over F_p, and exact inverse **operator** coordinates via finite-group methods. This is classical simulation of the finite-dimensional Weil/metaplectic / Clifford family, not a generic quantum speedup, optimizer, proof of RH, or any claim of computation without physical substrate.

This extends [TCN-001](../theta_cayley_navigation/README.md) (quadratic-phase discovery and cautious admission), [SGN-001](../spectral-ground-navigation/README.md) (conditional exact versus empirical spectral navigation), and [Guarded Shortcut Trade-off](../guarded-shortcut-tradeoff/README.md) (modular navigation costs). It does not replace these. The claimed November 20, 2026 RH/GRH Lean proof is **not an input or mathematical dependency**. Quadratic Gauss sums and finite-field symplectic representations are established mathematics independent of that claim.

## Finite-field construction and exact relative-state Ground

Let p be an odd prime and \(\omega=\exp(2\pi i/p)\). Define the **positive-sign Fourier transform** and quadratic chirp

\[
(Fv)(y)=\frac1{\sqrt p}\sum_x\omega^{xy}v(x),\qquad
(D_a v)(y)=\omega^{ay^2}v(y),\qquad T_a=D_aF.
\]

Our phase-space convention maps the elementary transform to the symplectic matrix

\[
J=\begin{pmatrix}0&-1\\1&0\end{pmatrix},\quad
S_a=\begin{pmatrix}1&0\\2a&1\end{pmatrix},\quad
A_a=S_aJ=\begin{pmatrix}0&-1\\1&-2a\end{pmatrix}\in SL(2,\mathbf F_p).
\]

A declared periodic chirp schedule \((a_0,\ldots,a_{L-1})\) has cycle matrix \(C=A_{a_{L-1}}\cdots A_{a_0}\). At step \(n=qL+r\), the exact symplectic representative is \(A(n)=P_r C^q\), with \(P_r=A_{a_{r-1}}\cdots A_{a_0}\). Binary exponentiation costs \(O(L+\log n)\) **2×2 modular products**. These matrices describe the action of the circuit on the Heisenberg/Weyl operators; *the global scalar phase of the unitary is deliberately not retained*.

For initial basis vector \(|x_0\rangle\), write \(A(n)=\begin{pmatrix}\alpha&\beta\\\gamma&\delta\end{pmatrix}\). The **output ray** (normalized wavefunction up to one common phase) is exactly:

- If \(\beta=0\), the delta state at \(y=\alpha x_0\pmod p\).
- If \(\beta\ne0\), the flat quadratic state \(p^{-1/2}\omega^{u y^2+v y}\), where \(u=\delta(2\beta)^{-1}\), \(v=-x_0\beta^{-1}\) in F_p.

The ray provides **exact** probabilities 0, 1, or 1/p; exact relative phase residues; and quadratic-congruence inverse queries for target relative phases. It does **not** yield absolute complex amplitudes, recover an arbitrary physical source, or efficiently materialize all p output values. A relative phase request on a delta ray is refused because the referenced amplitude may be zero.

### Inverting time rather than just predicting forward

By the trace discriminant of \(C\in SL(2,F_p)\), its order divides \(p-1\) (split eigenvalues), \(p+1\) (nonsplit), \(p\) (unipotent), or \(2p\) (negative-unipotent). `operator_period_bound()` factors and reduces the relevant candidate to the **exact order** \(o(C)\). The complete schedule therefore repeats the same projective operator after at most \(L\,o(C)\) steps, potentially much sooner.

`find_operator_coordinate(target)` determines the earliest nonnegative step with the **same symplectic matrix**, by solving \(C^q=P_r^{-1} target\) for each remainder with baby-step giant-step. This is an inverse on a finite cyclic subgroup, costing \(O(L\sqrt{o(C)})\) matrix products and \(O(\sqrt{o(C)})\) memory, plus order factorization—not \(O(\log n)\) inversion and not an arbitrary observation-time oracle. Matching symplectic operators means matching the projective action; full scalar unitary phases need not recur at that time.

## Discovery, cost, and verification boundaries

`Ground` assumes a **declared** chirp schedule. It does not infer one. `bridge.py` accepts a *qualified* [TCN-001](../theta_cayley_navigation/README.md) quadratic-phase discovery as the initial state: \(\omega^{ax^2+bx+c}\) matches \(T_a|b\rangle\) up to common phase. A subsequent schedule must be supplied by the caller, and continuation beyond the observed model **requires explicit hypothesis opt-in**. The TCN-001 observation digest is preserved; future state observations are not fabricated. This is an in-repository integration, not a live E-CPU transport.

`receipt()` produces a deterministic SHA-256 bound to source, field, schedule, claimed 2×2 matrix, ray, and enormous decimal step index. `verify_receipt()` independently recomputes the mathematical result and rejects falsified fields even if the hash is recomputed. It does **not authenticate the author of a receipt or independently establish that the external schedule occurred**. For future integration, see E-CPU's `mailcpu/navigation_admission.py` (hypervisor-owned approval) and `mailcpu/law_certifier.py` (witness scopes and horizon refusal), and VGI's evidence/ground separation. Those components remain authoritative; SGN/TCN's local mathematical receipts cannot silently grant VM execution rights.

### Quadratic-frame residual audit

For any complete p-vector (including an arbitrary nonquadratic one), `quadratic_frame_audit` scans all p curvature choices; for each curvature, the p linear characters form an **orthonormal basis**. It reports how many coefficients in the *selected frame* are needed for 99% of observed energy, at a discovery cost of \(O(p^2\log p)\). This is an in-sample compression diagnostic, not an incompressibility theorem or an observer-independent certificate. Generic states are still expressible with p coefficients. A vector with 1 coefficient is a quadratic ray, whereas a high required count points toward a more expensive representation. `diagnose_quadratic_ray` additionally checks the strict delta/flat-quadratic family from complete data; partial noisy observations require a separate inference and holdout process.

**Important compositional obstacle:** Summing several projective rays requires their *relative global phases*, which are precisely what the 2×2 symplectic representation omits. A correct nonquadratic sparse-sum extension must attach exact finite-field Gauss-factor phases (or another verified cocycle), otherwise interference between branches will be wrong. We did not hide this omission behind a vector reconstruction claim.

## Falsification and measured results

Locally run `OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/quadratic_transfer_grounds -p 'test_*.py' -v` and `OPENBLAS_NUM_THREADS=1 python experiments/quadratic_transfer_grounds/run_experiment.py > /tmp/tcn002.json`. CI tests Python 3.11–3.13. Tests compare projective fidelity to **independent full p-dimensional FFT execution** for several prime fields, schedules, and source coordinates; test target congruence inversion; all finite operator orders in sampled cases; temporal inverse consistency; unknown-schedule refusal; out-of-family cubic phases; random/nonflat vectors; actual TCN-001 admission integration; and tamper-resistant deterministic recomputation.

Recorded local run (NumPy CPU, three timing repeats, one host; reproducible JSON provided by runner, timing not a portable speed guarantee):

| Trial | Observation |
| --- | --- |
| Exact long jump | p=101, schedule (7,13,29), source=33, n=10^100+123: 491 modular matrix products; ray \(\omega^{44x^2+99x}/\sqrt{101}\) |
| Inverse operator time | Same operator first appears at step **25**; declared schedule's projective period bound = **153** |
| Numerical cross-check | p=127, 4096 transfer steps: projective fidelity **1.0** vs dense repeated FFT; **20** small modular products |
| Illustrative local timing | Median dense execution ≈103.29 ms vs compact description ≈0.019 ms (excludes model/schedule discovery and output materialization) |
| Quadratic frame p=31 | 1 mode for 99% energy (single-mode fidelity 1.0) |
| Cubic frame p=31 | 22 modes for 99% energy (best selected-frame single-mode fidelity ≈0.109) |
| Random phase p=31 | 25 modes for 99% energy (selected-frame peak ≈0.161) |
| Changed schedule negative control | Internally valid assumed schedule had projective fidelity ≈0.0099 against a different realized schedule |

A small but exact **no-go** within this declared state family: from a basis input, the final probability at any coordinate is either 1/0 for a delta or **1/p for every coordinate** in the flat state. Thus pure quadratic Clifford interference alone does **not** selectively amplify an arbitrary marked set of objective solutions. It is not an optimizer for general SAT, integer programs, or random objectives. It remains useful as a structurally navigable subroutine.

## Files

- `transfer.py`: projective finite-field symplectic composer, exact rational ray, inverse-time solver, frame and closure audits, independently recomputed digest receipts.
- `bridge.py`: narrow, scoped adapter from TCN-001 discoveries to hypothesized future quadratic schedules.
- `test_transfer.py` and `test_bridge.py`: deterministic regression, high-index, and adversarial checks.
- `run_experiment.py`: complete machine-readable evidence and single-host timing measurements.
- `.github/workflows/tcn002-quadratic-transfer.yml`: explicit CI entrypoint.

## Next experiment

**TCN-003: phase-aware sparse stabilizer expansion.** Find a compact exact cyclotomic/Gauss-phase representation of sums of quadratic rays, verify composition against direct FFT, and measure how representation rank grows under cubic and other nonquadratic oracles. Compare against direct FFT/enumeration and report when maintaining a compressed Ground costs *more* than simply executing the original operator. A proof-checked or independently hosted E-CPU/VGI adapter would follow **after** the phase and witness contracts survive these tests.

## Sources and provenance

This uses original code implementing classical results about quadratic characters and the finite-field symplectic representation. Related general mathematical sources: Gross et al., [Schur–Weyl Duality for the Clifford Group](https://link.springer.com/article/10.1007/s00220-021-04118-7) (qudit symplectic/Clifford correspondences); finite-field quadratic [Gauss sums](https://www.cambridge.org/core/books/abs/finite-fields/exponential-sums/60D3D9DC74D98A5DF17D7BF9D2019B34); and the [metaplectic representation](https://pmc.ncbi.nlm.nih.gov/articles/PMC7072060/) for quadratic Fourier transforms. No text/code from these resources is copied.

## TCN-003 — Exact scalar Gauss-cocycle continuation (20 November 2026)

The companion [TCN-003 study](COCYCLE.md) now **restores the global fourth-root phase** omitted by the TCN-002 projective summary. It composes pairs `(symplectic 2x2 matrix, Gauss phase modulo 4)` exactly, supplies symbolic absolute basis-to-basis amplitudes at very large coordinates, and evaluates an arbitrary *supplied* complex input vector at a requested output without replaying intermediate Fourier steps. It also distinguishes projectively equivalent operators whose full complex phases differ. Its evidence and tests are in `cocycle.py`, `test_cocycle.py`, and `run_cocycle.py`; it does not change TCN-002's consciously projective API or its witness restrictions. A full exact amplitude is a mathematical model value, not an external measurement or authorization.
