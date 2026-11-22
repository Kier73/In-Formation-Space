# SPN-010 — The Ground compiler investigates and improves its own construction cost

**Status:** executable finite research stage; 21–22 November 2026; Python standard library. **P versus NP remains unresolved.** SPN-010 reuses the SPN-008 source SAT proof producer, SPN-009 intention-specific language compiler, and their independent source-replaying verifiers as instruments to evaluate and change the construction pipeline itself. The result is a small, transparent experimental **self-use loop**, not autonomous arbitrary source editing or a general-purpose synthesis theorem.

## 1. Why self-use matters

A useful compiler should investigate its *own* inference path, not just the external SAT instance. A source-bound transcript exposes which expensive tasks it performed: source recognition, a spectral transform, direct search, proof generation and source checking. We can observe those costs, propose an alternative order of operations, test the alteration on distinct sources, and reject it without turning a performance hypothesis into a mathematical theorem.

SPN-009's source code reveals two avoidable operations in decision SAT:

1. After it had already rejected a *complete source XOR encoding*, its DPLL fallback called SPN-008, which scanned for **the same complete XOR encoding again**.
2. Before its cheap `goal=decision, n<20` gate could refuse a spectral branch, it called `spectral_form` on the entire CNF anyway. On eligible larger inputs it constructed that exact same conversion **twice**.

SPN-010 modifies those existing implementations (not just a new parallel algorithm). SPN-008 accepts an expert-only `skip_complete_xor` producer hint; SPN-009 supplies it **only after it has already proved the source recognizer returned `None`**. That hint never carries proof authority: SPN-008's source-bound checker still recomputes every received witness, contradiction or explicit refusal. SPN-009 also now evaluates cheap conditions before building the spectral representation and passes its single result to downstream computation.

A wrongly asserted producer hint can cause an efficient XOR-only solve to become `UNKNOWN`. It cannot make the independent verifier accept an unsupported SAT or UNSAT result. It is therefore a performance permission, not a source-equivalence proof.

## 2. Use SAT to improve SAT's own strategy

`self_use_cycle.py` implements a finite, proof-carrying policy compiler:

- **Observe the earlier system.** For the *same source CNF*, call SPN-008 directly and SPN-009's full portfolio, independently validate both answers, and retain measured runtime, proof bytes and source digest. `UNKNOWN` remains explicit.
- **Construct the meta problem.** Six small source-only predicates are available: `many_variables`, `high_hub`, `scope_repetition`, `sparse_large`, `hub_and_repeated`, `dense_large`. Boolean variables mean **enable this predicate as a reason to try the more expensive portfolio**. A training case where direct SAT refuses but the portfolio proves a decision requires one applicable predicate. The reverse requires no selected predicate to match that case. Cardinality clauses restrict the number of selected predicates to at most two.
- **Solve with the system itself.** All 64 six-bit policy candidates are tested using SPN-008's *existing* source-bound SAT solver on the generated meta-CNF plus candidate unit assignments. The meta SAT constraints are 3-CNF; longer disjunctions use explicit Tseitin auxiliaries. Every meta verdict is independently checked. Among feasible models, prefer the lowest measured training execution cost, breaking ties by smaller rule sets. Meta-solving and verification are charged, not given as free advice.
- **Freeze and challenge the policy.** The policy holds its source-only guards, a canonical digest of its training observations, and the identities of training inputs. Performance evidence itself is observational; elapsed numbers can be falsified without falsifying SAT mathematics. A separate validation cohort decides whether to *admit the candidate improvement*. The final cohort is never used for this admission choice.
- **Use and verify the compiled policy.** The runtime recomputes its guard values from the new source CNF; a chosen backend emits an ordinary source-bound receipt. A separate `verify_self_use_receipt` checks policy/source binding, recomputes which backend was required, and then invokes the already-existing source proof verifier. Unknown remains unknown.

This is a conventional finite algorithm-selection model written as a meta-SAT problem. Its value is *using the existing interpreter and proof system to construct and test a subsequent interpreter*. No claim is made that this architecture has an asymptotic advantage over DPLL, CDCL, XOR reasoning, or SATzilla.

## 3. Negative control: the system refuses its own proposed improvement

`self_use_campaign.py` uses three disjoint source cohorts: **41 training**, **38 validation**, and **38 untouched final** CNFs, encompassing random, planted, high-overlap spectral, and complete-XOR instances. All accepted decisions are checked against original clauses, while run budgets of eight proof nodes deliberately produce some `UNKNOWN` results. The training stage validates all observation receipts again before constructing its meta-SAT problem.

One CPython local run produced:

| Stage | Result |
| --- | --- |
| Meta SAT search | 6 guard variables; 20 clauses; **64 source-checked meta SAT calls** |
| Feasible candidate sets | **22** within two-rule budget |
| Selected training rule | `hub_and_repeated` |
| Validation decisions | **29/38**, identical to fixed direct SAT |
| Validation observed cost | Candidate **67.78 ms** vs direct **56.46 ms** (single run) |
| Admission | **REJECTED**: no coverage benefit and no 5% cost advantage |
| Frozen final policy | Empty rule set -> direct SAT |
| Final decisions | **25/38**; the same 25 that fixed direct SAT establishes |

These are measurements in one local environment with small, deliberately chosen families; timings are not calibrated, may vary, and do not prove speedup or generalization. The complete, run-specific values, chosen policy and source hashes are in `self_use_results.json`. The learned source-feature rule was plausible and correct on its verified outputs, but insufficient as a speed improvement. Rejecting it is a positive outcome for the **development process**, not an algorithmic win.

The admission rule is explicit: reject any loss of coverage, and admit an equal-coverage candidate only if it is at least 5% faster on the validation observations; a verified coverage gain may be accepted with additional computation. This is a heuristic engineering threshold, not a statistical significance test. The final cohort is held untouched until after the decision. The policy is source-digest-bound, not authenticated to a remote host.

## 4. Positive control: profile-driven changes to existing code

`self_use_overhead.py` separately emulates the **precise redundant calls** removed from the predecessor implementation and executes source-checked decisions on 60 matched random small 3-SAT instances. Because this is an injected old-work emulation rather than a historical unmodified checkout, the strongest claim is the exact operation-count difference, not a measured old-release performance benchmark.

| Work on 60 matched cases | Emulated former path | Modified path |
| --- | ---: | ---: |
| Source complete-XOR recognition scans | **120** | **60** |
| Unnecessary spectral conversions | **60** | **0** |
| Decisions changed | **0** | **0** |

Four repeated single-process runs observed total old/new times of approximately `104.93/74.21`, `95.29/75.82`, `91.92/73.48`, and `89.17/70.87` ms, respectively. These are local wall times with source checking, not asymptotic bounds. An independent randomized test runs 162 additional non-XOR formulas with both full and prechecked producers, verifying identical proof payloads and the same decisions. The complete previous SPN suites are also rerun.

The **net effect** is an actual change to earlier code supported by reproducible operation counts, while the larger learned-policy proposal is retained as an explicit *failed optimization*. This distinction is essential: useful learning includes a record of when not to change the interpreter.

## 5. Verification and complexity obligations

The meta-CNF's domain consists of exactly six rule bits plus any auxiliary bits. At most 64 guarded assignments are tested, with verification for each. This finite design is not a universal synthesis algorithm. Training requires both source solvers and re-verification for every training formula; the final policy is not free precomputation. The choice is specific to the decision-SAT intention. The existing SPN-009 exact #SAT path remains available, unchanged by the new policy.

A verified meta-SAT model certifies that the selected guards satisfy **the encoded training constraints**. It does *not* certify that they are cost-optimal for an unseen workload. The compiler chooses lowest *observed training* cost among feasible models, and validation can reject it. Timing fields, selected rules, estimated savings, and identities are not mathematical proofs of future performance. No hidden ground truth labels or result-dependent rules enter deployment.

This work does not prove P=NP; it does not prove a polynomial-time universal policy learner or solver; and it does not turn SHA-256 digests into cryptographic execution authority. The source-ground checker remains the arbiter for every affirmative SAT/UNSAT claim.

## 6. Reproduce

From `experiments/pnp-ground-navigation/spectral_phase_navigation/`:

```sh
python -m unittest -v test_self_use_cycle.py
python -m unittest discover -p 'test_*.py' -q
python self_use_campaign.py
python self_use_overhead.py
```

The new tests include source-only policy selection, authenticated-to-source **content binding only** (not host authentication), a verifier replay of the meta-SAT model, anti-forgery checks, deliberate false producer hints, stable `UNKNOWN`, training recheck, train/final collision refusal and 162 paired non-XOR producer comparisons. The full local staged suite reported **87 tests passed or correctly skipped** (86 passed, one skipped because optional SFI sibling modules were not present in local staging). In the complete GitHub checkout, SFI sibling modules are included; CI is authoritative for that integration path.

## 7. Next frontier

Feed the self-use profiler into **compiler construction**, not just policy selection. A good experiment would let SPN produce multiple *sound source-equivalent transformation proposals* (e.g. clause normalization, affine reduction, or frontier decomposition), each accompanied by a replayable proof, then let the previous version of the compiler independently verify those proposals before promoting one. Separate verified semantics from unverified speed evidence and preserve a rollback path. More ambitious directions include proof-carrying program rewrites, a cross-process compiled Ground exchange with E-CPU, and hardware-calibrated time/bytes/energy accounting. Never let a policy optimize away the checker that makes its results admissible.
