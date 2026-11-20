# TCN-008 — Intention-to-Ground synthesis

**Status:** executable constrained research experiment. **Scope:** finite-field, single-qudit *relative-phase* target states over an odd prime p in [7,1021], and a declared finite menu of computational hosts. This is not arbitrary program synthesis, proof of physical realization, or a universal optimizer.

## A reversal of the query

The previous TCN experiments start with a declared operator and evaluate or invert its trajectory. TCN-008 starts with a **desired result**: a set of required output phase residues `(coordinate, relative_phase)` of a normalized constant-magnitude ray. The user does **not** supply the polynomial degree, coefficients, carrier family, source preparation, or host.

The compiler seeks the least-degree polynomial `f(y)` (maximum degree five, always `< p`), a computational basis input `|b>`, a transfer `D_a F`, a higher-degree phase carrier if necessary, and an available declared host such that

    |target>(y) = p^(-1/2) * exp(2πi * f(y)/p)
    f(y) = b*y + a*y² + c3*y³ + c4*y⁴ + c5*y⁵  (mod p).

The scalar phase at `y=0` is fixed to zero: the target is a relative-phase specification and does **not** make an absolute global-phase claim. The input `|b>` is a *resource*, not a free variable: a declared host must list it as a preparable source. `D_aF|b>` is supplied by the existing **TCN-003 exact Gauss-cocycle operator**; cubic phase is also cross-checked using the existing **TCN-006 moving-frame compiler**. Quartic/quintic phase carriers are a new explicit extension; those generators do not inherit TCN-006's full moving-frame algebra.

## Construct the space, don't forecast it

The compiler tries polynomial degrees 0 through 5 in ascending order. Each candidate is calculated using exact modular Vandermonde elimination on a small subset of distinct prescribed coordinates, then checked against *every stated target constraint*.

- A degree-2 result uses the existing quadratic transfer family.
- A degree-3 target admits a nonquadratic cubic carrier only when a host declares cubic support.
- Degree-4 or degree-5 targets require an explicit higher-polynomial carrier on a suitable host.
- A family-cap violation produces a **finite algebraic obstruction**, not a claim that the target is incompressible or universally impossible.

**Minimality certificate:** the first `d` distinct coordinates uniquely determine a polynomial of degree `<=d-1`. If a further required coordinate contradicts it, there is no lower-degree solution for those constraints. This remains valid with incomplete intentions, but matching sparse constraints does **not** mean the completed state is uniquely determined outside those constraints. For a degree-six negative control, the first six points fix the only candidate degree-5 polynomial, and a seventh mismatch excludes every degree-5-or-lower family.

**Cost-aware placement:** each host declares (without proving or authenticating) its maximum supported degree, allowed basis-source preparations, costs for transfer/preparation/higher phase coefficients, and capacity. A global goal budget also applies. The compiler selects the least declared execution cost, then the lexicographically smallest host name for ties. It distinguishes `realizable`, `refused_budget`, `unreachable_with_declared_hosts`, and `unreachable_in_degree_5_family`. These are mathematical/planning statuses over the *declared host menu*, not an E-CPU hypervisor admission decision.

## Computational semantics and work

- Intent reading and full-constraint validation cost O(m · d) modular arithmetic for m specified coordinates and degree d<=5; solving each degree uses at most a fixed 6×6 modular system. Discovering the representation is **not** O(log p).
- The successful Ground stores <=6 finite-field coefficients plus one source coordinate. Given the declared generator capabilities, one output coordinate uses O(d) arithmetic; constructing all p complex amplitudes costs Ω(p) because of output size.
- `D_aF|b>` uses the existing symbolic full-phase TCN-003 Gauss cocycle. The additional diagonal carrier is represented as exact modular polynomial residues. Complex exponentials are evaluated at *rendering* time and carry floating-point rounding; no error-free real arithmetic is claimed.
- Long coordinate indices are first reduced mod p. The 100-digit coordinate example is an alias in a finite field, not a newly realized future state.
- Independent reference evaluation uses a dense `numpy.fft.ifft` from basis `|b>`, followed by the explicitly constructed diagonal phase. This tests numerical agreement for the stated synthetic operators, **not** an independently observed physical host.

## Deliberate tests that can fail

1. Supply a cubic intention with hosts that can execute only quadratic operations: refuse; then add a cubic-capable host and reconstruct the target.
2. Supply quartic/quintic intentions: cubic support alone does not help; adding a higher-polynomial carrier does.
3. Supply a degree-six or pseudorandom full target: refuse **only the implemented degree<=5 family**, carrying an exact mismatch witness.
4. Supply a source coordinate unavailable on the host: refuse even if the polynomial is otherwise representable.
5. Supply an adequate host but an insufficient cost budget: `refused_budget`, not `unreachable`.
6. Supply only a few target coordinates: honor those exact constraints without falsely claiming all other outputs are specified.
7. Independently render and compare entire p-dimensional state vectors for primes 7, 11, 31 and 127, degrees 0..5; compare cubic cases against the existing TCN-006 implementation.
8. Tamper with a receipt and recompute its *unkeyed* hash: verification recomputes the mathematical solution and refuses the false result. This does not authenticate the author, source, or external system.

## Reproduce

From the root of In-Formation-Space:

```sh
python -m pip install numpy
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/quadratic_transfer_grounds -p 'test_intention_ground.py' -v
OPENBLAS_NUM_THREADS=1 python experiments/quadratic_transfer_grounds/run_intention_ground.py
```

The TCN-008 test can also run alongside older `test_cocycle.py`, `test_moving_frame.py`, `test_inverse_ground.py` suites to guard against regressions.

## Integration interpretation

E-CPU has execution-admission and mathematical-law-certification contracts; VGI has typed operator navigation and an explicit distinction between observation, admitted Ground, and replay. TCN-008 does **not** bypass them. Its receipt records the complete stated intention, the *declared* hosts, selected mathematical Ground, finite certificates, a deterministic SHA-256 digest, and `authenticated_hosts=false`, `external_realization_witnessed=false`.

To realize a target on E-CPU, an independent admission stage would need to authenticate the host and capabilities, authorize the phase gates and source preparation, witness execution through authenticated transport, verify the resulting observable, and bind that evidence to the intended result.

## Known open work

This is a deliberately narrow proof-of-concept: it does not infer goals from language, synthesize arbitrary matrices or byte strings, infer physical dynamics, or search open-ended abstract Grounds. A higher-degree polynomial phase is not universally cheap under arbitrary intervening Fourier gates; moving-frame noncommutativity may force more expensive representations or refusal. The host cost model measures declared units, not wall time or verified energy. Source-state preparation and global phase are explicitly scoped and should remain so as the system expands.

## Related mathematics

Classical finite-field polynomial interpolation and the prime-dimensional diagonal Clifford hierarchy give relevant mathematical context. See Cui, Gottesman & Krishna, *Diagonal gates in the Clifford hierarchy*, Physical Review A 95, 012329 (2017), https://doi.org/10.1103/PhysRevA.95.012329 . This experiment applies established mathematics to an explicit synthesis/admission workflow; it does not claim a new universality theorem.
