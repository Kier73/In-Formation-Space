"""Integration gates for existing native E-CPU mTLS + M1; no local mock success."""
from __future__ import annotations
import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
from test_atlas import SOURCE
from connectome_ground import ConnectomeGround
from observer_quotient import ExpandedSyntheticGround,discover,QuotientRefused
from atlas import prepare_atlas,execute_batch

NATIVE=importlib.util.find_spec('mailcpu') is not None

@unittest.skipUnless(NATIVE,'installed native E-CPU source is mandatory')
class NativeAuthenticatedTests(unittest.TestCase):
    def test_receiver_admission_replay_and_local_quorum_distinction(self):
        from native_handoff import AtlasReceiver,SCHEMA
        raw=SOURCE.encode();pin=hashlib.sha256(raw).hexdigest()
        ground=ConnectomeGround.from_csv(raw,require_original=False)
        op=ExpandedSyntheticGround(ground,groups=8,copies=32,seed=11)
        cert=discover(op);atlas=prepare_atlas(op,cert)
        receiver=AtlasReceiver(raw,pin,atlas['digest'],groups=8,copies=32,seed=11,
                               require_original=False)
        batch=[{'tick':2**56+73,'sources':[[2,1],[14,9]],
                'readout':{'kind':'sum_squares','indices':[0,2,4]}}]
        req={'schema':SCHEMA+'.request.v1','request_id':'request.1',
             'source_sha256':pin,'atlas_digest':atlas['digest'],'batch':batch,
             'provision':{'certificate':cert,'atlas':atlas}}
        first=receiver.handle(req)
        self.assertTrue(first['cold_admission'])
        self.assertEqual(first['receiver_execution_count'],1)
        self.assertEqual(first['batch']['values'],execute_batch(op,cert,atlas,batch)['values'])
        replay=receiver.handle(req)
        self.assertTrue(replay['replayed'])
        self.assertEqual(receiver.executions,1)
        with self.assertRaisesRegex(QuotientRefused,'conflict'):
            receiver.handle({**req,'batch':[{'tick':1,**{k:v for k,v in batch[0].items() if k!='tick'}}]})
        warm={**req,'request_id':'request.2','provision':None}
        second=receiver.handle(warm)
        self.assertFalse(second['cold_admission'])
        self.assertEqual(second['m1_manifest_digest'],first['m1_manifest_digest'])
        checkpoint=receiver.m1.checkpoint()
        new=AtlasReceiver(raw,pin,atlas['digest'],groups=8,copies=32,seed=11,
                          require_original=False,checkpoint=checkpoint,
                          checkpoint_head=checkpoint['digest'])
        self.assertFalse(new.handle(warm)['cold_admission'])
        with self.assertRaises(QuotientRefused):
            AtlasReceiver(raw,pin,atlas['digest'],groups=8,copies=32,seed=11,
                          require_original=False,checkpoint=checkpoint,
                          checkpoint_head='0'*64)

    def test_actual_authenticated_loopback_and_hard_kill_m1_rehome(self):
        from native_handoff import run_experiment
        raw=SOURCE.encode();pin=hashlib.sha256(raw).hexdigest()
        ground=ConnectomeGround.from_csv(raw,require_original=False)
        op=ExpandedSyntheticGround(ground,groups=8,copies=32,seed=11)
        cert=discover(op);atlas=prepare_atlas(op,cert)
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            source=folder/'source.csv';source.write_bytes(raw)
            certificate=folder/'certificate.json';certificate.write_text(json.dumps(cert))
            candidate=folder/'atlas.json';candidate.write_text(json.dumps(atlas))
            report=run_experiment(source,certificate,candidate,source_pin=pin,
                                  groups=8,copies=32,seed=11,fixture=True,requests=6)
        self.assertEqual(report['verified_answers'],6)
        self.assertTrue(report['real_tls_loopback'])
        self.assertTrue(report['recovered_native_m1_after_hard_loss'])
        self.assertEqual(report['cold_admissions'],1)
        self.assertEqual([x['cold'] for x in report['measurements']],[True,False,False,False,False,False])
        self.assertGreater(report['actual_network_bytes'],0)

if __name__=='__main__':unittest.main()