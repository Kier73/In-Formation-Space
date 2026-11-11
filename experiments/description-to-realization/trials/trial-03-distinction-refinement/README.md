# Distinction refinement

**Question:** When does new information actually add a new distinction?

Let S be a finite set of possible states. Existing observations induce an equivalence relation:

\[
s \sim_O t \quad\text{iff}\quad O(s)=O(t).
\]

The equivalence classes form a partition of S. A new observation d refines that partition:

\[
s \sim_{O,d} t \quad\text{iff}\quad O(s)=O(t)\ \text{and}\ d(s)=d(t).
\]

The new observation is redundant exactly when it is constant inside every previous equivalence class. If it splits at least one class, it creates a real new distinction relative to the existing observation family.

## Two complementary measurements

1. **Newly separated pairs:** count state pairs that were previously indistinguishable and become distinguishable. This is independent of any probability distribution.
2. **Conditional entropy:** compute H(D | O) under explicit positive state weights. This measures the additional information supplied by the observation relative to the prior observation signature and the chosen distribution.

The entropy is distribution-dependent. The redundant/non-redundant test is not.

## Example

For four states (x,y) in {0,1}²:

- observing x creates two equivalence classes;
- observing y next splits each previous class;
- the partition grows from two blocks to four;
- under the uniform distribution, y contributes one conditional bit.

If a second feature is a deterministic function of x, it does not split any class and contributes zero conditional entropy.

The terms “dimension” and “independence” should be used carefully. This experiment measures refinement of a finite observational partition; it does not establish a geometric dimension or prove that arbitrary observations are statistically independent.

## Files

- Construction brief: brief.md
- Implementation: distinction_space.py
- Tests: test_distinction_space.py
- Construction report: construction-report.md

## Reproduce

    python -m unittest discover -s experiments/description-to-realization/trials/trial-03-distinction-refinement -p 'test_*.py' -v
