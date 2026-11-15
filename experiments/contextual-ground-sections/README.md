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

Intersect these constraints. For one connected graph, there are **exactly 0, 1, or p global sections**. This is a theorem for this *particular affine-field model*, not for arbitrary Grounds. The solver is linear in vertices plus edges (ignoring finite-field arithmetic costs); unlike the independent oracle, it never enumerates p^|V| assignments. Primality checking is a separate simple trial-division input guard; this is not a cryptographic field implementation.

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

The independent verifier checks every edge/map and cycle/conclusion relation for the full graph. No state assignment is enumerated. The naive ambient assignment space has **65521^1024** possible coordinate tuples, but spanning-tree propagation and exact cycle constraints classify all of them at once, with work proportional to graph size in this model. This directly tests a constrained interpretation of "navigation rather than iteration": the implementation computes a certificate for an entire family of states without visiting every member. It does *not* prove constant-time global computation, physical substrate independence, or an actual speedup compared with optimized production solvers.

    node experiments/contextual-ground-sections/scale.js 1024
    node --test experiments/contextual-ground-sections/test_scale.js

The CLI prints elapsed local solver-plus-verifier time to permit reproducible measurements; the exact result record intentionally excludes environment-dependent elapsed times. No statistically controlled hardware speed comparison is claimed. The program accepts 4–8,192 contexts in this fixture family, but the tested default is 1,024. The independent verifier has a different modular inversion algorithm from the producer; this is mathematical implementation diversity on one JavaScript runtime, not a separate machine trust boundary.

## Relationship to prior mathematics and other projects

Global sections and their obstruction by local compatibility are established in the sheaf-theoretic contextuality literature; cycle consistency and group synchronization are established in graph theory and geometry. **Do not claim that those ideas are first discovered here.**

- Abramsky & Brandenburger (2011), *The Sheaf-Theoretic Structure of Non-Locality and Contextuality*: https://arxiv.org/abs/1102.0264
- Lerman & Shi (2022), *Robust Group Synchronization via Cycle-Edge Message Passing*: https://doi.org/10.1007/s10208-021-09532-w
- Recent work explicitly examines higher-order compatibility from cycle holonomy: https://arxiv.org/abs/2604.19682

CGS-001 is a **fresh, falsifiable integration experiment in this repository**, not a demonstration that a novel universal mathematical principle has been discovered. The new practical distinction it exercises here is between *map-level interoperability*, *pointwise realizability*, and *intention-relative sufficiency*.

This work **studied** IFS GCI-003 and GCI-005 as conceptual resources; it does not copy or invoke their code, modify E-CPU or VGI, assert physical observer signatures, or silently upgrade any inferred state to a verified reading.

## Frontier after CGS-001

Attach *evidence-scoped* maps to real E-CPU/VGI observations. Reject a synthetic cycle unless its links are authorized and current; distinguish unavailable links from contradictory ones; derive the smallest observation needed to decide the intended output **without** disclosing internal coordinates. Later examine nonlinear, noninvertible and partially observed maps, where section cardinalities are no longer confined to {0,1,p}. Those are open tasks, not capabilities established here.
