# Trial 02: finite descriptions and unbounded distinguishability

**Brief ID:** d2r-finite-description-02  
**Status:** formal computational experiment; implementation and tests supplied.  
**Question:** Can a finite description denote an infinite space, and can two such finite descriptions require radically different representational resources?

## Desired construction

Build a small, dependency-free Python demonstration of two recursively or finitely described infinite languages:

1. All finite binary strings, with an even-parity property recognized by a two-state automaton. Add an independent length-modulo-k distinction and show the reachable product has exactly 2k states.
2. The recursively defined language S -> 0S1 | epsilon, whose members are 0^n1^n. Show that distinct prefixes 0^i and 0^j can be distinguished by a suffix 1^i, so the language has unboundedly many distinguishable prefix states.

## Hard constraints

- Standard-library Python only.
- Enumerate members lazily; never attempt to materialize an infinite set.
- Define the recognition rules precisely.
- Include constructive witnesses for every parity/length-mod-k state.
- Include distinguishing suffixes for unequal balanced-language prefixes.
- Tests must verify finite prefixes, exact counts, witness reachability, and rejection cases.

## Interpretation boundaries

This is a formal language experiment. It demonstrates the difference between a finite description and the size or state requirements of its denotation. It does not establish that a physical infinite object is materialized, nor that every infinite language is operationally accessible with finite resources.
