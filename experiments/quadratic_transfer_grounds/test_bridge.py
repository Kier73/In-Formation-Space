"""Cross-project conceptual TCN-001 discovery to TCN-002 execution tests."""
from __future__ import annotations
from dataclasses import dataclass
import sys
from pathlib import Path
import unittest

import numpy as np
from bridge import InitialPhaseWitness
from transfer import fidelity


@dataclass(frozen=True)
class FittedFixture:
    """A structural fixture only; the native TCN-001 admission test is below."""
    p: int = 31
    a: int = 7
    b: int = 11
    observed_digest: str = 'a'*64
    decision: str = 'qualified'


class BridgeTests(unittest.TestCase):
    def test_declared_future_requires_explicit_hypothesis(self):
        w=InitialPhaseWitness.from_tcn001(FittedFixture())
        ray, note=w.continue_hypothetically((3,9),0)
        self.assertEqual((ray.kind,ray.a,ray.b),('flat',7,11))
        self.assertFalse(note['future_schedule_assumed'])
        with self.assertRaisesRegex(ValueError,'schedule not independently observed'):
            w.continue_hypothetically((3,9),100)
        with self.assertRaises(ValueError):
            InitialPhaseWitness.from_tcn001(FittedFixture(decision='refused'))
        with self.assertRaises(ValueError):
            InitialPhaseWitness.from_tcn001(FittedFixture(observed_digest='invalid'))

    def test_relative_circuit_from_fitted_phase_matches_direct_fft(self):
        w=InitialPhaseWitness.from_tcn001(FittedFixture())
        p=w.p
        x=np.arange(p)
        v=np.exp(2j*np.pi*((w.a*x*x+w.b*x+4)%p)/p)/np.sqrt(p)
        pattern=(3,9)
        for n in range(20):
            ray, note=w.continue_hypothetically(pattern,n,assume_future_schedule=True)
            self.assertGreater(fidelity(ray,v),1-1e-10)
            self.assertEqual(note['future_schedule_assumed'],n>0)
            v=np.fft.ifft(v)*np.sqrt(p)
            v*=np.exp(2j*np.pi*((pattern[n%len(pattern)]*x*x)%p)/p)

    def test_with_actual_neighbor_tcn001_module_when_in_repo_checkout(self):
        """CI native integration, local copies may not have sibling checkout."""
        sibling=Path(__file__).resolve().parents[1]/'theta_cayley_navigation'
        if not (sibling/'theta_cayley.py').exists():
            self.skipTest('native TCN-001 sibling requires complete IFS checkout')
        sys.path.insert(0,str(sibling))
        from theta_cayley import admit, _phase
        p=127
        rng=np.random.default_rng(912)
        shuffled=rng.permutation(p)
        train,valid=shuffled[:77],shuffled[77:102]
        truth=_phase(p,17,31,7,np.arange(p))
        discovered=admit(p,train,truth[train],valid,truth[valid],null_trials=19)
        self.assertEqual(discovered.decision,'qualified')
        w=InitialPhaseWitness.from_tcn001(discovered)
        ray, info=w.continue_hypothetically((9,4,2),1000,assume_future_schedule=True)
        self.assertEqual(info['discovery_sha256'],discovered.observed_digest)
        self.assertTrue(ray.kind in ('delta','flat'))


if __name__=='__main__':
    unittest.main()
