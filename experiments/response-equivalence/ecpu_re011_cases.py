"""Run with pinned, genuine mailcpu.temporal (local stand-in is insufficient)."""
import copy
import unittest
from detection_calibration import CalibrationError, enrollment, sha
from ecpu_re011_hosts import source_host, observer_host, verify, _check

class ECPUCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.reg=enrollment(deterministic=True)
        self.src=source_host(self.reg)
        self.a=observer_host(self.src,self.reg,'A')
        self.b=observer_host(self.src,self.reg,'B')

    def test_actual_temporal_handoff_concurrent_observers(self):
        result=verify(self.src,self.a,self.b,self.reg)
        self.assertEqual(result['causal_relations']['A_concurrent_B'],'concurrent')
        self.assertEqual(result['calibration']['counts']['joint_non_detection'],12)
        self.assertIsNone(result['physical_detection_guarantee'])

    def test_cross_host_elapsed_not_inferred(self):
        self.assertIsNone(verify(self.src,self.a,self.b,self.reg)['cross_host_elapsed'])

    def test_missing_source_handoff_rejected(self):
        bad=copy.deepcopy(self.a)
        bad['binding']['source_seal']='0'*64
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaises(CalibrationError):verify(self.src,bad,self.b,self.reg)

    def test_unkeyed_frame_edit_and_rehash_does_not_forge_causal_proof(self):
        bad=copy.deepcopy(self.b)
        bad['frame']['causal']['vector']['S']=0
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(CalibrationError,'binding'):
            verify(self.src,self.a,bad,self.reg)

    def test_swap_frames_fails_even_with_rehashed_envelope(self):
        bad=copy.deepcopy(self.a)
        bad['frame']=copy.deepcopy(self.b['frame'])
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaises(CalibrationError):verify(self.src,bad,self.b,self.reg)

    def test_cross_challenge_fails(self):
        changed=copy.deepcopy(self.reg)
        changed['challenge']='other-run'
        with self.assertRaises(CalibrationError):verify(self.src,self.a,self.b,changed)

    def test_observer_holds_only_own_role_key(self):
        for actor in ('A','B'):
            scoped=copy.deepcopy(self.reg)
            scoped['keys']={actor:self.reg['keys'][actor]}
            observation=observer_host(self.src,scoped,actor)
            self.assertEqual(observation['role'],actor)

if __name__=='__main__':unittest.main()