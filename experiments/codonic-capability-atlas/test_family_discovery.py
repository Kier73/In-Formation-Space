"""COG-004: family inference, new nonlinear composition, source and refusal tests."""
import copy
import importlib.util
import random
import unittest
from capability_atlas import Affine, compile_regions
from adaptive_arbiter import VersionSpace, Witness, restore as restore_selection
from structural_discovery import EvidenceAtlas, infer_affine, restore as restore_source
from family_discovery import (ShearGround, identify, choose_probe, typed_catalogue,
                              verify_catalogue, feature_rank, matrix_rank,
                              MixedFamilyAtlas)
from test_structural_discovery import random_affine


def target_pair(seed=0):
    affine=random_affine(257,7000+seed*2)
    shear=ShearGround(random_affine(257,7001+seed*2),1+seed%256)
    return {"alpha":affine,"beta":shear}


def collinear_pool(p=257):
    return [(x,(3*x+7)%p) for x in range(90)]+[
        (0,0),(0,1),(1,0),(2,0),(7,43),(16,19),(122,75)]


def gather(seed=0,method="active",budget=6,targets=None):
    from adaptive_arbiter import fixture_atlas
    models=targets or target_pair(seed)
    state=EvidenceAtlas(fixture_atlas(),("alpha","beta"))
    pool=collinear_pool()
    rng=random.Random(51+seed*17)
    for context in state.contexts:
        for _ in range(budget):
            available=[x for x in pool if x not in {w.source for w in state.for_context(context)}]
            x=choose_probe(state,context,available) if method=="active" else rng.choice(available)
            state=state.admit(context,x,models[context].apply(x))
    return state


class FamilyDiscoveryTests(unittest.TestCase):
    def test_both_unknown_families_are_identified_from_witnesses(self):
        for seed in range(12):
            state=gather(seed)
            original=target_pair(seed)
            affine=identify(state,"alpha")
            nonlinear=identify(state,"beta")
            self.assertEqual(affine.family,"affine")
            self.assertEqual(nonlinear.family,"quadratic-shear-before-affine")
            self.assertEqual(affine.ground,original["alpha"])
            self.assertEqual(nonlinear.ground,original["beta"])
            self.assertEqual(len(affine.basis_indices),4)
            self.assertEqual(len(nonlinear.challenge_indices),2)
            for x in ((0,0),(0,1),(2,0),(190,170),(256,1)):
                self.assertEqual(affine.apply(x),original["alpha"].apply(x))
                self.assertEqual(nonlinear.apply(x),original["beta"].apply(x))

    def test_new_nonlinear_region_is_invertible_with_existing_affine_compiler(self):
        for seed in range(15):
            s=target_pair(seed)["beta"]
            self.assertIsInstance(s,ShearGround)
            plan=s.plan()
            self.assertEqual(plan["regions"][0],"quadratic-shear")
            self.assertEqual(plan["regions"][1:],
                             [part.region for part in compile_regions(s.affine).steps])
            rng=random.Random(seed)
            for _ in range(50):
                x=(rng.randrange(257),rng.randrange(257))
                self.assertEqual(s.inverse(s.apply(x)),x)
                self.assertEqual(s.apply(s.inverse(x)),x)

    def test_three_point_affine_interpolation_does_not_certify_nonlinear_family(self):
        from adaptive_arbiter import fixture_atlas
        nonlinear=target_pair(0)["beta"]
        state=EvidenceAtlas(fixture_atlas(),("beta",))
        for x in ((0,0),(1,0),(0,1)):
            state=state.admit("beta",x,nonlinear.apply(x))
        naive_affine,_=infer_affine(257,state.for_context("beta"))
        self.assertNotEqual(naive_affine.apply((2,0)),nonlinear.apply((2,0)))
        with self.assertRaisesRegex(ValueError,"underdetermined family"):
            identify(state,"beta")
        state=state.admit("beta",(2,0),nonlinear.apply((2,0)))
        with self.assertRaisesRegex(ValueError,"missing independent"):
            identify(state,"beta")
        state=state.admit("beta",(3,2),nonlinear.apply((3,2)))
        self.assertEqual(identify(state,"beta").ground,nonlinear)

    def test_rank_directed_probes_vs_equal_budget_random_control(self):
        active=random_success=0
        for seed in range(100):
            a=gather(seed,"active")
            b=gather(seed,"random")
            if all(identify(a,c) for c in a.contexts):active+=1
            try:
                if all(identify(b,c) for c in b.contexts):random_success+=1
            except ValueError:pass
        self.assertEqual(active,100)
        self.assertEqual(random_success,19)  # deterministic seeded fixture only

    def test_complete_small_field_ground_and_full_inverse(self):
        from adaptive_arbiter import Atlas
        base=Atlas((("a",Affine(5,((1,0),(0,1)),(0,0))),
                    ("b",Affine(5,((2,1),(0,3)),(1,1)))))
        nonlinear=ShearGround(Affine(5,((2,1),(1,1)),(3,1)),3)
        affine=Affine(5,((1,2),(0,1)),(1,4))
        source=EvidenceAtlas(base,("alpha","beta"))
        for context,ground in (("alpha",affine),("beta",nonlinear)):
            for x in range(5):
                for y in range(5):
                    source=source.admit(context,(x,y),ground.apply((x,y)))
        self.assertEqual(identify(source,"alpha").ground,affine)
        self.assertEqual(identify(source,"beta").ground,nonlinear)
        self.assertEqual(len(identify(source,"beta").challenge_indices),21)
        for x in range(5):
            for y in range(5):
                self.assertEqual(nonlinear.inverse(nonlinear.apply((x,y))),(x,y))

    def test_unsupported_non_shear_and_cubic_behavior_refuse(self):
        from adaptive_arbiter import fixture_atlas
        a=EvidenceAtlas(fixture_atlas(),("alpha",))
        def unsupported(x):
            u,v=x
            return ((u+u*u)%257,(v+v*v)%257)
        for x in ((0,0),(1,0),(0,1),(2,0),(8,11),(200,7)):
            a=a.admit("alpha",x,unsupported(x))
        with self.assertRaises(ValueError):identify(a,"alpha")
        b=EvidenceAtlas(fixture_atlas(),("alpha",))
        def cubic(x):
            u,v=x
            return ((u+u*u*u)%257,v)
        for x in ((0,0),(1,0),(0,1),(2,0),(3,0),(4,2)):
            b=b.admit("alpha",x,cubic(x))
        with self.assertRaises(ValueError):identify(b,"alpha")

    def test_witness_chain_and_external_pins_refuse_forged_catalogue(self):
        source=gather(3)
        original=typed_catalogue(source)
        self.assertEqual(original["distinct_family_count"],2)
        self.assertTrue(verify_catalogue(source,original,receiver_expected_head=source.head,
                                         receiver_expected_fingerprint=source.fingerprint))
        restored=restore_source(source.base,source.trace(),expected_head=source.head,
                                expected_fingerprint=source.fingerprint)
        self.assertEqual(typed_catalogue(restored),original)
        for change in ("changed","untrusted","truncated"):
            tampered=copy.deepcopy(original)
            if change=="changed":tampered["capabilities"][1]["ground"]["q"]+=1
            if change=="untrusted":tampered["source_root"]="0"*64
            if change=="truncated":tampered["capabilities"].pop()
            with self.assertRaises(ValueError):
                verify_catalogue(source,tampered,receiver_expected_head=source.head,
                                 receiver_expected_fingerprint=source.fingerprint)
        with self.assertRaisesRegex(ValueError,"pins"):
            verify_catalogue(source,original,receiver_expected_head="0"*64,
                             receiver_expected_fingerprint=source.fingerprint)

    def test_new_family_uses_existing_COG002_contextual_version_space(self):
        source=gather(11)
        atlas=MixedFamilyAtlas.from_evidence(source)
        self.assertEqual(len(atlas.choices),2)
        rng=random.Random(8081)
        pool=[]
        while len(pool)<160:
            x=(rng.randrange(257),rng.randrange(257))
            if x not in pool:pool.append(x)
        session=VersionSpace.empty(atlas)
        model=target_pair(11)
        def truth(x):
            return (model["alpha"] if (x[0]+x[1])%2==0 else model["beta"]).apply(x)
        for _ in range(12):
            x=session.acquisition([p for p in pool if p not in {w.x for w in session.witnesses}])
            session=session.admit(Witness.create(atlas,len(session.witnesses),session.head,x,truth(x)))
        policy=session.best_policy()
        self.assertEqual(policy.feature,"parity-sum")
        self.assertEqual((policy.zero,policy.one),("learned_alpha","learned_beta"))
        rebuilt=restore_selection(atlas,session.trace(),receiver_expected_head=session.head,
                                  receiver_expected_fingerprint=session.fingerprint)
        self.assertEqual(rebuilt,session)
        for _ in range(250):
            x=(rng.randrange(257),rng.randrange(257))
            self.assertEqual(policy.output(atlas,x),truth(x))
            receipt=atlas.typed_certificate(policy,x)
            self.assertEqual(tuple(receipt["output"]),truth(x))
            self.assertEqual(receipt["source_root"],source.head)

    def test_bad_fields_incomplete_challenges_and_contexts_refuse(self):
        state=gather(5)
        with self.assertRaises(ValueError):choose_probe(state,"beta",[(257,0)])
        with self.assertRaises(ValueError):choose_probe(state,"wrong",[(0,0)])
        with self.assertRaises(ValueError):matrix_rank([[1,2,3.1,4]],257,4)
        with self.assertRaises(ValueError):identify(state,"alpha",min_challenges=3)
        with self.assertRaises(ValueError):ShearGround(target_pair(0)["alpha"],0)

    @unittest.skipUnless(importlib.util.find_spec("vgi") is not None,"native VGI unavailable")
    def test_real_native_VGI_on_affine_factor_no_false_nonlinear_native_claim(self):
        from vgi_adapter import vgi_check
        source=gather(9)
        for context in source.contexts:
            claim=identify(source,context)
            underlying=claim.ground if isinstance(claim.ground,Affine) else claim.ground.affine
            native=vgi_check(underlying,((0,0),(1,0),(0,1),(93,21)))
            self.assertEqual(native["probes"],4)
            self.assertFalse(native["combined_dense_materialized"])


    def test_opaque_names_do_not_provide_a_family_metric(self):
        from capability_atlas import point_label, encode
        source=gather(4)
        affine=identify(source,"alpha")
        address=encode(affine.ground)
        self.assertNotEqual(point_label("opaque-seed-one",address),
                            point_label("opaque-seed-two",address))
        self.assertEqual(identify(source,"alpha"),affine)
        self.assertEqual(identify(source,"beta").family,
                         "quadratic-shear-before-affine")


if __name__=="__main__":unittest.main()
