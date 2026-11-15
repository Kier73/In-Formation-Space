# IWI-001 — Intention without identification

**Research experiment, 2026-11-15.** Can an observer **guarantee a target state without identifying its hidden original state**? How does this differ from each state being individually reachable?

This is a restricted and reproducible application of established **strong planning under partial observability** and **synchronizing automata**. It does not claim a new theorem about those broad fields, physical E-CPU execution, or observer honesty.

## Exact model and question

A finite deterministic state machine has states 0 through n-1, complete transitions T[action][state], and a visible state label O[state]. The initial set of possible states B and target set G are nonempty bitmasks. The observer has **no initial sensor read**; it chooses an action, the action changes the hidden world state, and it then sees O of the destination. A policy may depend on all earlier observed outcomes and may **stop at different times on different branches**.

The requirement is universal: for *every* possible initial state consistent with B, the resulting policy must terminate in G. This is not maximizing expected success. A fixed action word is a restricted policy: it neither branches on observations nor terminates differently across hidden states.

For each belief B and action a, define successor B(a,o) as the nonempty states that action a could produce and that share observed label o. The minimal guaranteed worst-case action count is the first entry depth in the finite attractor:

    W[0] = {nonempty B : B subset of G}
    W[d+1] = W[d] union {B : some a has all B(a,o) inside W[d]}

The solver stores the rank of every nonempty belief, or -1 if no guaranteed strategy exists. There are at most 2^n-1 such beliefs; a successful policy decreases rank on every possible observed branch. For a losing belief **each action has at least one losing observed successor**. This is a coinductive impossibility certificate. For winning beliefs the independent audit checks terminal claims, the rank decrease, and minimality against all other actions. A second powerset search either constructs a shortest open-loop word or a closed orbit of non-goal beliefs proving that none exists.

This is a machine-checkable finite **mathematical witness**, not a kernel proof, cryptographic signature, physical observation, network receipt or authority to produce effects.

## Exhaustive finite census

Complete labelled model class: **3 states, 2 actions, binary labels, initial belief all 3 states, target state 0**. There are 3^6 transition tables and 2^3 observation maps, or **5,832** configurations. Repeated/isomorphic machines are retained; the counts are not a count of equivalence classes.

| Exact outcome | Machines |
| --- | ---: |
| All configurations | 5,832 |
| Observation-dependent universal winners | 3,656 |
| Open-loop winners | 3,128 |
| Universal winners with no fixed winning word | **528** |
| Each state has some individual path to goal | 3,960 |
| Each has a path, but no universal observer policy | **304** |

The 528-model distinction includes cases where observation-dependent **termination alone** accounts for the advantage; it does not imply every model requires different continuation actions. A separately preserved fixture below requires different actions.

## Three discriminating experiments

**Blind funnel.** T = [[0,1,2],[0,0,0]], O = [0,0,0]. Action 1 guarantees target 0 in one step; all three possible origins generate the **same entire observed action/output transcript**. Certainty of the present state is not identification of the original state.

**Genuinely conditional branch.** T = [[0,2,1],[1,0,0]], O = [1,1,0]. A winning policy of worst-case length 3 exists; no fixed word of *any* length wins. The initial action has two distinct **nonterminal** observed branches, whose winning continuations require **different actions** in the preserved policy.

**Erased observations.** The same transition tables as the conditional branch, but O = [0,0,0]. Every initial state separately has a path to target 0; nevertheless **no observation-driven uniform strategy** exists. The negative rank certificate and closed blind-belief orbit are independent kinds of impossibility witness.

## Reproduction

Requires Node.js 20+ and only the standard library. From repository root:

    node --test experiments/intention-without-identification/test_experiment.js
    node experiments/intention-without-identification/experiment.js

The ten tests include all 5,832 rank/losing-trap certificates; a separately written bounded-depth recursive oracle for every belief in all three fixtures; tampered certificates; adversarial bad inputs; state-renaming invariance; trace replay; and byte-for-byte reconstruction of the committed deterministic JSON data. GitHub Actions runs Linux/Windows with Node 20/22. The workflow's actual successful completion must be checked separately; no hosted success is implied by these instructions.

## Interpretation and harder follow-up

The observed separation supports a *task-relative convergence* interpretation: navigation can realize an intended final condition without enough evidence to infer the hidden starting identity. Conversely, individually possible realizations do not automatically compose into one observer-safe realization. This makes the **quantifier order** operational: every hidden state has its own path need not imply there is one policy that succeeds for every hidden state.

The important future experiment is to replace the fully trusted transition tables with **versioned, partial, independently admitted E-CPU/VGI transition evidence**. A strategy should survive *every* completion of the missing Ground relations, and should refuse a purported guarantee when one evidence-compatible completion invalidates it. Adversarial reports and real receiver effects require distinct authority checks; they are not inferred from the synthetic oracle.

## Nearby research and attribution

- [Strong planning under partial observability — Bertoli, Cimatti, Roveri & Traverso (2006)](https://doi.org/10.1016/j.artint.2006.01.004). Established AND/OR belief-space planning with correctness and completeness results; IWI-001 is a deterministic finite special case.
- [Synchronizing Automata: Open Problems — Szykuła (2026)](https://arxiv.org/abs/2608.24245). Established reset-word and synchronization questions; adaptive conditional strategies need not be synchronizing words.
- [RIV-003 in this repository](../bounded-memory-representation-relevance/README.md) examines bounded-memory probability of survival, not universal target reachability.
- [Trial 08 in this repository](../description-to-realization/trials/trial-08-intervention-aware-attention/README.md) plans state-mutating observations to determine a **fixed initial query**; IWI-001 instead certifies a **final-state goal** that may erase origin identity.

No third-party implementation was copied. Results pertain only to the declared finite model class and certified code behavior.

## IWI-002: uncertainty over the transition law

The companion [IWI-002 report](IWI-002.md) reuses this solver to certify strategies across an immutable ensemble of candidate Ground laws. Individually solvable laws can be jointly impossible under indistinguishable observations; one safe diagnostic can restore robust realization. Synthetic observations are still not admitted E-CPU evidence.

## IWI-003: incomplete but persistent transition and observation laws

[Read the IWI-003 finite-law experiment](IWI-003.md): a lazy strong planner preserves unknown transition and output assignments across time, distinguishes static unknowns from fresh adversarial effects, and verifies a one-step reset against 2^24 possible complete Grounds without enumerating unused transitions. A separate exact global oracle checks a five-step conditional plan and an unbounded negative case. All models are synthetic pending authenticated receiver evidence.

## IWI-004: evidence-directed Ground construction

[Read IWI-004](IWI-004.md): exact minimum-worst-case evidence acquisition when an incomplete static Ground prevents guaranteed execution, with signed-sample versus complete-law-coverage separation, full-revision conflict refusal, and a read-only ECDSA feature-receipt bridge to IFS GCI-004/005. The symbolic offline law oracle is an explicit hypothesis; actual E-CPU observations are **not** promoted to universal transition restrictions.
