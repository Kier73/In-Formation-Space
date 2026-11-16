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
