# SPN-007 — Goal-aware compilation and independently checked direct-sum spectral Grounds

**2026-11-21 · width-three CNF · exact integer/rational arithmetic · standard-library Python**  
**Status:** a constructive, source-checked finite experiment. No general polynomial-time SAT, #SAT, P-versus-NP, or quantum-computation claim.

## Question

Can an observer select a computational language that makes an intended result inexpensive to construct, without hiding the cost of constructing that language? We preserve three observer goals: produce **some** satisfying assignment; establish the **exact ground energy**; or, if exact, count **all** ground states. A SAT witness is not automatically an exact-ground certificate, and a failed Ground construction is not an UNSAT proof.

SPN-001/006 construct signed, fixed-width Fourier descriptions and admit phase-compatible witnesses or contradiction certificates. SPN-007 adds an exact decomposition into *linearly independent parity subspaces*, then lets a goal-aware compiler try less expensive methods before invoking an existing decision-proof search. Its producer policy is a heuristic; its conclusions are admitted only by a checker reconstructing the original CNF's rational Fourier coefficients.

## 1. Mathematical theorem: independent parity Grounds

For a width-three CNF, define the integer nonnegative clause-violation energy

\[
 E(x)=\widehat E(0)+\sum_{S\ne 0}\widehat E(S)\chi_S(x),\quad
 \chi_S(x)=(-1)^{\langle S,x\rangle_{\mathbb F_2}}.
\]

Let the nonzero Fourier supports be partitioned into nonempty disjoint sets \(B_1,\ldots,B_q\), and write \(U_j=\operatorname{span}_{\mathbb F_2}(B_j)\). Require that

\[
 \operatorname{rank}\Big(\bigcup_j B_j\Big)=\sum_j\dim U_j.
\]

That **rank-additivity condition is checked**, not assumed from source-clause disjointness. The spans then form an internal direct sum. For each \(j\), define \(f_j(x)=\sum_{S\in B_j}\widehat E(S)\chi_S(x)\). It depends on only \(r_j=\dim U_j\) binary parity coordinates. Let \(\mu_j\) be its exact minimum over those \(2^{r_j}\) coordinates, with \(d_j\) coordinates attaining that minimum.

**Proposition (exact ground and multiplicity).** Under rank additivity,

\[
 \boxed{E_0=\widehat E(0)+\sum_j\mu_j},\qquad
 \boxed{|G|=2^{n-\sum_jr_j}\prod_j d_j}.
\]

Further, any choice of one minimizing local coordinate per \(j\) can be lifted to an original-variable assignment \(x\) attaining \(E_0\) by exact Gaussian elimination.

**Proof.** Select a parity basis for each \(U_j\). Because the combined basis has rank \(r=\sum_j r_j\), the linear map \(x\mapsto(\langle S,x\rangle)_{S\text{ in the combined basis}}\) from \(\mathbb F_2^n\) to \(\mathbb F_2^r\) is surjective, with every output having exactly \(2^{n-r}\) preimages. Therefore the local parity coordinates can be chosen independently. The energy is a sum of functions on those independent coordinates plus its constant term, so the minimum is their sum. The number of joint minimizing coordinate tuples is \(\prod_j d_j\), each with \(2^{n-r}\) original-variable lifts. Back-substitution constructs one of them. QED.

**Complexity statement.** With \(t\) nonzero Fourier terms and a known partition, exact component minimization uses \(\sum_j O(|B_j|2^{r_j})\) integer operations, plus polynomial-time GF(2) partition checking and lifting. Fourier construction costs \(O(m2^3)\) clause events. The fundamental-circuit partition producer uses elimination and term-index union-find; the independent verifier reconstructs rational coefficients and uses a *different* exhaustive XOR-span algorithm for each capped component. **When a single component has rank \(\Theta(n)\), the method refuses under its rank cap; no polynomial general bound follows.** Large integer arithmetic and serialized evidence bytes must also be accounted for.

## 2. Why source-variable overlap does not prevent factorization

The constructed family `shared_variable_cycle_cnf(B, frustrated=True)` contains \(B\) XOR-inconsistent parity triangles. All triangles share source variable \(x_0\) and the same auxiliary variable \(z\), and each triangle uses two distinct satellite variables \(a_j,b_j\). Each XOR equation is encoded by **four actual width-three CNF clauses**, pairing each forbidden two-bit assignment with both values of \(z\), so the auxiliary variable cancels exactly in the Fourier expansion. The \(j\)-th triangle demands

\[
 x_0\oplus a_j=0,\quad a_j\oplus b_j=0,\quad x_0\oplus b_j=1.
\]

These requirements conflict. Each triangle contributes an exact minimum of one violated parity equation. Its three Fourier supports are connected by one XOR relation and have rank two. Across triangles, the 2-dimensional spans are independent even though **every original triangle includes \(x_0\)**. Therefore, with \(n=2+2B\),

\[
 E_0=B,\quad r=2B,\quad |G|=2^2\cdot 3^B.
\]

At \(B=128\), this source has **258 variables, 1,536 width-three clauses, 384 nonzero Fourier terms, global Fourier rank 256, and 128 rank-two Grounds**. The producer evaluates exactly \(4\cdot128=512\) local parity configurations, constructs a 258-bit witness with energy 128, and the rational source-bound checker independently proves that 128 is the global minimum and that exactly \(4\cdot3^{128}\) assignments attain it. This is a 62-digit count (no global assignment enumeration). The satisfying-variant control changes the last equation to parity zero; it has ground energy zero and exactly four satisfying assignments.

A connected clause-primal graph is not a proof of an irreducible Fourier parity space. Conversely, low-dimensional Fourier components are **not** guaranteed on arbitrary formulas, and special parity families are already approachable by established algebraic and exact-inference methods.

## 3. Goal-aware compilation and source-bound proof grammar

`adaptive_ground_compiler.py` implements the following deterministic ordered policy:

1. For `goal='decision'`, try a direct **conditional-mean SAT witness**. If it satisfies all original clauses, stop; this does not claim exact ground energy.
2. Try globally compatible preferred Fourier signs, using Gaussian elimination. If a witness attains the source-derived termwise lower bound, issue an **exact ground** receipt (with multiplicity \(2^{n-r}\)); any inconsistent sign system is inconclusive.
3. Attempt the **direct-sum exact Ground**. Discover the fundamental-circuit partition and its ranks before spending exponential time on component minimization. Refuse when the largest component exceeds the declared cap. Otherwise emit local supports, exact minima, local multiplicities, and the global witness.
4. For `goal='exact_ground'`, if neither exact method is admitted, emit **UNKNOWN**. For `goal='decision'`, continue to an existing SPN-006 Gaussian circuit proof search. Only when `t<=24` and all \(t(t-1)/2\) possible support pairs fit within an explicit budget may the SPN-005 pair method be chosen instead. Each method has a separate proof-node budget.

The outer `SPN-007-adaptive-v1` receipt binds source SHA-256 and observer goal to a versioned proof. It carries result `SAT`/`UNSAT`/`UNKNOWN`, ground energy and multiplicity **only if exact**, nested source-bound proof, declared method, and untrusted producer observations. The verifier dispatches by proof kind and checks original-clause witnesses, rational coefficient minima, support coverage, rank additivity, joint attainability, and ground multiplicity; it does **not** trust producer timing, selection, or discovery counters. A registered `UNKNOWN` is not a verified impossibility result.

`verify_adaptive_json.py` is a **stateless JSON stdin/stdout checker** with a 2 MB input cap, tested by launching a new Python process. It rejects mismatched formula hashes and forged minima. It still imports proof/checker modules from the **same codebase**, and is **not** an independently implemented cross-language or formal-kernel verifier. SHA-256 relies on standard collision-resistance assumptions. Producer and checker both rely on Python big integers, exact `Fraction`, and the soundness of the specified rational source expansion.

## 4. Reproduced measurements and tradeoffs

`adaptive_ground_campaign.py` reproduces the previous 90-instance random seed `73176` with the same `(n,m)=(8,34),(10,43),(12,51)` groups (30 formulas each; 69 SAT and 21 UNSAT), and exhaustive SAT truth references. `adaptive_ground_results.json` is the record of **one local CPython run**; wall times are uncalibrated and not stable performance claims.

| Decision portfolio (90 instances) | SPN-006 Gaussian | SPN-007 adaptive |
| --- | ---: | ---: |
| Correct SAT/UNSAT decisions | 90 | 90 |
| Cumulative producer+self-check wall time | 858.2 ms | 1,044.7 ms |
| Proof-search nodes across all instances | 648 | 595 in 37 fallback cases |
| Direct SAT witness without fallback | included in baseline | 53 cases |
| Serialized output (all receipts, source clauses excluded) | 72,303 bytes | 134,086 bytes |

All 90 random instances had one full-rank Fourier component (largest ranks 8, 10, or 12), so the rank-three exact-ground shortcut refused in each case. The **adaptive approach is slower and more verbose in this sample**, despite reducing fallback-search visits. The strategy-selection, attempted decomposition, nested self-checks, and outer verification are not free. This negative control is deliberately retained.

For the constructed shared-variable family at \(B=24\) (50 variables, 288 clauses), direct-sum exact-ground production took approximately 2.0 ms and standalone source verification about 5.8 ms in the recorded local run. The goal-aware exact compiler took about 8.8 ms including verification. For \(B=128\) (258 variables, 1,536 clauses), the full frustrated exact-ground compiler took about 54 ms in that same run. Source-enumerated proof data, integer operations, and the source clauses remain part of the total computational account. These measured numbers do **not** imply any asymptotic superiority to conventional XOR solving, SAT, or PNG-001 factor-frontier elimination.

## 5. Reproduction

From `experiments/pnp-ground-navigation/spectral_phase_navigation`:

```sh
python -m unittest -v test_direct_sum_grounds.py test_adaptive_ground_compiler.py test_adaptive_transport.py
python adaptive_ground_campaign.py > adaptive_ground_results.reproduced.json
python -m unittest -q test_*.py
```

**Testing:** 19 new tests alongside 40 preceding tests = 59 passed locally under Python 3.13. The added suite includes source-linked proof tampering, inconsistent partition rejection, forged energies and multiplicities, 210 seeded random small-CNF cases checked against exact exhaustive minima and multiplicities, 75 additional random decision comparisons, 200 random support-partition checks, SAT/UNSAT/UNKNOWN controls, and proof verification in a fresh Python process. The CI workflow includes the new tests and campaign.

### What remains in development

- Test **the same formulas** against PNG-001's factor-frontier solver with matched preprocessing and independently validated factor certificates; no comparable PNG-001 timing claim is made here.
- Implement a separately written checker (another language or Lean formalization); different Python code paths and processes are useful controls but not independent foundational trust.
- Learn an evidence-backed compilation policy that avoids extra decomposition and verification work on dense formulas. Existing one-shot heuristics have not shown a general speedup.
- Explore observer-specific requirements such as a single SAT witness versus exact ground energy versus #SAT; charge for the Ground and the decoder, not just navigation.
- Test genuinely hard, high-width adversarial instances and authenticated cross-host transport; this run establishes only local serialized round trips.

**Core checkpoint:** the right coordinate system can turn a globally high-rank, source-variable-overlapping constraint family into independently solvable small parity Grounds, with exact, source-checked minimum, multiplicity, and one realizing assignment. Discovering such a decomposition *uniformly and cheaply for arbitrary inputs* remains open.
