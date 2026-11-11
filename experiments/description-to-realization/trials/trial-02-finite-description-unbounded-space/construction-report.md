# Construction report: finite description, unbounded space

**Trial:** 02  
**Brief:** d2r-finite-description-02  
**Implementation:** finite_description.py  
**Tests:** test_finite_description.py  
**Execution receipt:** results/test-encounter.json

## Construction

The experiment implements two finite descriptions with countably infinite denotations:

1. The generator for all finite binary strings orders members by length and yields them lazily. The even-parity recognizer uses the two-state transition p' = p XOR b. The product signature (parity, length modulo k) has exactly 2k reachable states. For each parity and residue, a finite witness is constructed and checked.
2. The recursive grammar S -> 0S1 | epsilon generates L = {0^n 1^n : n >= 0}. A counter recognizer checks membership for finite words. The code constructs distinguishing suffixes for unequal prefix lengths.

## Mathematical result

Define the Myhill-Nerode relation u equivalent_L v when every suffix z either makes both uz and vz members of L or makes neither a member.

For any distinct natural numbers i and j, let u = 0^i, v = 0^j, and choose suffix z = 1^i. Then 0^i 1^i belongs to L, while 0^j 1^i does not belong to L when i differs from j.

Thus every pair of distinct prefixes 0^i and 0^j belongs to different equivalence classes. There are infinitely many classes, so no finite-state DFA recognizes L.

By contrast, even parity over all finite binary strings needs only two states, regardless of input length. Tracking parity and length modulo k yields a product representation with 2k reachable states. This is a reachability result; the experiment does not claim every product-state construction is minimal without a separate distinguishability proof.

## Verification

GitHub Actions run 18, commit 61a29c2eea511d98fc2a267ac8fc0ebeb57ce8c5, executed the seven tests under Python 3.11.18 on ubuntu-latest:

- balanced-language generation agrees with the recursive description;
- membership accepts generated members and rejects selected non-members;
- the binary-string generator emits the expected finite prefixes by length;
- distinguishing suffixes work for every unequal pair among the tested prefix lengths;
- even-parity recognition agrees with direct counting on all binary strings through length eight;
- a finite description constructs and recognizes a length-10,000 member;
- all 2k parity/length-modulo signatures are witnessed for 1 <= k <= 7.

**CI result:** 7 tests passed. The exact receipt is stored separately.

## Boundaries

The test suite samples finite members and finitely many prefix pairs. The non-regularity conclusion is supported by the general distinguishing-suffix proof, not inferred from finite test enumeration.

The experiment shows that:

- an infinite denotation does not imply infinite description length;
- an infinite denotation does not imply unbounded automaton state;
- a finite description can define a language whose exact recognition requires unboundedly many distinguishable states;
- adding a new independent distinction can multiply reachable representation states, while redundancy need not.

It does not establish that a physical infinite object has been materialized, or that a finite observer can enumerate or construct every member under a finite budget.