# GRC-001 — Proof-carrying Ground continuity under CNF source refinement

**Research checkpoint:** 21–22 November 2026, local CPython standard library. **Status:** bounded tested semantic layer; no E-CPU authority, host handoff, live migration, or P-vs-NP result is claimed.

## 1. Cross-repository discovery came before construction

This experiment was chosen **after** inspecting current public revisions and implementation documentation in the repositories, to avoid developing another parallel SAT compiler or another authority service.

| Repository / inspected revision | Capability already present | Avoid duplicating / remaining connection |
| --- | --- | --- |
| [In-Formation-Space](https://github.com/Kier73/In-Formation-Space), `77321ee8f801a1e6e8b1a3905ba34fa99aac753d` | [SFI-001](../SFI-001.md): original-source checked problem-formed SAT; [SFI-002](../SFI-002.md): non-affine/heterogeneous compiler; [SFI-003](../SFI-003.md): meta-SAT selects improved generated interpreter; SPN-008/009/010: SAT, exact counting, and cost-qualified self-use | SFI-003 explicitly identifies **incremental meta-Ground continuity** as unfinished; GRC-001 is an exact source-change certificate, not another generator |
| [VL-I](https://github.com/Kier73/VL-I), `f93a22222e1aa369c0a4891f593252e28d7e9bfc` | [PFI-001–004](https://github.com/Kier73/VL-I/blob/main/docs/PROBLEM_FORMED_SAT_PFI004.md): machine constructed from problem, native E-CPU partition execution, quorum-fenced source-bound results, recovery/rehome tests | PFI-004 uses SFI-001 and pinned source; it has **not been demonstrated here** with a changed source Ground justified by a mathematical continuity receipt |
| [E-CPU](https://github.com/Kier73/E-CPU), `9064559d6e9b621034953b7135fc991a436d7746` | [GGE-001](https://github.com/Kier73/E-CPU/blob/main/docs/GENERAL_GROUND_EXECUTION_GGE001.md): Ground contracts; [IPS-003–006](https://github.com/Kier73/E-CPU/blob/main/docs/DISTRIBUTED_GENERATED_GROUND_IPS006.md): generated execution, mTLS qualified peers, quorum-fenced recovery; [NCB-004](https://github.com/Kier73/E-CPU/blob/main/docs/SOURCE_GENERATED_DEVELOPMENT_BENCHMARK_NCB004.md): generated computation helps test development itself | Do **not** replace Hypervisor, seed admission, mTLS authority, quorum, epoch, or worker; semantic equivalence is not permission to publish under a new identity |
| [Virtual-Ground-Interpreter](https://github.com/Kier73/Virtual-Ground-Interpreter), `7a3c4a368d1d24044a6c06a317c26ef316513e6d` | [Proof-search dogfooding](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/docs/PROOF_SEARCH_DOGFOOD.md), exact/partial Grounds, explicit known/unknown/ambiguous and external kernel obligations | GRC-001 emits a **candidate observation/proof envelope** that may be qualified by VGI; it is not VGI's kernel or authenticated observation evidence |

**Finding:** the full architecture was already investigated in **more than one repository**. The missing experimental seam selected here is *continuity of a mathematical SAT claim as its actual source description changes*, before an authority may construct and admit a new runtime Ground.

## 2. Exact theorem and source contract

Take canonical CNF `F_0` of width at most three and a strengthened source `F_t = F_0 ∧ C_1 ∧ ... ∧ C_t`. The producer and verifier independently normalize duplicate literals, duplicate clauses and tautological clauses. The source-transition certificate proves literal inclusion of the *normalized* original clauses; a **deleted or weakened constraint is rejected**, not silently treated as a refinement.

Let `N(F)` count satisfying assignments over the unchanged `n` declared Boolean variables. Define `A_i = F_{i-1} ∧ ¬C_i`, where `¬C_i` is a conjunction of the negations of its literals. Then

\[
N(F_i) = N(F_{i-1}) - N(A_i).
\]

**Proof:** the models of `F_{i-1}` partition into those satisfying `C_i` and those falsifying it. There is no double counting; the second class has precisely `N(A_i)` members. The identity holds for any clause, but proving the lost count may be #P-hard.

The proof producer tries the following certified choices for each added constraint:

- **Zero-preserving:** if the original exact count is zero, every strengthening remains UNSAT.
- **Entailment:** check a complete SPN-008 refutation of `F_{i-1} ∧ ¬C_i`; if UNSAT, count loss is exactly zero.
- **Exact delta:** source-check a complete SPN-009 #SAT receipt for `F_{i-1} ∧ ¬C_i`; subtract only a checked nonnegative count.
- **Refusal:** if the compiler cannot establish a complete refutation or count under its budget, return `UNKNOWN`—never reuse the old positive count as if the new clause were harmless.

For decision SAT: a verified old **UNSAT** result remains UNSAT under strengthening; an old **SAT** result requires a witness satisfying the **new** source (the prototype runs a bounded source SAT solver to obtain one); otherwise status is `UNKNOWN`. No previous decision status is magically upgraded.

The receipt retains original ordered source hashes, original proof, new source hash, exact ordered added clauses, and nested source-verifiable proof objects for every count decrement. Producer timings, method choices and byte lengths are never trusted by the source verifier. No generator-supplied host identity is accepted as authority.

## 3. Measured experiment: different kinds of reuse

`ground_revision_campaign.py` compared **44 strengthening/equivalence cases** against independently verified fresh SPN-009 counts. All 44 new counts agreed, including exhaustive reference enumeration for n ≤ 12. Single CPython process; timer values are noisy and are **not** complexity bounds.

| Change type | Instances | Median incremental construction+source check | Median fresh recount+source check |
| --- | ---: | ---: | ---: |
| Proved redundant added clause | 10 | 0.938 ms | 0.998 ms |
| Nonzero counted model loss | 5 | **2.595 ms** | **0.801 ms** |
| Already UNSAT, monotone | 25 | 0.664 ms | 0.668 ms |
| No new semantic constraint | 4 | 0.706 ms | 0.684 ms |

The **negative result is important**: a delta-count proof can cost considerably more than recounting the updated formula, even though it reuses the previous exact count. This prototype does **not** automatically know when reuse will save work. Both incremental and full recount numbers **exclude** the old compilation, because the old proof is a retained prior result.

The carefully structured 200-variable control starts with `F=(x_1)` and adds a clause already implied by it, `(x_1∨x_2∨x_3)`. The original exact count is `2^199`, and the continuity checker establishes **the same exact count** by one source-checked UNSAT entailment instead of recounting all 200 source coordinates. In one run, incremental produce+self-check took **0.233 ms** versus **34.262 ms** for fresh replay counting. This is a reused special structure and a local observation, **not** a SAT speedup claim.

A genuine changed-meaning control begins with `F=(x_1∨x_2)∧(¬x_1∨x_2)` over three variables, count four, then adds `(x_1)`. The certificate counts two lost models and establishes the new exact count **two**. Unproved positive-count reuse is rejected.

## 4. Test and verification scope

`test_ground_revision_continuity.py` includes eleven targeted tests: 100 seeded independent small arbitrary-CNF source refinements with exhaustive truth-table references; multi-clause updates; 200-variable exact-count entailment; cost-budget `UNKNOWN`; monotone UNSAT; checked new SAT witnesses; normalization of tautologies and duplicates; source weakening refusal; forgery of nested count, clause, source identity, previous proof and result; and verification in a **fresh Python process** using `verify_ground_revision_json.py`.

The current staging runner additionally executed the preceding SPN modules individually: **98 total test cases** across 14 modules; 97 passed, one optional SFI test skipped because the local staging tree did not include its sibling source modules. CI in a complete checkout can cover that integration.

The checker still reuses SPN's Python code and source reconstruction. A fresh process is not an independently formalized kernel. For the `frontier_replay` counting path, source verification **recomputes** the count and may itself take exponential time.

To reproduce from `experiments/pnp-ground-navigation/spectral_phase_navigation`:

```sh
python -m unittest -v test_ground_revision_continuity.py
python ground_revision_campaign.py > reproduced_grc_results.json
python verify_ground_revision_json.py revision_record.json
```

## 5. P-versus-NP and the next integration gate

This is an **incremental theorem**, not a uniform fast SAT/#SAT method. The new formula's solution set is a subset of the old one, but computing how many old solutions are removed remains generally #P-hard. A compact old proof cannot justify an unsupported new positive count.

Before adding a new E-CPU/VL-I runtime test, the next appropriate gate is:

1. Feed a **genuine SFI-003 generated interpreter revision** and its independently checked source equivalence into a typed `GroundRevision` envelope. A source-preserving machine revision is different from adding a CNF clause; each needs its own validity rule.
2. Check the proposed revision against original CNF intention, output projection, model count if claimed, and any retained state coordinates. A change in machine layout may need a verified state translator rather than merely a shared CNF hash.
3. Submit the *new* Ground and interpreter identity to **existing PFI-004 and E-CPU authority** for fresh claim assignment and epoch fencing. Correct old-host computation is not authorization to publish under the revision.
4. Kill an old worker during the handoff; require an authorized replacement to reexecute or reconstruct its original-source semantic result and reject stale publication. Measure construction, verification, bytes, duplication and recovery—not just the narrower abstract proof.

**Existing mechanisms to reuse:** SFI-003 `recursive_sat_compiler.py` and `morphic_verifier.py`, VL-I `problem_formed_sat.py`, E-CPU `TransferableExecutionClaimStore`/mTLS authority, and VGI's proof/observation status. GRC-001 supplies **only** the source-refinement part of the seam and does not pretend to execute stages on network hosts.
