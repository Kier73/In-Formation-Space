# TCN-007 — Inverse intervention navigation over finite symplectic orbits

**Status:** executable research contribution; 20 November 2026. Extends [TCN-006](MOVING_FRAME.md) and reuses the exact central-phase implementation from [TCN-003](COCYCLE.md). No new assumptions about the validity of the claimed RH/GRH proof are required.

## Research question

Given a **desired final operator**, rather than a forward evolution to inspect, can a system identify *when* to introduce a bounded native control so that a long known transformation chain realizes that requested operator? Can it establish that an intervention is unreachable within a declared model, without confusing that with an exhausted search budget?

This experiment solves an exact, narrow case: one odd-prime-dimensional finite-field state, a **declared periodic quadratic** transfer schedule, one prior **native modular cubic** gate, one after-schedule native cubic countergate, and a requested residual native cubic. The coefficients, schedule, and allowed action strengths are supplied rather than inferred. This is an exact synthesis problem for known symbolic operations, **not** an external prediction, proof of universal computational compression, or physical action.

## Mathematical target and representation

Let `p` be an odd prime, `omega=exp(2*pi*i/p)`, and `G_c |x> = omega^(c*x^3)|x>`. With `U_n` denoting the first `n` operations of a periodic quadratic schedule, the *intention* is the **whole-operator identity**

\[
G_g U_n G_c = G_t U_n.
\]

The prior cubic strength `c`, requested residual strength `t`, and permitted final control alphabet `A` are inputs; the unknowns are the coordinate `n >= min_step` and the final action strength `g in A`. When `A=None`, any residue is permitted.

TCN-006 established that quadratic conjugation sends a Weyl generator `v=(q,k)` to `M_n v` where `M_n in SL(2,F_p)`. For native `Z`-axis cubic gates the condition used here is

\[
M_n(0,1)=(0,d),\qquad g+c d^3\equiv t\pmod p.
\]

This is a sufficient constructive identity in the declared operator family, checked by TCN-006's phase-block compiler. The selected **entire quadratic operator** is independently reconstructed with `ExactSchedule.navigate(n)`, including TCN-003's Gauss central phase (not merely its projective 2x2 matrix). Dense short-circuit checks exercise all input amplitudes for several sources via a separate FFT implementation.

### Inverting the orbit, not iterating the requested horizon

For schedule length `L`, let `C` be the exact symplectic matrix of one cycle and `P_r` the known prefix for remainder `r`. Then

\[
M_{qL+r}=P_r C^q.
\]

The inverse target is a **Weyl vector orbit** `C^q e_Z`, where `e_Z=(0,1)`. It is often smaller than the full operator's orbit. Its order `h` divides `ord(C)` and is obtained by factoring the known finite-field matrix-order bound and testing divisors.

**Unrestricted final cubic strength:** only the projective *direction* must be vertical. The solver builds a baby-step/giant-step index of `C^j e_Z`, modulo nonzero scalar. Each remainder `r` asks for the first `q` whose direction matches `P_r^-1 e_Z`. After finding the earliest time `n >= min_step`, the full operator is reconstructed and its **actual scalar** `d` is used to compute `g = t-c*d^3`. If an enormous `min_step` advances through multiple projective periods, `d` is recomputed at the chosen large coordinate; it is **not** presumed to repeat with the direction.

**Restricted alphabet:** the scalar is operationally meaningful. The solver enumerates permissible exact finite-field vectors `(0,d)` for which `(t-c*d^3) mod p` belongs to the given action alphabet. It then uses an **exact-vector** orbit index, not a projective one. This can enlarge the orbit period, but prevents the incorrect substitution of a direction recurrence for a strength recurrence.

For each candidate residue `n0=qL+r`, with exact vector or projective period `H=L*h`, the earliest allowed time is

\[
n=n_0+H\max\bigl(0,\lceil (n_{min}-n_0)/H\rceil\bigr).
\]

Every returned coordinate is checked by recomputing `U_n`, applying its Weyl vector to `e_Z`, and reconstructing the operator using TCN-006's phase blocks. No iteration proportional to `n` is performed.

### Computational accounting

The inverse stage uses baby-step/giant-step on an orbit of size `h`, requiring `O(sqrt(h))` baby vectors, order-factorization and modular powering, and up to `O(L * candidates * sqrt(h))` giant-step probes. In unrestricted mode there is one projective target per schedule remainder; restricted mode has at most `p-1` exact vector targets per remainder. The finite-field scan for permissible `d` is `O(p)` and its cost is not hidden in the `O(log n)` evaluation claim. The complete TCN-003 operator at `n` uses `O(L + log n)` small algebraic products. Floating-point rendering of basis amplitudes, and materialization of a full `p`-component state, are separate work.

**Refusal semantics:** `found` means a declared-model operator identity; `unreachable` means the complete finite orbit lacks the permitted target; `outside_window` means its first usable future occurrence exceeds `max_step`; `refused_budget` means preparation/search was curtailed, and **does not imply nonreachability**. The solver is bounded to the existing TCN odd-prime family (`p<=1021` in TCN-006's operational protocol); `max_babies` and `max_probes` are explicit. No E-CPU/VGI authority is inferred from the resulting unsigned SHA-256 computational receipt.

## Experiments, including negative evidence

Run from this folder (Python >=3.10, NumPy):

```bash
OPENBLAS_NUM_THREADS=1 python -m unittest -v test_inverse_ground
OPENBLAS_NUM_THREADS=1 python run_inverse_ground.py > tcn007-results.json
```

The test suite covers nonzero target cubic residuals, restricted action alphabets, commutation refusal, exact and projective Weyl-axis inverse queries, exhaustive short-orbit comparisons, 100-digit temporal jumps, different global Gauss phases, tamper rejection, malformed input and budget refusal. The fixed unit suite includes **620 deterministic inverse-orbit property checks** across primes 3, 5, 7, 11, 13, 17 and 31, comparing every result against direct finite-orbit enumeration; they are part of the CI contract.

Representative local results:

| Case | Result |
| --- | --- |
| `p=127`, schedule `(1,2)`, prior cubic `7`, target `0`, any control | Earliest `n=63`, countergate `28`, projective period `126` in time, 5 charged giant probes |
| Independent dense FFT, previous case, three basis inputs | Max amplitude error approximately `1.71e-15` |
| `p=31`, schedule `(0,)`, prior `7`, target `5`, permitted `{12}` | Earliest `n=2`, control `12`, exact vector period 4 |
| Same requested target with only `{5}` permitted | `unreachable` for the complete declared finite orbit |
| Same target with `{12}` but maximum coordinate 1 | `outside_window` |
| `p=257`, schedule `(1,2,3)`, prior `7`, target `0`, minimum `10^100+37` | Earliest `10^100+98`, 489 counted full-phase operator products, 25 giant probes, period 387 |
| Deliberately insufficient baby memory | `refused_budget`, not `unreachable` |
| Known nonreachable Weyl line under Fourier-only schedule | `unreachable` |

**Counterintuitive measured limitation:** at `p=1009`, a sequential scan of the short earliest echo orbit (`n=1009`) took approximately **0.41 ms** median while the inverse search took approximately **0.53 ms** median (7 measurements on one local Python process). Short finite orbits can make brute force cheaper than constructing an inverse index. The method's benefit is primarily *semantic*—the ability to navigate from an arbitrarily distant `min_step` to a coordinate with a proved declared-model action—and could help repeated queries amortize index preparation. It is **not** universally faster at small finite fields.

## Reproducible receipts and cross-repository relationship

`make_receipt(spec)` deterministically reconstructs an entire declared intervention program from bounded canonical JSON. It retains the selected coordinate as a **decimal string**, the exact 2x2 symplectic matrix, the TCN-003 global phase quadrant, transported Weyl vector, permitted action, residual target, solver status, charged probe counts, and SHA-256 digest. `verify_receipt` reruns the solution, not merely the checksum, and rejects changes even if an attacker recomputes an arbitrary hash.

The receipt is a **mathematical reconstruction witness** and lacks authentication, live source evidence, a fresh context, a host identity, receiver-authorized capability, or an external observation. For those, the existing related implementations must remain authoritative:

- E-CPU `mailcpu/law_certifier.py` provides explicit law/horizon qualification and `mailcpu/navigation_admission.py` governs hypervisor admission (reviewed at E-CPU `063e04f4dcd1027f3662427c79410f82a5c2aba6`).
- E-CPU `mailcpu/inverse_navigation.py` indexes declared, validated process paths; TCN-007 is complementary because it searches an algebraically described **operator orbit**, rather than materializing all state digests first (same revision).
- VGI `virtual_ground_interpreter/vgi/evidence.py` separates observation, finalized ground, and replay, while `typed_operator_navigation.py` preserves named finite-space types and demand-driven navigation (reviewed at VGI `7a3c4a368d1d24044a6c06a317c26ef316513e6d`).
- TCN-002/003/006 source is **reused inside In-Formation-Space** without copying E-CPU or VGI implementation into this project.

Mathematical precedents: finite-field Bruhat/Weil representations, cyclic-group orbit/discrete-log algorithms and baby-step/giant-step are established tools; relevant external references include [O'Brien's constructive recognition notes](https://www.math.rwth-aachen.de/~Graduiertenkolleg/schools/2011/slides/slides_ss11_obrien_2.pdf), [Handbook of Finite Fields (discrete log)](https://archive.ymsc.tsinghua.edu.cn/pacm_download/672/12637-dingjt-p2.pdf), and the [Magma group-recognition reference](https://docs.magma-maths.org/FiniteGroups/AlmostSimpleGroups/group-recognition.html). The novelty here is in **combining the exact TCN moving-frame phase contract with an intention-specific inverse actuator policy and honest search refusal**, not a claimed new group-theoretic theorem.

## Proposed next frontier

Introduce multiple legal control sites and operators whose induced Weyl axes may differ, then solve an intention-specific shortest **authorized** synthesis with rigorous bounds. Algebraic reachability would remain separate from E-CPU execution authority and from independently witnessed physical realization. Compare the cost of precomputing reusable orbit indexes with one-shot direct scans; study when action constraints genuinely reduce search rather than merely shifting the work into representation discovery.
