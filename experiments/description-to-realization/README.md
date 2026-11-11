# From description to realization

**Status:** open hypothesis and experiment proposal; not yet empirically tested.  
**Seed intuition:** “Describe what you want, and it exists as a result; information is an infinite dimension in-formation.” The wording is retained as a starting intuition, not treated as an established law.

An optional [construction brief template](brief-template.md) is included for preparing a common input to independent contributors.

## 1. The question

When does a description stop being merely a statement about a desired thing and become an effective means of bringing a thing into being?

A description can make an object exist as a representational object immediately: it can be inspected, shared, transformed, criticized, and used to guide action. That is not the same as constructing an artifact, making it work, or realizing a state in an external environment.

The research opportunity is the transition between these senses of existence. A description may do more than select a point from a fixed catalogue. By introducing variables, distinctions, constraints, and operations, it may define or enlarge the space in which new candidates can be constructed.

## 2. Keep several meanings of “exists” distinct

These are evidence categories, not a guaranteed sequence. A project may satisfy one without satisfying the next.

| Sense | What exists | What would support the claim |
| --- | --- | --- |
| **Described** | A specification, intention, or concept is recorded. | An inspectable description and its provenance. |
| **Represented** | A model, symbol structure, or candidate state can be manipulated. | A representation with defined semantics or operations. |
| **Constructed** | An artifact has been produced from the description. | The artifact, construction method, inputs, and provenance. |
| **Operational** | The artifact behaves within a stated computational or physical substrate. | Execution or use evidence against explicit criteria. |
| **Externally realized** | A target state has been brought about in an environment outside the description or model. | An observed intervention path and independent evidence of the resulting state. |

The important boundary: a generated description is not evidence that its described process exists. A generated artifact is not evidence that it works. A passing test is not proof of unrestricted behavior beyond its tested conditions.

## 3. A provisional model

Let a request or intention be represented as:

\[
D = (C_h, C_s, O, R, U)
\]

where:

- \(C_h\): hard constraints that must hold;
- \(C_s\): soft preferences that can be traded off;
- \(O\): observable success criteria and required witnesses;
- \(R\): available resources, tools, substrate, and permissions;
- \(U\): unresolved choices or missing information.

Given a representational substrate \(\mathcal{B}\), the description can induce a candidate space:

\[
\mathcal{X}_D = \operatorname{ConstructSpace}(D, \mathcal{B})
\]

This notation intentionally allows two cases:

1. **Restriction:** the description selects candidates from a space already available in \(\mathcal{B}\).
2. **Expansion:** the description introduces new variables, relations, or operators, so the useful representation space itself is extended.

A constructor operating under a finite budget \(b\) may then produce:

\[
G(D, \mathcal{B}, b) \rightarrow (A, P)
\]

where \(A\) is a candidate artifact (or an explicit failure/no-solution result) and \(P\) is provenance: inputs, transformations, tool activity, and assumptions.

A separate evaluator returns:

\[
V(D, A) \rightarrow (S_h, S_s, U', W)
\]

where \(S_h\) records hard-constraint satisfaction, \(S_s\) records soft-constraint fit, \(U'\) records unresolved conditions, and \(W\) contains witnesses such as tests, proofs, measurements, or execution receipts.

The distinction between constructor and evaluator matters. The system that creates an artifact should not be the sole authority declaring that the artifact meets its own description.

## 4. What “information is an infinite dimension” could mean

One useful interpretation is not that physical storage or any one observer is literally infinite. Rather:

- Every new distinction can make previously indistinguishable states representably different.
- A distinction adds an effective information dimension only when it separates possibilities that the earlier representation treated as equivalent; a redundant label expands vocabulary without necessarily expanding the state-space.
- A new variable or relation can create directions of exploration that were not present in the earlier model.
- Descriptions can be composed, refined, translated, and used to create new representational primitives.
- No finite contributor needs to enumerate the entire possibility space in order to construct a useful path through it.

A simple schematic is:

\[
\mathcal{X}_{n+1} = \operatorname{Extend}(\mathcal{X}_n, d_{n+1})
\]

where \(d_{n+1}\) is a newly introduced distinction. The extension may be a product space in a simple case, but it need not be; constraints can couple dimensions, collapse alternatives, or make some combinations impossible.

This suggests a productive research question: **Can an independently understandable description carry enough structure not only to specify a desired result, but to teach a later constructor how to create the representation and operations needed to reach it?**

## 5. Failure modes that should remain visible

- **Underspecification:** many artifacts satisfy the description; the constructor must preserve choices instead of silently inventing requirements.
- **Overconstraint:** no artifact satisfies all hard constraints; the correct result may be a minimal conflict explanation, not a fabricated success.
- **Hidden assumptions:** a constructor imports defaults, libraries, data, or interpretations that were not part of the description.
- **Substrate mismatch:** the described result is not constructible with the available tools, permissions, materials, or time budget.
- **Evaluator mismatch:** a test measures a proxy rather than the requested outcome.
- **Self-certification:** the constructor reports success without an independent witness.
- **Representation lock-in:** the first vocabulary is mistaken for the only possible representation of the desired thing.

A valuable constructor should be able to return: “I can describe it,” “I can model it,” “I can build this approximation,” “I cannot satisfy these constraints together,” or “I need one discriminating piece of information.” Those are materially different outcomes.

## 6. Proposed experiment: independent realization from one description

### Question

How much useful construction can two independent contributors recover from the same compact description, and which parts of the result are stable versus interpretation-dependent?

### Procedure

1. Choose a small task whose result can be inspected or tested. Keep the target within the available tools and permissions.
2. Write one brief with hard constraints, soft preferences, success criteria, known resources, and explicit unknowns. Do not prescribe an implementation unless implementation is itself a requirement.
3. Give the same brief to two independent contributors with no access to each other's work.
4. Ask each to return an artifact, a construction trace, assumptions, unresolved decisions, and verification evidence. They must distinguish generated/simulated behavior from actual execution.
5. Evaluate both artifacts against the same criteria, preferably using an evaluator that did not produce either artifact.
6. Give a third contributor both outputs and ask it to identify common structure, incompatible choices, reusable parts, and a possible synthesis. Do not require a single winner.

### Record

- Exact brief and its hash or revision.
- Contributor/tool context and additional resources available.
- Artifact and construction trace from each contributor.
- Hard constraints met or violated; soft preference fit.
- Tests and witnesses actually executed.
- Assumptions introduced, unresolved choices, and failures.
- What was combinable, what was irreducibly different, and what new representation emerged during synthesis.

### What would count as a useful result

A useful result is not necessarily identical artifacts. It may be:

- independent constructions that share a stable functional core;
- distinct constructions that expose hidden degrees of freedom in the brief;
- a synthesis that is more capable than either input artifact;
- a precise demonstration that missing information blocks construction;
- a counterexample showing that the brief is inconsistent or the evaluator is inadequate.

Textual similarity alone is not a success metric. Functional correspondence, constraint satisfaction, provenance quality, and ability to continue the work matter more.

## Active trials

- [Trial 01: Poset Causal Interleaver](trials/trial-01-poset-interleaver/brief.md) — construction of a lightweight, zero-dependency causal interleaver that verifies acyclicity with cycle witness extraction, counts linear extensions via down-set dynamic programming, and verifies trace validity. A follow-up review added query-purity and randomized brute-force cross-checks.
  - [Construction report](trials/trial-01-poset-interleaver/construction-report.md) — implementation trace and constraint satisfaction evidence.
  - [Independent evaluation](trials/trial-01-poset-interleaver/evaluation.md) — verification against hard constraints and soft preferences.
  - [Code: poset_interleaver.py](trials/trial-01-poset-interleaver/poset_interleaver.py) | [Tests: test_poset_interleaver.py](trials/trial-01-poset-interleaver/test_poset_interleaver.py) | [Encounter receipt](trials/trial-01-poset-interleaver/results/test-encounter.json)

### Trial 02: Finite description, unbounded space

[Trial 02](trials/trial-02-finite-description-unbounded-space/README.md) contrasts an infinite language recognized by a finite-state machine with an infinite language whose distinct prefixes require unbounded distinguishability. The implementation supplies lazy generators, constructive product-state witnesses, distinguishing suffixes, and finite tests.

- [Construction brief](trials/trial-02-finite-description-unbounded-space/brief.md)
- [Implementation](trials/trial-02-finite-description-unbounded-space/finite_description.py)
- [Tests](trials/trial-02-finite-description-unbounded-space/test_finite_description.py)
- [Construction report](trials/trial-02-finite-description-unbounded-space/construction-report.md)
- [Independent evaluation](trials/trial-02-finite-description-unbounded-space/evaluation.md)
- [Encounter receipt](trials/trial-02-finite-description-unbounded-space/results/test-encounter.json)

### Trial 03: Distinction refinement

[Trial 03](trials/trial-03-distinction-refinement/README.md) turns the phrase “new information adds a dimension” into a finite partition-refinement test. It distinguishes genuinely new observations from features determined by the current representation, and reports both newly separated state pairs and conditional entropy under explicit weights.

- [Construction brief](trials/trial-03-distinction-refinement/brief.md)
- [Implementation](trials/trial-03-distinction-refinement/distinction_space.py)
- [Tests](trials/trial-03-distinction-refinement/test_distinction_space.py)
- [Construction report](trials/trial-03-distinction-refinement/construction-report.md)
- [Independent evaluation](trials/trial-03-distinction-refinement/evaluation.md)
- [Encounter receipt](trials/trial-03-distinction-refinement/results/test-encounter.json)

### Trial 04: Active distinction selection

[Trial 04](trials/trial-04-active-distinction-selection/README.md) turns active attention into a cost-aware observation-selection problem. It chooses a minimum-cost packet of observations that separates a target from its remaining alternatives, using exact weighted set-cover dynamic programming for modest ambiguity sets and a labelled greedy approximation for larger ones.

- [Construction brief](trials/trial-04-active-distinction-selection/brief.md)
- [Implementation](trials/trial-04-active-distinction-selection/attention_selection.py)
- [Tests](trials/trial-04-active-distinction-selection/test_attention_selection.py)
- [Construction report](trials/trial-04-active-distinction-selection/construction-report.md)
- [Independent evaluation](trials/trial-04-active-distinction-selection/evaluation.md)
- [Encounter receipt](trials/trial-04-active-distinction-selection/results/test-encounter.json)

### Trial 05: Query-directed attention

[Trial 05](trials/trial-05-query-directed-attention/README.md) generalizes active observation selection from identifying one target state to resolving a Boolean question over a set of remaining hypotheses. It chooses observations that separate every hypothesis pair on opposite sides of the query, without paying to distinguish hypotheses that agree on the question. A Poset example shows when other pairwise event-order measurements cannot resolve a queried cross-stream relation without a direct shared-clock comparison.

- [Construction brief](trials/trial-05-query-directed-attention/brief.md)
- [Implementation](trials/trial-05-query-directed-attention/query_attention.py)
- [Tests](trials/trial-05-query-directed-attention/test_query_attention.py)
- [Construction report](trials/trial-05-query-directed-attention/construction-report.md)
- [Independent evaluation](trials/trial-05-query-directed-attention/evaluation.md)
- [Encounter receipt](trials/trial-05-query-directed-attention/results/test-encounter.json)

### Trial 06: Adaptive attention policies

[Trial 06](trials/trial-06-adaptive-attention-policy/README.md) extends static observation packets into outcome-dependent decision trees. It chooses the next observation after seeing the previous result, minimizing expected additive cost under a supplied prior and reporting worst-case path cost. The exact subset solver is bounded to a modest finite hypothesis set and reports pairs that no available observation can distinguish.

- [Construction brief](trials/trial-06-adaptive-attention-policy/brief.md)
- [Implementation](trials/trial-06-adaptive-attention-policy/adaptive_attention.py)
- [Tests](trials/trial-06-adaptive-attention-policy/test_adaptive_attention.py)

[Attention and Distinction Landscape](attention-landscape.md) compares Trials 03–06 and explains when partition refinement, target isolation, query resolution, or adaptive policies are appropriate.

## 7. Open questions

1. Which parts of a description are sufficient to make a construction reproducible across different model families and tool environments?
2. Can a description encode the procedure for creating missing representational primitives, rather than only naming a desired output?
3. How should a constructor request clarification when the cost of a wrong assumption exceeds the cost of another observation?
4. Can independent realization reveal a useful invariant that was not explicit in the original brief?
5. When is divergence between constructions evidence of underspecification, and when is it evidence of genuinely different but valid realizations?
6. Can an artifact carry its own compact witness of how it was derived and what its verification does—and does not—establish?

## 8. Boundaries

This proposal does not claim that language alone changes external reality, that every desire is feasible, or that an infinite possibility space can be exhaustively searched. It treats description as a potential constructive instrument whose power depends on representation, resources, operations, and verification.

The experiment is intentionally small. The framework should become more precise only where actual construction attempts expose a need.
