# Trial 04: active distinction selection

**Brief ID:** d2r-active-distinction-04  
**Parent experiment:** From Description to Realization  
**Status:** finite weighted-set-cover model and unit tests supplied.

## Question

When a target remains ambiguous under current observations, what is the least-cost set of additional observations that would distinguish it from every remaining alternative?

## Desired construction

Given a finite state set, a target state, its current observational equivalence class, and candidate observations with costs, select a packet of observations that separates the target from every other state in that class.

Candidate costs may represent latency, money, tool calls, energy, or another explicit resource. The experiment assumes additive costs and observation functions that are available for the selected states.

## Hard constraints

- Standard-library Python only.
- Existing signatures and candidate outputs must be hashable.
- Candidate costs must be finite and strictly positive.
- Candidate names must be unique.
- If no candidate can distinguish an alternative from the target, report it explicitly.
- Exact minimum-cost selection must be used for ambiguity sets within the configured threshold.
- Larger cases may use a deterministic greedy approximation, but the result must be labelled non-optimal unless independently proved.
- A target already unique under existing observations must require no additional observations.

## Interpretation boundaries

The exact problem is weighted set cover, which is NP-hard in general. The bitmask dynamic program is intended for small ambiguity sets. The greedy fallback is a practical approximation, not a proof of minimum cost.

The model assumes candidate observations do not change the system being observed and that costs add independently. Real experiments may violate both assumptions. A chosen observation packet is a plan, not evidence that the observations have already occurred.
