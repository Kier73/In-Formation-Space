# CGS-001 — Contextual Ground Sections: when local observers cannot be joined

**Status:** new finite mathematical experiment (2026-11-15), not a claimed discovery of an unknown general theorem.  
**Research question:** Can each pair of observer Grounds translate states correctly under its declared map, yet the whole network fail to admit a common state? If a loop fails full map-level consistency, can it still preserve *some* jointly realizable states?

This is an independent investigation inspired by, but **not a dependency of**, the existing [GCI-003 intention-relative observation sufficiency](../cross-ground-continuity/gci003/README.md) and [GCI-005 signed disagreements](../cross-ground-continuity/gci005/README.md). Neither real observers nor actual mTLS receipts are used here. The subject is an exact mathematical counterexample and a potential *pre-admission* test for federated Grounds.

## Finite model and the crucial distinction

Each vertex v has a copy of the finite field F_p (p prime). Every **directed** edge u -> v declares an invertible affine translation

    T_uv(x) = a_uv*x + b_uv  (mod p),   a_uv != 0.

Traversing an edge backward uses the exact inverse map. Each edge is individually a valid bijection. We distinguish:

1. **A globally flat chart:** all path translations agree for **every** root value, i.e., every closed loop has identity holonomy.
2. **A global section:** a selection of *one value at each vertex* satisfying **every edge equation simultaneously**.
3. **An intention-specific answer:** a requested output is constant across all admissible global sections. When there are no sections, an answer must be refused rather than inferred by vacuity.

These are genuinely different obligations. In particular, a nonidentity loop can fix one value without fixing the whole coordinate system.

## Exact method (no full assignment search required)

Choose any spanning tree and root r. Let P_v be the unique affine map taking a root value to the value at v along the tree. For a non-tree edge e=(u,v), compute the *root-space cycle holonomy*

    H_e = inverse(P_v) o T_uv o P_u.

For every valid global section, its root coordinate x must obey H_e(x)=x. Conversely, if x satisfies every such constraint, assigning x_v=P_v(x) satisfies every edge. The proof of the converse is direct substitution in tree edges and non-tree edges; it does not assume probabilistic independence.

Write H_e(x)=a_e*x+b_e mod p. Then

    (a_e - 1)*x = -b_e mod p.

Because p is prime, each constraint has exactly three possible types:

- a_e=1, b_e=0: every x is allowed.
- a_e=1, b_e!=0: no x is allowed.
- a_e!=1: exactly one x=(-b_e)/(a_e-1) mod p is allowed.

Intersect these constraints. For one connected graph, there are **exactly 0, 1, or p global sections**. This is a theorem for this *particular affine-field model*, not for arbitrary Grounds. The graph traversal and cycle-equation pass uses O(|V|+|E|) field operations; deterministic ordering adds O(|V| log |V| + |E| log |E|) sorting cost. Unlike the independent oracle, the solver never enumerates p^|V| assignments. Primality checking is a separate simple trial-division input guard; this is not a cryptographic field implementation.

## Four experiments: exact F_5 counterexamples

Every example has locally invertible edge maps. The table reports *global* conclusions.

| Fixture | Map-level flat? | Number of sections | Interpretation |
| --- | --- | ---: | --- |
| flat | yes | 5 | all root values survive |
| translation-obstruction | no | 0 | one cycle acts as x -> x+1, fixing nothing |
| nonflat-but-realizable | no | 1 | one cycle acts as 3x, fixing root x=0 |
| incompatible-fixed-points | no | 0 | two loops separately admit x=0 and x=1, but no common point |

The explicit cycle holonomies depend on the deterministic spanning tree and root, but the **existence and number of global sections** do not. A chart change at each observer, G_v, transforms each edge to G_v o T_uv o inverse(G_u). This bijects old sections with new sections and conjugates rooted loop holonomies. Thus the cardinality and chart-flatness are observer-coordinate invariant.

The returned "obstruction_edges" are names of non-tree edges witnessing impossible root constraints *relative to the recorded spanning tree*. They are not, on their own, authenticated evidence or an unsatisfiability proof detached from the graph.

## CGS-002 within the same investigation: exact multicycle ensemble

The solver is deterministic. To investigate how realizability behaves in a *specified synthetic ensemble*, independently choose each fundamental-cycle holonomy uniformly from the affine group AGL(1,F_p), with size

    M = p*(p-1).

Exactly p-1 of the M affine maps fix a specified point x, including identity. The identity is the only map fixing *every* point; any other affine map fixes at most one point. Inclusion–exclusion is not needed because different nonidentity fixed-point choices are disjoint. Over k independently chosen cycle holonomies, the **exact counts** among M^k combinations are

    all       = 1
    singleton = p * ((p-1)^k - 1)
    empty     = M^k - all - singleton.

The k=0 case has one assignment of holonomies and preserves all p root coordinates. For k>=1, the fraction with at least one valid section is

    [1 + p*((p-1)^k - 1)] / [p*(p-1)]^k.

For p=5, k=2, the counts are 1 all, 75 singleton, **324 empty**, among 400 total combinations. For p=3, k=1, the counts are 1/3/2 among 6 holonomies. The exhaustive **216** three-edge affine-labelled triangles multiply those proportions by 36: **36 all / 108 singleton / 72 empty**.

The distribution describes *artificially independent, uniform affine holonomies*. It does **not** predict reliability, faults, or agreement rates in an actual observer fabric. Real transport maps are often correlated, measured imperfectly, and not invertible.

## Verification and reproduction

Requires **Node.js 20+**, standard library only:

    node --test experiments/contextual-ground-sections/test_sections.js experiments/contextual-ground-sections/test_verifier.js
    node experiments/contextual-ground-sections/sections.js
    node experiments/contextual-ground-sections/ensemble.js
    node experiments/contextual-ground-sections/scale.js 1024

The main solver tests include:

- an independent brute-force oracle enumerating every assignment over each small test graph;
- all 216 labelled three-edge triangles over F_3;
- all 400 two-cycle AGL(1,F_5) combinations and 216 three-cycle AGL(1,F_3) combinations;
- 120 deterministic four-vertex chart-change challenges with independent section-set comparison;
- reversal of every edge, adversarial incompatible fixed points, witness removal, and refusal on empty Grounds;
- invalid primes, disconnected graphs, invalid transport maps, and an intention-relative query that must remain unknown when outputs differ.

The independent verifier adds five more test groups, including 216 full certificate reconstructions and 14 deliberate report mutations. Four additional scaling test groups reconstruct the larger charts and check sample edge equations.

The brute oracle is bounded and intentionally uses the direct edge equations rather than the spanning-tree theorem. Passing these finite tests is evidence of implementation agreement in these cases, not a machine-checked universal theorem. The mathematical proof above is separate from program execution. See [the retained results](results/finite-results.json) and [GitHub Actions](../../.github/workflows/contextual-ground-sections.yml).

## CGS-003: a separately implemented verifier for portable section claims

The primary solver emits a **complete certificate record**: typed edges, its chosen spanning tree, root-to-vertex maps, every non-tree cycle holonomy, fixed-point constraints, chart-flatness, section count and any finite obstruction witness. None of these entries is trusted solely because the producer emitted it.

The standalone [verifier](verifier.js) uses an independently implemented modular inverse (**extended Euclidean algorithm**, versus the producer's modular exponentiation). It checks edge normalization, graph connectivity, every tree-edge map equation, every non-tree holonomy, every fixed-point constraint and the final classification. Replaying its claims is polynomial in graph size and does not require enumerating all field assignments. A deliberately mutated chart, edge, cycle, witness, or conclusion is rejected. The 14 adversarial mutation cases in the test suite exercise these checks; a larger hostile input audit remains open.

    node experiments/contextual-ground-sections/sections.js --certificates > certificates.json
    node experiments/contextual-ground-sections/verifier.js certificates.json
    node --test experiments/contextual-ground-sections/test_verifier.js

These are **mathematical consistency certificates**. They are *not signed or provenance-bound*, and a self-consistent certificate can describe a fictitious graph. An external witness of the graph's source and authority would be required for an authenticated E-CPU/VGI Ground. No claim is made that the two JavaScript implementations constitute different trust domains.

## CGS-004: navigate a huge implicit Ground without enumerating its assignments

The [scaling construction](scale.js) builds 1,024 distinct virtual observer contexts over F_65521. It gives each observer an invertible coordinate chart, derives 1,023 chain links plus 1,022 extra paths (2,045 declared edges), and uses exactly **1,022 fundamental cycles**. This is a deterministic software graph, not 1,024 processes or physical computers.

Three graph variants differ only in the chosen cycle translations:

| Synthetic Ground | Root solutions | Why |
| --- | ---: | --- |
| Flat charts | 65,521 | Every loop is the identity |
| One fixed-point cycle | 1 | A loop forces x = 65,516 |
| An additional translation loop | 0 | x -> x+1 fixes no point |

The independent verifier checks every edge/map and cycle/conclusion relation for the full graph. No state assignment is enumerated. The naive ambient assignment space has **65521^1024** possible coordinate tuples, but spanning-tree propagation and exact cycle constraints classify all of them at once, with graph-traversal work linear in vertices and edges plus canonical sorting. This directly tests a constrained interpretation of "navigation rather than iteration": the implementation computes a certificate for an entire family of states without visiting every member. It does *not* prove constant-time global computation, physical substrate independence, or an actual speedup compared with optimized production solvers.

    node experiments/contextual-ground-sections/scale.js 1024
    node --test experiments/contextual-ground-sections/test_scale.js

The CLI prints elapsed local solver-plus-verifier time to permit reproducible measurements; the exact result record intentionally excludes environment-dependent elapsed times. No statistically controlled hardware speed comparison is claimed. The program accepts 4–8,192 contexts in this fixture family, but the tested default is 1,024. The independent verifier has a different modular inversion algorithm from the producer; this is mathematical implementation diversity on one JavaScript runtime, not a separate machine trust boundary.

## CGS-005: exact navigation across *uncertain* observer paths

The preceding experiments assumed every edge's affine map was specified. CGS-005 introduces an explicitly **open mathematical evidence state**: the confirmed-base graph stays fixed, while pending links each carry a declared set of *possible* translations. A missing map is not treated as the identity or silently dropped. An expired map is not implicitly trusted; a contested edge retains all declared candidate maps without selecting a witness by preference. **No actual signature or transport receipt is verified by this model.**

Source: [uncertain.js](uncertain.js), [direct-assignment oracle](test_uncertain.js), and the [replayable scenarios](demo_uncertain.js). The accepted base is first rechecked by the independent CGS-003 verifier, but this only validates *mathematics*, not the authenticity of the base's claimed observations.

**Declared input.** The accepted graph must be connected and have the existing verified affine certificate. Each pending edge names an existing pair of vertices, an evidence-state label (`missing`, `contested`, `expired`, or `unconfirmed`), a declared source revision, and exactly one of:

- a finite nonempty **set** of distinct invertible affine maps;
- the symbolic domain **all-affine**, meaning every member of AGL(1,F_p), without allocating all p(p-1) maps.

Domains are independent *modelling choices* for this experiment; an observer's real signed testimony may correlate several edges, so the world counts must not be interpreted as physical likelihoods. A label like `contested` is retained metadata, **not** proof that any signer exists or that any map has been authenticated.

### Mathematical identity: count worlds without enumerating worlds

Given the original connected Ground's root-to-vertex maps P_v, each pending candidate map T_e induces a root-space holonomy

    H_e = inverse(P_v) o T_e o P_u.

For each pending domain D_i define the number of possible maps fixing root x:

    F_i(x) = #{ T in D_i : H_i(x) = x }

and the number of maps with identity holonomy:

    I_i = #{ T in D_i : H_i = identity }.

If the accepted base admits all p root states, the number of feasible (completion, root-value) pairs is

    S = sum over x in F_p of product_i F_i(x).

Every completion has either 0, 1, or p global sections, by CGS-001. Let A be the number of fully flat completions and B the number with exactly one section. Then

    A = product_i I_i
    S = B + p*A
    B = S - p*A
    consistent_completions = A+B = S-(p-1)*A
    inconsistent_completions = product_i |D_i| - A - B.

If the accepted base admits exactly one root x0, every completion admits at most one section, and

    consistent_completions = product_i F_i(x0).

If the accepted base has **no** sections, adding pending constraints cannot repair it; all completions remain contradictory.

For an unconstrained all-affine domain, group multiplication/conjugation is a bijection, giving:

    |D_i| = p*(p-1)
    I_i = 1
    F_i(x) = p-1 (same for all x).

A finite domain contributes a constant I_i plus a sparse correction at its nonidentity fixed points. The implementation computes S from the product of constant contributions for ordinary x, with exact corrections at the union of exceptional roots. It does **not** enumerate the Cartesian product of pending domains or the assignment space of observer states. This is an algebraic count of declared possible worlds, not a new general complexity result for arbitrary constraint systems.

### Intention-relative decisions

An intention is scoped to one vertex and a specified projection: exact state, parity, threshold, or a constant value. It is evaluated over every root that survives **at least one consistent completion**.

| Classification | Interpretation |
| --- | --- |
| `refuse-inconsistent` | No declared completion contains a global state |
| `conditional` | Some completions admit a state and some do not; no unconditional result |
| `undetermined` | All completions are consistent, but the intention varies |
| `robust` | All completions are consistent and the intention is constant |

The report *also* exposes `output_invariant_on_consistent_worlds`, which may be true even in `conditional` cases: agreement among the surviving worlds cannot hide the existence of contradictory ones. `can_admit` is **always false**, even if the mathematics is robust, because this experiment has no independent authority/signer validation. This is the crucial distinction between *proved agreement under a declared model* and *authorization to realize a live output*.

### Controlled examples over F_5

| Scenario | Complete worlds | Consistent | Contradictory | Result |
| --- | ---: | ---: | ---: | --- |
| One all-affine missing chord | 20 | 16 | 4 | Conditional |
| Two all-affine missing chords | 400 | 76 | 324 | Conditional |
| Contested map fixes root 0 or root 2 | 2 | 2 | 0 | Parity=0 is robust; exact root is unknown |
| Contested scale or conflicting translation | 2 | 1 | 1 | Conditional |
| One fully specified candidate fixing root 0 | 1 | 1 | 0 | Mathematically robust; not authenticated |

The third example is an *intention-relative compression*: multiple legitimate internal root states can imply one external answer, even while their full state cannot be reconstructed. It is not a magical recovery of the hidden phase.

### Large implicit world-space

A deterministic test uses a 1,024-observer, 2,045-accepted-edge connected atlas over F_65521, adds **128 unobserved all-affine edges**, and computes the exact completion counts and intention status. The Cartesian product of possible edge-map sets has

    [65521 * 65520]^128

members (1,233 decimal digits), yet **zero completion combinations and zero joint vertex assignments are enumerated**. The computation uses symbolic affine-group counts and sparse root constraints. The original accepted graph certificate is checked independently.

This does **not** show that missing evidence can be replaced by proof: the result is `conditional` precisely because some completions are contradictory.

Reproduce:

    node --test experiments/contextual-ground-sections/test_uncertain.js
    node experiments/contextual-ground-sections/demo_uncertain.js

The suite compares exact algebraic counts against a structurally distinct oracle that enumerates **each small completion** and independently enumerates **all vertex assignments** (not the producer's root-cycle formula). It additionally tests forged base reports, invalid domains, all four evidence-state labels, contradictory fixed points, and the 1,024-context/128-unknown-edge construction. Exact deterministic outputs are retained in [results/uncertain-worlds.json](results/uncertain-worlds.json).

### Next substantive experiment

Replace *declared* map domains with authority-checked observations from E-CPU or VGI, using a pinned Ground revision, receiver-specific evidence and freshness rules. Map uncertainty must then be tied to verified source constraints rather than an arbitrary independent ensemble. Explore coupled constraints between pending maps and other non-affine observation families. CGS-005 does not solve those problems.


## CGS-006: independent reconstruction of uncertain-world certificates

The new [uncertain-world verifier](uncertain_verifier.js) rechecks the *accepted* graph using CGS-003, but does **not import** the [CGS-005 analysis implementation](uncertain.js). Rather than constructing cycle holonomies, it substitutes each candidate affine edge equation directly into the root-to-vertex charts:

    candidate_a * P_u(x) + candidate_b = P_v(x) (mod p).

It solves these equations by extended Euclid, counts exact map alternatives per root, and reconstructs the claims from scratch. An `all-affine` domain is retained as a symbolic group-count factor, so the verifier also handles the 1,024-context / 128-pending-link case without enumerating the immense completion space.

It checks the stated counts, possible-root cardinality, target-result invariance, classification, evidence-state labels, declared source revisions, example outputs and the important `can_admit=false` distinction. Deliberately mutated world counts, results, revisions, and authority flags fail closed. The verifier also checks results for all 36 pairs of F_3 singleton affine-map alternatives.

    node --test experiments/contextual-ground-sections/test_uncertain_verifier.js

Five independent-verifier test groups passed in the in-session JavaScript V8 execution harness. As before, these two versions are independent mathematical implementations in **one JavaScript runtime**, not independent network authorities or evidence of physical measurements. A self-consistent *false premise* remains self-consistent and therefore requires source authentication in a subsequent E-CPU/VGI experiment.


## Relationship to prior mathematics and other projects

Global sections and their obstruction by local compatibility are established in the sheaf-theoretic contextuality literature; cycle consistency and group synchronization are established in graph theory and geometry. **Do not claim that those ideas are first discovered here.**

- Abramsky & Brandenburger (2011), *The Sheaf-Theoretic Structure of Non-Locality and Contextuality*: https://arxiv.org/abs/1102.0264
- Lerman & Shi (2022), *Robust Group Synchronization via Cycle-Edge Message Passing*: https://doi.org/10.1007/s10208-021-09532-w
- Recent work explicitly examines higher-order compatibility from cycle holonomy: https://arxiv.org/abs/2604.19682

CGS-001 is a **fresh, falsifiable integration experiment in this repository**, not a demonstration that a novel universal mathematical principle has been discovered. The new practical distinction it exercises here is between *map-level interoperability*, *pointwise realizability*, and *intention-relative sufficiency*.

This work **studied** IFS GCI-003 and GCI-005 as conceptual resources; it does not copy or invoke their code, modify E-CPU or VGI, assert physical observer signatures, or silently upgrade any inferred state to a verified reading.

## Frontier after CGS-001

Attach *evidence-scoped* maps to real E-CPU/VGI observations. Reject a synthetic cycle unless its links are authorized and current; distinguish unavailable links from contradictory ones; derive the smallest observation needed to decide the intended output **without** disclosing internal coordinates. Later examine nonlinear, noninvertible and partially observed maps, where section cardinalities are no longer confined to {0,1,p}. Those are open tasks, not capabilities established here.
