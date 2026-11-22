# SPN-008 — Direct SAT, proof-admitted machine selection, and the P versus NP cost ledger

**Date:** 2026-11-21. **Status:** reproducible finite experiments, Python standard library, direct source-DIMACS support. **No P=NP/P!=NP claim.**

## Research question

Can the intended result, together with the structure of a SAT instance, construct a more suitable computational language and verified execution procedure **without hiding the cost of discovering that language**?

SPN-001–007 represented violation energy in a signed Walsh basis and explored spectral restriction, phase cycles, parity obstructions, direct-sum minimization and source-bound receipts. PNG-001 provides a different exact Ground through traditional factor elimination and counts all satisfying assignments. **SPN-008 tests direct SAT** instead of relying on an energy-ground proxy: it accepts ordinary DIMACS CNF, returns `SAT`, `UNSAT`, or `UNKNOWN`, and admits a decision only after checking evidence from the original clauses.

This is a matched comparative experiment, not a replacement for a state-of-the-art clause-learning SAT solver. The exact 3-SAT solver in this folder is intentionally small and inspectable.

## The three computational languages

**1. Literal/CNF language — bounded DPLL.** Unit propagation repeatedly derives forced assignments. Search branches on an unassigned variable and (for UNSAT) retains a complete two-child proof tree. A `conflict` leaf is accepted only when the separate checker derives a false clause from the *original* formula plus the path's branch decisions through its own unit-closure implementation. A `witness` is accepted only when all original clauses evaluate true. If the node limit prevents closure, the result is `UNKNOWN`.

**2. Recovered parity language — complete XOR clauses.** For a variable scope `S` of width `k<=3`, each `k`-literal clause forbids one local assignment. Exactly `2^(k-1)` clauses forbidding one parity class encode the complementary XOR equation on the variables in `S`:

\[
\bigwedge_{a: \oplus a=b}\bigvee_{i\in S}(x_i\ne a_i)
\quad\Longleftrightarrow\quad\bigoplus_{i\in S}x_i=1-b.
\]

The producer recognizes whole parity groups from the original clauses, then solves the resulting linear system over `GF(2)`. **Only when every relevant source clause is represented by a verified group** is the recovered linear language used to decide the whole formula. Repeated literals are simplified and tautologies omitted; both operations preserve the original conjunction. For a SAT proof, the source assignment is checked directly. For UNSAT, the receipt names a combination of recognized equations whose left-hand XOR cancels to zero and right-hand XOR is one. The checker **does not trust the producer's equation recognizer**: it independently evaluates each original clause group on every local assignment and verifies exact parity equivalence, then checks the named XOR dependency.

This is a well-established tractable class (XOR-SAT), not a new polynomial-time algorithm for unrestricted SAT. The specialized compiler is small because the clause width is bounded, and Gaussian elimination is polynomial in the number of equations and variables. Arbitrary mixtures of XOR and non-XOR clauses are *not* declared linear by this implementation.

**3. Walsh/spectral Ground language — optional fallback.** When a bounded direct DPLL search refuses, and the source has exactly three distinct variables per clause, the compiler may invoke SPN-007 on a *semantics-preserving conversion* to forbidden-bit constraints. It wraps the nested SPN source-bound certificate, and the outer verifier reconstructs the conversion and rechecks the nested result. A fallback's own `UNKNOWN` remains `UNKNOWN`.

The system currently makes a deterministic choice: recognized complete XOR first, direct DPLL second, optional SPN certificate third. This is a **proof-admitted selection policy**, not a learned optimal policy. Producer timings and chosen strategy are untrusted telemetry, not logical premises of the proof.

## Admissibility and the P versus NP distinction

* For arbitrary width-3 CNF, direct source verification of a SAT witness is polynomial, but complete DPLL UNSAT proof trees can be exponentially large. A bounded failure never means UNSAT.
* A complete XOR encoding can have a high-dimensional state space and still be decided by polynomial-time parity solving. The *source-bounded equivalence check* is essential: a few extracted XOR consequences would not automatically be equivalent to the whole formula.
* PNG-001 counts models exactly using factor elimination; its explicit factors may grow exponentially with the induced frontier width. Its counts are used as comparisons, not substituted for a source-checkable UNSAT proof.
* SPN-007 can construct exact finite spectral Grounds when a cheap decomposition exists. Its discovery/verification work may outweigh any reduction in search nodes.
* If a **uniform** compiler plus navigator solves *every* SAT input correctly in polynomial total time, it yields a deterministic polynomial-time SAT decision algorithm and thus `P=NP`. These limited experiments do not supply that universal hypothesis.

We therefore distinguish `description size`, `language recognition`, `ground construction`, `proof search`, `proof bytes`, `verification`, `frontier width`, and `explicit UNKNOWN`. The source problem is never judged by a compressed coordinate alone.

## Reproduced experiment A — matched direct SAT and earlier Grounds

Run:

```bash
cd experiments/pnp-ground-navigation/spectral_phase_navigation
python direct_sat_campaign.py > direct_sat_results.reproduced.json
```

Seed `84008`. For the 120 sampled 3-CNFs (90 near-density `m/n~4.25` and 30 planted satisfying formulas) and a 12-variable, 22-clause pigeonhole contradiction, the script checks every count exhaustively (all cases have `n<=12`), rechecks the direct SAT receipts from source, checks the SPN-007 receipts (where 3-CNF representation applies), and compares with the **existing sibling PNG-001** factor solver's exact model count. The PNG execution time includes factor construction and min-fill ordering.

The following values are one local CPython run, not stable performance rankings or comparable external solver benchmarks:

| Sample | Instances | SAT / UNSAT | Direct SAT: total ms | PNG-001 exact count: total ms | SPN-007 decision: total ms | Direct DPLL nodes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Random 3-SAT, n = 8, 10, 12 | 90 | 72 / 18 | 57.3 | 738.9 | 906.3 | 673 |
| Planted 3-SAT, n = 8, 10, 12 | 30 | 30 / 0 | 15.6 | 197.4 | 19.7 | 203 |
| Pigeonhole 4 into 3 | 1 | 0 / 1 | 0.49 | 2.07 | Not applicable (mixed widths) | 11 |

Every accepted decision agreed with the exhaustive answer. All methods have different objectives: PNG solves **#SAT**, whereas the two decision solvers need only **SAT/UNSAT**, so their times are not head-to-head proof of algorithm superiority. The source-checking costs are included in direct and SPN production; PNG counting is validated externally by exhaustive enumeration on these small cases.

## Reproduced experiment B — high-variable parity instances

`test_direct_sat_compiler.parity_cycle_family` builds disjoint six-variable blocks; each has four three-variable parity equations encoded using four 3-CNF clauses each. The frustrated case flips one equation's right-hand parity, creating a four-equation zero-left/one-right contradiction. The SAT case has compatible equations.

At 20 blocks (120 variables, 320 width-three clauses):

| Goal | Direct SAT | SPN-007 | PNG-001 |
| --- | --- | --- | --- |
| SAT | Source-checked XOR witness, ~2–3 ms | Source-checked SAT witness, ~5 ms | Exact #SAT via factor elimination, ~15 ms |
| UNSAT | Four-equation XOR contradiction, ~2–3 ms | Exact Ground, ~14 ms | Exact count 0, ~17 ms |

The direct UNSAT receipt is under 500 serialized bytes, *excluding* the 320-clause source; this illustrates proof compression, not data-free computation. The SAT case has **2^60** satisfying assignments (one 3-rank system per 6-variable block), despite an exponentially large Boolean cube. Gaussian elimination never enumerates them. The factor solver's largest generated scope has four variables on this family.

**Negative control:** If the CNF contains a partial parity group or an arbitrary non-parity clause, this version refuses XOR-only compilation. The direct DPLL engine remains available. Source-preserving duplicate literals and tautologies are handled by normalization and checked against the unmodified source.

## Reproduced experiment C — direct bounded SAT near density 4.26

Run `python direct_sat_hardness.py > direct_sat_hardness.reproduced.json` (seed `80488`). The 3-SAT formulas choose three distinct variables per clause and random signs, `m=round(4.26*n)`. This ratio is a **stress location motivated by random 3-SAT research**, not an assertion of an exact threshold or proof of difficult asymptotic behavior. The benchmark uses 12 cases for `n=16,20,24,28,36,48`; 8 each for `n=64,80,96`; and 4 for `n=120`. Larger cases are verified only via source-checkable SAT/UNSAT receipts; there is no exhaustive reference at these sizes.

| n | Samples | DPLL at 256: SAT / UNSAT / UNKNOWN | DPLL at 2,048: SAT / UNSAT / UNKNOWN |
| ---: | ---: | --- | --- |
| 48 | 12 | 8 / 4 / 0 | 8 / 4 / 0 |
| 64 | 8 | 3 / 2 / 3 | 4 / 4 / 0 |
| 80 | 8 | 2 / 0 / 6 | 6 / 2 / 0 |
| 96 | 8 | 1 / 0 / 7 | 4 / 3 / 1 |
| 120 | 4 | 0 / 0 / 4 | 1 / 0 / 3 |

The 256-node run fails to settle most n>=80 observations. Increasing the budget resolves many, but leaves four unresolved at n>=96. No budget failure was classified as UNSAT. Twelve small high-density cases (`n=16,20,24`, 4 each) also ran the SPN-007 decision fallback at 128 nodes and checked agreement when both approaches admitted a decision. The measured spectral approach sometimes remained UNKNOWN even when direct SAT produced a proof. This is an intentional falsification attempt against unwarranted claims that spectral representation is automatically more efficient.

## Tandem development: SFI-001 and PNG-002/003 (same account, studied)

The concurrently merged [SFI-001 problem-formed SAT interpreter](../SFI-001.md)
(source revision `276e669b4aa1bbd251dd5bb9e76f33bad65e692b`)
already goes beyond strategy selection. It constructs registers, a decoder,
partition topology and an intention-specific accumulator from source-verified
[PNG-003](../PNG-003.md) algebraic Grounds, then evaluates the **original CNF**
for each generated free-coordinate state. The [PNG-002](../PNG-002.md)
parity recovery and PNG-003 proof verifier allow it to handle some *mixed*
linear-plus-CNF examples that the present SPN-008 all-XOR recognizer refuses.
SFI-001 includes complete coverage/refusal rules for #SAT and direct SAT.

**Division of research:** SPN-008 is a portable direct DIMACS SAT baseline with
small, checkable DPLL/XOR decision receipts and matched SPN/PNG campaigns.
SFI-001 is the stronger *problem-formed interpreter* construction and should
be the preferred starting point for mixed Ground synthesis. No result in
SPN-008 claims to supersede its verified source-equivalence work. An important
follow-up is to run **the same source CNFs** through SFI-001 and this direct
baseline with identical goals, include SFI-001's Ground construction costs,
and compare proof size, model counts and budget refusals.

## Direct usage and evidence portability

```bash
# Obtain SAT, UNSAT, or UNKNOWN from an ordinary DIMACS file.
python direct_sat_cli.py examples/xor_cycle_unsat.cnf --node-budget 256 --out proof.json
# Independent process, same Python trusted base, checks against source.
python direct_sat_cli.py examples/xor_cycle_unsat.cnf --verify proof.json
# Optional SPN fallback when a CNF search budget expires.
python direct_sat_cli.py examples/three_var_sat.cnf --node-budget 1 --spectral-budget 256
# Test and reproduce.
python -m unittest -q test_direct_sat_compiler.py test_direct_sat_cli.py
python direct_sat_campaign.py > direct_sat_results.reproduced.json
python direct_sat_hardness.py > direct_sat_hardness.reproduced.json
```

`direct_sat_cli.py` requires a strict `p cnf n m` declaration, zero-terminated clauses, and width at most three. It supports comments and clauses continuing across lines. Its emitted JSON binds the source's ordered clause semantics using SHA-256. That hash is a source identity convention under collision resistance, not a proof of formula equivalence. A verifier must receive the original CNF; a free-floating proof without the source is not sufficient. Because this is an experimental Python checker rather than a formally verified kernel or broadly supported SAT-proof format, further independent implementation work is warranted.

For external SAT tooling, the relevant standard is DIMACS CNF; proof-carrying industrial SAT commonly uses DRAT/LRAT rather than this small recursive proof grammar. Do not compare this educational unit-propagation DPLL engine to contemporary CDCL systems as though it were a tuned benchmark. See the [Stanford SAT course DIMACS slides](https://web.stanford.edu/class/cs257/slides/Lecture_3.pdf), the [SAT Handbook preprocessing chapter](https://cca.informatik.uni-freiburg.de/papers/BiereJarvisaloKiesl-SAT-Handbook-2021-Preprocessing-Chapter-Manuscript.pdf) on extracting encoded XOR relations, and [Extending SAT Solvers with Parity Reasoning](https://research.aalto.fi/en/publications/extending-sat-solver-with-parity-reasoning/).

## Next experiment: mixed Ground synthesis

This stage can discover an exact XOR language only when the whole CNF lies in that class. An important next test is **mixed language compilation**: extract *source-certified* parity constraints from some clause groups, retain the remaining clauses, choose free parity coordinates, and solve the residual constraint problem in those coordinates. Proving this reduction equivalent to the source and generating a compact UNSAT receipt would be the next major step. It could substantially reduce effective decision dimension on partially algebraic SAT families, while still admitting UNKNOWN when the reduction makes no progress.

Further requirements: independent external checker, exact proof size/production cost, CDCL baseline, width-4+ generalization with certified source conversion, and adversarial benchmark suites. Maintain the no-hidden-advice and uniformity requirements central to PNG-001.
