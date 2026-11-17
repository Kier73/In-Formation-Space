"""Native E-CPU IOS-001 & long-horizon law navigator are independent gates."""
import importlib.util
import unittest
import numpy as np
from procedural_ground_training import sha,exact_plan
from cross_family_curriculum import FAMILIES,world_for,_affine_jump

@unittest.skipUnless(importlib.util.find_spec('mailcpu') is not None,
                     'native E-CPU is hard-required in hosted CI')
class NativeECPUTransferTests(unittest.TestCase):
    def test_all_four_ground_families_match_native_ios001(self):
        from mailcpu.intention_sufficiency import FiniteGround,FiniteState,MeasurementCapability,plan_sufficiency
        rng=np.random.default_rng(327)
        total=0
        for family in FAMILIES:
            for nstates in (16,32):
                for k in range(40):
                    w=world_for(family,rng,k,nstates)
                    states=tuple(FiniteState.create(f's{i:03d}',0,int(w.targets[i]),
                         {'f0':int(w.features[i][0]),'f1':int(w.features[i][1]),'f2':int(w.features[i][2])})
                         for i in range(nstates))
                    ground=FiniteGround(*(sha({'authority':role}) for role in ('ground','public','target','context')),states)
                    offers=tuple(MeasurementCapability(f'f{j}',sha({'contract':j}),f'provider-{j}',w.costs[j]) for j in range(3))
                    native=plan_sufficiency(ground,0,offers,sha({'admission':'native'}))
                    predicted=8 if native['status']=='REFUSE' else sum(1<<int(s[-1]) for s in native['selected_features'])
                    self.assertEqual(predicted,exact_plan(w))
                    total+=1
        self.assertEqual(total,320)

    def test_distant_coordinate_matches_native_lcg_without_intermediate_trajectory(self):
        from mailcpu.law_certifier import lcg_navigate
        for m in (16,32,101):
            for a,c,x in ((5,1,3),(7,11,6),(1,0,8)):
                for t in (0,1,32,10**15+137,10**30+11):
                    expected=_affine_jump(a,c,m,x%m,t)
                    self.assertEqual(expected,lcg_navigate(a,c,m,x%m,t))

if __name__=='__main__':unittest.main()
