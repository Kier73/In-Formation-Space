# Translation Discovery Log — TDL-003

**Continuation:** [TDL-004 — Intention-formed observer hosts and typed communication routes](TRANSLATION_DISCOVERY_LOG_004.md) integrates the existing SAB-001 host/path admission and reports a semantic output-type identity requirement exposed by its first execution tests.
## From minimal information to affordable, admitted observations

**Round:** 2026-11-22. [TDL-001](TRANSLATION_DISCOVERY_LOG.md) · [TDL-002](TRANSLATION_DISCOVERY_LOG_002.md) · [VL-I TDL-003 technical contract](https://github.com/Kier73/VL-I/blob/main/docs/COST_AWARE_REFINEMENT_TDL003.md)

**Research method:** reconstruct the source implementation as mathematics, then use the mathematical form to discover a different optimization objective, implement it, and compare it against independently verified evidence. **I** = source implementation, **M** = deduction, **O** = observed execution, **H** = next experiment.

## TDL-003/A — Minimum additional bits and minimum measurement cost are distinct

**I — code:** [`plan_cost_aware_observations`](https://github.com/Kier73/VL-I/blob/main/src/vli/cost_aware_refinement.py) takes the two independently verified VL-I PFI-001 interpretations and a finite set of `ObservationOffer` records: source-space GF(2) row, positive declared cost, offer ID, and proposed observer-locus label.

**M:** the minimal independent information deficit from TDL-002 remains

\[
d=\operatorname{rank}([B_o;B_n])-\operatorname{rank}(B_o).
\]

The new decision is which offered rows \(A_S\) to acquire, selecting the least-cost subset satisfying

\[
\boxed{\operatorname{rowspan}(B_n)\subseteq
\operatorname{rowspan}([B_o;A_S]),\qquad
S^*=\arg\min_S\bigl(\sum_{i\in S}c_i,\ |S|,\operatorname{IDs}(S)\bigr).}
\tag{TDL3-A1}
\]

When offers can include vectors outside the requested new observer span, a minimum-cost solution can require **more than \(d\) measured bits**. Example with old observer \(x_0\), new intention also needing \(x_1\):

| Offer | Declared cost | Information |
|---|---:|---|
| direct | 10 | \(x_1\) |
| cheap-left | 1 | \(x_1\oplus x_2\) |
| cheap-right | 1 | \(x_2\) |

The last two reconstruct \(x_1=(x_1\oplus x_2)\oplus x_2\), for total cost 2 instead of 10. Here \(d=1\), but the cost-minimizing set has 2 measurements.

**I:** the optimizer exhaustively enumerates at most \(2^{12}=4096\) declared subsets and selects a deterministic cost/count/ID minimum. A separate verifier uses combinations enumeration, independent GF(2) rank elimination and source-space row equality. This makes optimality a checkable contract within the current bounded candidate domain.

**H:** benchmark a scalable exact or admissible-bound cost solver on larger observer catalogues and compare with matroid-greedy rules restricted to the target observer span. Distinguish declared price from measured host transport/energy cost.

## TDL-003/B — Completion is a policy-finalized event, not an untrusted bit

**I — VGI bridge:** [`acquire_vgi_refinement`](https://github.com/Kier73/VL-I/blob/main/src/vli/cost_aware_refinement.py) requires a real `TransitionEvidenceLedger` and revalidates its retained record. Its `context_digest` binds the exact chosen plan and old native coordinate. Each chosen `ObservationOffer.offer_id` is the action of one VGI `refinement` event with a single GF(2) bit output. The transition is accepted only through VGI's `AUTHORIZED` post-finalization decision. `PENDING`, `REFUSED` and `CONFLICT` cannot contribute a witness bit.

\[
\text{Plan}(B_o,B_n,\mathcal A)
\to \text{Observe}(A_Sx)
\to \text{VGI Finalize}
\to \text{Decode}_{L}(z_o,A_Sx).
\tag{TDL3-B1}
\]

**M:** the mathematical proposition \(B_n=L[B_o;A_S]\) is a universal source-space equality, but the actual new coordinate is conditional on the values of the acquired evidence. That yields two separate verification obligations: (1) the representation is sufficient for any true source state, and (2) the received bits were admitted under the declared source/context policy.

**I:** the [independent receipt verifier](https://github.com/Kier73/VL-I/blob/main/src/vli/cost_aware_refinement_verify.py) rechecks optimum, map, plan identity, VGI ledger and policy identities, exact event decision digests, evidence IDs, and the resulting coordinate. The bridge uses the existing ChannelMessage, EncounterLedger, TransportFrameReceipt and VGI finalization implementations, rather than introducing another arbitration object.

**Scope:** VGI's transport receipts are adapter-origin evidence metadata and do not cryptographically attest source independence. Each offer's `locus` is a descriptive candidate, not yet an E-CPU authenticated host binding. The `cost` is caller-declared, not measured. These are separate future authority and resource-construction steps.

## TDL-003/C — Source identity through observer epochs

**I:** the plan digest binds source and interpreter identities, selected row masks, costs, and exact decoder. A second SHA-256 context binds that plan digest and old native coordinate to the VGI revision:

\[
\mathrm{ctx}=\operatorname{SHA256}(
\mathrm{schema},\mathrm{plan.digest},\mathrm{old\_native}).
\tag{TDL3-C1}
\]

The emitted receipt retains VGI policy and ledger digests and per-observation evidence lineage. A new old-coordinate or changed plan produces a new context.

**M:** when acquisition is state-sensitive, replaying a true measurement from a different old-coordinate revision need not justify the current migration; the context is an information and temporal identity. This parallels E-CPU's epoch/assignment fencing and VGI's finalized revision lineage, although separate processes/hosts are still to be admitted.

**H:** introduce a durable, independently authorized observation epoch for cross-host acquisition. Verify that stale frames, duplicate evidence, source-law drift and host rehoming cannot cause a previous witness to be used for a different intention state.

## TDL-003/D — Current implementation evidence

| Surface | What the code checks | Evidence source |
|---|---|---|
| Plan | Finite exact minimum declared cost; row-span inclusion and decoder identity | [VL-I cost planner and independent verifier](https://github.com/Kier73/VL-I/blob/main/src/vli/cost_aware_refinement_verify.py) |
| Accepted observation | Context-bound VGI strict policy and explicit finalized `AUTHORIZED` output | [VL-I integration tests](https://github.com/Kier73/VL-I/blob/main/tests/test_cost_aware_refinement.py) |
| Rejected observations | Unknown, missing, conflicting, unfinalized and wrong-context witnesses | [VL-I integration tests](https://github.com/Kier73/VL-I/blob/main/tests/test_cost_aware_refinement.py) |
| Regression | TDL-002 minimum bit witnesses and E-CPU/NCR finite quotient equivalence | Existing [TDL-002 tests](https://github.com/Kier73/VL-I/blob/main/tests/test_minimal_refinement.py) |
| Matrix | Linux + Windows, Python 3.11 and 3.13, pinned VGI/E-CPU/NCR | [TDL-003 CI](https://github.com/Kier73/VL-I/blob/main/.github/workflows/tdl003-cost-aware-refinement.yml) |

The source/test contracts above are now supported by the exact four-job verified CI run recorded below; physical sensor authentication and actual host route cost remain separate future evidence obligations.

**O — verified code execution (2026-11-22):** [VL-I Actions run 45069128848](https://github.com/Kier73/VL-I/actions/runs/45069128848) passed its complete Linux/Windows × Python 3.11/3.13 matrix on source head `0dbe698130bec8cffd0b853e97add8c76d2677e3`. Each job passed **7** new TDL-003 cost/VGI-evidence tests, **7** TDL-002 minimal-refinement regressions and **1** E-CPU/NCR cross-representation test: **15 passing test cases per environment**. The reviewed implementation was [merged as VL-I PR #64](https://github.com/Kier73/VL-I/pull/64).

**O — build-system discovery:** the first Windows CI checkout failed before tests because VGI's deeply nested historical research archive exceeded the runner's Windows path length. Restricting GitHub's sparse checkout to `virtual_ground_interpreter/` allowed the exact active VGI dependency to be installed and the full four-job matrix to pass. This illustrates that a repository's **historical representation layout** can affect the cost of composing computational systems even when the runtime implementation is correct.

## TDL-003/E — New opportunities revealed during translation

1. **Computational intent as a query language.** The minimal source-row complement \(C\) from TDL-002 is an explicit list of questions; the observation plan here translates them into available offered sensor relations. The processor can ask for its missing distinctions before their values are known.
2. **Joint row, quorum and path cost.** Given authenticated observer paths, the cost function becomes \(C(S,\text{hosts},\text{routes},\text{quorum})\). Optimize under both algebraic completeness and E-CPU admission, rather than assuming that an offered row is available at any arbitrary receiver.
3. **Asynchronous unknown state.** VGI's `PENDING` is information, not a false bit. A future adaptive planner can defer one offer, collect independent evidence, and revise the candidate set without forging state.
4. **Observer-relative locality.** When a cheaper basis uses auxiliary features outside the new observer span, the chosen computational path is influenced by where related information is easiest to measure. This is a concrete route from **intention → representation → host discovery**, not just host ranking after the processor already exists.
5. **Verifier as a second language.** The exact selector enumerates bitmask subsets, the independent verifier enumerates combinations and rank conditions, and VGI validates evidence with its own state machine. Agreement is a practical translation benchmark.

**Next experiment priority:** connect the offered measurement record to E-CPU's receiver-owned `AdaptiveBootstrap`/computational host admission so costs and authorization are evidenced by actual host/route reports, not declared offer labels. Compare route-coupled optimum against the current mathematical optimum, while keeping VGI evidence finalization as a separate prerequisite.

**Research invariant:** source mathematics, observational authority and measured execution cost are separate contracts. Linking them produces a stronger processor; none should be silently substituted for another.
