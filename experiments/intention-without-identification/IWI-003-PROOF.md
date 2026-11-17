# IWI-003 soundness and task-relative support

**Status:** mathematical argument for the finite implementation under explicitly stated premises; it is *not* a proof-assistant or external-kernel acceptance receipt.

## Definitions

Let S be a finite state set, A a finite action set, O a finite observation set, B₀ a nonempty set of initially possible states and G a set of targets. For each (a,s), a nonempty allowed transition domain D(a,s) is given, and for each s, a nonempty output domain E(s).

A **static completion** ω chooses one destination per D(a,s) and one output per E(s), with these values fixed for the duration of execution. All choices for distinct unknown cells are independent *by definition of this experiment's model*. The complete-law space Ω is the Cartesian product of these domains.

At observation history h, define the concrete belief C(h) as the set of pairs (s,ω) still compatible with actions and outputs seen along h. Each lazy **scenario** is (s,c), where c is a partial function assigning values to cells. It denotes a cylinder:

    [[(s,c)]] = { (s,ω) : ω in Ω, and ω extends c }.

For a set L of scenarios, [[L]] is the union of their cylinders.

## Lemma 1: Lazy expansion exactly represents static completions

**Claim.** After every action/output history h that is possible in the input model, the lazy scenario set L(h) satisfies [[L(h)]] = C(h).

**Proof.** Initially, for every s in B₀ the lazy state contains (s, empty assignment), whose cylinder contains every ω. Thus the union equals B₀ × Ω.

Assume the invariant holds before the next action a. Fix one (s,c). If the cell (a,s) is already assigned in c, every ω extending c has exactly that destination. Otherwise, partition the cylinder into the disjoint subcylinders corresponding to each allowed destination d in D(a,s), and add the commitment (a,s) = d. Next perform the same partition for the output cell of destination d if its value was not previously committed. Projecting by the actual observed output o deletes precisely the subcylinders incompatible with o. No other completions are removed. Deduplicating identical (current state, commitment) records does not alter their union. Therefore the resulting union is exactly the concrete successor belief. Induct on the history length. **QED.**

The crucial property is that commitments are **never forgotten** along any branch. Rechoosing a transition on each visit would represent a different, fresh-effect model and would violate this invariant.

## Proposition 2: A verified finite policy universally guarantees G

A policy tree contains a terminal node or an action with one child for **each** nonempty observed-output branch. The independent verifier reconstructs transitions and output partitions without calling the planner's expansion helper. At terminal leaves, it requires every surviving current state to be in G.

**Proof.** By Lemma 1, the represented scenarios cover all compatible concrete (state,completion) pairs. The verifier checks every observable branch, so no possible output trace escapes the tree. At each terminal leaf, every compatible concrete state lies in G. The policy therefore terminates in G for every s in B₀ and ω in Ω. **QED.**

The depth-increasing search enumerates all action choices and possible observation branches to depth H. If it first finds a strategy at depth d, it finds the minimum worst-case action depth **among finite strategies under this model**. For negative results, only nonexistence up to H is justified; hitting a configured cap yields an exception, not a theorem. The independent checker separately rejects a claimed shorter or unsupported policy.

## Proposition 3: A closed losing trap proves unbounded impossibility

In the separate small global oracle, every static completion is explicitly enumerated and combined with the state into one finite world identity. All observation-reachable beliefs are discovered. The least strong winning attractor begins with terminal beliefs and repeatedly includes a belief whenever **some** action has **all** output successors already winning. After stabilization, every reachable belief outside the attractor has, for every action, at least one successor still outside it.

If the initial belief is outside the attractor, no observer policy can force finite termination in G against all possible worlds: the opposing selection of a still-losing observation branch witnesses nontermination or failure. This is the standard finite-game attractor argument, applied here only to the exact supplied candidate laws. **QED.**

## Proposition 4: Conservative task-relative law support

For a **verified winning policy** P, define Support(P) as the union of unknown cell keys committed on **every terminal-world scenario across all branches**. Because commitments persist, this equals the union of unknown cells read along possible executions of P.

**Claim.** For any same initial state s and any static completions ω and ω' that agree on Support(P), P has the **same action/output trace and terminal state** under (s,ω) and (s,ω').

**Proof by first difference.** Suppose executions differ. Let the first differing output or destination occur. Before it, their histories, chosen actions and current states agree. The differing transition or output would come from a cell read by the execution under ω, hence a cell in Support(P). The two completions agree on that cell, a contradiction. Thus no first difference exists. **QED.**

Consequently, unspecified cells outside Support(P) can be left unresolved **for this policy and intention** without changing its execution. The support is a **sufficient, conservative overapproximation**, not a minimal sensor set or optimal feature selection. The certificate has no claim of independent physical authentication.

For the 24-unknown-cell reset fixture, Support(P) is **empty** and the 24-cell uncertainty remains irrelevant to that one-step intention. For the five-step probe fixture, Support(P) contains exactly the one unknown transition cell used by the policy. If any authentic E-CPU observation falls outside D/E, this entire certificate's premises must be revisited rather than extrapolated.

## Evidence levels

- **Verified relative to mathematical inputs:** the finite models, per-branch transition predictions, deterministic certificates and independent internal checkers.
- **Not verified by this experiment:** correctness or completeness of the supplied allowed domains, actor identity, receiver cryptographic signatures, physical transitions, VGI Ground admissions, authorized external effects, live reliability, or model robustness to malicious reports.
- **Unknown:** whether a compact certificate can be constructed directly from a realistic mixed symbolic/empirical Ground without state explosion or independently trusted sensor completeness.

The next natural task is not to trust a narrowed domain because one message says it is narrow. It is to acquire independently contextualized evidence and distinguish witnessed outcomes, universally justified exclusions, and unknown coverage before admitting a new Ground revision.
