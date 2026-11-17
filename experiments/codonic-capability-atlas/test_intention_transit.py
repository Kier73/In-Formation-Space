"""Real OS-process and mathematical tests for COG-010.

Local planner is a test-only oracle; native E-CPU IOS-001 is a required CI gate.
"""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cognitive_grounds import GroundRefused
from predictive_state import Machine, source_fixture, Teacher
from partial_observation import recover
from multi_observer_fabric import Host,HostProcess,SignedFabric
from run_multi_observer_fabric import prepare
from reference_ios_for_tests import ReferenceIOS
from intention_transit import (CognitiveProjection,FiniteCognitiveOrbit,
                               SignedFeatureReader,execute_intention,NativeIOSPlanner)

HERE=Path(__file__).resolve().parent

class DirectTransit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='cog010-')
        root=Path(cls.temp.name)
        cls.bundle=root/'bundle.json';cls.trust=root/'trust.json';cls.pins=root/'pins.json'
        prepare(cls.bundle,cls.trust,cls.pins,private_dir=root/'private',subjects=4,durations=2)
        cls.saved=json.loads(cls.bundle.read_bytes())
        cls.pinned=json.loads(cls.pins.read_bytes())
        cls.machine,_=recover(cls.saved['cognitive_checkpoint'],
                              expected_checkpoint_digest=cls.pinned['cognitive_digest'],
                              expected_ledger_head=cls.pinned['observation_head'],
                              expected_source_root=cls.pinned['source_root'])
        teacher=Teacher(*source_fixture(4,2),named=False)
        roster=json.loads(cls.trust.read_bytes())['hosts']
        cls.peers=[]
        for item in roster:
            name=item['name'];host=Host(name,item['public_key_pem'],item['cost'])
            cmd=(sys.executable,'-u',str(HERE/'observer_worker.py'),'--id',name,
                 '--key',str(root/'private'/f'{name}.pem'),
                 '--subjects','4','--durations','2','--fault',('target' if name=='beta' else 'none'))
            peer=HostProcess(host,cmd);peer.start();cls.peers.append(peer)
        cls.fabric=SignedFabric(teacher.source_root,teacher.alphabet,cls.peers)
        for item in roster:cls.fabric.qualify(item['name'])
        if cls.fabric.source_root!=cls.machine.source_root:
            raise AssertionError('restart produced an incompatible source epoch')
        cls.planner=ReferenceIOS()

    @classmethod
    def tearDownClass(cls):
        for peer in cls.peers:peer.stop(kill=True)
        cls.temp.cleanup()

    def test_pure_ready_with_no_qualified_host_work(self):
        p=CognitiveProjection(self.machine,'has_anchor')
        before=self.fabric.external_calls
        r=execute_intention(p,'anchored',self.planner,features=('minutes',))
        self.assertEqual(r['status'],'RESOLVED_WITHOUT_MEASUREMENT')
        self.assertEqual(r['result'],True)
        self.assertEqual(r['selected'],[])
        self.assertEqual(self.fabric.external_calls,before)

    def test_measure_only_one_relevant_signed_feature(self):
        p=CognitiveProjection(self.machine,'minutes')
        reader=SignedFeatureReader(self.machine,self.fabric,('noise','mention:topic_0001',))
        r=execute_intention(p,'anchored',self.planner,features=('minutes','repeat'),reader=reader)
        self.assertEqual(r['status'],'RESOLVED_AFTER_MEASUREMENT')
        self.assertEqual(r['selected'],['minutes'])
        self.assertEqual(r['result'],['minutes',24])
        self.assertGreaterEqual(r['additional_host_exchanges'],2)
        self.assertLessEqual(r['additional_host_exchanges'],3)
        self.assertEqual(reader.measurement_calls,1)
        self.assertEqual(len(r['measurement_receipts']),1)
        self.assertEqual(r['measurement_receipts'][0]['source_root'],self.machine.source_root)

    def test_intention_resolves_distinct_projection_without_evaluating_target_at_host(self):
        # A signed observer measures minutes; the admitted learned Ground
        # supplies the different (seconds) target through its structural law.
        p=CognitiveProjection(self.machine,'seconds')
        reader=SignedFeatureReader(self.machine,self.fabric,('mention:topic_0001',))
        r=execute_intention(p,'anchored',self.planner,features=('minutes',),reader=reader)
        self.assertEqual(r['status'],'RESOLVED_AFTER_MEASUREMENT')
        self.assertEqual(r['result'],['seconds',1440])
        self.assertEqual(r['selected'],['minutes'])
        self.assertEqual(reader.used_receipts[-1]['output'],['minutes',24])

    def test_identical_proven_measurement_cost_is_zero_after_caching(self):
        p=CognitiveProjection(self.machine,'minutes')
        reader=SignedFeatureReader(self.machine,self.fabric,('mention:topic_0001',))
        first=execute_intention(p,'anchored',self.planner,features=('minutes',),reader=reader)
        self.assertEqual(first['result'],['minutes',24])
        before=self.fabric.external_calls
        result=execute_intention(p,'anchored',self.planner,features=('minutes',),reader=reader)
        self.assertEqual(result['result'],['minutes',24])
        self.assertEqual(self.fabric.external_calls,before)
        self.assertEqual(result['additional_host_exchanges'],0)
        self.assertEqual(reader.measurement_calls,2)

    def test_refuse_ambiguous_intention_without_probe(self):
        p=CognitiveProjection(self.machine,'repeat')
        before=self.fabric.external_calls
        r=execute_intention(p,'anchored',self.planner,features=('minutes',))
        self.assertEqual(r['status'],'REFUSE')
        self.assertIsNone(r['result'])
        self.assertEqual(self.fabric.external_calls,before)

    def test_no_untrusted_reader_or_stale_roster(self):
        p=CognitiveProjection(self.machine,'minutes')
        with self.assertRaises(GroundRefused):
            execute_intention(p,'anchored',self.planner,features=('minutes',))
        from dataclasses import replace
        machine=Machine(self.machine.source_root[::-1],self.machine.alphabet,
                        self.machine.representatives,self.machine.transitions,self.machine.emissions)
        with self.assertRaises(GroundRefused):
            SignedFeatureReader(machine,self.fabric,('mention:topic_0000',))

    def test_ground_projection_matches_heldout_source(self):
        teacher=Teacher(*source_fixture(4,2),named=False)
        states={self.machine.state_after(('mention:topic_0000',)):
                ('mention:topic_0000',),self.machine.state_after(('mention:topic_0001',)):
                ('mention:topic_0001',)}
        for state,path in states.items():
            self.assertEqual(CognitiveProjection(self.machine,'minutes').target(state),
                             list(teacher.query(path+('minutes',))[-1]))

    def test_large_logical_tick_structural_jump(self):
        program=('mention:topic_0000','minutes','seconds','repeat','clear','noise',
                 'mention:topic_0001','minutes','repeat','clear')
        orb=FiniteCognitiveOrbit.compile(self.machine,program)
        self.assertTrue(orb.independent_validate())
        self.assertGreaterEqual(orb.period,1)
        self.assertLessEqual(len(orb.states),len(self.machine.representatives)*len(program))
        horizon=10**30+11
        state,phase=orb.at(horizon)
        self.assertEqual((state,phase),orb.at(orb.mu+(horizon-orb.mu)%orb.period))
        self.assertLess(len(orb.states),horizon)
        self.assertEqual(orb.at(0),(0,0))
        with self.assertRaises(GroundRefused):
            FiniteCognitiveOrbit.compile(self.machine,('not-an-operator',))

    def test_adversarial_tamper_of_compiled_orbit_is_rejected(self):
        from dataclasses import replace
        orbit=FiniteCognitiveOrbit.compile(self.machine,('mention:topic_0000','minutes','clear'))
        bad=list(orbit.states);bad[-1] = (bad[-1]+1)%(len(self.machine.representatives)*len(orbit.program))
        with self.assertRaises(GroundRefused):
            replace(orbit,states=tuple(bad)).independent_validate()

    def test_native_ecpu_integration_uses_actual_authoritative_code(self):
        try:from mailcpu.intention_sufficiency import SufficiencyRefused
        except ImportError:self.skipTest('native E-CPU is required on hosted CI')
        from hashlib import sha256
        native=NativeIOSPlanner(sha256(b'COG010-receiver-policy').hexdigest())
        for intention,expected,features in [
          ('has_anchor','READY',('minutes',)),
          ('minutes','MEASURE',('minutes','repeat')),
          ('seconds','MEASURE',('minutes',)),
          ('repeat','REFUSE',('minutes',)),
        ]:
            p=CognitiveProjection(self.machine,intention)
            plan=native.plan(p,'anchored',features)
            self.assertEqual(plan['status'],expected)
            if expected=='READY':
                report=execute_intention(p,'anchored',native,features=features)
                self.assertEqual(report['result'],True)
            if expected=='MEASURE':
                reader=SignedFeatureReader(self.machine,self.fabric,('mention:topic_0001',))
                report=execute_intention(p,'anchored',native,features=features,reader=reader)
                self.assertEqual(report['result'],['seconds',1440] if intention=='seconds' else ['minutes',24])
            if expected=='REFUSE':
                report=execute_intention(p,'anchored',native,features=features)
                self.assertEqual(report['status'],'REFUSE')
        orb=FiniteCognitiveOrbit.compile(self.machine,('mention:topic_0000','minutes','repeat','clear'))
        self.assertEqual(orb.native_at(10**30+11),orb.at(10**30+11))

if __name__=='__main__':unittest.main()
