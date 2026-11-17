# COG-001 → COG-002: persistent codonic capability atlas

**Repository role:** In-Formation-Space contains the standalone research fixture, exact algebraic atlas, source-aware adaptive arbitration, independent tests, and durable *research evidence*. VGI remains the authority for typed ring operator realization, and E-CPU remains the authority for admission/realization across observer-hosts. No duplicate scheduler or remote authority is introduced.

## Research continuity

This experiment descends from the user's [early codonic reference](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/Theory%20Docs/VirtualLayer_early_codonic_reference.md) and [early codonic insights](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/Theory%20Docs/Early%20Codonic%20Encoding%20Exploration%20insights.md). The *shape*, registry, opaque names, observer and time are separated. Hash-address proximity is **not** treated as functional similarity. An operator must possess mathematical invariants and an independently reconstructible result to be admitted.

COG-001, in `capability_atlas.py`, generates five exact region families of invertible 2D affine maps over `F_257`: translation, diagonal gain, upper/lower shears and frame swap. A compiler constructs a four- or five-region path for any requested invertible affine transformation without searching the enormous group. `AGL(2,257)` contains exactly **287,011,307,126,784** distinct maps. This is a set of mathematically different functions, **not** a set of trained expert parameters. Logical-time powering is valid only under the admitted affine closure.

COG-002 asks whether *task feedback* can make the arbiter discover which capability composition to use, instead of choosing a fixed named region. It reuses the COG-001 `Affine`, `encode`, `compile_regions`, and `point_label` implementations directly. `vgi_adapter.py` separately checks the compiled operator path through VGI's **existing** `FiniteSpace`/`homogeneous_affine_map`/`OperatorChain`/`fulfill` APIs; no new typed matrix engine is claimed.

## COG-002 experiment

The bounded admitted policy class has **27** distinct symbolic policies: 3 constant experts plus 4 binary observation features × 3 choices for the zero branch × 2 different choices for the one branch. Every selected capability is itself a 4–5 step COG-001 operator program; selection is contextual and may therefore make the full function piecewise affine.

The learner receives exact input/output task observations. It maintains a *version space* of all policies consistent with the evidence, then selects its next observation coordinate by maximum disagreement among surviving policy predictions. This is a finite, deterministic form of active learning. It does **not** discover new primitive operations, automatically infer the appropriate feature representation, or operate as an open-ended neural model. It refuses a witnessed output that no admitted policy can explain.

Four synthetic task families, `parity-x`, `parity-y`, `parity-sum`, and `half-x`, were generated using two known COG-001 affine Grounds. The arbiter does **not** receive the target feature identity. For each family and 100 deterministic seeds, an 80-point acquisition pool and a disjoint 100-point held-out set were drawn. The active learner, random-query control and best *static* capability all receive exactly **four** labeled observations per case; only observation-coordinate selection differs. Held-out evaluation is not used by either learner.

| Exact held-out test (400 cases × 100 points) | Accuracy | Cases with 100/100 correct |
|---|---:|---:|
| Active disagreement-based acquisition | **100.000%** | **400/400** |
| Four randomly chosen acquisition points | **86.065%** | **288/400** |
| Best single static capability | **50.380%** | N/A |

These values come from the deterministic local standard-library reference. The task family was deliberately chosen to lie inside the hypothesis class; perfect held-out scores are **not evidence of general intelligence**, and active learning does not eliminate the need for a task label / observation source.

## Persistence as structural memory, not authority invention

The experiment includes a canonical `Atlas` fingerprint (algorithm definitions and feature registry), version-space state and ordered `Witness` receipts. Each observation carries its exact previous digest and a source-bound output. The `restore()` function replays the evidence, reconstructs surviving candidate programs, and refuses any corruption or discrepancy against *externally supplied* receiver high-water pins.

The saved example session is a portable **research artifact**, not an authenticated multi-host E-CPU checkpoint. A sender can rehash fabricated observations; trusted-source authentication and independent quorum evidence belong to E-CPU's existing RecoveryLineage/Hypervisor infrastructure. An arbitrary pretrained model is not recovered from a small seed.

## Run and reproduce

```sh
python -m unittest discover -s experiments/codonic-capability-atlas -p 'test_*.py' -v
python experiments/codonic-capability-atlas/run_experiment.py
```

Local 2026-11-16 result: **14 mathematical tests passed**; **1 native VGI test skipped** because VGI is not installed in the local runtime. Dedicated CI installs a pinned VGI revision, requires the imports and executes the native test alongside the original COG-001 exhaustive small-field oracle.

## Frontier

1. Enrich the codonic feature registry with *discovered* structural probes and formal criteria for admitting a new operator family.
2. Feed authenticated E-CPU/VGI real observer receipts into the arbiter while preserving type/frame provenance and runtime cost.
3. Compare algorithm composition against independent external tasks and held-out **unrepresented** task families, not only in-class synthetic fixtures.
4. Integrate learned policy version/digest with E-CPU M3 session checkpointing and transfer between qualified Transit observers; test crash-cut recovery and independence from a specific physical host.
5. Monitor true capacity growth: distinguish algebraic reachable functions, retained algorithmic information, learned task adaptation and measured realization costs.

This repository folder is intended to remain a stable, inspectable research Ground for successive agents and revisions; it does not claim that geometry alone performs arbitrary neural arithmetic for free.
## COG-003 — Discover capabilities from geometric observations

[COG-003](COG-003.md) advances beyond choosing from the fixed COG-002 policy grammar. It reconstructs **previously unregistered** invertible affine Grounds from rank-sufficient observed input/output pairs; one further independent observation checks consistency. The discovered Grounds are fed directly through the original COG-001 region compiler and COG-002 contextual VersionSpace, with exact VGI verification in pinned native CI.

The deterministic local ablation across 100 seeded synthetic tasks reconstructed both unknown transformations in **100/100 geometry-directed** cases versus **4/100 random** cases with the same four-observation budget per context, using a pool dominated by collinear source states. The second stage identified a composed contextual policy with **300/300** held-out comparisons. These targets belong to the admitted affine class, and finite samples never prove that an arbitrary external observer follows this law globally. See [the local audit](results/COG003-local-audit.json), [implementation](structural_discovery.py), [tests](test_structural_discovery.py), and [run command](run_discovery.py).


## COG-004 — Discovery of algebraic *families* and mixed-family arbitration

See [COG-004 mathematical research record](COG-004.md), [family_discovery.py](family_discovery.py), [test_family_discovery.py](test_family_discovery.py), and [run_family_discovery.py](run_family_discovery.py). This continuation deliberately reuses **COG-003's EvidenceAtlas source chain and exact affine solver**, **COG-001's existing compiled region path**, and **COG-002's version-space acquisition and witness reconstruction**. The nonlinear part is an explicit new **invertible quadratic shear** before an existing affine path; native VGI validates only the affine factor. A separate typed adapter avoids treating COG-002's affine-only \`Policy.certificate\` as a nonlinear execution receipt.

A four-dimensional exact monomial observation basis distinguishes an affine hypothesis from the admitted nonlinear family. At least one additional observation challenges the fitted result, which can be falsified but cannot be globally proven for arbitrary unknown external behaviors. Under a deliberately rank-deficient 97-point candidate pool, six geometric probes per context identified both hidden family laws in **100/100 seeded trials**, versus **19/100** for equal-budget random probes; verified **10,000/10,000** synthetic held-out source outputs. Existing COG-002 contextual arbitration subsequently achieved **500/500** held-out cases with a learned affine/nonlinear selection rule. This is a bounded, synthetic hypothesis-class experiment, not arbitrary program synthesis, learned general intelligence, or a proven E-CPU observer-host realization.

For CI, run \`cog004-family-discovery.yml\` on Python 3.11 and 3.13; the native VGI job hard-requires a pinned VGI package. Never report queued CI as passed. A future gate is an **authenticated E-CPU source-observation path**, then **M3 quorum recovery** of the actual discovered capability catalogue and its selection evidence.

## COG-005 — Distinct high-order functional Grounds and native E-CPU observer handoff

[COG-005 research and evidence](COG-005.md) extends the admitted atlas from one quadratic nonlinear family to **all canonical polynomial-shear automorphisms through degree 32 over F257**, composed with COG-001 affine Grounds. The entire admitted function class has exactly **146496021316068964177697100939654664509940756846263280047895395372636291706111470799552512 distinct functions** (297-bit addresses), and a directly navigable **2^48-element injective subset** materializes only eight functions per requested observation. Each demand is verified by an independent power-series arithmetic oracle. The functions are procedurally defined, **not learned expert parameters**.

The [high-order learner](high_order_capability.py) reuses COG-003's source-witness ledger, actively seeks finite-field rank, infers previously unprovided polynomial degrees/coefficients and checks independent out-of-basis challenges. A three-degree synthetic audit recovered **300/300** true target functions, compared with **93/300** for equal-budget random probing; held-out results **30,000/30,000**. The local benchmark and exact numerical evidence are in [COG005-local-audit.json](results/COG005-local-audit.json). End-to-end cost includes learning and proof, not just sparse observation.

The [observer adapter](native_atlas_observer.py) delegates permitted pure realization to the **existing E-CPU-native `NativeInferenceHost`** from the VP repository; it never replaces E-CPU's Hypervisor. The [dedicated workflow](../../.github/workflows/cog005-high-order-observer.yml) tests mathematical programs and provenance on Python 3.11/3.13, then carries a source-pinned plan between three independent GitHub runner jobs: planner, E-CPU-native receiver, and independently recomputing verifier. These are transport and process boundaries, **not** proof of physical-network arithmetic, signed remote execution, or M3 quorum recovery. Native checks must pass on the exact head before such an execution claim is made. The follow-on is to reuse IFS SRH-007/008 mTLS and E-CPU recovery lineage for independently qualified nonlinear observation and durable rehome.

## COG-006 — Generate the structure of capability, not source code

[COG-006: evidence-compiled cognitive Grounds](COG-006.md) opens a second,
semantic/relational axis of the capability atlas inspired by
[huggingface/pybot](https://github.com/huggingface/pybot). It
**does not generate Python handlers**. A typed graph compiler enumerates
possible inference pathways (direct, steps-then-sum, first-step) and an
evidence-linked, actively acquired version space selects the one explaining
the admitted observations. The promoted path then answers new source records;
a later intention composes it with a typed unit conversion and retained
conversation referent.

The exact finite-model audit uses synthetic fact Grounds of
128, 4,096 and 65,536 records. After two witnessed examples, 3,000 sampled
held-out queries were correct under the declared sum-of-steps task law; each
realization visits one source record and two Ground operators. Source
construction, acquisition and query costs are reported **separately** in
[COG006-local-audit.json](results/COG006-local-audit.json).
The [source](cognitive_grounds.py), [test suite](test_cognitive_grounds.py)
and [replay program](run_cognitive_grounds.py) include contradictory evidence
refusal, task-relative memory ablation, full event replay and a separate
fresh-Python-process continuation with external high-water pins. A native
test imports the repository's existing observation-equivalence refinement
instead of duplicating it.

This is **neither general conversational intelligence nor a benchmark of
PyBot**; typed intentions and source knowledge are supplied by the
experiment. The [dedicated workflow](../../.github/workflows/cog006-cognitive-grounds.yml)
runs Python 3.11/3.13 tests and cross-job handoff. A GitHub artifact is not
an authenticated E-CPU observer, and its pins do not confer independent
authority. Next: acquire language-to-intention structures from actual
observations, compare to pinned PyBot behavior, and realize selected programs
through E-CPU's existing Hypervisor/mTLS/M3 infrastructure.

## COG-007 — predictive semantic memory from counterexamples

[COG-007](COG-007.md) learns the coarsest **future-behavior-preserving** finite cognitive state from black-box COG-006 turn observations, with actively acquired distinguishing continuations, independent exhaustive finite conformance, an external-pin checked structural handoff, and source-pinned real PyBot observation probes in hosted CI. For 512 synthetic source subjects with eight task-distinct durations, 1,537 explicit source states reduce to **25** exact predictive states under the duration-answer contract; adding `who` restores subject identity distinctions. This is not natural-language/PyBot equivalence, global intelligence, or E-CPU host authentication. Reproduction: `python experiments/codonic-capability-atlas/run_predictive_state.py audit`; tests: `test_predictive_state.py`.

## COG-008 — Provisional cognitive Grounds from black-box observations

[COG-008](COG-008.md) removes COG-007's complete-state conformance oracle from the *learner*: the candidate is constructed from an explicit, content-addressed membership ledger using COG-007's existing observation-table engine; task-directed future queries falsify insufficient predictive states and lead to structural revisions. Every candidate remains **provisional**, with unobserved continuations marked unknown. The exhaustive finite-model checker remains outside learning as a synthetic measurement.

The local audit includes 512 named synthetic subjects with eight distinct duration classes: **9 → 25** proposed states after one observed counterexample and 64,529 unique membership queries. The independently checked 512-subject synthetic source had 1,537 reachable states and 794,629 checked product-transition edges. Under an identity-sensitive contract the learner discovers that name recall requires a more discriminating **97-state** Ground for 32 subjects. Six audited settings pass 3,000/3,000 held-out symbolic continuations, with independently verified complete finite synthetic conformance. A restricted-query negative control passes its small challenge set but **fails** complete conformance, establishing why sampled evidence must not be promoted to global equivalence.

The [implementation](partial_observation.py), [tests](test_partial_observation.py), [audit runner](run_partial_observation.py), and [audit evidence](results/COG008-local-audit.json) also cover immutable source epochs, drift rechecks, rehashed/changed receipt refusal, external source pins, and zero-source-call cold-process replay. The [separate pinned PyBot membership collector](pybot_membership.py) runs against real PyBot only in hosted CI and retains original module/reply outputs for independent re-acquisition. No PyBot generalization, mTLS host authentication, M3 quorum, or E-CPU-native realization has been established by these tests.

The dedicated [COG-008 workflow](../../.github/workflows/cog008-partial-observer.yml) runs Python 3.11/3.13, independent process handoff, and the pinned external PyBot observation/replay gates. Its exact-head results are separate from local successes.


## COG-009 — source-qualified, signed multi-observer cognitive Grounds

[COG-009](COG-009.md) connects the **existing COG-008 partial-observation learner** to three real, separate worker processes, whose finite behavioral probes and Ed25519-signed observations are bound to independently enrolled public keys, source epochs, typed requests and append-only receipts. A two-distinct-source agreement is required for a provisional membership result; disagreements are preserved, and an unavailable third witness leaves the result **unknown**. A hard-killed worker is replaced, and earlier committed observations are not re-executed. A fresh verifier checks every source signature and reconstructs the learned model without any worker private keys or host calls.

**Direct test:** with 32 source-defined synthetic subjects (eight behaviorally distinct durations), the source-bound COG-008 learner acquired **4,529** membership observations, reconstructed **25 predictive states**, and retained **9,193 signed host receipts**. An independent *post-learning* finite reference checked **3,589** transitions, and a separate Python process replayed all 9,193 signatures and all COG-008 membership labels without new host activity. The retained evidence bundle was **11.5 MB**; evidence has real storage and verification cost. Local focus tests: **10 passed, one native E-CPU test skipped** because `mailcpu` is unavailable locally. The dedicated [COG-009 workflow](../../.github/workflows/cog009-signed-observer-grounds.yml) requires the actual pinned E-CPU SAB-003 qualification test, and separate prepare/fresh-verifier jobs; GitHub CI must not be reported as passed until its exact head is checked.

A signed **agreement is not proof of truth**: two colluding signing sources in the negative control report the same wrong value and remain provisional, while the independent synthetic reference detects the error. The worker processes share one machine and source law, and this is not native mTLS Transit, Hypervisor grant, M3/quorum recovery or proof of general PyBot behavior. The next natural connection is E-CPU's existing authenticated ReliableChannel and RecoveryLineage, not replacement infrastructure.

## COG-010 — Intention-conditioned transit navigation

[COG-010](COG-010.md) joins the **acquired** COG-009 predictive Ground to E-CPU's *existing* intention-relative observation sufficiency (IOS-001) and genuine typed observer/measurement fabric (IOS-002/003), rather than implementing a parallel planner or transport. A projection of learned cognitive states identifies three task-relative outcomes: **READY** (answer without reading a host), **MEASURE** (request exactly the permitted minute observation to determine the different, seconds-valued target), and **REFUSE** (the offered projection cannot distinguish differing repeat responses).

The local signed-stdio three-worker experiment deliberately kills and replaces a host while preserving source disagreement as \`unknown\`. At 32 synthetic subjects and eight distinct durations it uses a **25-state** learned cognitive Ground with **4,529** prior membership observations, resolves a seconds result after the required signed minute observation, and reconstructs the result in a separate process using zero new host calls. A learned Mealy/program-phase finite orbit has ten reachable states, sufficient to address logical coordinate \`10**30+11\` without replaying the intermediate transitions. This is *mathematical navigation*, not physically executed intermediate network operations.

The [direct audit](results/COG010-direct-audit.json), [bridge](intention_transit.py), [tests](test_intention_transit.py), [native mTLS test](test_native_ecpu_transit.py) and [reproducer](run_intention_transit.py) retain evidence and precise measurement scope. Local full COG-006→010 regression: **59 tests; 54 passed, 5 native-dependent skipped**. The [CI workflow](../../.github/workflows/cog010-intention-transit.yml) hard-requires a pinned actual E-CPU native IOS-001/002/003 path, including real mutual TLS and ReliableChannel, rather than treating local skips as success. That path is **not verified until the exact-head hosted CI is green**. The needed one-word E-CPU IOS-003 provider bug fix is separately proposed in [E-CPU PR #169](https://github.com/Kier73/E-CPU/pull/169).
