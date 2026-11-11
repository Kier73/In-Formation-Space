# Finite description, unbounded space

**Question:** How can a finite description define an infinite set, and when does its meaning require an unbounded number of distinguishable states?

This experiment contrasts two small descriptions.

## A finite-state infinite language

The set of all finite binary strings is:

\[
\Sigma^* = \{0,1\}^*
\]

It is countably infinite: for every length n, there are 2^n strings, and a distinct all-zero string 0^n exists for every n. The generator is finite code and yields one finite string at a time. It does not store the infinite set.

The property “contains an even number of 1s” is recognized by a two-state automaton. Its state is the parity bit:

\[
p_{k+1}=p_k\oplus b_k.
\]

The input length has no fixed upper bound, but the recognizer needs only two states.

Adding an independent distinction “length modulo k” gives a product state:

\[
(p,\; n\bmod k)
\]

with 2k reachable states. The code constructs a witness for every pair, rather than merely assuming the product states are reachable.

## A finite description with unbounded distinguishability

Now consider the recursive grammar:

\[
S \rightarrow 0S1 \mid \epsilon
\]

Its language is:

\[
L=\{0^n1^n\mid n\geq0\}.
\]

This language is also countably infinite and has a finite description. But a finite-state recognizer cannot recognize it exactly.

For any two unequal prefix lengths i and j, choose suffix 1^i:

- 0^i1^i belongs to L.
- 0^j1^i does not belong to L.

So every distinct prefix length is behaviorally distinguishable. There are infinitely many such equivalence classes. A recognizer must retain an unbounded amount of state information as the prefix grows; a stack or counter-like representation can do this, but a fixed finite-state automaton cannot.

The program's counter recognizer is a constructive demonstration, not a finite-state machine. It uses a growing count.

## What this says about “information as an infinite dimension”

This gives two different meanings of unboundedness:

- **Unbounded extension, bounded state:** an infinite collection of possible inputs can be described and navigated with a fixed finite state machine.
- **Unbounded extension, unbounded distinguishability:** the description is still finite, but recognizing membership requires the representation to preserve arbitrarily many different prefix conditions.

The number of possible objects and the number of distinctions needed to reason about them are therefore separate quantities.

This also sharpens the idea of a new information dimension. A new label does not necessarily add a new dimension. A distinction matters when it separates possibilities that were behaviorally indistinguishable under the previous representation. Independent distinctions can multiply reachable states; dependent or redundant distinctions may add no new state at all.

## Files

- Construction brief: brief.md
- finite_description.py
- test_finite_description.py
- construction-report.md — proof argument, implementation summary, and CI result.
- results/test-encounter.json — provenance record for the successful seven-test CI run.

## Reproduce

    python -m unittest discover -s experiments/description-to-realization/trials/trial-02-finite-description-unbounded-space -p 'test_*.py' -v

The tests use finite witnesses and bounded prefixes. The infinity claims come from the general constructions and distinguishing argument, not from attempting infinite enumeration.
