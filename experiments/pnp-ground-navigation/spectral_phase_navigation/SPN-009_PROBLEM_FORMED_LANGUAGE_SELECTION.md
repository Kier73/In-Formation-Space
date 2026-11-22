# SPN-009 — Intention-sensitive language selection on direct SAT

**Research state:** finite, executable, source-checked experiment, 21–22 November 2026. Python standard library. No assertion of P=NP, general polynomial SAT/#SAT, or a new SAT portfolio principle.

## 1. Question

Given a source CNF and an observer's declared intention, can a compiler cheaply choose a computational language that produces independently checkable evidence? If the same formula is presented for SAT *decision* and for exact *#SAT*, should the best interpreter be the same?

This work composes the existing In-Formation-Space projects rather than replacing them:

- **SPN-008:** ordinary width-≤3 CNF DPLL with verifiable SAT witnesses, complete UNSAT trees and sound `UNKNOWN`.
- **SPN-007:** exact signed-Walsh Fourier Grounds with source-reconstructed rank blocks, minimum energy and degeneracy.
- **PNG-001:** explicit factor-frontier exact model counting, with a min-fill-induced exponential-in-frontier-width cost.
- **SFI-001/PNG-003:** optional proof-producing formed interpreters, admitted only after replaying source-compilation evidence and evaluating all admitted original-CNF partitions.

These mathematical operations have different admissible conclusions. A SAT witness proves at least one solution; it does not establish an exact solution count. An UNSAT result requires either a complete refutation or independently validated exact zero count. An exhausted budget remains `UNKNOWN`.

**Prior art:** SATzilla and the broader per-instance algorithm-selection literature already use pre-solvers, cheap and expensive features, solver portfolios, and cost-sensitive selection. See [SATzilla: Portfolio-based Algorithm Selection for SAT](https://www.cs.ubc.ca/labs/algorithms/Projects/SATzilla/) and the [Handbook of Satisfiability chapter on algorithm selection](https://ada.liacs.leidenuniv.nl/papers/HooEtAl21.pdf). SPN-009 is not presented as a new general algorithm-selection theorem. Its distinctive research *testbed* is the exact correspondence between source constraints, Fourier coordinates, decomposable exact Grounds, evidence-carrying constructed interpreters, the declared goal and a cost ledger.

## 2. Exact proof contracts

The producer accepts DIMACS-style literals `±1..±n`, width at most three; an empty clause is allowed and directly certifies zero models. Its `goal` is one of:

1. `decision`: `SAT`, `UNSAT`, or `UNKNOWN`;
2. `count`: a decimal string containing the **exact number of solutions**, or `UNKNOWN`.

The verifier is given the *original source clauses and n*; the receipt's source digest must match their ordered JSON encoding. The digest is identity under collision-resistance assumptions, **not** a signature, certified host or remote provenance claim. The verifier disregards the selection policy and timing claims. It admits only:

| Receipt | What the independent source checker does | Claim admitted |
| --- | --- | --- |
| `empty_clause` | Confirms a literal-free clause exists | UNSAT / count 0 |
| `xor_count` | Independently truth-tables each complete clause scope, reconstructs equations, checks GF(2) rank/consistency; checks a witness for decision SAT | SAT/UNSAT and exact count for complete source XOR systems |
| `spectral_exact` | Re-expands original width-three clauses into the SPN encoding; replays SPN-007's exact-ground proof | SAT/UNSAT, exact count from zero-energy degeneracy |
| `frontier_replay` | Independently rebuilds factor tables and eliminates all variables with a separate implementation, checking claimed count and source witness | Exact count via **full reexecution**, not a short proof certificate |
| `sfi_count` | Replays PNG-003 source equivalence, reconstructs formed interpreter from proof, reexecutes each segment against original clauses | Exact count if complete SFI partition coverage is verified |
| `direct_decision` | Delegates to SPN-008 source-checked witness, DPLL conflict tree or semantically checked XOR dependency | SAT/UNSAT or explicit UNKNOWN |
| `unknown` | Checks only that the receipt explicitly refuses | No positive decision or count |

Producer telemetry, inferred cost, selected strategy and execution times **cannot** establish any truth claim. Because `frontier_replay` recomputes exact #SAT in the checker, its verification effort is fully included; calling this a succinct UNSAT certificate would be misleading.

The `sfi_count` path is admissible only when the SFI-001 sibling modules are importable. This experiment's local staging does **not** contain those sibling modules, so the SFI-specific unit test is skipped locally; the repository workflow is expected to exercise it in the complete checkout. SFI's construction/verification is deliberately *not* free advice.

## 3. Actual selector and charged features

Static, inspectable source policy (not learned, not an oracle):

1. Reject unsupported source encodings or an unsupported observer goal; admit source empty-clause zero count.
2. Try cheap complete source-XOR recognition; when it succeeds, eliminate equations exactly. Reconstruction may be done directly for decision.
3. On decision requests for large, highly concentrated clause-occurrence graphs, try a source DPLL **16-node pilot first**. If it fails, its effort is still charged and no verdict is inferred.
4. On eligible width-three source inputs, pay to construct signed Fourier coefficients and fundamental GF(2) components. Admit the exact spectral method only if all discovered components and their total enumerated states fit declared finite budgets. On ordinary decision SAT, use the costly spectral Ground only when the source exceeds a small-size gate and multiple independent components exist.
5. On counting requests with at least two source consensus-twin pairs, optionally try SFI-001's original-source evaluator with bounded free registers and a bounded number of partitions. Its proof-construction efforts count in total cost; a failed construction is not UNSAT.
6. On unresolved exact-count requests, calculate a deterministic min-fill factor-table size estimate, and execute PNG-001 only if the estimate fits the declared cell cap. Verification independently builds the source factors and counts.
7. On unresolved decision requests, run SPN-008 DPLL under the declared node budget. A budget miss remains `UNKNOWN`.

The policy is intentionally conservative, and all `observed_ms`, estimated table cells, inferred ranks, attempted methods, and receipt bytes are observable *work*, not verified facts about an unexamined source. The feature checks may cost more than the useful solver; benchmarking must include them.

The exact count from a Fourier direct sum follows directly from independent GF(2) coordinates: if the independent character-space components have ranks `r_j`, with `d_j` configurations attaining each component's minimum, the global minimizer multiplicity is `2^(n-sum r_j) * product d_j`. This equals #SAT **only when the independently checked global minimum energy is zero**. If the minimum is strictly positive, #SAT is zero. A ground-state count when the energy is positive is never mislabeled as #SAT.

### Executable reproduction

From `experiments/pnp-ground-navigation/spectral_phase_navigation`:

```sh
python -m unittest -v test_language_choice_sat.py test_language_choice_cli.py
python language_choice_campaign.py
python language_choice_cli.py examples/three_var_sat.cnf --goal decision --out decision.json
python language_choice_cli.py examples/three_var_sat.cnf --verify decision.json
python language_choice_cli.py examples/three_var_sat.cnf --goal count --out count.json
python language_choice_cli.py examples/three_var_sat.cnf --verify count.json
```

Receipts can travel as JSON. A separately started process receives the source CNF and checks the result. The checker still shares Python modules and mathematical assumptions with the producer; this is not a separately formalized Lean or independent-language kernel.

## 4. Same-source evidence and failure cases

Seeded campaign: 90 random width-three CNFs `(n,m)=(8,34),(10,43),(12,51)`; 30 planted SAT CNFs of the same sizes; one 12-variable pigeonhole UNSAT; eight connected source-variable-overlap spectral constructions; six complete XOR families; and one 3-variable guarded-XOR case. For the 121 small baseline formulas, independent full truth tables give exact model counts. The larger structured results have source-bound proofs; some count results are separately recomputed by PNG-001. One uncalibrated local Python 3 process; fixture generation excluded.

| Family | Cases | Chosen decision method | Chosen exact-count method | Selected decision total | Selected count total | Fixed direct decision total |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| Random CNF | 90 | 90 DPLL | 90 frontier | 91.9 ms | 1,763.8 ms | 56.5 ms |
| Planted SAT | 30 | 30 DPLL | 30 frontier | 28.8 ms | 523.9 ms | 15.6 ms |
| Pigeonhole | 1 | DPLL | frontier | 0.75 ms | 4.20 ms | 0.47 ms |
| Spectral overlap | 8 | 4 DPLL, 4 DPLL pilot | 8 spectral direct-sum | 17.8 ms | 70.5 ms | 9.6 ms |
| Complete XOR | 6 | 6 source XOR | 6 source XOR | 6.73 ms | 6.07 ms | 6.42 ms |
| Guarded XOR | 1 | DPLL | spectral direct-sum | 0.13 ms | 0.42 ms | 0.08 ms |

Local wall-clock observations are noisy and do not support speedup conclusions. **For these ordinary decision cases, the portfolio still loses to fixed DPLL in total measured time.** The direct pilot reduced the *eight overlap decisions* from about 63 ms to about 18 ms compared with the earlier policy on this machine, but fixed DPLL was still faster because it paid no selection overhead. Exact count is a different goal, so comparing those count times to decision SAT runtimes is not a like-for-like comparison.

The full `language_choice_campaign.py` also probes 15 seed-fixed random 3-SAT cases at `n=48,64,80` near a 4.26 clause ratio under a 256-node decision budget. The `n=80` sample returned `UNKNOWN` five times; `n=48,64` samples returned independently checked decisions. The larger sources were not independently exhaustively enumerated. `UNKNOWN` is a verified refusal rather than a hidden UNSAT label.

### What the experiment *does not* prove

- The language selector is a deterministic hand-written policy, not a general computational-language synthesis theorem.
- Random and planted CNFs here are small; the large cases are a finite seeded set, not a complexity-class characterization.
- A verifier replaying the whole count does not make #SAT polynomial-time.
- A structural feature such as source hub concentration, Fourier component rank or min-fill frontier width can be useful on selected families but does not imply low cost on every source.
- A hypothetical hindsight oracle that chooses the fastest method from *observed results* cannot be charged zero discovery work and called an executable algorithm.
- Neither the Fourier description nor a static interpreter specification establishes automatic physical execution, migration or quorum authority.

## 5. P versus NP — the tandem research obligation

The central difficulty is now a **total-cost, uniformity problem**. For a source CNF `F`, let `L(F)` be the *constructed* language/processor description, `N` its navigation, `V` its independent checker, and `W` the reconstruction of a source witness or accepted refutation. Any claimed universal polynomial SAT algorithm must bound the total cost of building `L`, running `N`, producing `W` and validating accepted results **uniformly over every input**, not merely on a selected fixture family. This is an immediate consequence of the NP-completeness of SAT, not a proof of P=NP.

In the tested families, the source state count, Fourier rank, direct-sum component ranks, factor-frontier width, algebraic nullity, producer proof size and verifier reexecution work are distinct parameters. A compact low-rank Ground is *not* necessarily the cheapest end-to-end method; a strong UNSAT proof can be much cheaper than counting all solutions; and the cheapest exact count may be an entirely different language than the cheapest decision witness.

**Next work:** construct a held-out benchmark where fixed DPLL, factor tables, source XOR, hidden algebraic SFI, and Fourier direct-sums each win on different cases; train or hand-design an honest, charged cost predictor without peeking at labels; measure regret and abstention on a separate split; and create an independently checkable *certificate of structural admissibility* before selecting execution. For high-width adversarial cases, preserve `UNKNOWN` and make compilation cost visible. Later, route and recheck selected partition receipts through E-CPU hosts with actual authenticated provenance; a JSON hash is not host authentication.
