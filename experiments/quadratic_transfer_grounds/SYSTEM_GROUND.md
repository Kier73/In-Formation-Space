# TCN-009 — Constructive system-level Grounds

**Status:** executable research experiment. **Scope:** exact single-coordinate finite-field state systems, with up to three named operations, polynomial transitions of degree ≤5 (and degree `< p`), a declared invariant subset, polynomial observables, explicitly stated goals, and a small menu of *untrusted* host capabilities.

## The reversal

TCN-008 constructs one desired relative-phase state. TCN-009 constructs a **computational system** from requirements: transition examples, safety invariant, available host operations, observables, and goal. Its result is a transition architecture **and** a concrete control path whose terminal state satisfies the goal. The available mathematical vocabulary is finite; the compiler does not derive arbitrary new mathematics, infer an unobserved physical law, or authenticate hosts.

Let `X` be a declared subset of `F_p`, operations `f_i ∈ F_p[x]`, observations `(x, f_i(x))`, polynomial observables `o_j(x)`, and intention `o_j(x*)=v_j`. The system has the following requirements:

1. Every operation matches its stated examples.
2. Every operation maps **all** of `X` into `X` (full finite-state inductive invariant).
3. Every operation is assigned to a host declaring that operation and sufficient polynomial degree.
4. A finite sequence of hosted operations carries the declared starting state to a state satisfying all desired observable values.
5. The entire architecture and selected path respect finite budgets.

The compiler **does not assume a transition model**. It constructs polynomial models consistent with observations, tests their global invariant, and searches their reachable finite graph. In contrast to merely interpolating a polynomial and then checking it, **the invariant can force higher-degree completions**.

## Exact construction and completeness scope

Given `m` distinct observation inputs, form the unique degree `<m` interpolant `I(x)`. Every polynomial matching those examples has the form

\[
f(x)=I(x)+\prod_{j=1}^{m}(x-x_j)\,Q(x).
\]

This parameterization is *complete* for the declared polynomial degree bound `D<p`: enumerate `Q` with `deg Q ≤ D−m`. The implementation enumerates increasing degree and nonzero highest coefficients. For each candidate, check the invariant on **every** member of `X` and either retain the map or produce a precise counterexample `(operation, input, output)`.

The compiler explores each permitted combination of surviving operation models, selects cheapest declared capable hosts, and runs Dijkstra over the exact finite state graph. Its deterministic architecture objective is: minimal **sum of polynomial degrees**, then least actual declared path execution cost, then fewest steps, then lexicographic tie breaks. No approximation or trained predictor appears in this synthesis.

**Budget and truth:** candidate enumeration is bounded (`candidate_budget`). If the bound would truncate the polynomial or architecture search, the result is `refused_search_budget`, *even if* a feasible partial solution was encountered. It cannot claim global optimality or impossibility. If exhaustive search completes, unreachable statuses apply **only to the declared polynomial, invariant and host families**. The reference implementation is intentionally limited to at most `p=257` and three operations; arbitrary program synthesis is outside scope.

### Exact invariant-driven correction

Take `p=7`, permitted states `X={1,2,4}`, initial state `4`, and a required control with examples `f(1)=1, f(2)=4`. Their minimal linear interpolant is

\[
f_1(x)=3x+5\pmod 7.
\]

But `f_1(4)=3`, which violates the invariant. Construct instead

\[
f(x)=3x+5+2(x-1)(x-2)=2x^2+4x+2\pmod7.
\]

The new operator preserves every permitted state, matches the supplied observations, and realizes the goal `x=1` with the single operation `4→1`. An independent reference test enumerates **all 7³ degree-≤2 polynomials** and confirms this is the only allowed invariant-preserving realization of the goal within that family. With only degree-1 host capability it refuses.

### Composed system and observer artifact

A second system uses `p=11`, safe states `{1,…,10}`, and two constructed operations `scale(x)=2x`, `cube(x)=x³`; it requires terminal observables `identity(x)=6` and `square(x)=3`. The compiler verifies invariant preservation on all ten states, chooses distinct declared hosts, and constructs a control path to the goal.

A dedicated adapter then **reuses TCN-008** to render the terminal state as the slope of an intended relative-phase output, with an explicitly supplied cubic term. It calls the existing TCN-008 synthesis and receipt-verification code. This readout convention is declared by the observer; it is not discovered as a necessary physical relationship. Producing the full phase-output intention costs Ω(p) observations/construction work.

The same constructed cubic transition can be navigated at a 101-digit coordinate by fully enumerating its small finite orbit **once**, finding transient and cycle, then reducing the requested coordinate. That computation has `O(|X|)` initial cost and `O(1)` coordinate lookup after big-integer modular arithmetic. It is not a claim of faster general simulation or execution of an external machine.

## Falsification and negative controls

The test suite includes invariant violations of the minimal interpolant, unreachable linear-only hosts, cubic-host placement, contradictory observable goals, impossible degree-four observations within a declared degree-three family, zero execution budget, incomplete search budget, a forged self-hashed receipt, cross-intention replay refusal, independent exhaustive polynomial enumeration, 101-digit repeat navigation, and **real TCN-008 adapter verification** against its independent dense Fourier reference.

A generated SHA-256 receipt records the complete intention, exact selected architecture, selected hosts, finite verification statistics, and path. `replay_receipt` independently **re-solves** the intended system and compares the full record, rather than trusting its supplied fields. SHA-256 is an unkeyed integrity digest, **not source authentication**. Declared hosts have not been authenticated or exercised on E-CPU's compute fabric.

## Reproduce

From the In-Formation-Space repository root (requires Python 3.11+ and NumPy because the reused TCN-008 module depends on NumPy):

```bash
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/quadratic_transfer_grounds -p 'test_system_ground.py' -v
OPENBLAS_NUM_THREADS=1 python experiments/quadratic_transfer_grounds/run_system_ground.py > /tmp/tcn009.json
```

The new model synthesis and reachability code itself uses Python's standard library. The optional TCN-008 terminal-phase adapter requires the installed numeric dependency and the existing TCN-003/006 files.

## Relation to other repositories and known work

- **TCN-008** already constructs and verifies a single relative-phase state. TCN-009 composes a full finite transition-and-observation system, then invokes TCN-008 to render one requested result.
- **VGI** `virtual_ground_interpreter/vgi/typed_operator_navigation.py` requires named typed frames and distinct domain/codomain semantics. TCN-009 carries a named finite-field frame and explicit polynomial observables, but does not claim live VGI integration.
- **E-CPU** `mailcpu/law_certifier.py` separates mathematical Ground qualification and horizon refusal. `mailcpu/navigation_admission.py` requires authenticated, policy-scoped execution rights. TCN-009's polynomial certificates do not grant either host identity or execution authority.
- **Prior formal methods:** counterexample-guided inductive synthesis (CEGIS) and finite-state controller synthesis are established. This implementation is a small exhaustive **constraint-driven program synthesis** experiment using exact finite-field polynomial parameterization, not a novel universal synthesis theorem. See Abate et al., *Automated Formal Synthesis of Provably Safe Digital Controllers for Continuous Plants*, Acta Informatica (2020), and SAT-Based Counterexample-Guided Inductive Synthesis of Distributed Controllers (IEEE, 2020).

## Next research task

Introduce **typed product-state spaces** (`F_p^d`) and inductive invariants as algebraic relations, not only enumerated subsets. Compose independently certified Grounds and search for missing state variables/gates driven by counterexamples, while bounding the combinatorial explosion. Then build an E-CPU/VGI **adapter that checks actual execution authority and observation provenance** rather than only mathematical completeness.
