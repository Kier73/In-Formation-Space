# OFC-001 — Observation-sufficient computation across existing systems

**Objective:** realize an intention using the smallest knowledge required for a
guaranteed outcome. Do not insist on identifying an unknown original state when
a single admissible action or contingent observation policy already suffices.

This experiment directly invokes the existing packages in **five repositories**:
IFS IWI-001, VGI, Navigable-Compute NCR-004/005, E-CPU INTENT-001/SAB-001,
and Virtual-Layer-Dynamics' proof-checked multi-backend intention compiler.
No replacement policy solver, abstract program synthesizer, native interpreter,
capability registry, or Hypervisor is introduced.

## Reproduce

Run on Python 3.11+ with Node 22. The four-platform GitHub workflow installs
the exact reviewed commits:

| Source | Immutable revision | Called implementation |
| --- | --- | --- |
| [In-Formation-Space IWI-001](../intention-without-identification/experiment.js) | This branch | `solve`, `audit`, original `funnel`, `branch`, `erased` |
| [Virtual-Ground-Interpreter](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/ae3f949b7d0b2aaa42236bc7cc37e9857384b174/virtual_ground_interpreter/vgi/transitions.py) | `ae3f949b7d0b2aaa42236bc7cc37e9857384b174` | `GroundTransitionSystem`, `step`, exact roundtrip |
| [Navigable-Compute](https://github.com/Kier73/Navigable-Compute/blob/66e216e53ab606547ba4a5316ed44044e327b67b/navigable_compute/observed_ground.py) | `66e216e53ab606547ba4a5316ed44044e327b67b` | `admit_observed_epoch`, NCR-004, NCR-005 native algebra and verifier |
| [E-CPU](https://github.com/Kier73/E-CPU/blob/d329b8ca6d1f9c94f77e7823a3352cbe66b34707/mailcpu/intention_formed_fabric.py) | `d329b8ca6d1f9c94f77e7823a3352cbe66b34707` | `FiniteObserverLaw`, `form_observer_machine`, `realize_formed_intention`, SAB-001 host/path planner and receipt verification |
| [Virtual-Layer-Dynamics](https://github.com/Kier73/Virtual-Layer-Dynamics/blob/afe54804bc15ea14b1c51766757edef3aac96817/src/vld/compiler.py) | `afe54804bc15ea14b1c51766757edef3aac96817` | `IntentionToRealizationCompiler`, `ProofProducingEGraph`, `RealizedObservationReceipt` |

```bash
python -m unittest discover -s experiments/observation-sufficient-computation -p 'test_bridge.py' -v
python experiments/observation-sufficient-computation/bridge.py
```

## 1. Goal first, not identity first

Let `B` be the set of possible current states. The receiver only knows that
the source state lies in `B`. It is not revealed before planning. The
objective is a target set `G` and actions `A` with source-declared
total deterministic transition relations `T_a`.

For action `a` followed by an actually returned *visible* observation
`o`, the next belief is

\[
B_{a,o}=\{T_a(s):s\in B,\;O(T_a(s))=o\}.
\]

The original IWI policy builds the guaranteed attractor

\[
W_0=\{B:B\subseteq G\},\qquad
W_{d+1}=W_d\cup
\{B:\exists a,\,\forall o,\,B_{a,o}\in W_d\}.
\]

An intention can be realized when `B0` has a finite rank. The selected
action must decrease rank on **every** possible observed branch. This
implements the stronger goal guarantee even when `B0` remains ambiguous.

The bridge invokes the original IWI producer in a distinct Node process,
checks its content head, and independently recomputes the winning ranks
and action descent across **all** belief subsets using separately written
Python control logic. The original IWI `audit` is not trusted as the sole
verification oracle.

## 2. Native Ground and processor construction

The receiver's declared static source table becomes:

- A VGI `GroundTransitionSystem` with distinct known/unknown/ambiguous
  transition semantics and canonical source fingerprint. In this first fixture,
  the declared source model is **complete**; arbitrary missing transitions
  are not silently made executable.
- An NCR-004 `ObservedEpoch` with the source-reported transition readings,
  then a verified future-observation language and an **NCR-005 algebra**.
  Neither source-state-identity nor the source monoid is supplied as an
  interpreter instruction sequence. The independent NCR-005 verifier checks
  the constructed observer-native transformation.
- An E-CPU `FiniteObserverLaw` with `visible` and `goal` channels.
  INTENT-001 forms the future-observation processor; SAB-001 chooses from
  **receiver-admitted** advertised host and path operations, then performs
  the generated interpretation and verifies the result against direct source
  replay.

All source-state/action combinations are cross-compared using independent
VGI transition dispatch, NCR-005 native execution and E-CPU replay *before*
any policy execution.

The actual hidden original state is retained inside `HiddenSourceHost`.
The policy controller never sees it, nor the extra `goal` audit channel.
It sees only the output `visible` after each admitted action. This is an
encapsulated source-host fixture, not an externally authenticated or remote
physical machine.

## 3. Alternative realization via Virtual-Layer-Dynamics

When the complete source transition table for an action is exactly
modular-affine, `a*x+b mod n`, the *host side* constructs an `IntentExpr`
from that verified action law, **not** from a guessed name. VLD's actual
`IntentionToRealizationCompiler` then:

1. Builds its proof-checked equivalence candidates.
2. Chooses the `fluid_in_transit_stream` backend when available, otherwise
   the selected admitted backend.
3. Executes the same action through its real `ContinuousVirtualSystem` with
   quorum continuity evidence, and compares its result to the original
   E-CPU execution.

Non-affine actions remain E-CPU realizations. The bridge never fabricates an
affine description for an arbitrary finite map or interprets an
`IntentExpr` digest as receiver authorization.

## 4. Three deliberately different experiments

| Source | Intent-relative situation | Required behavior |
| --- | --- | --- |
| `funnel` | Unknown initial state, common reset-to-goal action | One *blind* action; all three initial states converge to the goal, even though the pre-action state was never identified |
| `branch` | No open-loop word solves the problem | Select a contingent policy from observed outputs; it can vary the subsequent action and terminate after finite rank descent |
| `erased` | All original states have individual paths, but uninformative outputs cannot establish universal control | Explicit `UNREALIZABLE_FOR_ALL_DECLARED_INITIAL_STATES`, zero E-CPU actions and zero VLD realizations |

For `branch`, the observed host inventory is changed after the first
action. `worker.alpha` disappears and `worker.beta` must replace it.
The mathematical processor fingerprint remains constant. The controller
reuses its original model and IWI policy; the source is not reobserved
to reconstruct the machine after a host replacement.

## 5. Negative controls and evidentiary interpretation

Tests include all three possible actual initial states for both winning
fixtures; independent strategy-rank reconstruction; non-affine map
refusal; rehashed forged policies; source-head mismatch; unknown VGI
transitions; receiver policy revocation; host reformation and identical
processor fingerprint; noninterference of actual hidden-state identity
with the controller's action decisions.

**Source-model premise:** the transition table is an explicit stationary
finite model, not a result of external authenticated sensor sampling. The
`NCR-004` epoch's source-reported witnesses are equally model-relative.
The algorithm guarantees the goal for every hidden initial state *within
that source model*. Discovery and evidence finalization of arbitrary
external laws remain VGI/IFS admission tasks.

**Substrate:** E-CPU's INTENT-001 uses its native SAB-001 **local simulated
carriers**. VLD's fluid-in-transit backend is genuine VLD backend execution,
not evidence of a passive internet router executing computation.
None of these mathematical identities grants external resource authority.

**Next integration:** allow partial VGI evidence-ledger Grounds and IWI's
uncertain-static-law controller to enter this contract directly. Ask the
existing VLD active-probe scheduler for an observation *only when no
guaranteed policy exists*. Qualify the resulting observed relation through
VGI's original finalization and then re-run the same unchanged E-CPU
authority and VLD proof paths. This next step tests **observation creates
new computational affordances**, beyond selecting safe actions inside a
declared complete machine.
