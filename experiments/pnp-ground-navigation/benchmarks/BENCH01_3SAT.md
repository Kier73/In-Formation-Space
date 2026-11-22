# BENCH-01 — Direct 3-SAT: the first of twenty computational frontier challenges

**Research status:** executable, bounded 3-SAT benchmark and end-to-end source-checked evaluation; first local campaign recorded 22 November 2026. **Problem:** decide satisfiability of 3-CNF, an NP-complete problem. This is **not** a polynomial-time algorithm, a proof resolving P versus NP, a general UNSAT certificate standard, or an assertion that a state-space description computes its own result. **Milestone:** complete the actual problem input → generated interpreter → source-verified result → cost ledger → reproducible evidence path for a declared finite domain. When a given method cannot certify a result, the answer is `UNKNOWN`.

## 1. Experimental question and precise obligations

**Question:** Given an unfamiliar 3-CNF problem, does the problem-formed computation stack construct a useful interpreter, obtain a result that withstands independent source checking, and account for the price of constructing the interpreter? Which kinds of formula defeat its preferred structure? Can a separate proof-carrying solver already present in the research repos repair those failures?

For a declared `n`-variable source formula `F = ∧_i (l_i1 ∨ l_i2 ∨ l_i3)` (clauses may contain fewer than three literals), the observation contract is:

- **SAT:** emit a concrete, canonical complete assignment `a∈{0,1}^n` and evaluate **every source clause** on `a` again, outside the selected interpreter. A planted or compiler-provided witness is not accepted without that check.
- **UNSAT:** demonstrate a complete finite search, a verified algebraic contradiction, or a source-checked complete DPLL conflict proof. With ≤15 source variables, also compare against an independent literal exhaustive truth table. The current research verifier is not an externally audited LRAT or DRAT checker.
- **UNKNOWN:** construction, proof or execution exceeded the finite bounds; no UNSAT conclusion is licensed. A wall-timeout and a resource refusal are distinguishable reasons.
- **ERROR:** invalid input, failed worker, wrong witness, or failed independent comparison. CI fails for errors, not for honest unknowns.

The main experiment uses the previously implemented **SFI-002 source-derived Boolean/affine interpreter chooser** (`self_selecting_sat.choose`) and executes the chosen interpreter using `realize`. Optional `--refine` invokes SFI-003's recursive meta-SAT improvement; `--composite` invokes SFI-002's exact disconnected-component architecture. Optional `--spn-fallback` admits an *existing separate* solver only when the formed-interpreter route reports `UNKNOWN` or refuses source size: SPN-008's direct DPLL/complete-XOR producer, **independently checked by its own native verifier**. No new competitive solver was invented in this benchmark.

## 2. Complete implemented workflow

1. **Source admission:** parse strict ASCII DIMACS `p cnf n m` with comment/multiline support, exact declared clause count, nonzero and bounded literals, and an input byte/hash record. A file can be `.cnf`, `.cnf.gz`, or `.cnf.xz`; decompressed input is capped at 8 MiB. The `corpus` interface scans files in deterministic name order with a bounded maximum count. Malformed files produce errors rather than solver verdicts.
2. **3-CNF domain:** ordinary clauses of width up to three are accepted. For intentionally wider `instance --convert-wide` inputs, apply the standard auxiliary-variable chain. For a clause `x1∨⋯∨xk`, use `(x1∨x2∨y1)∧(¬y1∨x3∨y2)∧⋯∧(¬y{k-3}∨x{k-1}∨xk)`. All transformed clauses have width ≤3. This preserves **existence of models**, not necessarily the model count. Source-model projection is rechecked against the original formula. This option is not part of the default strict 3-SAT corpus.
3. **Construct:** invoke both SFI-002 candidates: a checked truth-table Boolean network reconstructed from the CNF itself, and a source-proof-qualified GF(2) affine representation. Charge the cost of both attempted constructions. Choose only an independently admitted machine under finite register/coordinate/partition bounds; no output label can make an infeasible interpreter feasible.
4. **Optional native self-use:** run the existing SFI-003 meta-SAT gate-selection optimizer (`--refine`). Its improved gate set is audited using the original source; it may be slower than the original for a one-shot workload.
5. **Execute:** produce actual SAT work through SFI's native execution/partition receipts. Each source witness is normalized: SFI's affine engine can return an `n`-element bit vector, while the non-affine engine returns a decimal state. This transport distinction was discovered during the benchmark and addressed explicitly.
6. **Optional native proof fallback:** after `UNKNOWN`, use SPN-008 `produce_direct_sat` and *replay* `verify_direct_sat` against the same 3-CNF. Valid decisions include an original-source SAT witness, fully resolved DPLL conflict tree, or truth-table-checked XOR dependency; if the SPN proof-node budget also exhausts, retain `UNKNOWN`.
7. **Verification:** outside the subprocess, independently evaluate the SAT witness against the original source and compare all returned decisions on `n≤15` to exhaustive truth tables. Wrong small UNSAT results, false models and fixture mismatches raise errors. SPN-008 itself rechecks its nested proof in the worker. This is not a malicious-OS isolation or authenticated message channel.
8. **Budget and measurement:** one fresh Python subprocess per formula; kill on a wall-clock timeout; never call this UNSAT. Record source variable/constraint counts, semantic SHA-256, chosen architecture, generated register count, enumerated coordinates, construction time, execution time, total parent-observed wall-clock time, original source verdict, and reference work. **Process startup overhead is included** in the wall-clock record.
9. **Portability and audit:** the dedicated GitHub Actions matrix runs Windows/Linux × Python 3.11/3.13, the full test file, deterministic campaign, and additional SPN-008 fallback jobs. Machine-readable JSON results are uploaded for each job. No extra Python dependency is required.

### Finite default limits

| Resource | Default | Purpose |
| --- | ---: | --- |
| Native SFI source variables | 64 | Prevent overclaiming outside constructed interpreter budget |
| Native SFI source clauses | 400 | Keep local truth-table candidate discovery bounded in this campaign |
| Candidate coordinate states | 65,536 | Complete negative answers require full coverage |
| Native free registers | 16 | Protect complete enumeration |
| Native work partitions | 128 | Enforced by predecessor SFI code |
| Per-instance wall-clock | 6 s in suite; 8 s for standalone | Terminate out-of-budget attempts as UNKNOWN |
| Independent truth-table reference | `n≤15` | Reference from original clauses only |
| Optional SPN-008 proof nodes | 8,192 | Full proof must fit or remain UNKNOWN |
| Optional SPN source variables / clauses | 1,024 / 5,000 | Explicit separate direct-solver admission |
| Decompressed DIMACS | 8 MiB | Bounded corpus ingestion |

All timings are observations, not mathematical complexity bounds. The worker limits are wall-time and input-shape limits, not a portable OS memory quota. The SPN fallback is opt-in so the direct contribution of the problem-formed machine can be measured separately from the fallback.

## 3. Utilities actually used and adjacent capabilities

The table distinguishes **direct runtime use**, **inherited/transitive use**, **adversarial/verification use**, and **researched but not used**. A file being useful in another repo does *not* mean this experiment executed it.

| Repository and concrete utility | Role in BENCH-01 | Usage status |
| --- | --- | --- |
| **IFS** [`self_selecting_sat.py`](../self_selecting_sat.py): `choose`, `realize`, `choose_composite` | Source-driven selection of multiple finite interpreters and exact disconnected-component factoring | **Direct**; composite opt-in |
| **IFS** [`morphic_sat.py`](../morphic_sat.py): `compile_ground`, `seeded_circuit`, partition executor | Local CNF-derived Boolean functions (truth tables, not named gate primitives); deterministic non-affine circuit fixtures | **Direct fixture / native via selector** |
| **IFS** [`morphic_verifier.py`](../morphic_verifier.py): `verify`, `check_partition` | Independent replay of gate semantics, clause partitions, and actual work segments | **Inherited through native selector** |
| **IFS** [`derived_ground.py`](../derived_ground.py), [`derived_verifier.py`](../derived_verifier.py), [`self_forming_sat.py`](../self_forming_sat.py) | Reconstruct and independently prove GF(2) equations/resolution-derived constraints; build affine SAT interpreter and aggregate its partition results | **Inherited through native selector** |
| **IFS** [`recursive_sat_compiler.py`](../recursive_sat_compiler.py): `refine`, `audit_refinement` | Use SAT on gate selection itself to improve interpreter construction | **Direct via `--refine`**; independently tested |
| **IFS** [`spectral_phase_navigation/direct_sat_compiler.py`](../spectral_phase_navigation/direct_sat_compiler.py): `produce_direct_sat`, `verify_direct_sat` | Existing source-checked DPLL and exact-XOR engine supplies certified decisions where SFI's structural route refuses | **Direct opt-in `--spn-fallback`**, exercised by matrix CI |
| **IFS** [`construction_memory.py`](../construction_memory.py) | Previously admitted changing-source constructions can be reused and reverified; repeat-workload research | **Inspected; not reused in one-shot campaign**. No uncharged cache warm-start |
| **VL-I** [`problem_formed_sat.py`](https://github.com/Kier73/VL-I/blob/main/src/vli/problem_formed_sat.py) (PFI-004) | E-CPU-based software fabric execution of source-qualified SAT partitions | **Existing adjacent implementation**; not invoked by this subprocess benchmark |
| **VL-I** [`problem_formed_revision.py`](https://github.com/Kier73/VL-I/blob/main/src/vli/problem_formed_revision.py) (PFI-005) | Source-equivalent machine revision and qualified current publication ownership | **Existing adjacent implementation**; outside current benchmark |
| **E-CPU** [`computation_dag.py`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/computation_dag.py), [`owned_network.py`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/owned_network.py), [`virtual_layer.py`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/virtual_layer.py) | Typed dependency/frontier admission, actual software FIFO transmission and Hypervisor-authorized local execution | **Inspected / available through VL-I**, not exercised by this specific runner |
| **E-CPU** [`transferable_execution_claim.py`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/transferable_execution_claim.py), [`fenced_effect_receiver.py`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/fenced_effect_receiver.py) | Quorum-fenced work result publication and effect safety when hosts change | **Inspected**, not claimed by this SAT timing campaign |
| **VGI** [`PROOFGROUND_NAVIGATION.md`](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/docs/PROOFGROUND_NAVIGATION.md) and proof-search adapters | Future proof-state/missing-information reasoning | **Considered**, no Lean kernel or VGI qualification claimed |
| **Navigable-Compute** [`NCR-006`](https://github.com/Kier73/Navigable-Compute/blob/main/docs/NCR-006.md) / [`NCR-007`](https://github.com/Kier73/Navigable-Compute/blob/main/docs/NCR-007.md) | Exact observer-native affine / selected nonlinear quotients suggest alternate compact state construction | **Considered**, no NCR quotient used in this experiment |

The actual solver decisions in this milestone therefore originate in pre-existing IFS machinery, not from a synthetic mock of the whole five-repository fabric. This isolation is intentional: it makes mathematical efficacy measurable before adding network placement and recovery costs.

## 4. Development and experimental log

**2026-11-22: baseline inspection.** Confirmed SFI-001–004, SPN-008–010, VL-I PFI-004/005, native E-CPU authorization/recovery code, VGI ProofGround and NCR finite observer quotients. Chose to add an evidence/benchmark layer rather than a competing SAT implementation. Inspected [SAT Competition 2026 benchmark format](https://satcompetition.github.io/2026/benchmarks.html) and [UNSAT proof requirements](https://satcompetition.github.io/2026/rules.html). **No actual SAT Competition 2026 formula was run in the local seeded suite.** The `corpus` interface is ready to accept user-provided benchmark files, but the current numbers must not be compared with leaderboard results.

**2026-11-22: first integration problem.** The native affine path returns a list of bits for a SAT witness; the Boolean path returns a decimal string. The first benchmark incorrectly assumed only decimal strings. Fixed by deriving one canonical bitset from the declared `n`-bit vector, then applying a separate literal source evaluator in the benchmark. Added an explicit negative test for malformed bit vectors and false SAT models.

**2026-11-22: second integration problem.** The pigeonhole 5→4 fixture contains width-four clauses. Ordinary 3-SAT ingestion must not silently accept those. Added the explicit standard auxiliary-variable chain, tested its equivalence for 35 seeded small random CNF problems by independently checking *every* original assignment against the existence of an auxiliary extension, and preserved the distinction between SAT and #SAT transformation semantics.

**2026-11-22: third integration problem.** The composite SFI route returned local bit-vector witnesses and a variable map; the first assembly path tried to interpret those vectors as decimal strings. Fixed by normalizing each local witness and reconstructing the original variable assignment using the native component source map. The entire original CNF is checked after reassembly.

**2026-11-22: first complete 17-case single-process study.** Main campaign runs 17 independent subprocess workers with 6 s wall-clock per candidate, ≤65,536 candidate coordinates, and source-specific 15-variable exhaustive references. Results follow. At 3-SAT near the familiar hard random-clause density, even a source that *was generated with a known planted solution* often has no qualified compact interpreter: SFI is allowed to answer UNKNOWN. The refusal is informative, not a refutation of the problem.

**2026-11-22: revised portfolio experiment.** Added the existing, separately source-verified SPN-008 DPLL/complete-XOR engine behind `--spn-fallback`; SFI selection is attempted first, and SPN replays its proof against the unchanged 3-CNF before returning a final result. This distinguishes an interpreter failure from a problem failure. The dedicated GitHub Actions test also requires the previously UNKNOWN planted-24 case to return SAT and pigeonhole 5→4 to return UNSAT with native SPN evidence. Those checks are **not included** in the local SFI-only table and are not claimed locally without the upstream SPN source present.

**2026-11-22: parent-side publication verification.** During PR review, identified that the benchmark worker previously asserted `spn_original_proof_verified=True` without returning a proof object to the parent. Corrected this: the worker transmits its complete SPN-008 source-bound receipt, and the parent runs native `verify_direct_sat` against the original CNF before admitting SAT/UNSAT. A claimed proof flag without evidence, an empty-clause refutation without a source empty clause, and a native-SFI UNSAT without a bounded parent reference or parent-replayable proof are refused (the last becomes `UNKNOWN`). Added three adversarial checks. **Local suite: 20 passing, one SPN integration test skipped** in isolated execution. Parent SPN proof replay and cross-platform validation require GitHub CI evidence; worker proof-check flags are not authority.

### Recorded local SFI-only campaign

Environment: Linux x86-64, CPython 3.13.5, five reported logical CPUs in the research container. This is one uncalibrated run. `wall_ms` includes new Python-process startup, importing modules, construction, execution and independent parent witness/reference checking. Construction and execution numbers are emitted by the worker and should not be substituted for end-to-end wall-clock. See the adjacent machine-readable `BENCH01-results.json` for each canonical source SHA-256, exact counts, reference status, architecture and refusal reason.

| Instance | n | Clauses | Verdict | Interpreter | Coordinates checked | Wall time |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| `unit-sat` | 4 | 3 | **SAT** | Affine | 1 | 644.5 ms |
| `unit-unsat` | 3 | 2 | **UNSAT** | Affine | 8 | 660.6 ms |
| `php-3-into-2` | 6 | 12 | **UNSAT** | Affine | 0 | 602.2 ms |
| `php-4-into-3` | 12 | 34 | **UNSAT** | Boolean | 256 | 664.0 ms |
| `php-5-into-4` | 25 | 80 | **UNKNOWN** | undetermined | 0 | 815.1 ms |
| `clique-3-3color` | 9 | 21 | **SAT** | Boolean | 7 | 650.0 ms |
| `clique-4-3color` | 12 | 34 | **UNSAT** | Boolean | 256 | 707.6 ms |
| `planted-3sat-12` | 12 | 50 | **SAT** | Affine | 2,418 | 685.9 ms |
| `planted-3sat-16` | 16 | 68 | **SAT** | Affine | 64,101 | 1,832.1 ms |
| `planted-3sat-24` | 24 | 102 | **UNKNOWN** | undetermined | 0 | 683.7 ms |
| `planted-3sat-32` | 32 | 136 | **UNKNOWN** | undetermined | 0 | 726.9 ms |
| `planted-3sat-60` | 60 | 255 | **UNKNOWN** | undetermined | 0 | 789.9 ms |
| `planted-3sat-80` | 80 | 340 | **UNKNOWN** | none | 0 | 0.0 ms |
| `parity3-conflict` | 3 | 8 | **UNSAT** | Affine | 8 | 646.6 ms |
| `parity3-independent` | 9 | 12 | **SAT** | Affine | 1 | 703.2 ms |
| `circuit-8-3cnf` | 17 | 33 | **SAT** | Boolean | 110 | 998.5 ms |
| `circuit-16-3cnf` | 35 | 75 | **UNKNOWN** | undetermined | 0 | 673.1 ms |

**Interpretation:** source-checked SAT witnesses on 6 cases, source-qualified UNSAT results on 5, and source-budget refusals on 6. The 3-SAT near-threshold families at 24/32/60 variables were planted, so their `UNKNOWN` status is *not* actual UNSAT. 80 variables exceed the SFI input admission budget by design. The larger transformed non-affine case and PHP 5→4 also refuse a complete interpreter under the current budget. The optional SPN comparison is an explicit separate method and its time must be charged.

## 5. Independent adversarial checks

`test_bench01_3sat.py` covers: strict DIMACS parsing and declared clause counts; compressed input with bounded decompression; 35 random complete equisatisfiability comparisons for the width-reduction chain; literal truth tables of XOR encodings; pigeonhole and graph-colouring source reference truth tables; eight native SAT/UNSAT integration examples; component witness reassembly; opt-in self-refinement; very large problem guards; timeout→UNKNOWN; deliberately forged SAT models, false UNSAT reports, wrong expected SAT evidence, invalid affine vectors, and empty source clauses. The optional SPN proof-carrying native codepath is exercised in GitHub CI where the pinned upstream source is present. **This is behavioral testing, not a formal proof of the whole implementation.**

## 6. What the result establishes—and does not

Established: a reproducible SAT experiment can run actual problem-formed interpreters, expose failure cases, validate decisions against their literal source semantics, account for construction as well as execution, and reuse another preexisting proof-carrying solver when its structural method declines. The benchmark can ingest authentic DIMACS instances without pretending that its bundled seeded suite is the 2026 competition corpus.

Not established: a polynomial worst-case algorithm for SAT; a lower complexity bound; competitive performance against CaDiCaL, Kissat or other production SAT solvers; SAT Competition proof-checker compatibility; a strong security boundary across the benchmark worker IPC; unbounded space guarantees; or E-CPU authenticated live execution of these specific benchmark inputs. The local CI job uses independently launched subprocesses on one runner, **not** independent physical E-CPU hosts.

## 7. Exact reproduction

From the IFS repository root:

```bash
cd experiments/pnp-ground-navigation/benchmarks
python -m unittest -v test_bench01_3sat.py
python bench01_3sat.py suite --timeout 6 --output BENCH01-new-results.json
python bench01_3sat.py suite --spn-fallback --spn-nodes 8192 --id planted-3sat-24 --id php-5-into-4
python bench01_3sat.py instance fixtures/parity3-unsat.cnf
python bench01_3sat.py corpus /path/to/official-or-independent-DIMACS-files --limit 20 --timeout 12
```

Provide the uncompressed `.cnf`, `.cnf.gz` or `.cnf.xz` files yourself for external corpora. The parser verifies raw file digests and exact DIMACS structure, but does not automatically authenticate the benchmark publisher or install third-party solvers. The optional `instance --convert-wide` is explicitly a SAT-preserving reduction, not a model-count benchmark.

## 8. Next falsifiable question within problem 01

For actual 2026 competition benchmarks, how often is the cost of a problem-derived processor paid back before a good DPLL/CDCL solver finds a certificate? Benchmark the exact same source against (1) native SFI alone, (2) native SFI→SPN proof fallback, and (3) a pinned external CDCL baseline with independently checked SAT models and DRAT/LRAT proofs, reporting PAR-2 and proof bytes. Then test amortization when the same family is changed by constraints and SFI-004 can reuse a source-qualified construction.

Move to **challenge 02/20 (#SAT)** only after closing this 3-SAT implementation and its recorded verification checkpoint. #SAT will require exact counting, so 3-CNF auxiliary-variable satisfiability reductions are **not** sufficient for count preservation without additional proof obligations.

## 9. Recorded proof-carrying integration outcome (same challenge)

**CI source:** [BENCH-01 cross-platform run 45056995233](https://github.com/Kier73/In-Formation-Space/actions/runs/45056995233), commit `9c9ecc91e875c9a626011ba87478aa454ed19bf4`. All four jobs passed (Linux/Windows, Python 3.11/3.13); **21 tests passed per job without skips**. PNG-002 and PNG-003 predecessor workflows also passed. The post-PR implementation sends each native SPN proof back to the parent process, which invokes its original-source verifier before publishing a decision. This is still same-runner process isolation, **not** an authenticated E-CPU network receipt.

The seeded baseline **SFI alone** stayed at 6 SAT, 5 UNSAT, 6 UNKNOWN (17 source-bound cases). A separate opt-in **SFI→SPN-008** experiment checked three of the six previously UNKNOWN cases. These numbers are from the Linux Python 3.13 job log, single uncalibrated run; `wall_ms` includes process startup, native SFI construction, fallback, and parent source-proof verification.

| Previously unresolved 3-SAT instance | Native fallback result | Proof type | DPLL nodes | Wall-clock |
| --- | --- | --- | ---: | ---: |
| 5 pigeons into 4 holes, 3-CNF transformed (25 vars) | **UNSAT** | Complete source-replayed split/conflict tree | 61 | 229.14 ms |
| Planted random 24-variable 3-CNF | **SAT** | Source-replayed witness | 7 | 133.35 ms |
| Planted random 60-variable 3-CNF | **SAT** | Source-replayed witness | 20 | 272.38 ms |

**Scope of claim:** These three cases are independently admitted **only after switching from SFI's structurally formed interpreter to the separate SPN-008 proof-carrying DPLL path**. The other three baseline UNKNOWN instances were not part of this three-case fallback experiment and must not be relabeled solved without evidence. A native-SFI UNSAT without a bounded parent exhaustive oracle or replayable proof is explicitly downgraded to UNKNOWN. No production-CDCL performance comparison or official 2026 SAT Competition instance was run; external DIMACS support is ready, not an external benchmark result.

**Next falsifiable extension:** run a pinned external 2026 SAT benchmark corpus under uniform source, proof, resource and wall-clock contracts; compare native SFI alone, verified SFI→SPN, and a production CDCL solver with independently checked SAT models and certified UNSAT traces. Then measure whether SFI-004 structural memory amortizes compilation across related clauses. This remains challenge 01's research frontier, rather than claimed closure of arbitrary 3-SAT.
