# Active distinction selection

**Question:** When a target remains ambiguous, what is the least-cost observation packet that would separate it from every remaining alternative?

The trial treats each additional observation as a set of alternatives it distinguishes from the target. Selecting a minimum-cost packet is a weighted set-cover problem.

## Inputs

- A finite set of candidate states.
- A target state.
- Current signatures describing what is already known. Equal signatures mean states are still observationally indistinguishable.
- Candidate observation functions, each with an explicit positive cost.

Only states in the target's current equivalence class need further attention. States already distinguished from the target are not charged again.

## Output

The planner returns selected observation names, total estimated cost, alternatives separated, and alternatives no candidate can distinguish. It also reports whether the plan is complete and whether the solver was exact.

For small ambiguity sets, a bitmask dynamic program finds the minimum-cost packet. Above the configured threshold, a deterministic greedy set-cover approximation is used and explicitly labelled non-exact.

## Relation to “attention”

An attention packet is a selected set of observations that resolves a specific ambiguity. It need not gather every available fact or refine every state equally. It allocates observation effort toward the distinctions needed to identify a target under a stated cost model.

This is one concrete interpretation of active attention, not a general model of cognition or intention.

## Complexity and limits

With m candidate observations and n coverable alternatives, the exact bitmask dynamic program has worst-case time O(m * 2^n) and space O(2^n). This makes the exact solver suitable only for modest n. The greedy fallback is scalable but does not guarantee the minimum-cost packet.

The model assumes observations are non-intervening and additive-cost. If observing changes the system, if candidate costs depend on order, or if observations interact, a richer experimental model is needed.

## Files

- brief.md — construction requirements
- attention_selection.py — exact/greedy observation selector
- test_attention_selection.py — deterministic and brute-force cross-check tests
- construction-report.md — implementation argument, complexity, and CI result
- results/test-encounter.json — provenance record for the successful ten-test CI run

## Reproduce

    python -m unittest discover -s experiments/description-to-realization/trials/trial-04-active-distinction-selection -p 'test_*.py' -v
