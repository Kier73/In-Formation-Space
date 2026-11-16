"""RCG-004 native E-CPU authority and real mTLS transit gates."""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
import unittest

from connectome_ground import ConnectomeGround
from temporal_ground import SparseTransfer,TemporalGroundRefused,hash_object,navigate_verified
from test_temporal_ground import FIXTURE

NATIVE=importlib.util.find_spec('mailcpu') is not None


@unittest.skipUnless(NATIVE,"native E-CPU is required by hosted integration job")
class AuthenticatedTemporalTests(unittest.TestCase):
    def test_native_bm_host_replay_and_receiver_owned_policy(self):
        from experiments.real_connectome_ground.continuity.temporal_fabric.temporal_transport import (
            SCHEMA,TemporalHost,
        )
        raw=FIXTURE.encode()
        sha=hashlib.sha256(raw).hexdigest()
        receiver=TemporalHost(raw,allowed_source='AWCL',
                              allowed_target='AIYL',
                              source_sha256=sha,
                              require_original=False,native_ecpu=True)
        intention={
            'schema':SCHEMA+'.request.v1',
            'request_id':'first',
            'ground':receiver.ground.fingerprint,
            'source':'AWCL','target':'AIYL',
            'kind':'chemical','tick':2**56+73,
        }
        returned=receiver.handle(intention)
        self.assertEqual(returned['schema'],SCHEMA+'.response.v1')
        self.assertFalse(returned['replayed'])
        self.assertEqual(returned['receiver_execution_count'],1)
        self.assertEqual(returned['result'],
                         navigate_verified(returned['certificate'],2**56+73))
        replay=receiver.handle(intention)
        self.assertTrue(replay['replayed'])
        self.assertEqual(receiver.executions,1)
        with self.assertRaises(TemporalGroundRefused):
            receiver.handle({**intention,'tick':99})
        with self.assertRaises(TemporalGroundRefused):
            receiver.handle({**intention,'ground':'0'*64,'request_id':'new'})
        with self.assertRaises(TemporalGroundRefused):
            receiver.handle({**intention,'source':'ASER','request_id':'new'})
        with self.assertRaises(TemporalGroundRefused):
            TemporalHost(raw,allowed_source='AWCL',
                         allowed_target='AIYL',
                         source_sha256='0'*64,require_original=False)

    def test_real_pinned_multi_receiver_mtls_and_hard_loss(self):
        from experiments.real_connectome_ground.continuity.temporal_fabric.run_temporal_fabric import run
        source=Path(__file__).resolve().parents[1]/'data'/'herm_full_edgelist.csv'
        self.assertTrue(source.is_file(),'native hosted test requires original pinned source')
        report=run(source,requests=8,workers=3)
        self.assertEqual(report['requests'],8)
        self.assertEqual(report['verified_query_count'],8)
        self.assertTrue(report['real_authenticated_loopback'])
        self.assertTrue(report['failed_worker_not_selected_after_death'])
        self.assertEqual(len(report['real_tls_protocol']),1)
        self.assertEqual(report['failed_worker'],1)
        self.assertGreater(report['measured_sender_p50_ns'],0)
        self.assertGreater(report['total_wire_application_bytes'],0)


if __name__=='__main__':
    unittest.main()
