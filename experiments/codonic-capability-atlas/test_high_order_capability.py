"""COG-005: functional capacity growth, mathematical identifiability and refusals."""
import copy
import importlib.util
import random
import unittest

from capability_atlas import Affine, encode
from adaptive_arbiter import fixture_atlas
from structural_discovery import EvidenceAtlas, restore as restore_evidence
from high_order_capability import (
    PolynomialGround, NavigableExpertAtlas, count_family, decode_capability,
    encode_capability, infer_capability, select_probes, verify_claim,
)


def unknown(seed: int, degree: int=16) -> PolynomialGround:
    rng=random.Random(seed)
    # Choose known nonsingular (triangular) A, but unknown coefficients.
    a=rng.randrange(1,257); d=rng.randrange(1,257)
    b=rng.randrange(257)
    matrix=((a,b),(0,d))
    offset=(rng.randrange(257),rng.randrange(257))
    coeff=[rng.randrange(257) for _ in range(degree-1)]
    coeff[-1] = rng.randrange(1,257)
    return PolynomialGround(Affine(257,matrix,offset),tuple(coeff))


def gather(seed:int=3,degree:int=16,extra:int=3):
    target=unknown(seed,degree)
    state=EvidenceAtlas(fixture_atlas(),('alpha',))
    rng=random.Random(seed*31+99)
    pool=[(x,0) for x in range(100)]+[(0,1)]+[
        (rng.randrange(257),rng.randrange(1,257)) for _ in range(120)]
    selected=select_probes(state,'alpha',pool,degree=degree,limit=degree+2+extra)
    for x in selected:
        state=state.admit('alpha',x,target.apply(x))
    return state,target


class HighOrderCapacityTests(unittest.TestCase):
    def test_exact_functional_cardinality_at_32(self):
        n=count_family(257,32)
        self.assertEqual(n,257**31*257**2*(257**2-1)*(257**2-257))
        self.assertEqual(n.bit_length(),297)
        self.assertGreater(n, 1<<256)
        with self.assertRaises(ValueError):count_family(257,257)

    def test_encode_decode_bijection_with_distinct_coefficients(self):
        for degree in (2,3,8,16,32):
            n=count_family(257,degree)
            for address in (0,1,32,n-1,n//2,n//3,1<<48):
                g=decode_capability(257,degree,address)
                self.assertEqual(encode_capability(g,degree),address)
                self.assertEqual(decode_capability(257,degree,encode_capability(g,degree)),g)
            with self.assertRaises(ValueError):decode_capability(257,degree,n)

    def test_inverse_and_independent_polynomial_evaluation(self):
        for degree in (2,4,8,16,32):
            for seed in range(3):
                model=unknown(seed,degree)
                rng=random.Random(seed+degree)
                for _ in range(60):
                    x=(rng.randrange(257),rng.randrange(257))
                    self.assertEqual(model.inverse(model.apply(x)),x)
                    self.assertEqual(model.apply(model.inverse(x)),x)
                    from_expansion=sum(c*pow(x[0],i+2,257)
                                       for i,c in enumerate(model.coefficients))%257
                    (a,b),(c,d)=model.affine.mat
                    y=(x[1]+from_expansion)%257
                    self.assertEqual(model.apply(x),((a*x[0]+b*y+model.affine.bias[0])%257,
                                                     (c*x[0]+d*y+model.affine.bias[1])%257))

    def test_original_COG003_and_COG004_families_are_subclasses(self):
        from family_discovery import identify as old_identify
        from structural_discovery import infer_affine
        for degree in (2,4):
            state,target=gather(17,degree,extra=5)
            result=infer_capability(state,'alpha',max_degree=degree)
            self.assertEqual(result.ground,target)
            self.assertTrue(verify_claim(state,result.to_dict(),expected_head=state.head,
                                          expected_fingerprint=state.fingerprint))
            if degree==2:
                self.assertEqual(old_identify(state,'alpha').ground.q,target.coefficients[0])
        # degree-4 polynomial cannot be confused with the quadratic Ground.
        state,_=gather(19,4)
        with self.assertRaises(ValueError):old_identify(state,'alpha')

    def test_unknown_degree_is_identified_from_full_order_family(self):
        for target_degree in (2,5,9,16):
            rng=random.Random(target_degree)
            true=unknown(target_degree,target_degree)
            state=EvidenceAtlas(fixture_atlas(),('alpha',))
            pool=[(x,0) for x in range(60)]+[(0,1)]+[(x,3) for x in range(60,90)]
            sampled=select_probes(state,'alpha',pool,degree=16,limit=22)
            for x in sampled:state=state.admit('alpha',x,true.apply(x))
            claim=infer_capability(state,'alpha',max_degree=16)
            self.assertEqual(claim.ground.degree,target_degree)
            self.assertEqual(claim.ground,true)
            self.assertEqual(len(claim.basis_indices),18)
            self.assertGreaterEqual(len(claim.challenge_indices),2)
            for _ in range(100):
                x=(rng.randrange(257),rng.randrange(257))
                self.assertEqual(claim.ground.apply(x),true.apply(x))

    def test_evidence_restore_requires_external_high_water_and_refuses_tamper(self):
        state,true=gather(12,8)
        claim=infer_capability(state,'alpha',max_degree=8)
        evidence=state.trace()
        recovered=restore_evidence(state.base,evidence,expected_head=state.head,
                                   expected_fingerprint=state.fingerprint)
        self.assertEqual(infer_capability(recovered,'alpha',max_degree=8),claim)
        changed=copy.deepcopy(claim.to_dict())
        changed['ground']['shear_coefficients_from_degree_two'][-1]^=1
        with self.assertRaises(ValueError):verify_claim(state,changed,expected_head=state.head,
                                                         expected_fingerprint=state.fingerprint)
        with self.assertRaises(ValueError):verify_claim(state,claim.to_dict(),expected_head='0'*64,
                                                         expected_fingerprint=state.fingerprint)
        modified=copy.deepcopy(evidence)
        modified['observations'][3]['observed'][0]^=1
        with self.assertRaises(ValueError):restore_evidence(state.base,modified,expected_head=state.head,
                                                            expected_fingerprint=state.fingerprint)

    def test_rank_fail_closed_and_nonlinear_challenges(self):
        s=EvidenceAtlas(fixture_atlas(),('alpha',))
        model=unknown(42,8)
        for x in range(20):s=s.admit('alpha',(x,0),model.apply((x,0)))
        with self.assertRaisesRegex(ValueError,'underdetermined'):
            infer_capability(s,'alpha',max_degree=8)
        s=s.admit('alpha',(0,1),model.apply((0,1)))
        # Once the full basis is present, a fifth-order perturbation off that
        # basis is falsified by an additional, withheld challenge observation.
        c=infer_capability(s,'alpha',max_degree=8)
        self.assertEqual(c.ground,model)
        broken=s.admit('alpha',(200,201),((model.apply((200,201))[0]+1)%257,0))
        with self.assertRaisesRegex(ValueError,'contradicts'):
            infer_capability(broken,'alpha',max_degree=8)

    def test_giant_index_contains_distinct_functional_laws(self):
        atlas=NavigableExpertAtlas(degree=32)
        rng=random.Random(92)
        chosen={0,1,(1<<48)-1,1<<24}
        while len(chosen)<4000:chosen.add(rng.randrange(1<<48))
        coords=set()
        for i in chosen:
            g=atlas.capability(i)
            addr=encode_capability(g,atlas.degree)
            self.assertNotIn(addr,coords)
            coords.add(addr)
        self.assertEqual(len(coords),len(chosen))
        self.assertEqual(atlas.center(1<<62),atlas.center(1<<62))

    def test_materialization_is_bounded_and_independent_oracle_detects_rehashed_tamper(self):
        atlas=NavigableExpertAtlas()
        route=atlas.route((1<<56)+73,8)
        obs=atlas.observe((13,17),route)
        self.assertEqual(obs['materialized_experts'],8)
        self.assertEqual(len(set(route['indices'])),8)
        self.assertTrue(atlas.verify_observation(route,obs))
        changed=copy.deepcopy(obs)
        changed['per_expert_outputs'][0][0]^=1
        from structural_discovery import digest
        changed['digest']=digest({k:v for k,v in changed.items() if k!='digest'})
        with self.assertRaisesRegex(ValueError,'independent'):
            atlas.verify_observation(route,changed)
        bad=copy.deepcopy(route)
        bad['indices'][0]=0
        bad['digest']=digest({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(ValueError,'route'):
            atlas.observe((13,17),bad)

    def test_scale_does_not_mask_realization_cost(self):
        for n in (128,1<<20,1<<48):
            atlas=NavigableExpertAtlas(logical_experts=n)
            route=atlas.route((1<<56)+73)
            self.assertEqual(len(route['indices']),8)
            obs=atlas.observe((3,4),route)
            self.assertEqual(obs['materialized_experts'],8)
            self.assertTrue(atlas.verify_observation(route,obs))

    @unittest.skipUnless(importlib.util.find_spec('mailcpu') is not None,'native E-CPU not installed')
    def test_native_ecpu_temporal_orbit_agrees(self):
        a=NavigableExpertAtlas()
        for t in (0,13,(1<<48)+1,(1<<62)+35):
            self.assertEqual(a.center(t,native=True),a.center(t))

if __name__=='__main__':unittest.main()
