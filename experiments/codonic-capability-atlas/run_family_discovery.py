"""COG-004 deterministic family-discovery ablation and contextual transfer audit."""
from __future__ import annotations
import json
import random
from test_family_discovery import gather,target_pair
from family_discovery import identify,typed_catalogue,MixedFamilyAtlas
from adaptive_arbiter import VersionSpace,Witness,restore


def audit():
    success={"active":0,"random":0}
    total=correct=0
    for seed in range(100):
        models=target_pair(seed)
        for method in success:
            source=gather(seed,method,6,models)
            try:
                claims={context:identify(source,context) for context in source.contexts}
            except ValueError:
                continue
            success[method]+=1
            if method=="active":
                catalogue=typed_catalogue(source)
                assert catalogue["distinct_family_count"]==2
                rng=random.Random(seed*97+117)
                for context in source.contexts:
                    for _ in range(50):
                        point=(rng.randrange(257),rng.randrange(257))
                        total+=1
                        correct+=int(claims[context].apply(point)==models[context].apply(point))
    source=gather(11,"active")
    atlas=MixedFamilyAtlas.from_evidence(source)
    session=VersionSpace.empty(atlas)
    rng=random.Random(8081)
    pool=[]
    while len(pool)<160:
        point=(rng.randrange(257),rng.randrange(257))
        if point not in pool:pool.append(point)
    originals=target_pair(11)
    def truth(point):
        return (originals["alpha"] if (point[0]+point[1])%2==0 else originals["beta"]).apply(point)
    for index in range(12):
        x=session.acquisition([v for v in pool if v not in {w.x for w in session.witnesses}])
        session=session.admit(Witness.create(atlas,index,session.head,x,truth(x)))
    policy=session.best_policy()
    assert restore(atlas,session.trace(),receiver_expected_head=session.head,
                   receiver_expected_fingerprint=session.fingerprint)==session
    heldout=500
    contextual=sum(policy.output(atlas,(x,y))==truth((x,y)) for x,y in
                   ((rng.randrange(257),rng.randrange(257)) for _ in range(heldout)))
    return {"schema":"COG004/reproducible-local-audit/1",
            "hypothesis_families":["affine","quadratic-shear-before-affine"],
            "observation_budget_per_family":6,
            "independent_source_trial_count":100,
            "active_two_family_identification_success":success["active"],
            "random_two_family_identification_success":success["random"],
            "heldout_source_checks":total,
            "heldout_source_correct":correct,
            "mixed_family_contextual_acquisitions":12,
            "mixed_family_contextual_heldout":heldout,
            "mixed_family_contextual_correct":contextual,
            "selected_context_policy":policy.__dict__,
            "source_ground_root":source.head,
            "source_ground_fingerprint":source.fingerprint,
            "policy_evidence_root":session.head,
            "policy_evidence_fingerprint":session.fingerprint,
            "claims":"family unique only within declared finite class; no external source authentication",
            "nonlinear_semantics":"real VGI validates affine subplan only; shear executed in local reference"}


if __name__=="__main__":print(json.dumps(audit(),indent=2,sort_keys=True))
