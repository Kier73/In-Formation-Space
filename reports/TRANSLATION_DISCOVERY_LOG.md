# Translation Discovery Log — TDL-001

**Round:** 2026-11-22 · **Method:** implementation → mathematical relation → algorithm → independent evidence → new construction.

This is a living **technical research log** of discoveries that arise when working implementations are rewritten in other exact languages. The purpose is to expose properties that are hard to notice in implementation prose, without conflating existing code, mathematical deduction and proposed functionality.

[Documentation-editing standard](https://github.com/Kier73/E-CPU/blob/main/docs/IMPLEMENTATION_FIRST_DOCUMENTATION.md) · [Description-to-realization programme](../experiments/description-to-realization/README.md)

## Evidence notation

| Label | Meaning | Minimum record |
|---|---|---|
| **I — Implemented** | An exact API, algorithm or data invariant inspected in the current source | Repo/path, function, test name |
| **M — Mathematical deduction** | A consequence derived from an implemented formal contract, possibly awaiting an executable cross-check | Equation, assumptions, proof sketch |
| **H — Hypothesis / construction** | A new interface, optimization, experiment or generalization to build | Implementation target, falsifier, acceptance test |
| **O — Observation** | A measured or recorded result from a particular runtime/environment | Reproduction command, environment, source of evidence |

The documentation pass inspected GitHub source and test definitions. It did **not execute new full repository test suites**. Existing fixture assertions are referenced as *source evidence*; they should only be described as current test outcomes after rerunning or checking CI.

## TDL-001/A — Three exact languages for the same future-observation question

**Question:** Which distinctions of a source state are sufficient to preserve every future observation requested by an intention?

For source \(S\), action words \(A^*\), and observer \(O_F\), define the common semantic relation:

\[
x\equiv_F y
\iff
\forall w\in A^*:\ O_F(\delta^*(x,w))=O_F(\delta^*(y,w)).
\tag{TDL-A1}
\]

The three implementations construct different *representations* of this relation.

| Representation | Current code | Constructed state | Established optimization criterion |
|---|---|---|---|
| **Finite Moore quotient** | [E-CPU `form_observer_machine`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/intention_formed_fabric.py); [tests](https://github.com/Kier73/E-CPU/blob/main/tests/test_intention_formed_fabric.py) | Stable partition \(X/{\equiv_F}\), exact transition table | Minimum number of equivalence classes on the declared finite \(X\) |
| **Binary-affine dual observer space** | [VL-I `construct`](https://github.com/Kier73/VL-I/blob/main/src/vli/problem_formed_interpreter.py) using [NCR symbolic quotient](https://github.com/Kier73/Navigable-Compute/blob/main/navigable_compute/symbolic_quotient.py); [tests](https://github.com/Kier73/VL-I/blob/main/tests/test_problem_formed_interpreter.py) | Linear coordinate \(z=Bx\), \(\operatorname{rowspan}B=\operatorname{span}\{hA_w\}\) | Minimum future-stable linear observer subspace |
| **Nonlinear ANF Koopman observer space** | [NCR `construct_koopman_ground`](https://github.com/Kier73/Navigable-Compute/blob/main/navigable_compute/nonlinear_koopman.py); [tests](https://github.com/Kier73/Navigable-Compute/blob/main/tests/test_nonlinear_koopman.py) | Feature coordinate \(q(x)=(f_1(x),\ldots,f_r(x))\), pullback-closed GF(2) span | Minimum linear *function-feature* span containing all future observer pullbacks |

**I:** E-CPU performs repeated partition splitting and an independent pairwise fixed-point minimality check. VL-I imports an exact affine quotient and symbolically checks each generated XOR/FLIP circuit. NCR-007 builds nonlinear source laws from invariants, then closes exact observer ANFs under pullback with independent checks.

**M:** For all three, their respective admitted source laws make coordinate equality equivalent to (TDL-A1). But "smallest" depends on the representation language. In the affine case, a rank-\(r\) linear map on *all* of \(\mathbb F_2^n\) realizes \(2^r\) coordinates. In the nonlinear function-feature case, independent functions do not imply that every \(r\)-bit feature vector is realizable:

\[
|\operatorname{im}q|\le 2^r,\qquad
\lceil\log_2|\operatorname{im}q|\rceil\le r.
\tag{TDL-A2}
\]

**H:** Construct a shared finite-source fixture and independently derive E-CPU partitions, a suitable affine VL-I quotient (where source admits one), and NCR feature coordinates. Verify the same future-observation equivalence relation while recording different encodings, state counts and derivation costs. Falsifier: an accepted representation joins two states separated by any future observer word.

## TDL-001/B — Quantifying missing information during intention succession

[PFI-001 `certify_succession`](https://github.com/Kier73/VL-I/blob/main/src/vli/problem_formed_interpreter.py) **implements** the binary decision: map the new basis through the old if possible; otherwise require a full declared source-state anchor consistent with the old coordinate. [The PFI tests](https://github.com/Kier73/VL-I/blob/main/tests/test_problem_formed_interpreter.py) cover both directions and changed source-law refusal.

### B1. Affine source: conditional linear information

Let \(B_o\in\mathbb F_2^{r_o\times n}\) and \(B_n\in\mathbb F_2^{r_n\times n}\) be old/new future-stable quotient bases of the *same* admitted source law. The old native coordinate is \(z_o=B_ox\). Define

\[
d=\operatorname{rank}\begin{bmatrix}B_o\\B_n\end{bmatrix}
-\operatorname{rank}(B_o).
\tag{TDL-B1}
\]

**M (deduction):** For the full declared vector space, every old-coordinate fiber contains exactly \(2^d\) distinct new-coordinate values. To identify \(z_n=B_nx\) given only \(z_o\), at least \(d\) additional bits are needed in the worst case. They can be chosen as a basis for the rows of \(B_n\) modulo \(\operatorname{rowspan}(B_o)\), rather than the full \(n\)-bit source anchor.

Proof sketch: the joint map \(x\mapsto(B_ox,B_nx)\) has rank \(r_o+d\); restricting it to any nonempty old-coordinate fiber leaves an image of dimension \(d\). A choice of \(d\) independent complement rows distinguishes all those images.

For \(d=0\), the current `mathematically-derived-quotient-map` is sufficient. For \(d>0\), the current `declared-source-anchor-required` branch supplies more information than this lower bound generally requires.

**O — independent finite sanity check (this round):** enumerated all 961 pairs of nonzero one-row old/new observer matrices on \(\mathbb F_2^5\) and all 32 source states per pair (**30,752 source assignments**). Every old-coordinate fiber contained exactly \(2^d\) new-coordinate values; zero counterexamples. This checks the stated conditional-rank property on a small domain, separately from the repository's test suites.

A self-contained Python reproduction for that one-row finite check:

```python
def projection(row, x):
    return (row & x).bit_count() & 1

cases = 0
for old_row in range(1, 32):
    for new_row in range(1, 32):
        fibers = {}
        for x in range(32):
            old_z = projection(old_row, x)
            new_z = projection(new_row, x)
            fibers.setdefault(old_z, set()).add(new_z)
        # One-row nonzero matrices: joint rank increase is 0 iff identical.
        d = 0 if old_row == new_row else 1
        assert all(len(values) == 1 << d for values in fibers.values())
        cases += 1
assert cases == 961
```

**H:** Add a *minimal refinement witness* to PFI-001: exact complement-row basis, \(d\) observed bits, old coordinate and source/epoch digest. Reconstruct \(z_n\) by a matrix over \(\mathbb F_2\). Verify with an independent full-anchor oracle and adversarial tampering. Acceptance includes \(d=0\), rank-increasing cases, changed-law rejection, and multiple consistent source states giving identical reconstructed \(z_n\).

### B2. General finite source: conditional class information

For two future-observation partitions \(P_o,P_n\) on the same finite source \(X\), let \(P_n(C)\) be the new classes intersecting an old class \(C\in P_o\). The worst-case additional class-index information is bounded below by

\[
b_{\rm extra}=
\left\lceil\log_2\max_{C\in P_o}|P_n(C)|\right\rceil.
\tag{TDL-B2}
\]

**M:** This counts the number of new-class alternatives indistinguishable to the old processor and gives a finite-state counterpart of (TDL-B1). A witness identifying the new class within each old class suffices; a full source-state anchor can be unnecessary.

**H:** Build an E-CPU `FormedObserverMachine` succession certificate with an exact conditional-class mapping and a bounded auxiliary witness. Test refinement, coarsening, and incomparable observer partitions against exhaustive source replay.

**Research significance:** continuity has a measurable *information deficit*, not merely a yes/no requirement for retaining every original state bit.

## TDL-001/C — Evidence finalization has its own temporal semantics

**I:** [VGI `TransitionEvidenceLedger`](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/vgi/evidence.py) collects exact transport/Encounter-bound claims under a source-set/quorum policy. Its `status` may return `QUORUM`, but only `finalize` creates `AUTHORIZED`; pending becomes `REFUSED`. Ingest rejects new evidence for a finalized state/action event within that Ground/context revision. [Tests](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/tests/test_evidence.py) cover strict dissent, indeterminacy, explicit finalization and late-evidence rejection.

A compact operational model is:

\[
\operatorname{Observe}(e)\to\operatorname{Decide}_{P}(e)
\to\operatorname{Finalize}_{P}(e)\to
\operatorname{AdmittedTransition}(e).
\tag{TDL-C1}
\]

The commit decision is *monotone within one revision* even as more observations become available outside it.

**M:** A timing choice changes what can be established within a fixed Ground/context revision. Finalizing a pending event refuses it for that revision; later evidence must be represented as a new revision with a new admission event. This creates a connection to E-CPU's commit/recovery semantics and VL-I's intention-epoch continuity.

**H:** Formalize and test *evidence succession*: a parent revision with refused/unknown event evidence and a child revision with new witnesses, preserving parent provenance without mutating the old decision. Acceptance: no retroactive permission, no evidence loss, no duplicate source votes, exact new context digest and independently validated transition.

## TDL-001/D — Code translation exposes semantic-vs-encoding identity

**I:** E-CPU's `FiniteObserverLaw.fingerprint` hashes ordered state names, actions, transition rows and outputs. The formed machine also hashes exact quotient group data. VL-I's bundle binds the source digest, quotient packet and gate graph. NCR's family/feature packets bind exact symbolic polynomial coordinates.

**M:** Two isomorphic source machines may preserve identical intention-relative future-observation behavior but have different content-addressed digests. Their **exact provenance identity** and **behavioral isomorphism** are distinct relations.

For processor descriptions \(P,Q\) over corresponding action alphabets and observations, a candidate isomorphism \(\phi\) must preserve:

\[
\phi(\delta_P(p,a))=\delta_Q(\phi(p),a),
\qquad O_P(p)=O_Q(\phi(p)).
\tag{TDL-D1}
\]

**H:** Provide a separate, independently checked semantic-isomorphism receipt while retaining each original digest unchanged. Acceptance: renamed/reordered equivalent sources accepted with an explicit bijection; output or successor tampering refused; source authenticity remains an independent concern.

## TDL-001/E — A translation can become a test oracle

An eventual cross-repository test should ask whether two independently constructed representations commute with the same original source law. Let \(T_i\) construct a representation \(P_i\) from source/observer contract \(D\), \(E_i\) execute \(P_i\), and \(R_i\) decode the observable:

\[
\forall x,w:\quad
R_1(E_1(T_1(D),x,w))
=
O_D(\delta_D^*(x,w))
=
R_2(E_2(T_2(D),x,w)).
\tag{TDL-E1}
\]

**H:** Implement a finite exact cross-language checker (source table, affine basis, ANF feature law) with an explicit common-domain adapter; assert the commuting relation using independently written evaluators and preserve counterexamples as regression fixtures. The bridge must not conflate local mathematical equality with receiver authority, source admission, or remote physical execution.

## TDL-001/F — Information gain can be known before an observation

**I:** [VLD TRACE-002 `ActiveTraceInquiry.next_probe`](https://github.com/Kier73/Virtual-Layer-Dynamics/blob/main/src/vld/inquiry/trace_inquiry.py) uses rank gain over known prime-field recurrence regressors to choose the next query before observing its scalar result. The [independent auditor](https://github.com/Kier73/Virtual-Layer-Dynamics/blob/main/src/vld/independent_trace_inquiry_audit.py) checks each selected query and the retained digest-linked transcript. [Tests](https://github.com/Kier73/Virtual-Layer-Dynamics/blob/main/tests/test_trace_inquiry.py) cover two jointly identifying observers that are individually rank-deficient, stale selections, budget limits and forged query decisions.

For candidate observation regressor \(r_{c,t}\) and existing equations \(R\),

\[
\Delta_{c,t}=\operatorname{rank}(R\cup\{r_{c,t}\})
-\operatorname{rank}(R).
\tag{TDL-F1}
\]

This gain uses only observed predecessor values. The actual response \(y_c(t)\) determines consistency and coefficients, while held-out data determines empirical support.

**M:** The *choice of which unknown to resolve* and the *answer to that unknown* can be separated mathematically. Rank selection is an active-attention operation on representation structure, without pretending that missing data has a known value.

**H:** Connect VGI's `unknown`/ `ambiguous` state-action evidence to VLD-like query planners: choose a source-bound observation predicted to split possible Ground laws, then use the actual evidence to update the admitted law, and only then compile an E-CPU intention-relative processor. Acceptance: higher rank/partition discrimination from combined observers, independent transcript audit, preserved unknown status until finalization, and no false external-authority promotion.

## TDL-001/G — A stable dispatch graph can carry changing numerical weights

**I:** [E-CPU-Virtual-Processor `route_experts`](https://github.com/Kier73/E-CPU-Virtual-Processor/blob/main/vp/moe.py) consumes 128 finite externally supplied router logits, computes stable reference softmax, selects eight experts with deterministic index tie-breaking, then normalizes selected weights. [`compile_layer_frontier`](https://github.com/Kier73/E-CPU-Virtual-Processor/blob/main/vp/moe.py) builds 25 typed dependencies and binds the exact route receipt. [Tests](https://github.com/Kier73/E-CPU-Virtual-Processor/blob/main/tests/test_moe.py) cover top-k selection, ties, tampering, route verification and the typed E-CPU DAG.

Let \(m=\ell_{(k)}-\ell_{(k+1)}>0\) be the exact real-arithmetic separation between selected/unselected score groups. If \(|\Delta_i|\le\epsilon\) for every score, then

\[
2\epsilon<m\quad\Longrightarrow\quad
\operatorname{TopK}_k(\ell+\Delta)=\operatorname{TopK}_k(\ell).
\tag{TDL-G1}
\]

**M:** This is a sufficient *structural route-membership* invariant. It says nothing about exact float64 softmax weights, tensor values, or admitted neural execution. An unchanged selected-expert set may preserve operator/dependency **shape** while each receipt and weighted-sum result still needs its own numerical check.

**H:** Build a source-bound `RouteMembershipStabilityCertificate` with a lower bound on the top-k gap, an input perturbation contract and a checker that rejects threshold crossings. Compare reused task-graph construction against full per-request rebuilding while maintaining independently verified per-token weights. Test ties, float rounding, changed model Ground, and adversarial logits. Separate structural reuse from memoizing numerical expert outputs.

## TDL-001/H — Current editorial changes

| Repository | Applied edit | Outcome |
|---|---|---|
| [E-CPU](https://github.com/Kier73/E-CPU) | [INTENT-001 worked example](https://github.com/Kier73/E-CPU/blob/main/docs/INTENT_001_OBSERVER_FORMED_FABRIC.md), [documentation standard](https://github.com/Kier73/E-CPU/blob/main/docs/IMPLEMENTATION_FIRST_DOCUMENTATION.md) | Formula, source/test references, fixed-point audit, usable syntax |
| [Virtual-Ground-Interpreter](https://github.com/Kier73/Virtual-Ground-Interpreter) | [Evidence and reconstruction](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/virtual_ground_interpreter/docs/EVIDENCE_AND_RECONSTRUCTION.md) | Quorum equation, finalization semantics, code path, reconstruction contract |
| [VL-I](https://github.com/Kier73/VL-I) | [PFI-001](https://github.com/Kier73/VL-I/blob/main/docs/PROBLEM_FORMED_INTERPRETER_PFI001.md) | Affine observation quotient, gate semantics, exact succession criterion, source API |
| [Navigable-Compute](https://github.com/Kier73/Navigable-Compute) | [NCR-007](https://github.com/Kier73/Navigable-Compute/blob/main/docs/NCR-007.md) | ANF feature closure, actual callable API, image-versus-rank distinction |
| [Virtual-Layer-Dynamics](https://github.com/Kier73/Virtual-Layer-Dynamics) | [TRACE-002](https://github.com/Kier73/Virtual-Layer-Dynamics/blob/main/docs/TRACE_002_ACTIVE_OBSERVER_INQUIRY.md) | Exact rank-gain query choice, source API and independent transcript audit |
| [E-CPU-Virtual-Processor](https://github.com/Kier73/E-CPU-Virtual-Processor) | [VP-002](https://github.com/Kier73/E-CPU-Virtual-Processor/blob/main/docs/VP-002.md) | Exact sparse-router formula, source API and structural-margin research question |

Links to mainline documents become current after their respective documentation PRs merge. The code and test references were inspected at their current default branch during this round.

## Next round: minimal research experiment order

1. **TDL-B1:** Compute minimal affine refinement witnesses from PFI-001's existing `certify_succession` source/quotient types. Compare with full-source-anchor oracle and exact rank calculation.
2. **TDL-E1:** Build a shared small finite source whose three independent representations can be enumerated; verify observation commutativity and record witness digest.
3. **TDL-C1:** Make VGI evidence-revision lineage explicit, then test whether its admitted source law can drive the cross-representation compiler without erasing three-valued observation status.
4. **TDL-F1 / G1:** Prototype rank-aware evidence acquisition and separately certified sparse expert-membership stability; preserve exact source and output receipts.
5. **TDL-D1 / A2:** Profile semantic-isomorphism checking and nonlinear feature-image minimization separately; measure when smaller encoding improves actual execution rather than only the abstract state count.

Every later entry should record **source commit**, **formal contract**, **translation algorithm**, **actual verification**, **counterexample**, **new construction**, and **status**. Append results; do not silently revise a previously observed experiment to match a newer implementation.
