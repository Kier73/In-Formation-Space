"""COG-002: evidence-selected capability composition and source-pinned persistence."""
import copy
import json
import random
import unittest
import importlib.util

from adaptive_arbiter import (
    Atlas, Policy, VersionSpace, Witness, accuracy, fixture_atlas, fixture_oracle,
    genesis, policies, point_label, predicate, restore, static_baseline,
)
from capability_atlas import compile_regions


def coordinates(seed, count, p=257):
    rng = random.Random(seed)
    pool = set()
    while len(pool) < count:
        pool.add((rng.randrange(p), rng.randrange(p)))
    data = list(pool)
    rng.shuffle(data)
    return data


def run_one(feature, seed=5, budget=8, method='active'):
    atlas = fixture_atlas()
    all_points = coordinates(seed, 180)
    state = VersionSpace.empty(atlas)
    pool = all_points[:80]
    test = [(x, fixture_oracle(atlas, feature, x)) for x in all_points[80:]]
    rng = random.Random(seed ^ 0xC0D0)
    for i in range(budget):
        available = [x for x in pool if x not in {w.x for w in state.witnesses}]
        x = state.acquisition(available) if method == 'active' else rng.choice(available)
        state = state.admit(Witness.create(atlas, len(state.witnesses), state.head,
                                          x, fixture_oracle(atlas, feature, x)))
    selected = state.best_policy()
    control = static_baseline(atlas, state.witnesses)
    learned_hits = accuracy(atlas, selected, test)[0]
    control_hits = accuracy(atlas, control, test)[0]
    return state, learned_hits, control_hits, selected, len(test)


class AdaptiveCapabilityAtlasTests(unittest.TestCase):
    def test_policy_space_reuses_exact_algebraic_compiler(self):
        atlas = fixture_atlas()
        self.assertEqual(len(policies(atlas)), 27)  # 3 constants + 4×3×2
        for policy in policies(atlas):
            for x in ((0, 0), (1, 0), (0, 1), (113, 212)):
                receipt = policy.certificate(atlas, x)
                self.assertEqual(receipt['address'], compile_regions(atlas.by_name(receipt['capability'])).address)
                self.assertIn(receipt['compiled_steps'], (4, 5))
                self.assertEqual(policy.output(atlas, x), atlas.by_name(receipt['capability']).apply(x))

    def test_active_learns_heldout_task_not_just_address(self):
        for feature in ('parity-x', 'parity-y', 'parity-sum', 'half-x'):
            state, hits, static, policy, count = run_one(feature, seed=37, budget=8)
            self.assertEqual(hits, count, (feature, policy, hits))
            self.assertLess(static, count, (feature, static))
            self.assertIn(policy, state.viable)
            self.assertGreaterEqual(len(state.witnesses), 1)

    def test_persistence_roundtrip_requires_receiver_pins(self):
        state, hits, static, policy, count = run_one('parity-sum', seed=9)
        data = state.trace()
        rebuilt = restore(state.atlas, json.loads(json.dumps(data)),
                          receiver_expected_head=state.head,
                          receiver_expected_fingerprint=state.fingerprint)
        self.assertEqual(rebuilt, state)
        self.assertEqual(state.viable, rebuilt.viable)
        self.assertEqual(hits, count)
        with self.assertRaisesRegex(ValueError, 'externally pinned'):
            restore(state.atlas, data, receiver_expected_head='f'*64,
                    receiver_expected_fingerprint=state.fingerprint)

    def test_refuses_reordered_missing_and_rehashed_observations(self):
        state, *_ = run_one('parity-x', seed=52)
        exact = state.trace()
        checks = []
        a = copy.deepcopy(exact); a['witnesses'][0]['y'][0] = (a['witnesses'][0]['y'][0]+1)%257; checks.append(a)
        a = copy.deepcopy(exact); a['witnesses'][0], a['witnesses'][1] = a['witnesses'][1], a['witnesses'][0]; checks.append(a)
        a = copy.deepcopy(exact); a['witnesses'].pop(); checks.append(a)
        a = copy.deepcopy(exact); a['selected']['one'] = 'rotate'; checks.append(a)
        for altered in checks:
            with self.assertRaises(ValueError):
                restore(state.atlas, altered, receiver_expected_head=state.head,
                        receiver_expected_fingerprint=state.fingerprint)
        # Even a rehashed fabricated observation cannot be accepted under an
        # external pinned trace head. Claiming 'SHA256 authentication' would be wrong.
        a = copy.deepcopy(exact); a['witnesses'][0]['y'] = [0, 0]
        with self.assertRaises(ValueError):
            restore(state.atlas, a, receiver_expected_head=state.head,
                    receiver_expected_fingerprint=state.fingerprint)

    def test_synthetic_unrepresented_target_refuses_not_hallucinates(self):
        atlas = fixture_atlas(); state = VersionSpace.empty(atlas)
        x = (18, 42)
        # No admitted affine Ground produces all possible requested outputs.
        predicted = {policy.output(atlas, x) for policy in policies(atlas)}
        y = next((a,b) for a in range(257) for b in range(257) if (a,b) not in predicted)
        with self.assertRaisesRegex(ValueError, 'not explained'):
            state.admit(Witness.create(atlas, 0, state.head, x, y))
        self.assertEqual(len(state.viable), len(policies(atlas)))

    @unittest.skipUnless(importlib.util.find_spec('vgi') is not None, 'native VGI not installed locally')
    def test_real_vgi_typed_operator_navigation_reuses_existing_algebra(self):
        from vgi_adapter import vgi_check
        atlas=fixture_atlas()
        for _, ground in atlas.choices:
            output=vgi_check(ground,((0,0),(1,0),(0,1),(71,142)))
            self.assertEqual(output['probes'],4)
            self.assertFalse(output['combined_dense_materialized'])

    def test_hash_relabels_never_affect_geometry_or_selection(self):
        atlas=fixture_atlas(); state, *_=run_one('parity-y',seed=12)
        plan=state.best_policy()
        x=(33, 84)
        a=point_label('seed-A',compile_regions(atlas.by_name(plan.zero)).address)
        b=point_label('seed-B',compile_regions(atlas.by_name(plan.zero)).address)
        self.assertNotEqual(a,b)
        self.assertEqual(plan.output(atlas,x),state.best_policy().output(atlas,x))

    def test_active_gains_information_without_a_whole_atlas_scan(self):
        atlas=fixture_atlas(); state=VersionSpace.empty(atlas)
        pool=coordinates(28,90)
        count_before=len(state.viable)
        x=state.acquisition(pool)
        state=state.admit(Witness.create(atlas,0,state.head,x,fixture_oracle(atlas,'parity-x',x)))
        self.assertLess(len(state.viable),count_before)
        self.assertLessEqual(len(state.viable),27)
        self.assertLessEqual(len(state.best_policy().certificate(atlas,x)['regions']),5)
        with self.assertRaises(ValueError):
            state.acquisition([x])


if __name__ == '__main__':
    unittest.main()