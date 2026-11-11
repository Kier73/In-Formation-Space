import unittest
from itertools import product

from transition_congruence import check_transition_congruence


def state_space():
    return tuple(product(range(4), (0, 1), (0, 1)))


def observe(state, test):
    rax, hidden_phase, noise = state
    if test == "rax_mod_4":
        return rax
    if test == "hidden_phase":
        return hidden_phase
    raise ValueError(f"unknown test: {test}")


def transition(state, action):
    rax, hidden_phase, noise = state
    if action != "tick":
        raise ValueError(f"unknown action: {action}")
    return ((rax + hidden_phase) % 4, hidden_phase, 1 - noise)


class TransitionCongruenceTests(unittest.TestCase):
    def test_same_current_observation_can_have_different_future_behavior(self):
        report = check_transition_congruence(
            states=state_space(),
            actions=("tick",),
            tests=("rax_mod_4",),
            observation_fn=observe,
            transition_fn=transition,
        )
        self.assertFalse(report.is_congruence)
        self.assertEqual(len(report.partition), 4)
        self.assertGreater(len(report.violations), 0)
        witness = report.violations[0]
        self.assertEqual(witness.action, "tick")
        self.assertEqual(witness.distinguishing_test, "rax_mod_4")
        self.assertNotEqual(witness.left_observation, witness.right_observation)

    def test_refining_with_transition_relevant_state_restores_congruence(self):
        report = check_transition_congruence(
            states=state_space(),
            actions=("tick",),
            tests=("rax_mod_4", "hidden_phase"),
            observation_fn=observe,
            transition_fn=transition,
        )
        self.assertTrue(report.is_congruence)
        self.assertEqual(len(report.partition), 8)
        self.assertEqual(report.checked_state_pairs, 8)
        self.assertEqual(report.checked_transitions, 8)

    def test_representative_checks_cover_each_member_of_each_block(self):
        states = ((0, 0), (0, 1), (0, 2), (1, 0))
        report = check_transition_congruence(
            states=states,
            actions=("keep",),
            tests=("first",),
            observation_fn=lambda state, test: state[0],
            transition_fn=lambda state, action: state,
        )
        self.assertTrue(report.is_congruence)
        self.assertEqual(len(report.partition[0]), 3)
        self.assertEqual(report.checked_state_pairs, 2)

    def test_successor_outside_finite_universe_is_rejected(self):
        with self.assertRaises(ValueError):
            check_transition_congruence(
                states=((0,), (1,)),
                actions=("next",),
                tests=("value",),
                observation_fn=lambda state, test: state[0],
                transition_fn=lambda state, action: (state[0] + 1,),
            )

    def test_duplicate_and_unhashable_domain_entries_are_rejected(self):
        with self.assertRaises(ValueError):
            check_transition_congruence(
                states=((0,), (0,)),
                actions=(),
                tests=(),
                observation_fn=lambda state, test: state,
                transition_fn=lambda state, action: state,
            )
        with self.assertRaises(TypeError):
            check_transition_congruence(
                states=((0,),),
                actions=([],),
                tests=(),
                observation_fn=lambda state, test: state,
                transition_fn=lambda state, action: state,
            )

    def test_empty_test_suite_is_explicitly_coarse(self):
        report = check_transition_congruence(
            states=((0,), (1,), (2,)),
            actions=("stay",),
            tests=(),
            observation_fn=lambda state, test: None,
            transition_fn=lambda state, action: state,
        )
        self.assertTrue(report.is_congruence)
        self.assertEqual(len(report.partition), 1)
        self.assertEqual(report.scope, "finite-supplied-states-actions-tests")


if __name__ == "__main__":
    unittest.main()
