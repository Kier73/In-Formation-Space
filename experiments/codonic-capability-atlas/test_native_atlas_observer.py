"""COG005 independently check mathematical handoffs, E-CPU authority in native CI."""
import copy
import importlib.util
import unittest
from native_atlas_observer import form_plan, verify_plan, execute, verify_report


class NativeAtlasHandoffTests(unittest.TestCase):
    def test_discovery_plan_recovers_exact_distant_selected_function(self):
        plan=form_plan()
        atlas,model=verify_plan(plan,expected_head=plan['source_head'],
                                expected_fingerprint=plan['source_fingerprint'])
        self.assertEqual(atlas.degree,32)
        self.assertEqual(len(plan['source']['observations']),37)
        self.assertEqual(model,atlas.capability(plan['route']['center']))
        self.assertTrue(atlas.verify_observation(plan['route'],atlas.observe(plan['point'],plan['route'])))

    def test_artifact_cannot_pin_its_own_trust(self):
        plan=form_plan()
        with self.assertRaises(ValueError):
            verify_plan(plan,expected_head='0'*64,expected_fingerprint=plan['source_fingerprint'])
        broken=copy.deepcopy(plan)
        broken['source']['observations'][0]['observed'][1]^=1
        from structural_discovery import digest
        broken['digest']=digest({k:v for k,v in broken.items() if k!='digest'})
        with self.assertRaises(ValueError):
            verify_plan(broken,expected_head=plan['source_head'],
                        expected_fingerprint=plan['source_fingerprint'])

    @unittest.skipUnless(importlib.util.find_spec('mailcpu') is not None and
                         importlib.util.find_spec('vp') is not None,
                         'native E-CPU and VP-003 required')
    def test_native_qualified_execution_replay_and_denial(self):
        plan=form_plan()
        report=execute(plan,expected_head=plan['source_head'],
                       expected_fingerprint=plan['source_fingerprint'])
        self.assertTrue(verify_report(report,expected_head=plan['source_head'],
                                      expected_fingerprint=plan['source_fingerprint']))
        refused=execute(plan,expected_head=plan['source_head'],
                        expected_fingerprint=plan['source_fingerprint'],allow_compute=False)
        self.assertFalse(refused['accepted'])
        self.assertEqual(refused['handler_calls'],0)
        altered=copy.deepcopy(report)
        altered['native']['result']['expert_observation']['per_expert_outputs'][0][0]^=1
        from structural_discovery import digest
        altered['digest']=digest({k:v for k,v in altered.items() if k!='digest'})
        with self.assertRaises(ValueError):
            verify_report(altered,expected_head=plan['source_head'],
                          expected_fingerprint=plan['source_fingerprint'])

if __name__=='__main__':unittest.main()
