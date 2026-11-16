"""COG-005 reproducible functional-capacity and active-observation scale audit."""
from __future__ import annotations
from statistics import median
from time import perf_counter_ns
import json
import random
from adaptive_arbiter import fixture_atlas
from structural_discovery import EvidenceAtlas, canonical
from high_order_capability import NavigableExpertAtlas, count_family, select_probes, infer_capability
from test_high_order_capability import unknown


def run(seed_count:int=100,heldout_each:int=100,timing_samples:int=100)->dict:
    p=257
    pool=[(x,(3*x+7)%p) for x in range(128)]+[(0,1),(1,0)]
    cases=[]
    for degree in (8,16,32):
        active=random_ok=checks=correct=0
        for seed in range(seed_count):
            model=unknown(seed+degree*100,degree)
            state=EvidenceAtlas(fixture_atlas(),('alpha',))
            points=select_probes(state,'alpha',pool,degree=degree,limit=degree+4)
            for x in points:
                state=state.admit('alpha',x,model.apply(x))
            try:
                claim=infer_capability(state,'alpha',max_degree=degree)
                success=claim.ground==model
            except ValueError:
                success=False
            active+=int(success)
            rng=random.Random(seed+degree*10007)
            test=[(rng.randrange(p),rng.randrange(p)) for _ in range(heldout_each)]
            if success:
                checks+=len(test)
                correct+=sum(claim.ground.apply(x)==model.apply(x) for x in test)
            other=EvidenceAtlas(fixture_atlas(),('alpha',))
            for x in rng.sample(pool,degree+4):
                other=other.admit('alpha',x,model.apply(x))
            try:
                random_ok+=int(infer_capability(other,'alpha',max_degree=degree).ground==model)
            except ValueError:
                pass
        cases.append({'max_degree':degree,'trials':seed_count,
                      'active_recovered':active,'random_recovered':random_ok,
                      'heldout_correct':correct,'heldout_checked':checks})
    times=[]
    for n in (128,1<<20,1<<48):
        a=NavigableExpertAtlas(logical_experts=n)
        tick=(1<<56)+73
        spans=[]
        for i in range(timing_samples):
            start=perf_counter_ns()
            route=a.route(tick)
            value=a.observe((13+i%257,17),route)
            a.verify_observation(route,value)
            spans.append(perf_counter_ns()-start)
        r=a.route(tick)
        times.append({'logical_experts':n,'plan_route_bytes':len(canonical(r)),
                      'result_bytes':len(canonical(a.observe((13,17),r))),
                      'median_local_us':round(median(spans)/1000,2),
                      'materialized_experts':r['k']})
    return {'schema':'COG005/scalable-functional-capacity-audit/v1',
            'field':257,'max_polynomial_degree':32,
            'distinct_full_family_count':str(count_family(257,32)),
            'full_family_address_bits':count_family(257,32).bit_length(),
            'indexed_unique_experts':1<<48,
            'example_logical_time':(1<<56)+73,
            'tests':cases,'timing':times,
            'epistemic_scope':'synthetic source-defined bijective functions, not pretrained intelligence; local Python time excludes network and Hypervisor',
            'native_ecpu_validation':'separate mandatory CI gate, not included in local measurements'}

if __name__=='__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
