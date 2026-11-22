# BENCH-01F — SAT constructs a policy for whether SAT should construct an interpreter

**Challenge:** 01/20 — direct 3-SAT, reproducible research continuation.  
**Date:** 2026-11-22 (America/Toronto).  
**Status:** implementation and bounded local adversarial tests completed; independently sourced, CI-executed results must be inserted from a real run before declaring held-out performance.  
**Scope:** finite 3-CNF source-only policy synthesis, existing SFI and SPN backends, immutable external-source cohorts, source-verified SAT/UNSAT/UNKNOWN, cost-qualified validation. **Not** P=NP, a competitive CDCL result, automatic code modification, or native E-CPU distributed execution.

## 1. The problem being tested

BENCH-01E demonstrated a negative result on six independently sourced random 3-SAT formulas near the difficult clause/variable ratio: SFI's structural interpreter refused all six within its finite coordinate budget, while the existing SPN-008 DPLL/XOR source-checking engine resolved all six; the production CaDiCaL 1.9.5 baseline was faster on that limited sample. Repeating costly SFI construction on sources that will predictably refuse is avoidable overhead.

The next question is **whether the existing proof-carrying SAT tools can construct a source-only policy deciding when to attempt a problem-formed interpreter, and whether this policy really repays its own construction cost on held-out sources.**

The policy is *not* a solver and never predicts SAT or UNSAT. It chooses one of two existing, independently verified execution paths:

* **Direct SPN:** existing BENCH-01 `_spn_worker` (SPN-008 `produce_direct_sat` and independent `verify_direct_sat`). The worker carries the original proof across the process boundary and the parent replays it. A timeout is `UNKNOWN`.
* **Formed then SPN:** existing BENCH-01 `_native_worker`, which first calls SFI-002's `self_selecting_sat.choose` and `realize`, independently checking constructed Grounds and witnesses. If it cannot settle the source under its budget, SPN-008 is invoked. A timeout is `UNKNOWN`.

Both methods consume the **identical original CNF**; neither uses publisher labels as mathematical evidence.

## 2. Repository review and exact utilities reused

| Location | Existing component | Applied here | Execution or qualification scope |
| --- | --- | --- | --- |
| **IFS** `experiments/pnp-ground-navigation/benchmarks/bench01_3sat.py` | `check_cnf`, `sha`, `satisfies`, `run_case`, `_native_worker`, `_spn_worker` | Runs both decision paths in separately bounded Python workers, checks source SAT witnesses, replays SPN UNSAT proof in the parent | **Executable**. Small modification: opt-in `export_spn_proof=True` returns a proof already verified by the parent for independent later replay. The old behavior remains default. |
| **IFS** `spectral_phase_navigation/direct_sat_compiler.py` | SPN-008 `produce_direct_sat`, `verify_direct_sat` | Solves the *meta-SAT policy construction problem*, independently rechecks its full source proof, then replays every large-source UNSAT observation | **Executable in the real repository / CI**. Isolated local checkout lacks this module, so local policy tests use a **complete exhaustive small meta-SAT oracle**, independently rechecked at audit. This difference is recorded, never hidden. |
| **IFS** `experiments/pnp-ground-navigation/morphic_sat.py` / `morphic_verifier.py` | Local truth-table interpreter and independent verifier | Used indirectly by the original `run_case` / `self_selecting_sat`; the policy does not replace either | **Native inherited execution**, not new implementation |
| **IFS** `self_forming_sat.py`, `derived_ground.py`, `derived_verifier.py` | Exact affine Ground, producer and independent verifier | Inherited candidate construction and original-source verification inside `self_selecting_sat.choose` | **Native inherited execution** |
| **IFS** `recursive_sat_compiler.py` | SFI-003 SAT-generated gate improvement and exact candidate-optimality audit | Reviewed as analogous self-use; intentionally *not* invoked in the primary performance baseline, which measures default SFI and direct SPN fairly | **Inspected, not run by the new policy** |
| **IFS** `spectral_phase_navigation/self_use_cycle.py` | SPN-010 SAT-chosen policy over fixed source features; training/validation/final separation | Its meta-SAT and independent policy-checking pattern informs this implementation; BENCH-01F selects between *different benchmark decision paths*, under stronger original-source proof and all-training-cost accounting | **Inspected, not duplicated as a solver** |
| **IFS** `bench01_external.py` | Immutable source pinning, `git_blob_sha1`, `run_cdcl`, parent SAT model check, nonauthoritative UNSAT exit | Reuses file authenticity and optional production-CDCL comparator on the final cohort. UNSAT accepted as corroborated only if SPN independently proved the same source UNSAT | **Executable in CI** |
| **VL-I** `src/vli/problem_formed_sat.py`, `docs/PROBLEM_FORMED_SAT_PFI004.md`, `docs/PROBLEM_FORMED_REVISION_PFI005.md` | Problem-formed SAT workloads, E-CPU routes, source-equivalent processor revision | Tracked as future execution target for *policy-selected* Grounds. No network-fabric invocation in this benchmark | **Cross-repository utility reviewed, not executed** |
| **E-CPU** `mailcpu/computation_dag.py`, `mailcpu/recovery_lineage.py`, IPS-008 receiver handoff | Native computational DAG, recovery and external-effect fencing | Potential later place for dispatch and survivor continuity. This policy grants no right to publish a result or alter a resource | **Reviewed, not executed** |
| **VGI** `PROOFGROUND_NAVIGATION.md` and Ground refinement | Exact / unresolved proof observations and AND/OR transitions | Vocabulary for qualified policy observations and `UNKNOWN`; no VGI proof kernel invoked | **Reviewed, not executed** |
| **Navigable-Compute** `docs/NCR-006.md`, `docs/NCR-007.md` | Construct exact observer-native affine and nonlinear quotients under budgets | Candidate structural feature source for a later policy, not measured in this benchmark | **Reviewed, not executed** |

This stage does not add an alternative consensus mechanism, new SAT engine, self-authenticated performance evidence, or implicit access to E-CPU's Hypervisor.

## 3. Source-only policy construction

For each source 3-CNF `F`, `source_features` performs one bounded scan of the original clauses and their incidence graph to compute six Boolean indicators:

1. `small_source`: `n <= 18`;
2. `sparse`: `m <= 2n`;
3. `repeated_scope`: at least two clauses have identical sets of variable indices;
4. `unit_clause`: a clause has width zero or one;
5. `high_hub`: a variable occurs in at least one-sixth as many clauses as exist;
6. `many_components`: the original clause/variable graph has at least two components, including isolated variables.

These features cannot inspect a witness, proof, publisher label, or result. They are cheap architectural heuristics, **not** mathematical claims about SAT complexity. The fixed hypothesis grammar is a disjunction of at most two selected features. The policy calls SFI first iff any selected feature is present; otherwise it calls SPN directly.

From paired, source-audited training observations, create a meta-CNF:

* An SFI-only decisive case or an SFI speed win of at least 15% requires at least one of its observed features to be selected.
* An SPN-only decisive case or an SPN speed win of at least 15% forbids each of its observed features from being selected.
* Nondecisive/tied cases impose no rule constraint.
* At most two selected features are allowed (all three-variable negative clauses).
* Long positive disjunctions are converted to **exact Tseitin OR chains**, each clause of width at most three.

The first local or native solver evaluates this *new problem about how the existing solver should operate*. SPN-008 supplies a source-bound SAT witness or complete UNSAT proof; a separate checker replays it. The implementation also independently enumerates all `2^6` possible rule masks (and the finite Tseitin auxiliaries) to check policy feasibility and identify the minimum training-time compatible mask. It refuses a forged meta verdict or a purportedly optimal but inferior rule selection.

An unsatisfiable policy meta problem yields a **default direct SPN policy**, not a claim about the input 3-SAT formulas.

## 4. Mathematical evidence and trust contracts

The output policy is a *construction decision*, never an answer certificate. The source SAT certificate remains an original-source witness or source-bound DPLL/XOR proof, independently replayed by the BENCH-01 parent. `UNKNOWN` stays `UNKNOWN`. For source widths at most 14, the observation auditor independently exhausts the full Boolean space to recheck UNSAT. For larger widths, it rejects an alleged UNSAT observation that lacks a **portable original-source SPN proof**; a worker's `source_checked=True` flag is not a proof.

Policy observations have source SHA-256, measured wall time, model when SAT, and complete nested UNSAT proof when applicable. An observation's outer checksum is *not* authentication, and wall-clock measurements cannot be made mathematically true by hashing. The verifier checks source/model/proof consistency; the benchmark's CI runner is the provenance of the *performance measurement*.

Meta-identity binds the exact ordered training observations and meta-CNF. Validation observations cannot duplicate training source hashes; final observations cannot duplicate training or validation. Recomputed outer policy hashes do not bypass verifier-side meta-SAT replay or optimal-rule enumeration.

## 5. Admission, charge for construction and independent test

A frozen policy is admitted only when the validation cohort demonstrates **all** of:

* zero loss of independently supported direct-SPN decisions;
* at least one decided baseline source;
* at least 5% lower measured total validation time than direct SPN;
* enough absolute saved time to pay for **both measured training backends on every training source** **plus meta-policy compilation**.

The validation pass adds source-feature computation overhead on every dispatched instance. When any condition fails, the frozen policy has an empty rule set, forcing direct SPN. No synthetic speed benefit is assumed. The final cohort is inspected only *after* the policy is frozen, and is never used for admission. Its results are still allowed to be worse; that is a normal negative result.

**Caveats:** exploratory feature-engineering and cohort selection can still overfit, even if source hashes are disjoint. Timing is one per method per instance and includes subprocess startup and source verification. It does not prove generalization. Training costs are explicitly accounted rather than declaring an amortized speedup from a one-off benchmark. The optional CaDiCaL comparator is baseline context, not the final policy's own source-proof checker.

## 6. Immutable external corpus

Source: [`TimurIbrayev/SATsolver`](https://github.com/TimurIbrayev/SATsolver), commit `b285082ead7a89f51f50c0dc3a937ddefa3328ee`. All twelve distinct files are independently checked using their **Git blob SHA-1**, original DIMACS shape and separately logged byte SHA-256. No publisher-provided `sat`/`unsat` directory name is treated as verification.

| Cohort | Sources | Dimensions |
| --- | --- | --- |
| Training | `sat50-01`, `unsat50-01`, `sat75-01`, `unsat75-01` | 2 × (50,218); 2 × (75,325) |
| Validation | `sat50-02`, `unsat50-02`, `sat75-02`, `unsat75-02` | Same dimensions |
| Final untouched | `sat50-03`, `unsat50-03`, `sat75-03`, `unsat75-03` | Same dimensions |

These are independently authored threshold-random 3-SAT formulas, **not** official SAT Competition 2026 Main Track instances. Official 2026 source manifest provenance was recorded in BENCH-01E but is not being falsely represented as executed in BENCH-01F.

## 7. Implementation log and measured evidence

| Stage | Action and observation |
| --- | --- |
| Repository survey | Inspected actual `bench01_3sat`, `bench01_external`, `self_selecting_sat`, SFI-004, SPN-010, VGI, VL-I, E-CPU, Navigable-Compute. Discovered reusable proof and policy mechanisms; no alternative solver added. |
| Implementation | Created `bench01_policy.py` with source-only features, exact meta-CNF, native SPN meta solving, independent optimal-rule audit, disjoint cohort checks, explicit cost admission and rejection. |
| Source evidence | Extended BENCH-01 `run_case` with optional `export_spn_proof=False` default. When enabled, an already parent-replayed native proof can be retained and independently replayed when training from a serialized observation. |
| Reproduction harness | Created `run_bench01_policy.py` with 12 exact Git blob pins, explicit training/validation/final cohorts, optional pinned CaDiCaL final comparator and output JSON. |
| Adversarial regression | Checks false models, changed source SHA, forged UNSAT despite `source_checked=True`, changed meta proof, changed rule list, source leakage, UNKNOWN preservation, invalid external file bytes, Tseitin truth-table equivalence, policy acceptance and policy rejection. |
| Local bounded tests | `python -m unittest -q test_bench01_policy.py` — **15 tests passed**. Combined with predecessor BENCH-01/01E tests: **49 tests passed, 1 optional SPN integration skipped** in isolated local sources. |
| External CI performance | **Executed and qualified.** Four successful PR CI jobs, Linux/Windows × Python 3.11/3.13, completed the actual SPN meta-SAT proof path and twelve pinned external source observations each. Evidence and figures are below. |

### Failure found and corrected during implementation

A test initially attempted to run the *training source* through the held-out dispatcher. The source hash check correctly refused it. The test was changed to evaluate an unseen but structurally comparable source. This refusal is intentional—admission cannot measure itself using the same instances that selected the rules.

The next design correction charged **both paired training executions** to policy admission rather than only the meta-SAT construction time. Earlier self-use experiments sometimes treated training observations as reusable preexisting evidence; this more stringent one-off benchmark asks whether the entire current cost is repaid *within the measured validation cohort*. The policy may therefore be rejected even if it appears to improve individual calls.

### Reproduction

From the repository root (no special setup for logic/regression tests):

```bash
cd experiments/pnp-ground-navigation/benchmarks
python -m unittest -v test_bench01_policy.py test_bench01_3sat.py test_bench01_external.py
```

From the same directory with internet and the pinned production baseline installed:

```bash
python -m pip install --only-binary=:all: python-sat==1.9.dev13
python run_bench01_policy.py /tmp/bench01f_sources --timeout 12 --spn-nodes 8192 --output /tmp/bench01f-results.json
```

The first invocation requires the existing IFS parent source modules. The second fetches exactly twelve allowlisted upstream sources, validates their Git blob identities, obtains two independently source-qualified backend results per source, builds one policy with native SPN meta-SAT, tests it on the validation cohort, freezes it, and only then reports final results. GitHub Actions captures the complete JSON including source proof receipts and the summary.

## 8. Next research obligations

1. Run true 2026 SAT Competition Main Track instances under size, memory, and time limits, preserving instance digests, original release, source-verifiable proof and *UNKNOWN* when outside the tested domain.
2. For larger CDCL UNSAT instances where SPN does not complete, integrate a correctly validated LRAT/DRAT certificate checker. A solver status alone remains `UNVERIFIED_UNSAT`.
3. Replace single timing samples with repeated, randomized-order trials, report distributions and true training amortization across multiple requests.
4. Explore inexpensive *source evidence of decomposable Ground structure* beyond six fixed syntactic features. Charge its analysis and verify usefulness on unseen families; do not fit to publisher labels or held-out results.
5. After qualification, expose policy-selected work to VL-I PFI-005/E-CPU under existing authority and recovery semantics, rather than importing local benchmark artifacts as publication rights.

**Scientific conclusion to date:** We have built a proof-qualified mechanism for SAT to construct an execution policy for its own interpreter, with explicit admission/rejection and full acquisition cost. General speed advantage, competitiveness and transfer to new SAT families remain empirical questions.

## 9. Executed external campaign — source-checked negative result

**GitHub CI:** [BENCH-01E/F run 45060293327](https://github.com/Kier73/In-Formation-Space/actions/runs/45060293327), four passing jobs (Ubuntu and Windows × Python 3.11, 3.13). Full original-source proof objects, source digests, selected policies and individual execution costs are in the job-specific artifacts `bench01f-ubuntu-latest-py3.11`, `bench01f-ubuntu-latest-py3.13`, `bench01f-windows-latest-py3.11`, `bench01f-windows-latest-py3.13`. **No solver label was admitted from the publisher's directory name.**

| CI job | Paired source observation + policy training | Direct SPN: 4 validation formulas | Frozen policy: 4 validation formulas | Direct SPN: 4 untouched final formulas | Frozen policy: 4 untouched final formulas | Candidate policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Ubuntu, Python 3.11 | 3,126.49 ms | 831.62 ms | 833.22 ms | 1,336.49 ms | 1,338.08 ms | Empty / rejected |
| Ubuntu, Python 3.13 | 2,835 ms (rounded) | 744 ms (rounded) | 746 ms (rounded) | 1,137 ms (rounded) | 1,138 ms (rounded) | Empty / rejected |
| Windows, Python 3.11 | 3,295 ms (rounded) | 933 ms (rounded) | 934 ms (rounded) | 1,409 ms (rounded) | 1,411 ms (rounded) | Empty / rejected |
| Windows, Python 3.13 | 1,988 ms (rounded) | 568.03 ms | 569.01 ms | 811.48 ms | 812.45 ms | Empty / rejected |

Each platform independently reproduced the same exact twelve source identities, **four source-verified SAT or UNSAT results in validation, four in final**, zero admitted coverage losses, and matching final CaDiCaL decisions. A CaDiCaL UNSAT status was accepted as corroborated only where the native SPN-008 proof independently refuted the same CNF. That is **not** a separately checked LRAT/DRAT certificate emitted by CaDiCaL.

**What actually happened:** The native policy synthesizer found no source-only feature rule that justified paying for SFI construction on the four training sources. It emitted the empty rule set; validation rejected any claimed gain and froze direct SPN. This is a successful **refusal and cost-accounting benchmark**, not evidence that adaptive selection beats a strong direct solver on these instances. The policy wrapper itself adds a small feature/digest scan overhead even with an empty rule set. This measured overhead is a candidate for a later verified implementation improvement, not a speedup claimed here.

### CI-driven correction of the implementation itself

The first BENCH-01F PR workflow run failed during the external campaign because `observed()` accidentally passed `max_source_vars` twice when composing the direct-SPN call. The original local unit tests had not exercised that argument combination. We fixed the call, added `test_worker_calls_respect_distinct_admission_budgets`, reran the **49-test** local regression suite, and verified all four real CI jobs. This test now asserts the direct path uses `max_source_vars=0`, the SFI-first path uses its declared source budget, and both request the already-parent-replayed portable proof.

### Interpretation and next implementation target

The result rejects a tempting but unmeasured assumption: a self-formed interpreter should not be preferred merely because it can be constructed. The cost of selecting, forming, proving and later executing it must be strictly better *for the requested family*. This cohort's 50/75-variable near-threshold random 3-CNF contains little local algebraic structure that SFI's bounded compiler can exploit; SPN solves it directly. A useful next trial must include **independently sourced structured and unstructured families** under preregistered source-only descriptors, then check if one frozen policy handles both. No claims about official SAT Competition 2026 entries, production CDCL proof certificates, or P=NP follow from this finite campaign.
