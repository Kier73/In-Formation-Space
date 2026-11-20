# TCN-006 — Moving-frame computational Grounds and nonquadratic phase echoes

**Status:** implemented research experiment (20 November 2026). **Scope:** a single odd-prime qudit of size `p <= 1021`, a known basis-state input, declared quadratic Fourier/chirp operators, and known cubic/harmonic diagonal gates. This is neither a general simulator nor a proof that an unknown physical process obeys the proposed operator.

## Research question

Can a nonquadratic operation be transported through known quadratic evolution **without reconstructing the entire state**, and can one choose a future coordinate at which an inexpensive intervention cancels that operation? When must such a compact representation refuse to claim a cheap readout?

The answer in the implemented family is **yes for symplectically aligned generators, no cheap cancellation for misaligned generators by this method**. A refused budget is not an impossibility theorem.

This builds on [TCN-003 Gauss cocycle](COCYCLE.md) (full global-phase preservation), [TCN-004 phase-aware sparse branches](PHASE_BRANCHES.md), and [TCN-005 adaptive computational Grounds](ADAPTIVE_GROUND.md). Those files already provide the quadratic operator; TCN-006 does not introduce another implementation of the Gauss cocycle. The prior SGN-001 observations, and the user-shared RH/theta-chain discussions, are inspirations rather than theorems imported into this construction.

## Exact operator algebra

Let `p` be an odd prime, `omega = exp(2 pi i/p)`, `half = inverse_mod(2,p)` and let

`W(q,k) psi(x) = omega^(k*(x-q/2)) psi(x-q)`.

Writing `v=(q,k)` and `symp(v,w)=q*l-k*r` for `w=(r,l)`, the Weyl multiplication law is

`W(v) W(w) = omega^(-symp(v,w)/2) W(v+w)`.

Every quadratic Clifford/finite-field metaplectic operator `U_M` in TCN-003 satisfies the **exact** conjugation law

`U_M W(v) U_M^-1 = W(Mv)`.

The global Gauss cocycle of `U_M` is already accounted for by TCN-003's `ExactOperator` and cancels out of the conjugation itself. Tests explicitly compare conjugation on full, random complex input vectors, using separate dense numerical operations.

The new Ground stores an ordered product of phase blocks followed by one exact TCN-003 operator acting on a basis source:

`B_0 B_1 ... B_(r-1) U_M |source>`.

A block is a function of a single Weyl generator and may combine:

- an **exact modular cubic** `exp(2 pi i*c*X^3/p)`;
- **harmonic phases** `exp(i*sum gamma_f*cos(2 pi*f*X/p))`.

Here `X` denotes the eigenvalue coordinate of the Weyl operator after a Clifford change of frame. This is an analytic/symbolic description of supplied gates; the complex amplitudes are numerically evaluated only at readout. All blocks keep an explicit, canonical Weyl direction. Under `U_M`, these directions transform as `v -> Mv`; the cubic coefficient scales by the cube of the Weyl-direction scalar, and a harmonic frequency scales linearly. Thus phase generators can be moved through very long *known* schedules using the existing exact `ExactSchedule.navigate(n)`.

**Commutativity is decisive.** Two Weyl directions commute iff their symplectic pairing is zero mod `p`. For a single phase-space degree of freedom over a field, this is equivalent to collinearity. If the incoming gate aligns with the outermost existing phase block, the compiler algebraically adds its cubic and harmonic terms; a zero block disappears. It does **not** commute disjoint blocks through intervening noncommuting ones. Such blocks retain their chronological order, and their readout can be charged as a full p-dimensional calculation.

## Discovered constructive phenomenon: a cubic echo

Write `G_c = diag(omega^(c*x^3))`. If a quadratic operator `U_M` transports the native phase axis `(0,1)` to `(0,d)` (so `M[0,1] = 0`), its cubic generator transforms as `c -> c*d^3 (mod p)`. Therefore

`G_(-c*d^3) U_M G_c = U_M`.

This is an **identity of declared operators**, not a numeric fit. TCN-006 implements `cubic_echo_strength` to derive the needed countergate, or explicitly refuses if the transported axis is nonvertical.

Examples:

1. `F^2` is parity: `x -> -x` and sends the cubic generator to its negative. Consequently `G_c F^2 G_c = F^2`. (For harmonic cosine, which is even, the echo countergate has opposite real strength.)
2. A dilation with `M = diag(a,a^-1)` transports the cubic coefficient by `a^-3`; a suitable second cubic cancels it. This is tested against its complete operator kernel.
3. A *single* Fourier `F` transports a diagonal phase generator into a shift generator. With one native cubic countergate the axes cannot be aligned; the low-budget shortcut refuses. A full, costly ordered-operator calculation still agrees with direct FFT.

`first_native_cubic_echo` finds the earliest **enumerated** schedule coordinate where the native cubic countergate is possible. It charges up to `max_steps` group operations; **discovery is not claimed O(log n)**. Once that coordinate is found, navigating to a specified large, equivalent coordinate uses logarithmic operator composition.

## Local experimental evidence

`OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/quadratic_transfer_grounds -p 'test_moving_frame.py' -v`

`OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/quadratic_transfer_grounds -p 'test_moving_frame_receipt.py' -v`

`OPENBLAS_NUM_THREADS=1 python experiments/quadratic_transfer_grounds/run_moving_frame.py > tcn006-result.json`

The test suite checks Weyl conjugation for three odd prime fields, short dense-FFT reconstruction of cubic and harmonic operations, preservation of exact TCN-003 central phase, nontrivial symplectic dilation, full operator echoes, noncommuting-frame refusal, and the difference between an algebraic 100-digit jump and an independently executed short benchmark.

For `n=10^100+2` Fourier transfers, all tested field sizes `p=31,127,257` reduced the cubic-echo description to **zero nonquadratic phase blocks**. The current binary navigation implementation reports **439** matrix/operator products (including repeated squarings); model readout then requires one exact TCN-003 basis-amplitude evaluation. The corresponding *short* `G_c F^2 G_c` circuits were computed independently via direct FFT:

| Field `p` | Maximum absolute short-circuit amplitude difference |
| --- | ---: |
| 31 | `3.4053e-16` |
| 127 | `7.7777e-16` |
| 257 | `2.0368e-16` |

A single intervening `F` gave **two noncommuting phase blocks** and a **refused** small query-work budget. An explicitly larger budget permitted complete numerical reconstruction with maximum error `3.4332e-16` at `p=31`.

The long coordinate was **not** evaluated by 10^100 separate FFTs; the check is algebraic equality with the short representative. This does not establish hardware-independent performance or automatic discovery of unknown physics.

## Work accounting, evidence, and refusal

- With no phase blocks, an output basis amplitude is O(1) symbolic operator readout after the O(log n) schedule construction.
- With one aligned diagonal phase block, a coordinate remains O(1) in the chosen phase frame; a general single Weyl-axis block may require O(p) output work.
- Multiple noncommuting blocks retain their operator order. The current implementation conservatively budgets O(p^2 * blocks) for a full intermediate-state representation and **refuses** if a stated query budget is smaller. Better algorithms may exist; this is not a lower bound.
- The `receipt.py` writer preserves a bounded declared program, exact operator signature, phase blocks, requested coordinates, budget/decision, SHA-256, and rendered amplitudes. `verify_receipt` rebuilds the mathematical output and compares, for short Fourier-only schedules, with separately executed dense FFT. SHA-256 is an integrity fingerprint, **not a signature or external authority**. The large-step receipt is a mathematical replay only. E-CPU hypervisor admission and VGI independent observation authority have **not** been invoked.
- The symbolic cubic coefficient is exact modulo p. Real harmonic strengths and complex amplitudes use finite-precision floating-point, so their numerical outputs are approximate.

## Relationship to existing research and architecture

This is a special case of classical finite-dimensional Heisenberg–Weyl/Clifford conjugation, not a new metaplectic theorem and not quantum computing hardware. Related published work includes [Bravyi et al. (2019), *Simulation of quantum circuits by low-rank stabilizer decompositions*](https://quantum-journal.org/papers/q-2019-09-02-181/), which studies classical simulation with non-Clifford gates. Our experiment makes a narrower observation: an *intention-directed countergate* can cancel an earlier nonquadratic generator if a known intervening Clifford brings it back onto an accessible axis.

A possible E-CPU integration point is `mailcpu.law_certifier` (exact declared algebraic laws), `mailcpu.navigation_admission` (hypervisor-owned authority), and `mailcpu.holonomy_engine` (gauge-sensitive/independent phase concepts). For VGI, the missing extension is an external host supplying typed observations and a recheckable signed/admitted Ground. No repository-external integration or authentication is claimed in this run.

## Next frontier

Search over intended *operator effects* rather than single target states: for a requested cancellation, use projective orbit structure to find an eligible future clock **without enumerating every intermediate frame**. Then test higher-dimensional symplectic transport and genuinely coupled generators, where commuting subalgebras can have dimension >1 and readout costs may grow abruptly.
