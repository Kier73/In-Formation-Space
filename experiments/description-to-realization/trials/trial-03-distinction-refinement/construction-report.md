# Construction report: distinction refinement

**Trial:** 03  
**Brief:** d2r-distinction-refinement-03  
**Implementation:** distinction_space.py  
**Tests:** test_distinction_space.py  
**Execution receipt:** results/test-encounter.json

## Construction

The implementation treats a finite set of hashable states as a universe. Each named observation maps every state to a hashable value. Existing observations induce an equivalence relation: states are equivalent when their full observation signatures agree.

Adding an observation refines the existing partition. The implementation reports:

- the previous and refined block counts;
- the number of state pairs that were equivalent before but separated by the new observation;
- conditional entropy in bits under the explicitly supplied positive state weights;
- whether the new observation is redundant relative to the observations already present.

The model stores each observation only after it has been evaluated successfully for every state, so a failed addition does not leave a partial distinction in the model.

## Mathematical result

Let O be the tuple of existing observations and D be a proposed new observation. Define s ~_O t exactly when O(s)=O(t). Then the following are equivalent over a finite state set with strictly positive weights:

1. D is redundant relative to O.
2. D is constant on every equivalence class of ~_O.
3. There exists a function g on the image of O such that D = g composed with O.
4. No previously equivalent state pair is separated by D.
5. The conditional entropy H(D | O) is zero.

If D varies within at least one equivalence class, the partition is strictly refined, at least one previously equivalent pair is newly separated, and H(D | O) is strictly positive under strictly positive weights.

The pair-separation count is distribution-independent. Conditional entropy depends on the selected state weights. This distinction is useful: one measurement captures structural refinement, the other captures information under a chosen distribution.

## Verification

GitHub Actions run 25, commit bb7790eeb13b19c79e129fd971269febbc2c4f27, executed eight tests under Python 3.11.18 on ubuntu-latest. All eight passed.

The tests cover:

- an independent binary distinction that refines two blocks into four;
- a second parity feature that is already determined by the first and adds no distinctions;
- partial refinement that splits only one prior block;
- weighted conditional entropy;
- monotonicity of partition refinement;
- stable signatures and block ordering;
- rejection of malformed states, weights, names, and observations;
- duplicate-name and non-callable rejection.

## Boundaries

The experiment operates on a finite, explicitly chosen state universe. It does not define a universal ontology, establish a geometric dimension, or prove statistical independence of arbitrary features.

The phrase “new information dimension” is operationalized here in a narrow sense: an observation introduces new distinguishability when it splits an existing equivalence class. Several splits can arise from one categorical observation, and the number of partition blocks is not a geometric dimension. A later trial can examine whether this finite refinement model extends usefully to transition systems or infinite state spaces.