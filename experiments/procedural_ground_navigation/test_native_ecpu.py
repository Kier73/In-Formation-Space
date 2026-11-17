"""Hosted mandatory E-CPU IOS-001 and existing navigation conformance gate."""
from __future__ import annotations
import os,unittest,hashlib
try:
    from mailcpu.intention_sufficiency import (FiniteGround,FiniteState,MeasurementCapability,
                         plan_sufficiency,verify_sufficiency_plan,resolve_sufficiency,verify_sufficiency_resolution)
    from mailcpu.law_certifier import lcg_navigate
    AVAILABLE=True
except ImportError:
    AVAILABLE=False
from decision_experiment import H,N
from procedural_ground_training import World,exact_plan
from cross_family_curriculum import _affine_jump

class NativeAuthorityTests(unittest.TestCase):
    @unittest.skipUnless(AVAILABLE or bool(os.getenv('PGT003_REQUIRE_NATIVE')), 'native E-CPU package unavailable')
    def test_30_law_intention_plans_against_real_ecpu_ios001(self):
        if not AVAILABLE:raise AssertionError('native E-CPU missing despite CI required gate')
        for law in range(N):
            for costs in ((1,3,7),(4,2,8),(3,3,3)):
                f=tuple(tuple((q>>k)&1 for k in range(3)) for q in range(8))
                y=tuple(int(a) for a in H[law].tolist())
                w=World(f,y,costs,law)
                truth=exact_plan(w)
                digest=lambda tag:hashlib.sha256(tag.encode()).hexdigest()
                ground=FiniteGround(digest('ground:'+str(law)),digest('public'),digest('goal'),digest('context'),
                    tuple(FiniteState.create(str(q),0,y[q],dict(zip(('x','y','z'),f[q]))) for q in range(8)))
                offers=tuple(MeasurementCapability(name,digest('contract:'+name),'host.'+name,cost)
                             for name,cost in zip(('x','y','z'),costs))
                plan=plan_sufficiency(ground,0,offers,digest('authority'))
                verify_sufficiency_plan(plan,ground,0,offers,digest('authority'))
                self.assertEqual(plan['status'],'REFUSE' if truth==8 else 'READY' if truth==0 else 'MEASURE')
                self.assertEqual(plan['selected_features'],[('x','y','z')[k] for k in range(3) if truth<8 and truth>>k&1])
                if truth!=8:
                    measured={name:f[5][('x','y','z').index(name)] for name in plan['selected_features']}
                    result=resolve_sufficiency(ground,0,offers,digest('authority'),plan,measured,
                                               digest('sample-independent-receipt') if measured else None)
                    self.assertEqual(result['result'],y[5])
                    verify_sufficiency_resolution(result,ground,0,offers,digest('authority'),plan,
                                                  measured,digest('sample-independent-receipt') if measured else None)
    @unittest.skipUnless(AVAILABLE or bool(os.getenv('PGT003_REQUIRE_NATIVE')), 'native E-CPU package unavailable')
    def test_native_lcg_navigation_at_large_coordinate(self):
        if not AVAILABLE:raise AssertionError('native E-CPU missing despite CI required gate')
        for a,c,m,x in ((5,1,16,7),(7,3,32,21),(1,0,16,15),(3,19,32,4)):
            for t in (0,1,7,10**15+271,10**30+11):
                self.assertEqual(lcg_navigate(a,c,m,x,t),_affine_jump(a,c,m,x,t))

if __name__=='__main__':unittest.main()
