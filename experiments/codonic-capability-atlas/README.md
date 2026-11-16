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
