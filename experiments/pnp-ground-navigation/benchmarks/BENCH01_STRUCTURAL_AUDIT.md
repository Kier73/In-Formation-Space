# BENCH-01G — Deep utility audit and source-qualified separator navigation for 3-SAT

**Research checkpoint:** 22 November 2026. **Challenge:** 01/20 (direct 3-SAT). **Status:** bounded, executable source-checked implementation, not a general algorithmic complexity breakthrough. This stage builds on [BENCH-01](BENCH01_3SAT.md), [BENCH-01E](BENCH01_EXTERNAL_COMPARISON.md), [BENCH-01F](BENCH01_POLICY_ADMISSION.md) and [SFI-002](../SFI-002.md). All measurements below were obtained locally on one host; the workflow records independent CI executions. We neither claim P = NP nor benchmark competitiveness against CaDiCaL.

## 1. Why a deeper repository audit mattered

BENCH-01F correctly rejected constructing an expensive specialized SAT interpreter for the externally sourced 50/75-variable near-threshold random CNFs. It would be an error to conclude that source-formed interpreter construction is useless everywhere. A productive follow-up is to search for *structural information overlooked by the whole-problem classifier* and determine whether selecting a small observation exposes efficiently realizable subproblems.

The audit found two actionable facts in the existing source code:

1. The `self_selecting_sat._decompose` source-reconstruction check accidentally assumed that independent components contain numerically consecutive variable IDs. A legitimate disjoint partition `{1,3}` and `{2,4}` failed even though its clauses are independent. This patch changes the variable check to compare the **sorted union** of component variables with the full source coordinate set. New permutation/interleaving tests demonstrate that variable names do not change semantic factorization.
2. The preceding SFI-002 experiment already demonstrated a **104-variable disconnected** mixed Boolean/affine CNF for which heterogeneous component execution succeeds, but inserting one cross-component clause makes ordinary factoring return `UNKNOWN`. A small separator can handle the *coupled* case without pretending the blocks are independent before the coupling is accounted for.

The next piece was therefore **not another SAT solver**: it is a source-qualified separator-construction stage that invokes SFI-002's original independently verified component interpreters. The method is classical cutset conditioning, not a newly discovered exponential-time improvement.

## 2. Repositories and the exact utilities inspected

The table explicitly separates **executed by BENCH-01G** from **inspected as a structural connection**. Inspecting an API or discussing an analogy is not a runtime integration.

| Repository / utility | Existing capability found in source | BENCH-01G relationship | Executed? |
| --- | --- | --- | --- |
| [IFS `self_selecting_sat._decompose`, `choose_composite`](../self_selecting_sat.py) | Exact variable-disjoint source partition; heterogeneous Boolean/affine sub-interpreters; source-count product | Fixes permutation bug; reuses *actual* composer after a complete, reversible source restriction | **Yes** |
| [IFS `morphic_sat.normalize`, `compile_ground`](../morphic_sat.py), [`morphic_verifier.verify`, `check_partition`](../morphic_verifier.py) | Source-normalized CNF and exact functional-gate interpretation | Original interpreter is used unchanged through SFI `choose_composite`; each accepted partition is re-executed against original residual CNF | **Yes**, through native SFI |
| [IFS `derived_ground`, `derived_verifier`, `self_forming_sat`](../derived_ground.py) | Proof-carrying GF(2) source rewrites and independently checked affine interpreter | Component selector may choose this exact alternate mathematical Ground; no new parity solver is introduced | **Yes**, through native SFI |
| [IFS SPN-006 `parity_obstruction_grounds.py`](../spectral_phase_navigation/parity_obstruction_grounds.py) | Proven parity-sign obstruction lower bounds | Candidate later source-qualification gate for mixed spectral subproblems; not a replacement for full source verifier | No |
| [IFS SPN-007 `direct_sum_grounds.fundamental_components`](../spectral_phase_navigation/direct_sum_grounds.py) | **Nonlocal** decomposition by dependencies among GF(2) Fourier supports, not just disjoint variable labels | Distinct, promising next generalization: complement variable separators with basis-dependent direct sums when hypergraph has no small cut | No |
| [IFS SPN-008 `produce_direct_sat`, `verify_direct_sat`](../spectral_phase_navigation/direct_sat_compiler.py), BENCH-01E CaDiCaL | Independently rechecked DPLL/XOR SAT and UNSAT, and production CDCL comparison | Controls remain the proper baseline; BENCH-01G makes **no** claim to outperform them | Not in this stage |
| [IFS SPN-010 `self_use_cycle`](../spectral_phase_navigation/self_use_cycle.py), BENCH-01F `bench01_policy.py` | Proof-checked policy training and honest held-out *rejection* | New separator discovery is deliberately an opt-in candidate to evaluate under the same cost-admission principle; no learned performance claim yet | No |
| [IFS SFI-004 `construction_memory`](../construction_memory.py) | Source-strengthening-safe reuse of checked Boolean interpreters | Potentially reuse component machines when only separator observations change; currently each branch re-forms and re-verifies | No |
| [VGI `vgi.partial_attention.score_partial_probe`](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/vgi/partial_attention.py) | Counterfactual, cell-specific information gain with **unknown/ambiguous** explicit | Motivated separating source-only *observation choice* from verification of every observation scenario; no VGI transition-system object is created here | No |
| [VGI `vgi.invariant_blocks.infer_coordinate_blocks`](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/vgi/invariant_blocks.py) | Exact common-coordinate partition for typed finite-ring operators | Analogous invariant: separate coordinates only if the source representation mathematically permits it. SAT graph connected components are **not** VGI finite-ring invariant blocks | No |
| [Navigable-Compute NCR-007](https://github.com/Kier73/Navigable-Compute/blob/main/docs/NCR-007.md) | Exact nonlinear observer-relative Koopman feature closure, bounded by emitted basis size | Candidate future extension beyond variable deletion: use provably sufficient *constructed features* as separator coordinates. Unproved quotienting is forbidden | No |
| [E-CPU `NavigableComputationDAG`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/computation_dag.py) | Bounded content-addressed DAG, ready/commit/snapshot and recovery | Each qualified separator assignment is a potential independent DAG frontier. This prototype is **local Python only**, not E-CPU execution | No |
| [E-CPU `EvidencePathResolver`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/evidence_path_resolver.py) | Bounded routes between *verified* semantic representations; edges do not execute or authorize | Suggests a future verified route: source CNF → conditioned source → component Ground → witness/receipt → original source | No |
| [VL-I `problem_formed_revision.py` / PFI-005](https://github.com/Kier73/VL-I/blob/main/src/vli/problem_formed_revision.py) | Native E-CPU claim-backed interpreter revision and source-witness translation | A conditioned component would need a distinct computational identity and fresh native publication authority; current local separator work does **not** transfer claims | No |

**Cross-repository conclusion:** the useful shared abstraction is *qualified semantic representation change*. E-CPU's evidence paths, VGI's partial observations, NCR's exact quotient, VL-I's revision Ground and IFS's SAT factorization address different parts of that problem. They cannot be silently swapped because their proof obligations and execution authorities differ.

## 3. Mathematical source contract

Let the source be an original 3-CNF \(F(x_1,\ldots,x_n)\). A selected cut \(S\subseteq\{1,\ldots,n\}\) of size \(k\le1\) is chosen by the **source clause-variable connectivity graph only**, before SAT answers or models are known. Every cut assignment \(a\in\{0,1\}^k\) is explicitly considered. Standard exact substitution gives \(F\vert_{S=a}\), including an immediate contradiction if any original clause becomes empty.

Let the verified residual factorization be

\[
F\vert_{S=a}=\bigwedge_{i=1}^{m(a)} F_{a,i}(x_{a,i}),\qquad
x_{a,i}\cap x_{a,j}=\varnothing\;(i\ne j).
\]

Every unassigned source variable, even one occurring in no clause, is carried into **exactly one** component. Therefore the exact number of models (when all computations complete) is

\[
\#F=\sum_{a\in\{0,1\}^k}\prod_{i=1}^{m(a)}\#F_{a,i}.
\]

For *decision SAT*, an independently checked full original-source witness from **any** branch proves SAT. UNSAT requires that **every** branch is refuted; incomplete components produce `UNKNOWN`. For exact model counting, **every** component of **every** branch must be complete. These identities are elementary: the cut assignments partition the original source models, and disjoint residual variables yield a Cartesian product. They say nothing about worst-case polynomial cost.

The producer chooses a one-variable cut only when its deletion genuinely splits a connected incidence hypergraph. It favors a smaller maximum remaining component, does **not** search arbitrary width-\(k\) cuts or use model labels, and returns `UNKNOWN` on connected unseparable cases. This is conservative and sometimes declines even when a direct solver would easily solve the source. Maximum supported cut size is one in this version.

The new checker independently reconstructs clause restrictions using its own literal interpreter and reconstructs connected components by graph traversal rather than the producer's union/find. It then **re-executes native SFI** to verify all branch results, with the existing `morphic_verifier` / `derived_verifier` beneath. The SHA-256 envelope binds the exact source and claimed receipt but is not an authentication mechanism. For the current bounded prototype, full rerun verification is intentionally expensive and **counted**. No third-party UNSAT or untrusted performance claim is accepted without a source-proof path.

## 4. Real reproduction and measured results

Run from `experiments/pnp-ground-navigation`:

```bash
python -m unittest -v test_self_selecting_sat.py test_morphic_sat.py test_recursive_sat_compiler.py test_self_forming_sat.py test_derived_ground.py test_algebraic_ground.py
cd benchmarks
python -m unittest -v test_bench01_separator.py
python run_bench01_separator.py
```

The stored [`BENCH01-structural-results.json`](BENCH01-structural-results.json) is the reproducible single-run local ledger. At source creation, the combined regression sweep passed **76 tests** across existing and new SAT modules, including eight random variable permutations, forged counts with recomputed digests, forged cut identity, original-source mutation, full-branch UNSAT, and refusal on a dense graph without a small separator.

| Source | Native ordinary composite SFI | Separator-conditioned result | Separator construction + execution | Independent source/interpretation replay |
| --- | --- | --- | ---: | ---: |
| Interleaved, 7 variables / 8 clauses | SAT, 16 models | SAT, 16 models | **4.51 ms** | **4.22 ms** |
| Cross-linked Boolean/affine, **63 variables / 185 literal-3-CNF clauses** | `UNKNOWN`, no model count | SAT, **196,608** models (cut variable 31) | **607.55 ms** | **667.02 ms** |

The larger source has two strongly structured but connected regions: an acyclic 24-gate non-affine Boolean network, and a 22-vertex cubic-graph system of exact 3-variable parity clauses with consistent charge. The one cross-region clause defeats naïve multiplication of component counts. The source-only cut of original variable 31 splits its two branches into two disjoint components apiece. Branch counts are **65,536** and **131,072**; verified recombination yields **196,608**. No annotated gate labels, hidden SAT answers or prescribed separator IDs are passed to the compiler. The branch witness is mapped back through the exact original variable IDs and tested against every original clause.

The comparison is deliberately not advertised as faster: the native ordinary composite returns `UNKNOWN` after about **35 ms**, while qualified separator construction plus verifier replay takes about **1.27 seconds**. The small source was already solved by the baseline in about **3.2 ms**; the separator adds cost. Those are single-host, single-run measurements without confidence intervals. The external CaDiCaL and SPN-008 prior measurements are on **different formulas**, so they cannot be used as a head-to-head speed comparison. Running those same two baselines against this pinned source is future work.

## 5. Corrections and adversarial lessons

- **Counterexample to an implementation invariant:** comparing a concatenated ordered list of component variable names with `range(1,n+1)` rejects correct interleaved partitions. The fix compares the sorted union; the clause partition and complete variable cover remain checked.
- **Counterexample to naïve source-factor multiplication:** even one connecting clause makes the factors dependent. A separator must be evaluated exhaustively before multiplying branch-local counts.
- **Forged counts:** editing a branch count and recomputing the outer hash is rejected by independent replay of the original CNF and native component interpretation.
- **Forged separator:** a claimed cut inconsistent with the source-only selection rule is rejected.
- **Source mutation:** a valid result for the old CNF is never a valid proof for a changed original source.
- **Unseparable graph:** a source with no useful one-variable cut returns `UNKNOWN` rather than claiming a universal simplification.
- **Producer/validator independence:** the first prototype just reran its producer; the admitted revision adds separate source-restriction and graph-connectivity reconstruction before the native SFI proof replay. This still does not constitute a formal proof kernel.

## 6. Next challenge-01 benchmark obligations

1. Run the **same** cross-linked and randomly relabeled benchmark cases through SPN-008 and CaDiCaL, charging proof generation and proof replay. If direct solving is faster, the admission policy should refuse separator construction on that family even though it is mathematically possible.
2. Replace the expensive per-branch replay with **portable, source-bound child proofs** and have an independent verifier inspect them without redoing all execution. Parent proof must bind source digest, cut assignment, projected component variables, SFI Ground digest, exact count/decision and partition coverage.
3. Extend separator discovery from original variables to exact GF(2) features, combining SPN-007's independently checkable nonlocal direct sums with NCR-007's observer-coordinate idea without confusing their distinct algebras.
4. If source-qualified performance merits deployment, run child branches as E-CPU native `NavigableComputationDAG` operations under VL-I PFI's current claim/Hypervisor authority. Digest identity alone is not permission to publish or mutate effects.
5. Retain the exact observed failure and optimization in SFI-004 structural memory, but accept future reuse only after source semantics and independently measured benefit are both rechecked.

**Bottom line:** source-verified *which observation should split the problem* is a different computational question from *which interpreter should solve the whole problem*. It is a useful, bounded additional mechanism, not a general SAT breakthrough.
