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
