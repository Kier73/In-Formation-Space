# PNG-001 — P versus NP through observer-native grounds: the price of constructing the coordinate

**Status:** mathematical synthesis + reproducible finite experiment, 21 November 2026. **No resolution of P versus NP is claimed.** The exact variable-elimination algorithm implemented here is standard; the contribution is a cost- and evidence-accounted experiment connecting it to the repositories' ground-navigation research.

## 1. The motivating question

The connected research program asks whether an observer can describe a needed result, construct the transformation space in which it exists, and navigate directly to a realizable instance, rather than replaying every intermediate step. For P versus NP, the crucial test is not whether the destination can be *named* succinctly; it is whether the **uniform process of constructing a usable coordinate system and decoding its answer** is efficient on every input.

SAT expresses this sharply. A Boolean formula F can describe the potentially huge set of satisfying assignments in O(|F|) bytes. Given an assignment a, evaluating F(a) is polynomial time. Determining whether *some* such a exists is NP-complete. A one-bit observer state, SAT(F), is maximally compressed as an output, but a compact output alphabet does not make its value easy to compute.

Clay Mathematics Institute continues to list P versus NP as unsolved: https://www.claymath.org/millennium/p-vs-np/ . Nothing here proves or refutes P = NP.

## 2. The uniform-ground compilation test (elementary proposition)

Let C be a **uniform deterministic** compiler, mapping each CNF F to a ground G_F. Let N be a deterministic navigator that returns whether F has a satisfying assignment from G_F. Suppose that on every input:

1. C(F) terminates within a polynomial in |F|, and therefore emits at most polynomially many bits;
2. N(G_F) runs within a polynomial in |G_F| and is always correct for SAT.

**Then P = NP.** Proof: the composition F -> C(F) -> N(G_F) decides SAT in deterministic polynomial time; SAT is NP-complete. This is a conditional, immediate consequence of standard complexity theory, not a new separation theorem.

It matters precisely because several apparently distinct achievements do **not** imply its hypotheses:

- A short description of a ground may take exponential time to discover.
- A ground may be easy to construct but prohibitively expensive to navigate or decode.
- A ground might be supplied as input-specific advice; that is not a uniform algorithm. A single advice string depending only on input length invokes different, nonuniform complexity notions (e.g. P/poly), not this proposition.
- A verified satisfying assignment proves a YES instance, but absence of such an assignment from a bounded search is not an UNSAT proof.
- Jumping to f^t(x) can be cheap even if deciding whether any x satisfies an inverse target remains difficult.
- More processors, a distributed fabric, or preexisting caches can lower latency but cannot be omitted from total work, communication, memory, construction, and advice accounting.

Proposed research accounting: retain separate measurements for T_description, T_ground_construction, S_ground, T_navigation, T_witness_reconstruction, T_independent_verification, bytes moved, and precomputation/advice. Never label only T_navigation as the total complexity.

## 3. Connections to the living repositories (studied, not copied)

- **In-Formation-Space, CKN-001/002:** causal kernels, orbit atlases, and product/cascade composition replace stepping with algebra or a precomputed atlas. Their own reports already count atlas investment and its applicability. [CKN-001](https://github.com/Kier73/In-Formation-Space/blob/4aa43ebfa27ec13161567edfd83074050bac3d47/experiments/CKN-001%20Causal%20Kernel%20Navigation/CKN-001%20Causal%20Kernel%20Navigation.md), [CKN-002](https://github.com/Kier73/In-Formation-Space/blob/4aa43ebfa27ec13161567edfd83074050bac3d47/experiments/CKN-002%20Composed%20Atlases/CKN-002%20Composed%20Atlases.md).
- **In-Formation-Space, CGS-001:** affine holonomy constraints over finite fields permit direct exact intersection and a proof of impossibility in this *special algebraic family*. The analogous question for general logical relations does not inherit that algorithm. [Source](https://github.com/Kier73/In-Formation-Space/blob/4aa43ebfa27ec13161567edfd83074050bac3d47/experiments/contextual-ground-sections/README.md).
- **E-CPU, IPS-001 / formal navigation:** periodic schedule CRT construction, interval over-approximation, and independently admitted path/intent receipts distinguish possibility, witness, and actual execution. [IPS-001](https://github.com/Kier73/E-CPU/blob/9d60818a73db8816d5d4f44047d67af81fb1d796/docs/INTENTION_PHASE_SYNTHESIS_IPS001.md), [Formal navigation](https://github.com/Kier73/E-CPU/blob/9d60818a73db8816d5d4f44047d67af81fb1d796/docs/FORMAL_NAVIGATION.md).
- **VGI:** an observer quotient needs future-semantic soundness; collapsing states too early can erase the distinctions needed to reach the goal. [Formalization](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/7a3c4a368d1d24044a6c06a317c26ef316513e6d/virtual_ground/build_20/VIRTUAL_GROUND_FORMALIZATION.md).
- **Navigable-Compute, NCR-006/007:** exact observer-native quotients avoid enumerating source states for declared affine and selected nonlinear Boolean systems. Their closure budget and refusal cases are central to the complexity question: what causes the future-observer basis to remain small, or grow? [NCR-006](https://github.com/Kier73/Navigable-Compute/blob/559a1a813012d13ed37c04e2a117467e34ed3cb1/docs/NCR-006.md), [NCR-007](https://github.com/Kier73/Navigable-Compute/blob/559a1a813012d13ed37c04e2a117467e34ed3cb1/docs/NCR-007.md).
- **VL-I:** self-describing interpreters and derived ground languages highlight a second question: can choosing the *right language* for an intention make it cheap to solve, while charging for deriving that language? [Interpreter self-ground](https://github.com/Kier73/VL-I/blob/4d3ad575607f33e6b16f9e7447c048ee0620291a/docs/INTERPRETER_SELF_GROUND.md).

The distinction connecting all these cases is: *the source state count, the observer output count, and the construction complexity of the exact observer interface are different quantities.*

## 4. PNG-001 experiment: exact frontier-ground SAT and #SAT

Represent every CNF clause as a factor f_i: {0,1}^{S_i} -> {0,1}. Their product is the indicator of formula satisfaction. For a variable v, collect the factors whose scopes contain v, join their products, and eliminate v by exact summation:

    g(y) = sum_{b in {0,1}} product_{f in bucket(v)} f(y, v=b)

All other factors are retained. After eliminating every variable, the remaining scalar is the **exact integer number of satisfying assignments** (#SAT, a harder counting task in the standard worst-case complexity sense). A witness is reconstructed by reversing the elimination history, choosing a value for each eliminated variable consistent with positive bucket products. The recovered assignment is checked directly against the original CNF.

Each eliminated variable exposes a compact *frontier ground*: a factor on the variables shared with the remainder of the problem. An exact relation is retained, not merely a Boolean saying "some local solution exists". The code chooses a deterministic min-fill order in the primal graph. It does not claim optimal treewidth and is not an original SAT algorithm.

For elimination order pi, let w be the maximum number of surviving variables in any generated factor. Explicit tables contain up to 2^w integer entries. The elementary tabulation algorithm has costs exponential in w, with additional polynomial factors for the number of factors and big-integer arithmetic. This is the measured price of the exact coordinate. For bounded w the formulation can be tractable even when n is large. If w grows linearly with n the tables can become exponential. Discovering the best decomposition is itself a computation and is not assumed free.

**Executable:** `python frontier_ground.py`; **tests:** `python -m unittest -v test_frontier_ground.py`; Python standard library only. The campaign checks every small case against a separate brute-force enumeration, in addition to 30 seeded randomized cases per n=2..8 in the tests.

## 5. Measurements (one local run, Python 3, 2026-11-21)

| Case | Variables | Count | Maximum surviving interface variables | Factor lookups | Generated table entries |
| --- | ---: | ---: | ---: | ---: | ---: |
| 96-bit equality chain + x1=1 | 96 | 1 | 1 | 855 | 191 |
| Same chain + x96=0 | 96 | 0 | 1 | 856 | 191 |
| Seed 73 random 3-CNF, m=48 | 12 | 0 | 9 | 24,454 | 2,047 |
| Seed 73 random 3-CNF, m=64 | 16 | 28 | 11 | 80,738 | 7,679 |
| Four mutually incompatible binary clauses | 2 | 0 | 1 | 12 | 3 |

`factor_lookups` counts actual table reads during bucket joins and may stop early on zero products. `generated table entries` counts the sum of table cells emitted during projection. The initial clause table entries and min-fill ordering effort are tracked separately in the machine-readable output; timing is recorded but intentionally not used for asymptotic claims. No extrapolation from the two random examples to average-case or worst-case complexity is justified.

**Negative control: local consistency is not global consistency.** The four clauses (x OR y), (x OR NOT y), (NOT x OR y), (NOT x OR NOT y) are *individually satisfiable* yet jointly UNSAT. An observer that remembers only a one-bit local satisfiable status for each clause destroys the necessary correlation and can report a false possibility. Exact interfaces preserve the joint relation; their width is the cost.

**Verification scope:** 8 unit tests passed locally; random small instances compared against exhaustive references, and all three campaign cases with n <= 16 were exhaustively checked. For n=96, validation is through exact elimination and direct witness inspection for SAT; the contradictory UNSAT run has not been separately enumerated and should be regarded as verified under the implemented recurrence plus unit-level cross-checks. No independent proof checker or external physical-host execution is claimed.

## 6. A possible research frontier: discover the *least sufficient interface*, not just the shortest path

The experiment suggests a sequence of falsifiable questions:

1. **Representation discovery.** Can constraints be recognized as affine-field holonomy, parity, a separable product, or another compact algebra before making explicit truth tables? Require a source-bound equivalence certificate, not an unqualified guess.
2. **Intention-relative sufficiency.** For decision SAT, counting #SAT, witness generation, and multiple follow-up queries, different frontier information may suffice. Can the compiler prove which distinctions can safely be removed? A one-bit output does not imply a one-bit *computable* interface.
3. **Width versus algebraic rank.** Compare explicit Boolean factor width, algebraic normal-form support, affine rank, decision-diagram nodes, and proof-system width on the same input families. A small parameter in one representation need not stay small in another.
4. **Proof-producing abstraction.** Pair every compression rewrite with independently checkable equivalence. For UNSAT, investigate standard clausal proof traces (e.g. resolution/LRAT) rather than assuming failure to find a witness proves nonexistence.
5. **Adversarial families.** Include high-width formula families, planted solutions, affine/parity relations, and instances whose locally coherent clauses hide a global contradiction. Record compilations that time out or overflow budget as `undetermined`, not `unsat`.
6. **Federated realization.** Ship authenticated factor/ground receipts between E-CPU hosts, measure bytes/latency/work, and ensure that a distributed speedup does not silently move exponential work into a provisioning step.

One operational conjecture worth testing is: **on practically important constraint families, the minimum exact intention-preserving interface under a discovered algebra may be substantially smaller than a conventional Boolean frontier**. This is a research hypothesis about useful classes, not a universal claim or a route around NP-completeness.

## 7. Proof-theoretic reality check

P versus NP is a uniform **worst-case** question. Success on 96 variables, large simulated time horizons, an efficiently reducible class of Boolean systems, or every observed benchmark is not a universal algorithm. A future claim should specify its algorithm over all bitstrings, its total (including ground construction) time, the precise correctness theorem, and why existing proof-method barriers do or do not apply. Important contexts include relativization (Baker–Gill–Solovay), the conditional natural-proofs barrier (Razborov–Rudich), and algebrization (Aaronson–Wigderson). They constrain certain proof techniques; they do not say progress is impossible. See [Aaronson–Wigderson](https://eccc.weizmann.ac.il/eccc-reports/2008/TR08-005/Paper.pdf) and [Clay](https://www.claymath.org/millennium/p-vs-np/).

**Core research proposition:** in navigation-based computation, the crucial resource may be the smallest *efficiently constructible and verifiable* exact observer interface, rather than the nominal number of states or length of the target coordinate. We can investigate that quantity without pretending to have solved P versus NP.


## Companion: SPN-001/002 spectral phase navigation

[SPN-001/002](spectral_phase_navigation/README.md) studies exact signed Walsh transforms of width-three clause-violation energies as an alternative observer interface. It demonstrates a SAT/UNSAT pair with identical Fourier magnitudes, phase-preserving conditioning, and separately checked SAT-witness/UNSAT-lower-bound proof receipts with explicit UNKNOWN when the proof budget is exhausted. The construction is complementary to this factor-frontier #SAT implementation; neither claims general polynomial-time SAT.

## PNG-003 — proof-carrying nonlocal algebraic Grounds

[PNG-003](PNG-003.md) extends direct XOR recognition to exact consensus simplification and bounded resolution-derived parity, with replayable proof DAGs and independent source equivalence/count checks. Its guarded and implication-chain fixtures demonstrate hidden affine structure while retaining measured proof-construction costs and explicit undetermined outcomes.


## OFG-001/002 — observer-fiber Grounds and shared-separator navigation

The [observer-fiber experiments](observer_fibers/OFG-001.md) construct exact nonlinear observer-relative information certificates over independent SAT factors. [OFG-002](observer_fibers/OFG-002.md) extends this to private CNF bags connected by a verified small separator. When the separator is hidden, it counts overlapping output rectangles by exact inclusion–exclusion and navigates the resulting union by symbolic rank/unrank without enumerating the global assignment product. The implementation includes [source](observer_fibers/separator_fiber_ground.py), [exhaustive/adversarial tests](observer_fibers/test_separator_fiber_ground.py), and a [cost ledger](observer_fibers/OFG-002-results.json). It measures information bits, construction work, evidence checking and realization separately; it does not assert general polynomial SAT.

Run from `experiments/pnp-ground-navigation/observer_fibers`:

```sh
python -m unittest discover -p 'test_*.py' -v
python run_separator_fiber_ground.py
```

## OFG-003 — frontier-derived, cost-aware observer navigation

[OFG-003](observer_fibers/OFG-003.md) reuses PNG-001's actual `min_fill_order` to discover bounded separators from the original CNF, checks the resulting bag factorization, constructs independently verified OFG-002 local observer fibers, and optimizes which offered separator bits to observe under declared costs **before** knowing the measurement values. The intended output projection is invariant under separator selection. Its source-bound certificate supports partial-separator conditioning, exact union cardinalities, witness rank/unrank, cost-ledger replay and fresh-process verification. [Executable source](observer_fibers/frontier_observation_planner.py), [23-test combined regression suite](observer_fibers/test_frontier_observation_planner.py), and [measured ledger](observer_fibers/OFG-003-results.json). The planner uses a conservative structural-work price, not an inferred physical observation cost; arbitrary sources exceeding the decomposition budget are refused.

```sh
cd experiments/pnp-ground-navigation/observer_fibers
python -m unittest discover -p 'test_*.py' -v
python run_frontier_observation_planner.py
```


## CIG-001 — Intention-equivalent cut Grounds: one CNF, three exact observations

[CIG-001](cut_intention/CIG-001.md) constructs source-bound SAT, exact #SAT, and coefficient-tensor cut-rank Grounds from **one original equality-CNF source**, with a separately implemented original-clause verifier, exact GF(2) small-matrix oracle, adversarial mutation tests, and measured construction/replay costs. For node cut S of a complete k-node graph with ℓ independent edge bits, its exact identities are:

\[
\log_2 \operatorname{rank} M_S=\ell |S|(k-|S|)=2\ell\|v_S\|_1,\qquad
\#\operatorname{SAT}(F)=2^{\ell \binom{k}{2}}.
\]

The rank can grow exponentially while a selected SAT witness or #SAT result has a short, independently source-checkable structural Ground. The complete relation's exponential rank remains valid; a symbolic rank certificate does not materialize or factorize the relation tensor. The experiment admits only equality pairs proven directly from the original source clauses and refuses modified sources.

Run from `experiments/pnp-ground-navigation/cut_intention/`:

```bash
python -m unittest discover -s . -p 'test_*.py' -v
python run_cut_intention.py > CIG-001-results.reproduced.json
```

The study connects [PNG-001](frontier_ground.py) exact frontiers, [SFI-002](self_selecting_sat.py) source-qualified language formation and [OFG-003](observer_fibers/OFG-003.md) intention-specific observers, with next experiments targeting cross-component source coupling and nonlinear rank certificates.

## CIG-002 — One clause, three observer-cut ranks

[CIG-002](cut_intention/CIG-002.md) continues CIG-001 using the **same original endpoint-equality CNF language plus a single extra source clause**, rather than trusting an external latent-bit annotation. The compiler reconstructs a bounded residual CNF from source-proved equality pairs and an independent verifier recomputes SAT, #SAT and the exact GF(2) node-cut matrix rank. For the same cut and model count, one added clause can **decrease, preserve, or increase** the rank of the full source relation.

For the 24-node, two-bit-per-edge family with 288 crossing label bits, all three two-label OR constraints have exactly \(3\cdot 2^{550}\) source models. Depending on whether the constrained bits are crossing/crossing, left/crossing, or left/right, their ranks are \(3\cdot2^{286}\), \(2^{288}\), or \(2^{289}\). The last case is particularly useful: **a constraint removes assignments while doubling the full matrix's rank**, demonstrating that solution cardinality is not a substitute for a specified observer representation cost.

The admitted active constraint vocabulary is deliberately finite (at most 14 active label bits). The 9 new test groups include randomized original-CNF exhaustive oracles, literal full-matrix rank checks, forged receipts, and contradictions. [Executable coupled compiler](cut_intention/coupled_ground.py), [independent verifier](cut_intention/verify_coupled_ground.py), [ledger](cut_intention/CIG-002-results.json). The existing PNG-001 frontier solver is invoked on the source-derived residual as a separately billed counting comparator in repository CI; no simulation or P-versus-NP worst-case claim is made.

## CIG-003 — Source-discovered nonlinear observer coordinates

[CIG-003](cut_intention/CIG-003.md) builds on CIG-001/002's **unchanged original endpoint-CNF source** but discovers exact local nonlinear functions from the additional clauses without gate annotations. It derives Boolean-ring ANF coordinates, forms an exact two-feature pullback Ground for each disjoint source-proved nonlinear gate, factorizes independently source-audited CNF components, and chooses bridge observations by a worst-branch **conditional cut-rank + declared acquisition-cost** objective. It distinguishes mathematically constructed observation plans from actual measurements and authority to execute.

In the 132-source-variable, 24-active-label, eight-gate case, source-checked counting uses **112 local assignments instead of 2^24 global assignments**; the exact model count is `7·4^6·2^42` and the cut rank is `3·2^34`. Two free source-equivalent nonlinear observations reduce worst conditional rank to `2^34`. The old CIG-002 14-active-label enumerator correctly refuses this case. The new local suite has 13 test groups (30 combined CIG-001–003). [Compiler](cut_intention/nonlinear_observer_ground.py), [independent original-source receiver](cut_intention/verify_nonlinear_observer.py), [cost ledger](cut_intention/CIG-003-results.json), [native cross-repo checker](cut_intention/run_cross_repo.py).

The `cig-003.yml` CI workflow runs the **actual IFS PNG-001, SFI-002, OFG-003 and pinned NCR-007 Boolean ANF pullback** against a shared small source; the observer rank policy is a distinct objective from OFG-003's fiber planner. On dense connected residual CNFs, CIG-003 refuses when a component exceeds nine active labels and hands the problem to future separator/junction-tree and more general nonlinear feature-closure research. This is a structured-family, fully charged experiment, not a claim of a uniform SAT shortcut.


## CIG-004 — Temporal nonlinear observer closure and future-aligned intention

[CIG-004](cut_intention/CIG-004.md) continues source-derived nonlinear ANF computation beyond CIG-003's single-step idempotent gate update. Original endpoint CNF is reduced using the existing CIG-001/003 proof path; ordinary local clauses are independently reconstructed as exact total Boolean functions, oriented by an **explicit max-variable convention**, and composed as a multi-stage simultaneous rewrite law. The original CNF describes precisely the law's fixed points, while arbitrary initial machine states may traverse intermediate non-CNF states.

The depth-four test derives the exact least future-invariant five-feature observer span for the output of a nonlinear dependency chain and independently checks its Krylov rank, every polynomial pullback, transition matrix and large-time navigation. The **eventual-time intention** forms a different exact observer: for all t≥4, the requested output equals `ab ⊕ ac ⊕ d`, one invariant Boolean feature. This is not equivalent to the full time trace at t<4. The source has 90 original variables, 106 clauses and exactly `2^41` satisfying assignments; the ordinary CNF witness is independently rechecked.

Fourteen new regression groups (44 total CIG-001–004) pass in the measured local Python 3.13 environment, including all 256 small source configurations, large logical-time coordinates, forged-receipt rejection and an initially incorrect matrix multiplication orientation detected and repaired by a nontrivial state witness. [Producer](cut_intention/chain_observer_ground.py), [independent receiver](cut_intention/verify_chain_observer.py), [benchmark ledger](cut_intention/CIG-004-results.json), [native PNG/SFI/OFG/NCR integration](cut_intention/run_cross_repo_chain.py). The CI workflow checks four Python/OS environments and pins NCR-007; native integration status must be checked separately from the local tests.

A compact eventual output does not make the search for such a coordinate uniformly efficient on arbitrary SAT. CIG-005 extends the test to multiple source-derived observer intentions and a certified nonlinear quotient.


## CIG-005 — Shared nonlinear observer languages and minimal eventual quotients

[CIG-005](cut_intention/CIG-005.md) extends the same original-endpoint CNF and source-proved repair-law architecture to a branching four-gate graph with three declared observers `(y,j,z)`. The full-future minimal exact GF(2) feature spans separately require 4, 3 and 4 coordinates; one jointly closed source-certified language needs **9** instead of 11. When all three observers are requested only after the source-derived stabilization horizon `t >= 3`, their three eventual readouts span three independent ANFs, while the **realized quotient has four observation values** and therefore needs only two binary coordinates. Its nonlinear missing readout is reconstructed exactly as `Z = Y AND J`.

The intention planner compares 31 subsets of five declared observation offers and selects `(j, y XOR j)` for **3 declared units**, with source-proved nonlinear decoder `(Y,J,Z)=(p0 XOR p1,p0,(p0 XOR p1)*p0)`. Prices are receiver-bound; no physical measurement price or authentication is assumed. Local tests: **20 new, 64 total** across CIG-001–005, including independent original-CNF witness/functional source replay, full small-state time checks, source-modification refusal and forged certificate rejection. [Producer](cut_intention/joint_intention_ground.py), [independent verifier](cut_intention/verify_joint_intention.py), [benchmark ledger](cut_intention/CIG-005-results.json), [native PNG/SFI/OFG/NCR integration](cut_intention/run_cross_repo_joint.py).

**Next:** source-adaptive observer-language discovery beyond the chosen ascending-variable orientation; periodic nonlinear dynamics; independently source-checked nonlinear decoder synthesis; costed physical measurement and host authority; adversarial worst-case and held-out SAT comparisons.


## CIG-006 — Source-selected temporal languages and hard-problem usage

[CIG-006](cut_intention/CIG-006.md) removes CIG-005's supplied max-variable orientation from the finite interpreter-choice experiment. From the unchanged 90-variable source, it independently verifies all **four** conflict-free complete choices among nine local orientation combinations. Their minimal whole-future GF(2) feature dimensions are **10, 8, 9, 9**; their selected-time exact nonlinear output codes require **3, 2, 3, 2 bits**. The cheapest candidate is source-fixed-point equivalent to its alternatives, but the source alone **does not select its off-equilibrium temporal behavior**. The compiler publishes `INTERPRETATION_AMBIGUOUS` with a witness whenever candidate future observations differ, and can publish only bounded finite-class consensus when all admitted candidates agree.

The [heavy SAT/#SAT campaign](cut_intention/CIG-006-heavy-with-milp.json) applies source-forming construction to **192-variable XOR SAT/UNSAT**, **240-variable heterogeneous nonlinear counting**, **480-variable independent graph-coloring contradiction**, pigeonhole, odd-wheel coloring, random 3-SAT and twelve held-out near-threshold random sources. Structural GF(2), original-clause component factoring and bounded proof-carrying DPLL are independently checked; larger **200/300/500-variable** random tasks retain honest `UNKNOWN` outcomes. **23 new tests, 87 total local CIG-001–006 tests** passed. The separate [native integration script](cut_intention/run_cig006_native.py) and [CI workflow](../../.github/workflows/cig-006.yml) target real PNG/SFI/OFG and pinned NCR code; check GitHub Actions independently before claiming CI results.

**Next:** receiver-authorized temporal law admission through VGI proof evidence; nested separator search for coupled hard CNFs; identical DIMACS source controls against certified CDCL with full end-to-end resource ledgers; formal proof obligations for language selection and nonlinear decoding.


## CIG-007–013 — Evolving, costed, intention-specific architecture Grounds

The complete [CIG research directory](cut_intention/) now includes the following successive source-qualified experiments. Each linked document specifies its independent verification scope, executable interfaces and cost ledger. Local regression and remote CI evidence are distinguished.

| Iteration | Mathematical capability | Implementation |
|---|---|---|
| [CIG-007](cut_intention/CIG-007.md) | Intention-resolving probe policies; Hall-deficiency decision Grounds | [Evidence](cut_intention/evidence_ground.py), [Hall](cut_intention/hall_ground.py) |
| [CIG-008](cut_intention/CIG-008.md) | Private affine elimination and overlapping Boolean interfaces | [Composition](cut_intention/composed_ground.py) |
| [CIG-009](cut_intention/CIG-009.md) | Regional conditional-count structural memory | [Regional memory](cut_intention/regional_memory.py) |
| [CIG-010](cut_intention/CIG-010.md) | Adaptive splits, merges, bridge regions and semantic operation reuse | [Adaptive Ground](cut_intention/adaptive_ground.py) |
| [CIG-011](cut_intention/CIG-011.md) | Costed source-derived architecture selection and contraction-tree optimization | [Architecture navigation](cut_intention/architecture_navigation.py) |
| [CIG-012](cut_intention/CIG-012.md) | Source-region identities independent of derivation trees; exact interface transfer and projection | [Architecture memory](cut_intention/architecture_memory.py) |
| [CIG-013](cut_intention/CIG-013.md) | Anticipatory retention of richer regional tables; verified source strengthening on visible coordinates; incremental forecast costs | [Retention planner](cut_intention/anticipatory_memory.py), [verifier](cut_intention/verify_anticipatory_memory.py), [ledger](cut_intention/CIG-013-results.json) |

CIG-013's eight-revision campaign reaches 2,048 connected variables, with exact counts and independently checked original-source witnesses. **196 local CIG tests pass**. The richer retention policy reduces total preparation, fresh-query and restriction-cell work to 160,072 cells versus 589,696 cold on that workload; full source audits, verifier operations and measured planning latency remain charged separately. The finite forecasts and retention price are declared, not learned. General dense SAT remains a separate research frontier.

Reproduce:

```sh
cd experiments/pnp-ground-navigation/cut_intention
python -m unittest discover -s . -p 'test_*.py' -v
python run_anticipatory_memory.py --sizes 32 256 1024 --output CIG-013-results.reproduced.json
```


## CIG-014–017 — Self-extending sufficient observation languages

| Iteration | Source-verified mathematical operation |
|---|---|
| [CIG-014](cut_intention/CIG-014.md) | Nonlinear predicate fibers, exact signed-union translations and sufficient anticipatory interfaces |
| [CIG-015](cut_intention/CIG-015.md) | Source-implication decoders, counterexample-guided fiber extension and exact multiplicity conservation |
| [CIG-016](cut_intention/CIG-016.md) | One-sided proof-directed refinement; preserve partial split evidence and recover complementary counts by conservation |
| [CIG-017](cut_intention/CIG-017.md) | Global paired-source sufficiency, source-proved affine and nonlinear circuit decoders, independent receiver admission |

CIG-017 reuses the CIG-014 union translator, CIG-008 parity extraction and paired-source count checker, and CIG-016 receiver. Its two symbolic routes construct and independently check decoders on 8,192-variable sources with 1,024 observed bits, without enumerating observation codes. The general paired-source route distinguishes sufficiency, insufficiency witnesses and unknown results; executable decoder formation is separately budgeted. On an already admitted 16-fiber cyclic source at 1,024 variables, one global proof replaces 16 local contradiction checks. See the [implementation](cut_intention/global_sufficiency.py), [independent verifier](cut_intention/verify_global_sufficiency.py) and [measured ledger](cut_intention/CIG-017-results.json). **258 local regression tests passed**; remote CI is reported separately.

Next: proof-interpolant decoder synthesis over the shared observation language, with independently checked source implications and explicit compilation costs.

## CIG-018 — Proof-derived executable interpolants

[CIG-018](cut_intention/CIG-018.md) constructs shared-observation Boolean circuits directly from independently checked resolution refutations. Exact two-copy source obligations distinguish sufficiency from concrete counterexamples. On shuffled mixed and parity chains with 4,095 original variables and 1,024 nonlinear observation predicates, scope-aware resolution constructs and verifies executable interpolants in approximately half a second locally, without observation-code enumeration. Pair-count-only elimination exhausts its budget on the larger parity controls. The [compiler](cut_intention/interpolant_ground.py), [independent checker](cut_intention/verify_interpolant_ground.py), [benchmark](cut_intention/run_interpolant_ground.py) and [ledger](cut_intention/CIG-018-results.json) retain full proof and cost evidence. **275 local regression tests passed**; remote CI is separate. Next: incremental shared proof DAGs and multi-output interpolant reuse.


## CIG-019–020 — Shared proof architecture and adaptive verified execution

| Iteration | Mathematical capability |
|---|---|
| [CIG-019](cut_intention/CIG-019.md) | Target-independent colored resolution prefix; independently checked target suffixes; shared multi-output interpolant DAG |
| [CIG-020](cut_intention/CIG-020.md) | Receiver-owned incremental circuit state; complete dirty-frontier verification; atomic event admission; adaptive full/delta realization |

Eight adjacent intentions on the 4,095-variable mixed CNF require 48,694 candidate resolution pairs instead of 390,271 independent pairs. The shared circuit uses 4,130 gates rather than 35,924. Across 256 random single-coordinate observation changes, the incremental interpreter checks 1,631 gates per side instead of 1,057,280 each in full evaluation. Broad changes and long parity propagation favor full evaluation; the adaptive policy measures abandoned delta work. See the source contracts and measured tables in the two research documents, the [shared compiler](cut_intention/shared_proof.py), [proof checker](cut_intention/verify_shared_proof.py), [event interpreter](cut_intention/incremental_decoder.py), [event receiver](cut_intention/verify_incremental_decoder.py), and reproducible runners. **297 local tests passed**; remote CI remains separate. No source reachability or physical observation authority is implied by a supplied input vector.

Reproduce from the CIG directory:

```sh
python -m unittest discover -s . -p 'test_*.py' -q
python run_shared_proof.py
python run_adaptive_decoder.py
```

Next: source-qualified temporal jumps for the proof-derived circuit, costed propagation prediction, and existing E-CPU authority/host realization for retained gate state.


## CIG-021 — Source-qualified temporal and inverse-time navigation

[CIG-021](cut_intention/CIG-021.md) composes the CIG-019 proof-derived decoder with a separately qualified nonlinear block-transport transition, and independently verifies its lifted finite functional graph. The largest source has 4,091 variables, 1,023 observed bits and 2,728 lifted vertices. Exact jumps to 10^1000+173 are checked by a separate binary-composition oracle. A reusable constructive section proves every observation code has a valid source realization. Inverse-time navigation joins local periodic constraints by CRT, finding the earliest full observation target in a system with exact period 614,889,782,588,491,410. **324 local tests pass** (27 new). Full preparation and receiver costs are documented; the explicit law is not inferred from static source constraints. Reproduce with [forward campaign](cut_intention/run_temporal_ground.py) and [inverse campaign](cut_intention/run_inverse_time.py); remote CI remains separate.


## CIG-022 — Intention as a temporal destination

[CIG-022](cut_intention/CIG-022.md) computes the earliest time satisfying specified outputs of the actual CIG-019 proof-derived decoder under CIG-021's independently admitted transport and universal source section. It decomposes mandatory signed gate requirements into temporal factors on their spatial-cycle supports, groups identical supports, and composes residue sets by generalized CRT. On a 3,110-variable shuffled CNF with 1,023 observations, the exact global period is 614,889,782,588,491,410; eight coupled output factors admit 128 time classes. From 10^1000+173 the earliest offset is 5,418,922,329,477,735. Grouping reduces candidate CRT pairs from 80,574 to 270, with identical results. A wide parity control honestly returns UNKNOWN. **333 local regression tests passed**, including 300 randomized inverse-output queries checked exhaustively in both factor modes. See the [compiler](cut_intention/output_time.py), [independent verifier](cut_intention/verify_output_time.py), [runner](cut_intention/run_output_time.py) and [ledger](cut_intention/CIG-022-results.json). Full preparation and verification costs are recorded; remote CI remains separate. Next: proof-directed disjunctive temporal factorization to avoid joint-period expansion for wide output cones.

