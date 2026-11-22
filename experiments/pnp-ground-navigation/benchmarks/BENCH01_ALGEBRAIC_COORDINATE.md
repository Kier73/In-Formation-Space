# BENCH-01H — Algebraic-coordinate separation versus variable separators and direct SAT

**Research checkpoint:** 22 November 2026. **Challenge 01/20:** direct 3-SAT and exact #SAT observation. **Status:** bounded executable source-qualified experiment. This is **not** a new general polynomial-time SAT algorithm, a P=NP theorem, or an intrinsic speedup over CDCL. The repository CI exercises the native IFS modules; standalone local execution uses an explicitly identified fallback where SPN-007 is absent.

## Research question

Previous [BENCH-01G](BENCH01_STRUCTURAL_AUDIT.md) used a small *original-variable* observation to disconnect a coupled clause graph; a source-confirmed SFI-002 interpreter handled each resulting component. Can an exact change of coordinates reveal **independent algebraic components even when every original variable remains connected**, and can the resulting SAT and #SAT claims be independently checked from the original 3-CNF source?

## Mathematical construction and proof obligation

For a CNF `F` of **exactly three distinct literals per clause**, let `E_F(x)` be the integer number of violated clauses under source assignment `x ∈ GF(2)^n`. A clause that forbids local state `(b1,b2,b3)` contributes:

\[
1[\mathrm{clause\ violated}]
=\prod_{j=1}^3 \frac{1+(-1)^{b_j}(-1)^{x_{v_j}}}{2}.
\]

Thus its full energy has an **exact** Walsh expansion, using integer coefficients scaled by eight:

\[
8E_F(x)=c_{\varnothing}+\sum_{S\ne\varnothing}c_S(-1)^{\langle S,x\rangle}.
\]

Group the nonzero support masks into sets `C_i` such that their GF(2) spans `U_i` form an exact direct sum: `rank(∪C_i)=Σ_i rank(C_i)`. This is an algebraic condition, not variable-disjointness. Each rank-`r_i` component has a basis of parity observation masks and a cost `2^{r_i}` to enumerate all its coordinate values. Since the GF(2) map to the direct sum of coordinates is surjective, **every** combination of component coordinates is realized by exactly `2^{n-r}` source assignments, with `r=Σ_i r_i`.

For each component, calculate exactly its minimum scaled energy `m_i` and the number `a_i` of coordinates attaining that minimum. The global minimum is:

\[
8E_{\min}=c_{\varnothing}+\sum_i m_i.
\]

Because `E_F(x)` is nonnegative, `E_min > 0` establishes UNSAT without claiming any arbitrary component's energy is itself nonnegative. If `E_min=0`, independent minima can be chosen simultaneously, and exact model counting is:

\[
\#SAT(F)=2^{n-r}\prod_i a_i.
\]

The factor `2^{n-r}` is essential: ignoring it would undercount source assignments whenever the derived parity coordinates do not span the original variables. A concrete satisfying witness is reconstructed by solving the independent parity equations and then tested against **all original clauses**. The work is bounded by `Σ_i 2^{r_i}` plus support construction, coordinate linear algebra and **independent verification**. A component above the declared rank or cell budget returns `UNKNOWN`; a mere local failure is never an UNSAT proof.

The above identities are standard exact Walsh/Fourier analysis and GF(2) linear algebra. In the worst case one span can have rank `n`, so there is no general subexponential guarantee.

## Reused utilities: what actually runs and what was only inspected

| Repository | Exact module / utility | Status in BENCH-01H | Role |
| --- | --- | --- | --- |
| **In-Formation-Space** | `spectral_phase_navigation/direct_sum_grounds.py`: `fundamental_components`, `linear_coordinates` (SPN-007) | **Executed in full-repo CI**; isolated workspace has explicit offline fallback | Source-support fundamental-circuit partition and canonical GF(2) coordinate construction |
| **In-Formation-Space** | `morphic_sat.normalize` | **Executed** | Exact original 3-CNF normalization; separate verifier independently re-expands Walsh coefficients from original clause truth tables |
| **In-Formation-Space** | `benchmarks/bench01_separator.py`: `run`, `verify_receipt` | **Executed** | Same-input original-variable separator control, including source-replayed branch verification |
| **In-Formation-Space** | `benchmarks/bench01_3sat.py`: `run_case` with SPN-008 | **CI path** | Native source-proof DPLL/XOR decision baseline; parent replays complete proof, and timeouts remain UNKNOWN |
| **In-Formation-Space** | `benchmarks/bench01_external.py`: pinned `cadical195` baseline, external corpus download | **CI path** | Production CDCL comparator and exact Git-blob-pinned independent random 3-CNF; CDCL UNSAT receives no proof authority without separate verified refutation |
| **In-Formation-Space** | `self_selecting_sat.choose_composite`, SFI-002/003; SPN-006/009 | Inspected as prior machinery; affected predecessor tests **executed** | Distinguish plain original-variable decomposition and whole-problem affine compiler from Fourier-support decomposition |
| **Virtual-Ground-Interpreter** | `vgi.invariant_blocks.infer_coordinate_blocks`, `vgi.sparse`, `vgi.partial_attention` | **Inspected, not imported** | Their observer-relative factorization and explicit missing-evidence states motivated the experiment; typed operator blocks are **not** asserted equivalent to source CNF components |
| **Navigable-Compute** | NCR-007 exact observer pullback-invariant basis | **Studied, not imported** | Clarifies why exact observer coordinates can be much smaller than source-state enumeration, and why closure budget refusal matters |
| **E-CPU** | `mailcpu.computation_dag.NavigableComputationDAG`, `EvidencePathResolver` | **Inspected, not executed here** | Existing potential hosts for rank-independent computation and evidence-backed representation routing; a SHA-256 claim alone grants no host rights |
| **VL-I** | `src/vli/problem_formed_revision.py` (PFI-005) | **Inspected, not executed here** | Existing source-bound interpreter revision and native authority separation; no new activation or quorum protocol invented |

The next host integration should dispatch one independent parity-component task per verified rank component using **existing** E-CPU virtual-layer and DAG authority, rather than pretending a local for-loop is physically distributed computation. We do not claim that integration in BENCH-01H.

## Source-verifiable receipt architecture

`bench01_algebraic.py` binds the canonical source CNF and contains source nonconstant Fourier coefficients, support partition, each independent parity basis, coordinate maps, complete component minima, minimizer multiplicities, and the full original-source satisfying witness when found. Digests identify claims; they are **not cryptographic authorization or proof by themselves**.

`verify` uses a separate algorithm to reconstruct every coefficient from the original clause's **eight explicit truth assignments**, tests the support partition, recomputes all GF(2) ranks and independent-span conditions, checks that each source mask reconstructs from its declared coordinates, enumerates every eligible component value, recomputes minima/multiplicities, reconstructs and checks a source witness, and refuses unsupported status or model-count claims—even after an adversary recomputes the outer receipt hash. For `UNKNOWN`, the verifier enforces that no unsupported minimum is published.

## Experiment families, hypotheses, and controlled negative results

1. **Non-affine not-all-equal constraints:** Each block uses two genuine 3-literal clauses `(hub∨a∨b) ∧ (¬hub∨¬a∨¬b)` to exclude the all-equal states, leaving **three** possible `(a,b)` assignments for a fixed hub. The Fourier expansion of these two clauses has three even-parity masks with a **rank-two** subspace; independent blocks share the original hub variable yet have linearly independent support spans. The entire source has `n=2k+1` variables, `2k` clauses, and exactly `2 × 3^k` models. This is **not** an affine solution set (its model count is not a power of two). BENCH-01G's variable-cut path can also prove it, but requires conditioning the hub and reconstructing many separate interpreters; compare complete #SAT costs, not just yes/no SAT.
2. **Cyclic triple XOR:** `n` overlapping triple equations `x_i XOR x_(i+1) XOR x_(i+2) = b_i`, encoded with **four genuine three-literal clauses per equation**. For `3 ∤ n`, the cyclic triple-parity observation vectors are independent. All original variables are connected, and no single source variable disconnects the hypergraph. Expected: no BENCH-01G variable-cut admission, but native SPN-007 factorizes parity supports into many rank-one groups. Source-verified exact #SAT for the specified family is one.
3. **Contradictory triple XOR:** add the opposite parity requirement on one source scope. Expected: source-verified UNSAT when constant energy cannot fall to zero. This is not an assertion that all individual Fourier-component energies are positive.
4. **General strict 3-CNF:** a fixed seeded 16-variable formula with mixed clauses. Expected: a large irreducible support span and an honest rank-budget `UNKNOWN`. Native SPN-008 and CDCL may still solve it directly.
5. **Third-party random 3-SAT:** two instances from BENCH-01E's exact Git-SHA1-pinned 50-variable corpus, retrieved only by its existing source-verifying downloader. The algebraic system is expected to refuse without a small decomposition. Published labels never serve as proofs.
6. **96 seeded small formulas:** original truth-table exhaustive counting of all assignments, adversarial false minima/multiplicities/witnesses, rehashed modified supports, insufficient search budgets and invalid source clauses.

All measured times distinguish original construction, independent verification, variable-cut construction/replay, native SPN-008 result with parent proof replay, and CDCL engine time vs subprocess wall time. The CDCL solver has a different proof burden; its bare UNSAT exit is *not* labeled independently proven. **One-run timings are not a complexity theorem or a general solver ranking**.

## Reproduction

```bash
cd experiments/pnp-ground-navigation
python -m unittest -v test_algebraic_ground.py test_derived_ground.py test_frontier_ground.py test_morphic_sat.py test_recursive_sat_compiler.py test_self_forming_sat.py test_self_selecting_sat.py
cd benchmarks
python -m unittest -v test_bench01_algebraic.py test_bench01_separator.py
python run_bench01_algebraic.py --external --cdcl --spn --require-native --timeout 12
```

The workflow `.github/workflows/bench01-algebraic-coordinate.yml` installs `python-sat==1.9.dev13` (CaDiCaL 1.9.5), runs the cross-platform regressions, and saves actual JSON artifacts. The synthetic fixture source and the local offline result JSON are self-contained, but **only the CI artifacts qualify as proof that native SPN-007 and CDCL were executed**.


## Local checkpoint — isolated CPython 3.13.5

The finite benchmark and its independent checks were executed on a local isolated CPython 3.13.5 host **before publication**: **103 tests passed** (74 existing algebraic/non-affine/recursive/affine regression tests and 29 separator/new coordinate tests). The native SPN-007 files were absent in this isolated working directory, so the standalone fallback produced the coordinate partition; the full-repository CI **must** exercise `fundamental_components` and `linear_coordinates` directly before native reuse is claimed. All times below are one-run CPU wall times, include independent source checks for the algebraic path, and are not statistical benchmarks.

| Original-source 3-CNF | Variables / clauses | Algebraic status / exact #SAT | Algebraic full build + verifier | Variable separator |
| --- | ---: | --- | ---: | --- |
| Non-affine NAE-3 blocks | 15 / 14 | SAT / **4,374** | 1.55 ms | SAT, 4,374 models (16.77 ms) |
| Non-affine NAE-3 blocks | 25 / 24 | SAT / **1,062,882** | 2.42 ms | SAT, 1,062,882 models (25.90 ms) |
| Cyclic XOR SAT | 19 / 76 | SAT / **1** | 5.25 ms | UNKNOWN (4.15 ms) |
| Cyclic XOR SAT | 31 / 124 | SAT / **1** | 8.21 ms | UNKNOWN (8.72 ms) |
| Cyclic XOR SAT | 80 / 320 | SAT / **1** | 20.67 ms | UNKNOWN (50.01 ms) |
| Cyclic XOR contradiction | 31 / 128 | UNSAT / **0** | 8.01 ms | UNKNOWN (11.12 ms) |
| Unstructured strict 3-CNF | 16 / 52 | **UNKNOWN** | 4.15 ms | UNKNOWN (2.52 ms) |

The 25-variable NAE case is the crucial **non-affine** check: twelve independent rank-two components each have **three minimizers**, and the one-dimensional unused source-fibre contributes the factor two, giving exactly `2 × 3^12 = 1,062,882` models, without source-state enumeration. The cost comparison here is against the independently replayed BENCH-01G **#SAT** method, not CaDiCaL decision SAT, which has a different task.

The 80-variable SAT case uses exactly 80 independent rank-one Fourier components with 160 total local coordinate evaluations; its source has `2^80` assignments, but the source proof does **not** enumerate them. This is not a lower bound on another solver's time, and it is not an efficiency guarantee on arbitrary SAT formulas.

The only runnable production-CDCL comparison in this milestone is the **CI** cohort; the local isolated host does not have the pinned `python-sat==1.9.dev13` package. Do not compare the local Fourier timings to a solver that was not executed in that environment.

## Frontier and honest negatives

- This special-case algebraic method is excellent for original-variable-connected but linearly independent XOR descriptions. It is *not* a non-affine general 3-SAT algorithm, and affine Gaussian elimination is an established strong baseline for pure XOR instances.
- Original-variable source structure can be misleading: two large groups can share many variables and still be independent after exact GF(2) coordinate change. Conversely arbitrary 3-CNF can form one full-rank Fourier support component and require exponential work.
- In BENCH-01G, observation conditioning *creates* original-variable component independence; here, exact parity basis construction *finds* already independent algebraic factors. They are not interchangeable or guaranteed to coexist.
- A learned selector must charge the cost of detecting this rank structure and obtain *new* external test cohorts before claiming a generalization or speedup.
- Full E-CPU execution of support components, VL-I generated interpreter revision, VGI Ground provenance, and official SAT Competition 2026 Main Track datasets are subsequent integrations, not completed claims in this benchmark.

**Research direction:** combine low-cost source-only detection of parity support structure with the previously rejected BENCH-01F policy to decide when to *inspect* this algebraic representation; refuse it for general random formulas, preserve source-verified model counts, and reuse the constructed coordinate basis through SFI-004 structural memory when the source changes.
