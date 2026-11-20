# TCN-004 — Phase-aware sparse branches through nonquadratic interventions

**Status:** Executable finite-field experiment (2026-11-20). **Scope:** synthetic, *known* quantum-style quadratic Fourier and diagonal phase operators; a classical simulation experiment, not quantum hardware, a general optimizer, nor verification of the reported Alpöge/Claude RH proof.

## Question

Can a virtual computational state cross a nonquadratic intervention, remain economical to represent, and still support enormous time-coordinate jumps through later quadratic transitions? Can the same apparatus distinguish when the representation is *not* economical enough, without claiming that the underlying physical process has been proved to follow the model?

This extends [TCN-002/003](README.md) and reuses `cocycle.py`'s **exact** finite-field symplectic + Gauss-quadrant composition, not just a projective stabilizer ray. E-CPU's `mailcpu/law_certifier.py` and `mailcpu/navigation_admission.py` informed the separation of a fast mathematical law, a bounded witness, and externally authorized execution. VGI's observation-versus-Ground distinction informed the refusal/status vocabulary. **Neither E-CPU nor VGI is imported at runtime or claimed to have authorized these synthetic operations.**

## Two representations and the exact closure step

Let p be an odd prime, \(\omega=e^{2\pi i/p}\), and \(T_a=D_a F\), where \(F_{y,x}=p^{-1/2}\omega^{yx}\) and \((D_av)_y=\omega^{ay^2}v_y\). A state is stored as one *orthonormal* family with complex coefficients:

- **Flat quadratic frame:** \(v(y)=p^{-1/2}\omega^{ay^2}\sum_{b\in B}c_b\omega^{by}\).
- **Delta frame:** \(v(y)=\sum_{b\in B}c_b\mathbf1_{y=b}\).

These are actual complex amplitudes, **not projective rays**. In both frames \(\lVert v\rVert_2^2=\sum_b|c_b|^2\). Keeping relative complex coefficients is essential when branches later interfere.

For any TCN-003 quadratic unitary \(U\), the canonical matrix \(M\) of \(U T_a\) (flat input) or \(U\) (delta input) has \(M=\begin{pmatrix}A&B\\C&D\end{pmatrix}\):

- If \(B\ne0\), its kernel sends source coordinate \(b\) to a quadratic flat mode with curvature \(D/(2B)\), frequency \(-b/B\), and an **exact Gauss-cocycle phase** from \(\langle0|U T_a|b\rangle\sqrt{p}\) (or \(\langle0|U|b\rangle\sqrt{p}\) for delta input).
- If \(B=0\), the mode moves to the delta coordinate \(A b\) and takes the phase of the unique nonzero basis amplitude.

Thus an arbitrary *known* quadratic schedule changes frame coordinates and complex coefficients but **never increases the number of modes**. For a periodic schedule of length L, its exact operator is found by binary powering of the cycle and a residual prefix in \(O(L+\log n)\) small modular compositions; the subsequent k-mode target amplitude is evaluated in \(O(k)\) arithmetic. This is a computational formula; it does not witness an outside system at time n.

## Two ways to cross a nonquadratic phase gate

**General scan (a deliberately expensive control):** Multiply the complete p-vector by the chosen gate and scan all p quadratic frames with FFTs; keep the top k orthonormal coefficients of the best frame. This costs \(O(p^2\log p)\) and requires materializing p amplitudes. `fit_frame` reports selected curvature, omitted \(\ell_2\), and the rank required for a chosen tolerance. It supplies no impossibility theorem.

**Procedural harmonic gate:** The gate is \(G_\gamma(y)=\exp(i\gamma\cos(2\pi y/p))\). Its Taylor polynomial in \(\cos\theta\) has a finite, explicitly generated Fourier sum:

\[
G_\gamma(y)\approx\sum_{m=-r}^{r}h_m\,\omega^{my},\qquad
h_m=\sum_{j=0}^{r}\frac{(i\gamma/2)^j}{j!}
\sum_{\ell=0}^{j}\binom j\ell\mathbf1_{m=j-2\ell}.
\]

An existing quadratic branch at frequency b therefore expands only to frequencies \(b+m\) (mod p). The expansion is computed from the **gate description and the sparse coefficients alone**—no p-vector, no scan of p curvatures. The generated modes number at most \(2r+1\), independent of p, and the construction costs \(O(k r^2)\) before sorting and truncating. On a delta-frame state the gate is exact scalar multiplication, with no branching.

For real gamma and r ≥ 0, the uniform complex Taylor remainder satisfies

\[
\sup_\theta\left|e^{i\gamma\cos\theta}-\sum_{j=0}^{r}\frac{(i\gamma\cos\theta)^j}{j!}\right|
\le e^{|\gamma|}\frac{|\gamma|^{r+1}}{(r+1)!}=:R_r.
\]

Let \(\epsilon\) be the incoming \(\ell_2\) bound, \(s=\lVert v_{\mathrm{approx}}\rVert_2\), and \(\delta\) the discarded orthogonal-mode norm **of the Taylor approximation**. The next mathematically justified bound is

\[
\epsilon'\le\epsilon+R_r s+\delta.
\]

This inequality accumulates errors across nonquadratic interventions; exact quadratic propagation preserves it by unitarity. A rank or error-budget miss refuses a new compact representation rather than silently pretending that the truncation is exact. **Caveat:** These are exact-complex-arithmetic inequalities evaluated through floating-point coefficients, not interval/rigorously rounded numerical certificates. Independent dense parity checks are supplied for small finite dimensions.

## Findings on local NumPy CPU

Reproduce via `OPENBLAS_NUM_THREADS=1 python -m unittest -v test_phase_branches` and `OPENBLAS_NUM_THREADS=1 python run_phase_branches.py`. The script prints complete measured JSON. Timings are medians of seven in-process repetitions on a particular host, not stable cross-hardware benchmarks.

| p | harmonic gamma=0.7, rank 7 | observed l2 error | ideal model bound | procedural time | exhaustive frame scan |
|---:|---:|---:|---:|---:|---:|
| 31 | admitted | ~0.000865 | ~0.000865 | ~0.06 ms | ~0.85 ms |
| 127 | admitted | ~0.000865 | ~0.000865 | ~0.06 ms | ~6 ms |
| 257 | admitted | ~0.000865 | ~0.000865 | ~0.06 ms | ~19 ms |
| 1009 | admitted | ~0.000865 | ~0.000865 | evaluated procedurally, no frame scan | not evaluated |

The independent dense-FFT references (including interfering multibranch inputs) agree at approximately floating-point roundoff for quadratic chains. A query at \(10^{100}+1,234,567\) steps is represented by exact schedule composition; it was checked against the algebraic period reduction, not a \(10^{100}\)-step dense execution.

**Negative controls:** With a rank cap of eight and absolute \(\ell_2\) budget 0.1, a cubic phase \(\omega^{5y^3}\) requires approximately 25 modes at p=31, 108 at p=127, and 200 at p=257 to reach the requested error tolerance in the best of the scanned quadratic frames. These are conditional on *this frame dictionary and synthetic inputs*, not lower bounds on any possible representation. A second harmonic phase intervention after a mixing quadratic schedule also exhausts a seven-mode budget in the recorded two-intervention example; repeated gates need not remain sparse.

## Witnesses, authority, and attacks

`witness.py` serializes finite sparse coefficients as exact hexadecimal IEEE-754 bit-pattern strings, includes the operation, budget, admitted/refused outcome and SHA-256 content digest, and reconstructs the witness. Rechecking recomputes the proposal and compares **all p complex coordinates** against the declared diagonal phase action. It refuses altered coefficient fields, altered decisions and broken hashes. A bare SHA-256 digest offers **integrity, not a signature or provenance**. Rechecking synthetic declared arithmetic is **not evidence of a live host** executing it. External admission requires E-CPU/VGI-provided source identities, authorizations and independent observation witnesses.

## File map / reproduction

- `branch.py`: general full-vector frame-scan control, exact phase-aware sparse representation, procedural harmonic Taylor gate, refused budget transactions, independent dense FFT function.
- `witness.py`: canonical state codec, computational receipts and reconstructing verifier.
- `test_phase_branches.py`: 14 deterministic tests across p=5,11,31,71,127,257; phase-sensitive interference, huge-time algebraic alias, bounds, gates, refusal and tamper checks.
- `run_phase_branches.py`: deterministic synthetic experiments and operation accounting, with local timing medians.
- `.github/workflows/tcn004-phase-branches.yml`: Python version matrix and deterministic tests.

**Parent source:** IFS TCN-003 `cocycle.py` and `transfer.py`, existing main branch (read 2026-11-20), reused as imports and not copied into the repository. E-CPU architecture references inspected on the same date; source implementations not copied. This line is an experimental implementation of classical finite-field Clifford/normalizer ideas; it is **not** a proof that Clifford simulation, stabilizer rank, or Gauss sums are new.

Related literature: [periodic quadratic Gauss-sum classical simulation](https://arxiv.org/abs/1812.00224), [quopit Clifford circuit amplitudes via quadratic sums](https://arxiv.org/abs/1702.03316), [stabilizer rank and higher-order Fourier analysis](https://ir.cwi.nl/pub/31373/31373D.pdf), [prime-dimensional Clifford hierarchy](https://www.math.purdue.edu/~cui177/Papers/11.pdf).

## Next question

Can one **adaptively choose a new small dictionary** (rather than keeping one quadratic frame) after multiple nonquadratic interventions, preserving all relative phase and coherent error bounds? Competing models should include short rational generating functions, low-rank tensor-factor representations, linearized constraints over extension fields and ordinary dense FFT; any reuse in E-CPU would require authorized observation and receipt continuity across independent hosts.
