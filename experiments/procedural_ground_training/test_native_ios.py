"""Mandatory hosted E-CPU comparison to its genuine IOS-001 exact planner."""
import unittest
import numpy as np
from procedural_ground_training import World, make_world, exact_plan, sha
from mailcpu.intention_sufficiency import FiniteState,FiniteGround,MeasurementCapability,plan_sufficiency

class NativeOracleTest(unittest.TestCase):
    def test_generated_ground_labels_against_native_ecpu(self):
        for nstates,seed in ((16,95),(32,96)):
            rng=np.random.default_rng(seed)
            for k in range(140):
                w=make_world(rng,k,nstates=nstates,extended=nstates==32)
                model=FiniteGround(*(sha({'role':role}) for role in ('ground','public','intention','context')),
                    tuple(FiniteState.create(f's{i:02d}',0,int(w.targets[i]),
                        {'f0':int(w.features[i][0]),'f1':int(w.features[i][1]),'f2':int(w.features[i][2])})
                        for i in range(nstates)))
                offers=tuple(MeasurementCapability(f'f{i}',sha({'test':i}),f'observer-{i}',w.costs[i]) for i in range(3))
                native=plan_sufficiency(model,0,offers,sha({'role':'policy'}))
                plan=8 if native['status']=='REFUSE' else sum(1<<int(s[-1]) for s in native['selected_features'])
                self.assertEqual(plan,exact_plan(w))

if __name__=='__main__':unittest.main()
