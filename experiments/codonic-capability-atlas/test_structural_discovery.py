"""COG-003: discover formerly unregistered laws using active geometric probes."""
import copy
import json
import random
import unittest
import importlib.util

from adaptive_arbiter import fixture_atlas, VersionSpace, Witness
from capability_atlas import Affine, compile_regions, encode
from structural_discovery import EvidenceAtlas, rank, restore


def random_affine(p, seed):
    rng = random.Random(seed)
    while True:
        a,b,c,d = [rng.randrange(p) for _ in range(4)]
        if (a*d-b*c) % p:
            return Affine(p, ((a,b),(c,d)), (rng.randrange(p),rng.randrange(p)))


def pool(p=257):
    # 60 misleading rank-2 coordinates, four noncollinear alternatives.
    return [(x,(3*x+7)%p) for x in range(60)]+[(0,0),(0,1),(3,5),(190,173)]


def trial(seed=0,method='active'):
    base = fixture_atlas()
    rng = random.Random(seed)
    left = random_affine(base.p, 991+seed*17)
    right = random_affine(base.p, 827+seed*17)
    originals = {encode(g) for _,g in base.choices}
    if encode(left) in originals or encode(right) in originals or left == right:
        raise AssertionError('fixture must supply two previously unregistered maps')
    state = EvidenceAtlas(base,('left','right'))
    truth = {'left':left,'right':right}
    candidates = pool()
    for context in state.contexts:
        for _ in range(4):
            available = [x for x in candidates if x not in {w.source for w in state.for_context(context)}]
            x = state.select_probe(context,available) if method=='active' else rng.choice(available)
            state = state.admit(context,x,truth[context].apply(x))
    try:
        discovered = state.discovered_atlas()
    except ValueError:
        return None,state,truth
    for context in state.contexts:
        learned = state.discover(context).candidate
        if learned != truth[context] or compile_regions(learned).realization != truth[context]:
            raise AssertionError('source-ground exact reconstruction failed')
        for _ in range(50):
            x = (rng.randrange(base.p),rng.randrange(base.p))
            if learned.apply(x) != truth[context].apply(x):
                raise AssertionError('held-out output differs')
    return discovered,state,truth


class COG003Tests(unittest.TestCase):
    def test_rank_and_geometric_observation_selection(self):
        state = EvidenceAtlas(fixture_atlas(),('left',))
        actual = random_affine(257,612)
        chosen = []
        for _ in range(4):
            x = state.select_probe('left',pool())
            chosen.append(x)
            state = state.admit('left',x,actual.apply(x))
        self.assertEqual(rank(chosen[:3],257),3)
        self.assertEqual(state.discover('left').candidate,actual)
        self.assertEqual(len(state.discover('left').challenge_indices),1)

    def test_unregistered_affine_regions_exactly_reconstructed(self):
        original = {encode(x) for _,x in fixture_atlas().choices}
        for seed in range(80):
            new,state,truth = trial(seed)
            self.assertIsNotNone(new,seed)
            self.assertEqual(len(new.choices),5)
            for context in state.contexts:
                self.assertEqual(new.by_name('learned_'+context),truth[context])
                self.assertNotIn(encode(truth[context]),original)

    def test_active_rank_selection_outperforms_budget_matched_random(self):
        active = random_success = 0
        for seed in range(80):
            active += trial(seed,'active')[0] is not None
            random_success += trial(seed,'random')[0] is not None
        self.assertEqual(active,80)
        self.assertLess(random_success,active)

    def test_collinear_observations_must_not_be_interpreted_as_unique_law(self):
        state = EvidenceAtlas(fixture_atlas(),('left',))
        ground = random_affine(257,9)
        for x in pool()[:50]:
            state = state.admit('left',x,ground.apply(x))
        with self.assertRaisesRegex(ValueError,'underdetermined geometry'):
            state.discover('left')

    def test_non_affine_context_oracle_refuses_false_global_model(self):
        state = EvidenceAtlas(fixture_atlas(),('left',))
        for x in ((0,0),(1,0),(0,1),(2,0)):
            state = state.admit('left',x,((x[0]*x[0])%257,x[1]))
        with self.assertRaisesRegex(ValueError,'contradicts inferred'):
            state.discover('left')

    def test_noninvertible_candidate_is_refused(self):
        state = EvidenceAtlas(fixture_atlas(),('left',))
        for x in ((0,0),(1,0),(0,1),(1,1)):
            state = state.admit('left',x,(x[0],0))
        with self.assertRaisesRegex(ValueError,'invertible'):
            state.discover('left')

    def test_receipts_restore_only_under_external_pins(self):
        learned,state,truth = trial(104)
        snapshot = json.loads(json.dumps(state.trace()))
        rebuilt = restore(state.base,snapshot,expected_head=state.head,
                          expected_fingerprint=state.fingerprint)
        self.assertEqual(rebuilt,state)
        self.assertEqual(rebuilt.discovered_atlas(),learned)
        with self.assertRaisesRegex(ValueError,'receiver pins'):
            restore(state.base,snapshot,expected_head='f'*64,expected_fingerprint=state.fingerprint)
        for kind in ('change','reorder','truncate','rehash','context'):
            broken = copy.deepcopy(snapshot)
            if kind=='change':broken['observations'][0]['observed'][0]=(broken['observations'][0]['observed'][0]+1)%257
            if kind=='reorder':broken['observations'][0],broken['observations'][1]=broken['observations'][1],broken['observations'][0]
            if kind=='truncate':broken['observations'].pop()
            if kind=='rehash':broken['observations'][0]['digest']='0'*64
            if kind=='context':broken['observations'][0]['context']='unknown'
            with self.assertRaises(ValueError,msg=kind):
                restore(state.base,broken,expected_head=state.head,
                        expected_fingerprint=state.fingerprint)

    def test_capability_expansion_tracks_evidence_not_hash_distances(self):
        learned,state,truth = trial(21)
        original = {encode(x) for _,x in state.base.choices}
        current = {encode(x) for _,x in learned.choices}
        self.assertEqual(len(current-original),2)
        for context in state.contexts:
            record = state.discover(context)
            self.assertEqual(record.source_root,state.head)
            self.assertEqual(record.source_count,8)
            self.assertEqual(record.candidate,truth[context])
            self.assertGreaterEqual(len(record.challenge_indices),1)

    @unittest.skipUnless(importlib.util.find_spec('vgi') is not None,
                         'native VGI unavailable; pinned CI must install it')
    def test_native_vgi_typed_operator_reuse(self):
        from vgi_adapter import vgi_check
        learned,state,truth = trial(0)
        for context in state.contexts:
            result = vgi_check(state.discover(context).candidate,
                               ((0,0),(1,0),(0,1),(27,31)))
            self.assertEqual(result['probes'],4)
            self.assertFalse(result['combined_dense_materialized'])


class HierarchicalArbitrationTests(unittest.TestCase):
    def test_discover_two_maps_then_use_existing_cog002_active_arbiter(self):
        learned,state,ground = trial(811)
        self.assertEqual(len(learned.choices),5)
        learner = VersionSpace.empty(learned)
        rng = random.Random(9347)
        pool = []
        while len(pool)<180:
            x = (rng.randrange(257),rng.randrange(257))
            if x not in pool:
                pool.append(x)
        for _ in range(12):
            x = learner.acquisition([z for z in pool if z not in {w.x for w in learner.witnesses}])
            y = (ground['left'] if (x[0]+x[1])%2==0 else ground['right']).apply(x)
            learner = learner.admit(Witness.create(learned,len(learner.witnesses),learner.head,x,y))
        policy = learner.best_policy()
        self.assertEqual((policy.feature,policy.zero,policy.one),
                         ('parity-sum','learned_left','learned_right'))
        for _ in range(300):
            x = (rng.randrange(257),rng.randrange(257))
            y = (ground['left'] if (x[0]+x[1])%2==0 else ground['right']).apply(x)
            self.assertEqual(policy.output(learned,x),y)


if __name__=='__main__':
    unittest.main()
