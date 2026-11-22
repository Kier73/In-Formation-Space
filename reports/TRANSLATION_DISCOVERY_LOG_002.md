# Translation Discovery Log — TDL-002
## Intention succession as a minimum-information reconstruction

**Date:** 2026-11-22. **Round:** apply TDL-001/B to actual VL-I code, independently verify its algebra, and compare two independent processor representations for the same declared source.

[TDL-001](TRANSLATION_DISCOVERY_LOG.md) · [VL-I implementation and reproducer](https://github.com/Kier73/VL-I/blob/main/docs/MINIMAL_REFINEMENT_TDL002.md) · [Implementation-first standard](https://github.com/Kier73/E-CPU/blob/main/docs/IMPLEMENTATION_FIRST_DOCUMENTATION.md)

**Evidence notation:** **I** = source implementation; **M** = mathematically derived property; **O** = actual observed verification; **H** = future construction. Test code committed is identified separately from tests whose CI execution has been observed.

## TDL-002/A — Additional observer information is a rank difference

**I — implemented:** [`vli.minimal_refinement`](https://github.com/Kier73/VL-I/blob/main/src/vli/minimal_refinement.py) constructs a source-relative refinement plan from two verified PFI-001 quotients of the **same binary-affine transition law**. [`vli.minimal_refinement_verify`](https://github.com/Kier73/VL-I/blob/main/src/vli/minimal_refinement_verify.py) independently checks the GF(2) row identities and minimality using a separate rank-elimination procedure.

Let \(z_o=B_ox\in\mathbb F_2^{r_o}\), \(z_n=B_nx\in\mathbb F_2^{r_n}\), with full declared source domain \(x\in\mathbb F_2^n\). Define

\[
\boxed{d=\operatorname{rank}\begin{bmatrix}B_o\\B_n\end{bmatrix}
-\operatorname{rank}(B_o).} \tag{TDL2-A1}
\]

The code selects a deterministic complement \(C\in\mathbb F_2^{d\times n}\) and expresses every new row in the combined basis:

\[
B_n=L\begin{bmatrix}B_o\\C\end{bmatrix},\qquad
z_n=L\begin{bmatrix}z_o\\Cx\end{bmatrix}. \tag{TDL2-A2}
\]

**M — proof:** Restrict the joint map \((B_o,B_n)\) to any nonempty fixed old-coordinate fiber. Its additional image dimension is \(d\). Hence that fiber contains exactly \(2^d\) possible new coordinates and requires at least \(d\) bits to distinguish them in the worst case. The constructed \(Cx\) has exactly \(d\) bits and suffices. The argument assumes all source states in the declared binary vector space are possible; external reachability constraints may alter the minimum.

**O — isolated algebra check in this round:** a separate randomized GF(2) calculation tested complement formation and exact reconstruction on 5,600 small row-space instances (widths 1–14), finding zero mismatches. This runs the algebra independently of the repository imports, not its complete application stack.

**I — repository test cases authored:** [`tests/test_minimal_refinement.py`](https://github.com/Kier73/VL-I/blob/main/tests/test_minimal_refinement.py) covers a 128-bit source for which the old processor has two registers, the finer processor three, and only **one additional witness bit** is needed; coarsening, incomparable projections, changed source-law epochs, forged/rehashed plans and receipts, strict bit domains, and 25 observer-pair × 32-source-state reconstructions.

**Subtlety revealed by translation:** the old state and the \(d\) supplemental bits determine the *new mathematical coordinate*, but do not by themselves attest which physical source state supplied those bits. Algebraic reconstruction and observation authority remain separate obligations.

## TDL-002/B — Correspondence is an independently checkable commutative diagram

**I — implemented cross-representation test:** [`tests/test_translation_commutation.py`](https://github.com/Kier73/VL-I/blob/main/tests/test_translation_commutation.py) converts a declared 5-bit binary-affine source into a total 32-state `FiniteObserverLaw` for E-CPU. It independently forms:

1. E-CPU's future-stable finite Moore partition using `form_observer_machine` and `verify_formed_machine`.
2. NCR-006 / VL-I's linear future-observer quotient using `construct` and `verify_interpreter`.

It checks five requested output projections, all \(5\times32^2=5,120\) ordered source-state pairs, and \(5\times32\times6=960\) short source-action executions. The required relation is:

\[
\forall x,y\in\mathbb F_2^5:\quad
\operatorname{class}_{\rm ECPU}(x)=\operatorname{class}_{\rm ECPU}(y)
\iff
B x=B y. \tag{TDL2-B1}
\]

For checked action words \(w\) and source-state \(x\), both constructed interpreters must render the same observer value as the original source:

\[
O(\delta^*(x,w))=
O_{\rm ECPU}(\hat\delta_{\rm ECPU}^*(q(x),w))=
D\,\hat\delta_{\rm NCR}^*(Bx,w). \tag{TDL2-B2}
\]

**M:** if both sides preserve all future observations on the same declared source, their partitions must coincide even when their source encoding and generated processor identities differ. This gives us a representation-independent *semantic certificate target* that can be checked without claiming identical digest bytes.

**H:** promote this small finite test adapter into a portable typed equivalence receipt, so a new processor representation can be independently checked against a known Ground without copying the producer implementation.

## TDL-002/C — The information requirement becomes an inquiry question

**I:** VLD TRACE-002's rank-gain planner already chooses evidence to resolve unknown recurrence coefficients; VGI preserves `unknown` and `ambiguous` Ground transitions until explicit finalization. The new VL-I plan exposes the exact source-space covectors \(C\) whose values are missing at intention succession.

**M:** an observer can request the missing linear measurements as a *well-defined intention*:

\[
\text{request } w=Cx,\quad
\text{with proof obligation } B_n=L[B_o;C]. \tag{TDL2-C1}
\]

A planner may choose capable observer-hosts to realize \(w\), while E-CPU's authority and VGI's evidence finalization determine whether the measured bits are admitted. The mathematical plan can be formed before the observation values are known.

**H — next implementation:** build an adapter that turns \(C\)'s row masks into typed VGI/E-CPU observation requests, retains uncertainty/authorization, and commits the new native coordinate only after valid evidence for all \(d\) bits is present. Acceptance: independent source identity, missing/ambiguous outcomes preserved, authenticated receiver binding, and successful continuation after host rehome.

## TDL-002/D — Generalizing beyond affine source states

**M:** a general finite quotient refinement from old class \(Q_o\) to new class \(Q_n\) can be described by the maximum number of distinct new classes inside an old class:

\[
b_{\min}=\Big\lceil\log_2\max_{C\in Q_o}
|\{Q_n(x):x\in C\}|\Big\rceil. \tag{TDL2-D1}
\]

For full-domain linear GF(2) quotients, the expression equals \(d\) from (TDL2-A1). For nonlinear Koopman coordinates, \(\operatorname{rank}\) of the feature span need not equal the log of the **realized** image size, so the finite class count is a separate optimization opportunity.

**H:** derive an exact finite/nonlinear class-selection witness using small independent ANF oracles, then test whether encoding/decoding cost offsets bit savings. Preserve original feature-space certificates and source-law digests.

## Implementation and verification inventory

| Location | Current change | Source evidence |
|---|---|---|
| VL-I `minimal_refinement.py` | Rank-optimal complement, exact row map, compact witness and receipt | Producer + plan-time independent audit |
| VL-I `minimal_refinement_verify.py` | Source epoch checks, independent rank and row identities, strict receipt reconstruction | No import of the witness producer |
| VL-I `test_minimal_refinement.py` | Full-anchor comparison, 128-bit reduction, tamper controls, exhaustive small transfers | Unit assertions; CI execution tracked separately |
| VL-I `test_translation_commutation.py` | E-CPU Moore quotient vs NCR affine quotient | Complete 5-bit pair check and six short words per initial state |
| VL-I `tdl002-minimal-refinement.yml` | Linux/Windows × Python 3.11/3.13; existing PFI-001 regression | Pinned predecessor commit IDs |
| [VL-I technical document](https://github.com/Kier73/VL-I/blob/main/docs/MINIMAL_REFINEMENT_TDL002.md) | Formula, actual source API and reproduction commands | Code/test references |

The central round result is a **constructive translation of a mathematical information requirement into an executable receipt protocol**. Independent source/receipt verification addresses the algebra, while typed observation authority is the next separate integration.

## Next round — order and falsifiers

1. **Source-bound measurement:** request the exact \(d\) missing row projections; preserve ambiguous, missing and conflicting evidence, and enforce finalization before accepting a new processor coordinate.
2. **Portable semantic certificate:** verify a small finite Ground through multiple independent representation families; counterexample must identify the exact source state and action word on which equality fails.
3. **Nonlinear conditional image:** compute exact conditional class counts for selected NCR-007 families and compare them with linear feature rank; use a counterexample that forces additional bits.
4. **Memory and resource accounting:** measure receipt bytes, old/full-anchor bytes, execution cost and reconstruction time rather than presuming that fewer observation bits imply a faster complete migration.

**Scope of this log:** source inspection and new repository code/tests are explicit. Only the standalone randomized algebra check is an observed execution result at the time of initial authorship; CI status should be appended separately after a matching workflow run.
