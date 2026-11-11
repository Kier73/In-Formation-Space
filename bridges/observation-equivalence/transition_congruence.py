"""Check whether a finite observational partition is transition-stable.

Agreement on current observations is not enough to justify merging states in a
transition system. A sound deterministic quotient also needs every shared
action to send equivalent states into equivalent successor classes.

This checker is exhaustive only for the explicitly supplied finite state set,
action set, and test suite. It is not a proof about unlisted states, actions,
or observation continuations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Hashable, List, Sequence, Tuple, TypeVar

State = TypeVar("State", bound=Hashable)
Action = TypeVar("Action", bound=Hashable)
Test = TypeVar("Test")


@dataclass(frozen=True)
class CongruenceViolation:
    left_state: Hashable
    right_state: Hashable
    action: Hashable
    left_successor: Hashable
    right_successor: Hashable
    distinguishing_test: object
    left_observation: object
    right_observation: object


@dataclass(frozen=True)
class TransitionCongruenceReport:
    partition: Tuple[Tuple[Hashable, ...], ...]
    checked_state_pairs: int
    checked_transitions: int
    violations: Tuple[CongruenceViolation, ...]
    scope: str = "finite-supplied-states-actions-tests"

    @property
    def is_congruence(self) -> bool:
        return not self.violations


def check_transition_congruence(
    states: Sequence[State],
    actions: Sequence[Action],
    tests: Sequence[Test],
    observation_fn: Callable[[State, Test], object],
    transition_fn: Callable[[State, Action], State],
) -> TransitionCongruenceReport:
    """Check whether current observational classes survive every supplied action.

    The checker compares each member of a block with its representative.
    Since finite-test observational equality is an equivalence relation,
    representative checks suffice for the entire block.

    Every successor must remain inside the supplied finite state universe.
    A violation includes the source pair, action, successor pair, and a
    concrete test that distinguishes the successor states.
    """
    state_list = list(states)
    if not state_list:
        raise ValueError("states must contain at least one state")
    try:
        state_set = set(state_list)
    except TypeError as exc:
        raise TypeError("states must be hashable") from exc
    if len(state_set) != len(state_list):
        raise ValueError("states must be unique")

    action_list = list(actions)
    try:
        action_set = set(action_list)
    except TypeError as exc:
        raise TypeError("actions must be hashable") from exc
    if len(action_set) != len(action_list):
        raise ValueError("actions must be unique")

    test_list = list(tests)
    if not callable(observation_fn) or not callable(transition_fn):
        raise TypeError("observation_fn and transition_fn must be callable")

    def equivalent(left: State, right: State) -> Tuple[bool, object]:
        for test in test_list:
            if observation_fn(left, test) != observation_fn(right, test):
                return False, test
        return True, None

    blocks: List[List[State]] = []
    for state in state_list:
        for block in blocks:
            if equivalent(block[0], state)[0]:
                block.append(state)
                break
        else:
            blocks.append([state])

    violations: List[CongruenceViolation] = []
    checked_pairs = 0
    checked_transitions = 0

    for block in blocks:
        if len(block) < 2:
            continue
        representative = block[0]
        for member in block[1:]:
            checked_pairs += 1
            for action in action_list:
                left_successor = transition_fn(representative, action)
                right_successor = transition_fn(member, action)
                checked_transitions += 1
                if left_successor not in state_set or right_successor not in state_set:
                    raise ValueError(
                        "transition left the supplied finite state universe; "
                        "include all reachable successors or use a larger model"
                    )
                same_class, witness = equivalent(left_successor, right_successor)
                if not same_class:
                    violations.append(
                        CongruenceViolation(
                            left_state=representative,
                            right_state=member,
                            action=action,
                            left_successor=left_successor,
                            right_successor=right_successor,
                            distinguishing_test=witness,
                            left_observation=observation_fn(left_successor, witness),
                            right_observation=observation_fn(right_successor, witness),
                        )
                    )

    return TransitionCongruenceReport(
        partition=tuple(tuple(block) for block in blocks),
        checked_state_pairs=checked_pairs,
        checked_transitions=checked_transitions,
        violations=tuple(violations),
    )


@dataclass(frozen=True)
class PartitionRefinementReport:
    initial_partition: Tuple[Tuple[Hashable, ...], ...]
    stable_partition: Tuple[Tuple[Hashable, ...], ...]
    refinement_rounds: int
    checked_transition_evaluations: int
    scope: str = "finite-supplied-states-actions-tests"

    @property
    def is_transition_stable(self) -> bool:
        return True

    @property
    def initial_block_count(self) -> int:
        return len(self.initial_partition)

    @property
    def stable_block_count(self) -> int:
        return len(self.stable_partition)


def refine_to_transition_congruence(
    states: Sequence[State],
    actions: Sequence[Action],
    tests: Sequence[Test],
    observation_fn: Callable[[State, Test], object],
    transition_fn: Callable[[State, Action], State],
) -> PartitionRefinementReport:
    """Compute the coarsest transition-stable refinement of a finite partition.

    The initial partition groups states that agree on every supplied test.
    Each round splits a block when its members transition, under some action,
    into different blocks of the current partition. Blocks are only split,
    never merged. Iteration stops at the fixed point, which is the coarsest
    deterministic transition congruence contained in the initial partition.

    The model must be finite and closed: every supplied action must be defined
    for every state, and every successor must belong to the supplied states.
    """
    state_list = list(states)
    if not state_list:
        raise ValueError("states must contain at least one state")
    try:
        state_set = set(state_list)
    except TypeError as exc:
        raise TypeError("states must be hashable") from exc
    if len(state_set) != len(state_list):
        raise ValueError("states must be unique")

    action_list = list(actions)
    try:
        action_set = set(action_list)
    except TypeError as exc:
        raise TypeError("actions must be hashable") from exc
    if len(action_set) != len(action_list):
        raise ValueError("actions must be unique")
    test_list = list(tests)
    if not callable(observation_fn) or not callable(transition_fn):
        raise TypeError("observation_fn and transition_fn must be callable")

    def same_observations(left: State, right: State) -> bool:
        return all(
            observation_fn(left, test) == observation_fn(right, test)
            for test in test_list
        )

    partition: List[List[State]] = []
    for state in state_list:
        for block in partition:
            if same_observations(block[0], state):
                block.append(state)
                break
        else:
            partition.append([state])

    initial = tuple(tuple(block) for block in partition)
    rounds = 0
    evaluations = 0

    while True:
        block_of = {
            state: block_index
            for block_index, block in enumerate(partition)
            for state in block
        }
        refined: List[List[State]] = []
        for block in partition:
            buckets = {}
            for state in block:
                successor_signature = []
                for action in action_list:
                    successor = transition_fn(state, action)
                    evaluations += 1
                    if successor not in state_set:
                        raise ValueError(
                            "transition left the supplied finite state universe; "
                            "include all reachable successors or use a larger model"
                        )
                    successor_signature.append(block_of[successor])
                signature = tuple(successor_signature)
                buckets.setdefault(signature, []).append(state)
            refined.extend(buckets.values())

        if len(refined) == len(partition):
            stable = tuple(tuple(block) for block in partition)
            return PartitionRefinementReport(
                initial_partition=initial,
                stable_partition=stable,
                refinement_rounds=rounds,
                checked_transition_evaluations=evaluations,
            )

        partition = refined
        rounds += 1
