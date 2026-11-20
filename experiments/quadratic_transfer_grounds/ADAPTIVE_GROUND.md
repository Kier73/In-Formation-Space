# TCN-005 — Adaptive computational Grounds: sparse frame or exact phase carrier

**Status:** executable experiment, 20 November 2026. Extends [TCN-004](PHASE_BRANCHES.md) and reuses the full-phase [TCN-003 Gauss cocycle](COCYCLE.md). No new claim of RH/GRH verification or a general state-space optimizer.

## Research question

Can a navigator change *which mathematical representation it uses* after discovering that its current frame is too expensive, rather than declaring an otherwise simple state incompressible? Can that choice depend on the particular observable and its tolerated error/readout cost?

The relevant lesson from TCN-004 is that an orthonormal quadratic Fourier frame may require nearly p modes for a cubic character, even though the cubic phase is given by **one modular coefficient**. In contrast, a weak smooth harmonic gate can have a cheap sparse Fourier–Taylor description with a rigorous ideal-arithmetic approximation bound.

TCN-005 implements two alternatives, charged separately:

1. **Sparse orthonormal Ground.** Uses existing `StructuredState.after_harmonic` or an explicitly requested full curvature scan. TCN-003 propagates the resulting finite branches through quadratic schedules in O(rank · log steps) symbolic work, and individual output coordinates cost O(rank).
2. **Analytic phase carrier.** Keeps the existing `StructuredState` plus `cubic` (integer mod p) and `harmonic` (real strength) phase coefficients, **then** an exact TCN-003 operator. It does not truncate the supplied phase function. An output coordinate after mixing takes O(p · input_rank) arithmetic (and temporary O(p) memory); in permutation-only cases it needs O(input_rank). This is not O(log p) readout.

Given an input state φ(x), the carrier denotes

[
psi = U; mathrm{diag}!left[
omega^{a x^3} exp(igammacos(2pi x/p))
ight]phi,qquad omega=e^{2pi i/p}.
]

The quadratic schedule U is described by the exact 2×2 symplectic matrix *and* the Gauss cocycle phase. For a requested set Q of output coordinates, `choose_ground` compares the candidate sparse model against the analytic carrier subject to a rank cap, cumulative ideal L2 error budget, and estimated readout work budget. An unsupported choice **refuses** rather than silently truncating.

**Important:** The carrier preserves the *declared* analytic mathematical operation, not an externally observed system's behavior. Complex rendering is floating-point, not an exact complex-number proof. The conservative bound on a sparse description is an ideal-arithmetic bound and does not enclose numerical rounding. A request for exact phase carrier preserves any pre-existing error in its input state: it cannot recover information lost earlier.

## The structural result: fuse commuting interventions

When consecutive phase gates share the *same input frame*, their descriptions combine:

[
D_{gamma_1}D_{gamma_2}=D_{gamma_1+gamma_2},qquad
D_{a_1x^3}D_{a_2x^3}=D_{(a_1+a_2)x^3}.
]

A test fused **200 nonquadratic gate applications into two phase parameters** before a massive known quadratic transfer. No p-coordinate vector was retained between gates, and the exact modular phase of U survived the jump. This is an algebraic identity *for commuting operations only*; it does not imply general compression of arbitrary operator chains. The compiler refuses to append a new phase gate after a pending noncommuting quadratic transfer, unless an explicit re-anchoring procedure is performed and its error/rank budget is met.

The choice is **intention scoped**. A few output coordinates can afford the analytic carrier's O(p) readout, while a long output vector may be better served by a sparse frame or a direct dense FFT. `estimated_query_work` is a deliberately simple symbolic cost (not a wall-time guarantee); discovery cost and the full-frame search O(p² log p) are separately described and must be considered in total planning. Repeating a dense readout for each coordinate is not the preferred method for materializing the full state.

## Reproduction

Dependencies: Python 3.10+ and NumPy. From repo root:

```bash
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/quadratic_transfer_grounds -p 'test_adaptive_ground.py' -v
OPENBLAS_NUM_THREADS=1 python experiments/quadratic_transfer_grounds/run_adaptive_ground.py
```

Tests cover: cubic frame refusal and exact carrier admission; harmonic sparse admission; required zero-truncation selection; finite query-work refusal; 200 commuting operations; noncommuting re-anchor refusal; independent dense FFT parity for p=31/71/127; huge period aliasing with full Gauss phase; delta source; malformed inputs; SHA-256 receipt replay; corrupted receipts; and successful reconstruction of refused decisions. The experimental runner measures p=31,127,257 and records all readout and construction distinctions.

**Representative local observations (p=31/127/257):**

| p | Cubic model | Best quadratic-frame required rank at zero omission | Harmonic model | Bound on harmonic ideal L2 error |
|---|---|---:|---|---:|
| 31 | One-parameter cubic carrier | 31 | 7-mode sparse frame | 0.000865 |
| 127 | One-parameter cubic carrier | 127 | 7-mode sparse frame | 0.000865 |
| 257 | One-parameter cubic carrier | 256 | 7-mode sparse frame | 0.000865 |

The cubic carrier matched independent repeated FFT at tested coordinates to ≲5×10⁻¹⁶ maximum absolute error. The harmonic 7-mode candidate had ≲2.1×10⁻⁴ observed per-coordinate error. A 101-digit step for a 3-element periodic schedule used 491 exact modular operator products (including sequence-prefix construction). This is **conditional mathematical navigation**, not a time-to-physical-event forecast. The reported wall timings of any runner are hardware-dependent and not evidence of a universal speedup.

## Computational receipts and authority

`choice_receipt` encodes the input state from TCN-004's `witness.state_record`, gate, schedule, requested coordinates, budgets, decision, predicted amplitudes, and an SHA-256 digest. `verify_choice_receipt` independently reconstructs the decision and, for short schedules (≤40 steps), compares the selected outputs to direct FFT execution. For longer steps it checks against the declared exact full-phase operator, *not* direct physical execution.

These records are **not signed**, do not authenticate an external observation source, and do not grant E-CPU hypervisor authority. An E-CPU/VGI integration would have to bind them to a live context, host identity, source authorization, observation digest, and an independent reviewer.

## Critical negative results and next frontier

- A cubic phase can be expensive in all quadratic Fourier frames despite having an O(1)-size polynomial description. Frame incompressibility does not imply description incompressibility.
- A new gate after noncommuting mixing generally cannot be folded into the existing carrier. Re-anchoring can require full reconstruction and fail the requested sparsity budget.
- A carrier with one stored phase parameter can have O(p) *readout* work. Storage compression is not automatically a computational speedup.
- This compiler **does not discover its phase-law coefficients from new observations**. Discovery and external witnessing remain independent research tasks.
- The next frontier is to track conjugated phase carriers in the Heisenberg/Weyl frame and detect commutation *after* a quadratic transform. That could permit more operations to fuse without reconstructing a state; noncommuting carriers would still carry explicit growth and refusal.

## Related external research

The finite-field symplectic/Clifford connection is classical; see [Dehaene–De Moor (2003)](https://arxiv.org/abs/quant-ph/0304125) and [quadratic-form expansions](https://cqwbkpro.s3.eu-west-2.amazonaws.com/wp-content/uploads/2021/10/27145056/210923_CQ_Fast-Stabiliser-Simulation-with-Quantratic-Form-Expansions.pdf). The relationship between non-Clifford resources, stationary phase, and Gauss-sum count is treated in [Kocia and Love (2018)](https://arxiv.org/abs/1810.03622). These are contextual sources, not dependencies copied into the implementation. This module is a synthetic testbed, not a quantum-computation advantage claim.
