# Trial 03: distinction refinement

**Brief ID:** d2r-distinction-refinement-03  
**Parent experiment:** From Description to Realization  
**Status:** finite-state mathematical model and unit tests supplied.

## Question

When does adding information create a genuinely new distinction, rather than merely adding a new label for something already determined?

## Desired construction

Given a finite set of states and a sequence of observations, construct the partition induced by observational equivalence. Add a new observation and measure how it refines the existing partition.

A distinction is redundant if it is constant on every existing equivalence class. It is informative relative to the current representation if it splits at least one class.

## Required measurements

- Number of equivalence classes before and after the observation.
- Number of state pairs that were previously indistinguishable but become distinguishable.
- Conditional entropy of the new observation given existing observations, under explicit state weights.
- A clear redundant/non-redundant classification that does not depend on probability weights.

## Hard constraints

- Standard-library Python only.
- State and observation values are hashable.
- Weights, when supplied, are finite and strictly positive.
- Failed additions do not partially mutate the partition model.
- Redundant observations report exactly zero incremental entropy and zero newly separated pairs.
- Tests cover fully independent, redundant, partial, and weighted refinements.

## Interpretation boundaries

The finite partition is a model of distinguishability relative to a chosen observation family. It is not a universal ontology or a geometric dimension. Conditional entropy depends on the supplied distribution. The pair-separation count does not.

This experiment does not claim every new observation adds an independent dimension. It operationalizes one narrower criterion: a distinction is new when it splits an existing equivalence class.
