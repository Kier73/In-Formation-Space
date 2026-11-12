# Attention and distinction landscape

**Purpose:** connects Trials 03–06 and 08 as a progression from identifying information to selecting how to acquire it.

## The shared state-space model

Let H be the finite set of hypotheses or states still possible under the evidence currently available. Existing observations induce an equivalence relation:

    h1 ~ h2  iff  every current observation gives the same result for h1 and h2.

The equivalence classes form the current observational partition. New observations refine that partition. A task then specifies what distinction is actually needed.

## Five different questions

| Trial | Question | Output |
|---|---|---|
| [03 — Distinction Refinement](trials/trial-03-distinction-refinement/README.md) | Does a new observation add any distinction relative to what is already known? | Refined partition, newly separated pairs, conditional entropy. |
| [04 — Active Distinction Selection](trials/trial-04-active-distinction-selection/README.md) | What minimum-cost observation packet isolates one known target state? | Static weighted observation set. |
| [05 — Query-directed Attention](trials/trial-05-query-directed-attention/README.md) | What minimum-cost packet resolves one Boolean property without identifying the full state? | Static weighted observation set covering all true/false hypothesis pairs. |
| [06 — Adaptive Attention Policies](trials/trial-06-adaptive-attention-policy/README.md) | What should be observed next, given the outcomes already seen? | Outcome-dependent decision tree minimizing expected cost. |
| [08 — Intervention-aware Attention](trials/trial-08-intervention-aware-attention/README.md) | What should be probed when the probe can change the hidden state? | Outcome-dependent policy with a Pareto frontier over observation and intervention costs. |

## Choosing the right model

Use Trial 03 to evaluate whether a candidate feature is informationally new. It does not select an observation strategy.

Use Trial 04 when the desired endpoint is one particular state. It may spend effort distinguishing alternatives that are not themselves relevant to other goals.

Use Trial 05 when only a predicate matters. It avoids paying to distinguish hypotheses that agree on that query.

Use Trial 06 when observations are sequential, later choices depend on earlier outcomes, and the act of observing does not change the system.

Use Trial 08 when probes can change the hidden state. It keeps the query about the initial hypothesis explicit while carrying each candidate's current state forward, and preserves observation and intervention costs as separate Pareto dimensions.

## Common assumptions and limits

All five attention models use finite, explicit hypothesis sets. Their results are relative to those sets and the available observation functions. A missing hypothesis cannot be recovered by optimizing over the others.

Trial 04 and Trial 05 assume a static additive cost for selecting a packet. Trial 06 assumes deterministic, non-intervening observations and additive path costs, with expected cost measured under an explicit prior. Trial 08 permits deterministic, state-changing probes but still assumes a fully supplied finite transition model and a query about the initial hypothesis. Real experiments may be stochastic, may evolve between probes, may have order-dependent costs, and may introduce new hypotheses after an observation.

Most importantly, the planners select **proposed** observations. They do not execute them. A plan becomes evidence only after the observations are performed and recorded with provenance, results, and relevant environmental context.

## The next integration boundary

The [Evidence-gated Observation Path](../../bridges/observation-path/README.md) now supplies an append-only lifecycle model, and the [Adaptive Attention Execution bridge](../../bridges/adaptive-attention-execution/README.md) connects Trial 06 to it. Trial 08 contributes a planner only; the same evidence-gated path remains necessary to establish that a proposed intervention was actually performed. Together they separate:

1. predicted observation under a hypothesis;
2. selected observation request and its cost model;
3. request dispatch and receiver admission;
4. raw returned observation;
5. interpretation and partition update;
6. verification of whether the intended query is now resolved.

The remaining work is to bind this experimental coordinator to real observer/transport adapters, reusing their actual dispatch, admission, and Encounter Envelope receipts rather than inventing a second execution or provenance system.