# Attention and distinction landscape

**Purpose:** connect Trials 03–06 as a progression from identifying information to selecting how to acquire it.

## The shared state-space model

Let H be the finite set of hypotheses or states still possible under the evidence currently available. Existing observations induce an equivalence relation:

    h1 ~ h2  iff  every current observation gives the same result for h1 and h2.

The equivalence classes form the current observational partition. New observations refine that partition. A task then specifies what distinction is actually needed.

## Four different questions

| Trial | Question | Output |
|---|---|---|
| [03 — Distinction Refinement](trials/trial-03-distinction-refinement/README.md) | Does a new observation add any distinction relative to what is already known? | Refined partition, newly separated pairs, conditional entropy. |
| [04 — Active Distinction Selection](trials/trial-04-active-distinction-selection/README.md) | What minimum-cost observation packet isolates one known target state? | Static weighted observation set. |
| [05 — Query-directed Attention](trials/trial-05-query-directed-attention/README.md) | What minimum-cost packet resolves one Boolean property without identifying the full state? | Static weighted observation set covering all true/false hypothesis pairs. |
| [06 — Adaptive Attention Policies](trials/trial-06-adaptive-attention-policy/README.md) | What should be observed next, given the outcomes already seen? | Outcome-dependent decision tree minimizing expected cost. |

## Choosing the right model

Use Trial 03 to evaluate whether a candidate feature is informationally new. It does not select an observation strategy.

Use Trial 04 when the desired endpoint is one particular state. It may spend effort distinguishing alternatives that are not themselves relevant to other goals.

Use Trial 05 when only a predicate matters. It avoids paying to distinguish hypotheses that agree on that query.

Use Trial 06 when observations are sequential and later choices should depend on earlier outcomes. It can outperform a static packet by avoiding observations on branches where they are unnecessary.

## Common assumptions and limits

All four trials use finite, explicit hypothesis sets. Their results are relative to those sets and the available observation functions. A missing hypothesis cannot be recovered by optimizing over the others.

Trial 04 and Trial 05 assume a static additive cost for selecting a packet. Trial 06 assumes deterministic, non-intervening observations and additive path costs, with expected cost measured under an explicit prior. Real experiments may be stochastic, may alter the system, may have order-dependent costs, and may introduce new hypotheses after an observation.

Most importantly, the planners select **proposed** observations. They do not execute them. A plan becomes evidence only after the observations are performed and recorded with provenance, results, and relevant environmental context.

## A useful next bridge

The next integration opportunity is to connect these planners to an actual observer/transport path. That would require separating:

1. predicted observation under a hypothesis;
2. selected observation request and its cost model;
3. request dispatch and receiver admission;
4. raw returned observation;
5. interpretation and partition update;
6. verification of whether the intended query is now resolved.

That bridge should reuse real transport and evidence-receipt mechanisms where available rather than inventing a second execution or provenance system.