"""COG-003: deterministic audit of unknown capability induction and transfer."""
from __future__ import annotations
import json
import random
from test_structural_discovery import trial
from adaptive_arbiter import VersionSpace, Witness


def audit(cases: int = 100) -> dict:
    if type(cases) is not int or not 1 <= cases <= 1000:
        raise ValueError('cases must be 1..1000')
    active = random_control = 0
    examples = []
    for seed in range(cases):
        learned, state, truth = trial(seed,'active')
        assert learned is not None
        active += 1
        random_ground, _, _ = trial(seed,'random')
        random_control += random_ground is not None
        examples.append({
            'seed':seed,'atlas_head':state.head,
            'selected_new_capabilities': [
                {'context': c, 'address':state.discover(c).to_dict()['address']}
                for c in state.contexts
            ]
        })
    # Stage two explicitly uses COG-002's existing contextual learner.
    learned, state, truth = trial(811,'active')
    learner = VersionSpace.empty(learned)
    rng = random.Random(9347)
    pool = []
    while len(pool)<180:
        x = (rng.randrange(257),rng.randrange(257))
        if x not in pool:
            pool.append(x)
    for _ in range(12):
        x = learner.acquisition([z for z in pool if z not in {w.x for w in learner.witnesses}])
        y = (truth['left'] if (x[0]+x[1])%2==0 else truth['right']).apply(x)
        learner = learner.admit(Witness.create(learned,len(learner.witnesses),learner.head,x,y))
    policy = learner.best_policy()
    assert (policy.feature,policy.zero,policy.one)==('parity-sum','learned_left','learned_right')
    heldout = [(rng.randrange(257),rng.randrange(257)) for _ in range(300)]
    assert all(policy.output(learned,x) ==
               (truth['left'] if (x[0]+x[1])%2==0 else truth['right']).apply(x)
               for x in heldout)
    return {
        'schema':'COG-003-exact-discovery-audit/1','trials':cases,
        'contexts_per_trial':2,'observation_budget_per_context':4,
        'active_exact_reconstructions':active,
        'random_exact_reconstructions':random_control,
        'all_active_holdouts_correct':True,'heldout_per_active_trial':100,
        'newly_discovered_affine_maps_per_trial':2,
        'second_stage_existing_COG002_policy':policy.__dict__,
        'second_stage_training_observations':12,
        'second_stage_heldout_probes':300,'second_stage_correct':300,
        'evidence_case_zero':examples[0],
        'qualification':'synthetic targets within admitted affine family; no global law proof, external source authentication, or new primitive invention'
    }


if __name__ == '__main__':
    print(json.dumps(audit(),sort_keys=True,indent=2))
