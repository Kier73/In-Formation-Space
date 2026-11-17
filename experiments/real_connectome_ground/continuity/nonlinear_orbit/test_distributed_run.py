"""Sender-side RCG-005 admission gates; actual TLS covered in hosted native CI."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import unittest
from pathlib import Path

from connectome_ground import ConnectomeGround
from temporal_ground import SparseTransfer, TemporalGroundRefused, \
    prepare, navigate_verified, hash_object
from conjugate_ground import ConjugatedGround
from distributed_run import verify_reply
from test_temporal_ground import FIXTURE


class SenderReplyGates(unittest.TestCase):
    def setUp(self):
        original=FIXTURE.encode()
        self.source=ConnectomeGround.from_csv(original,require_original=False)
        self.model=ConjugatedGround(
            SparseTransfer.from_ground(self.source,'AWCL','AWCL'),
            ('AWCL','ASER','AIYL'))
        self.raw_sha=hashlib.sha256(original).hexdigest()
        self.request={'schema':'ifs.rcg004.temporal-transit.v1.request.v1',
                      'request_id':'a-latent-query','ground':self.source.fingerprint,
                      'source':'AWCL','target':'ASER','kind':'chemical','tick':2**56+73}
        op=SparseTransfer.from_ground(self.source,'AWCL','ASER')
        cert=prepare(op)
        result=navigate_verified(cert,self.request['tick'])
        body={'schema':'ifs.rcg004.temporal-transit.v1.response.v1',
              'request_id':self.request['request_id'],'ground':self.source.fingerprint,
              'source_sha256':self.raw_sha,'intention_digest':hash_object(self.request),
              'certificate':cert,'result':result,'receiver_compute_ns_local':1000,
              'receiver_pid':12345,'receiver_execution_count':1,'replayed':False}
        self.response={**body,'digest':hash_object(body)}
        self.route={'peer_certificate_sha256':'a'*64,'tls_version':'TLSv1.3','sender_total_ns':12000}

    def verify(self,**overrides):
        kw={'source':self.source,'model':self.model,'original_sha':self.raw_sha,
            'request':self.request,'response':self.response,'telemetry':self.route,
            'receiver_pid':12345,'peer_sha':'a'*64,'checked':{}}
        kw.update(overrides)
        return verify_reply(**kw)

    def test_accepts_exact_receiver_original_source_and_rechecks(self):
        self.assertEqual(self.verify(),self.response['result']['value_mod_p'])
        seen={}
        self.verify(checked=seen)
        self.assertEqual(len(seen),1)
        self.verify(checked=seen)
        self.assertEqual(len(seen),1)

    def test_refuses_forged_identity_route_and_numerical_results_even_when_rehashed(self):
        for changed in ('request-id','pid','ground','source_sha','intention','value','certificate','replay'):
            reply=copy.deepcopy(self.response)
            if changed=='request-id':reply['request_id']='different-request'
            if changed=='pid':reply['receiver_pid']=23456
            if changed=='ground':reply['ground']='a'*64
            if changed=='source_sha':reply['source_sha256']='a'*64
            if changed=='intention':reply['intention_digest']='a'*64
            if changed=='value':reply['result']['value_mod_p']+=1
            if changed=='certificate':reply['certificate']['coefficients'][0]+=1
            if changed=='replay':reply['replayed']=True
            if changed=='value':reply['result']['digest']=hash_object({k:v for k,v in reply['result'].items() if k!='digest'})
            if changed=='certificate':reply['certificate']['digest']=hash_object({k:v for k,v in reply['certificate'].items() if k!='digest'})
            reply['digest']=hash_object({k:v for k,v in reply.items() if k!='digest'})
            with self.subTest(changed=changed),self.assertRaises(TemporalGroundRefused):
                self.verify(response=reply)
        with self.assertRaises(TemporalGroundRefused):
            self.verify(peer_sha='wrong-peer')
        with self.assertRaises(TemporalGroundRefused):
            self.verify(telemetry={**self.route,'tls_version':'TLSv1.0'})
        with self.assertRaises(TemporalGroundRefused):
            self.verify(request={**self.request,'target':'UNKNOWN'})
        with self.assertRaises(TemporalGroundRefused):
            self.verify(receiver_pid=33333)

    def test_source_replacement_and_cached_certificate_collision_refused(self):
        raw=FIXTURE.replace('AWCL,AWCR,11','AWCL,AWCR,12').encode()
        replaced=ConnectomeGround.from_csv(raw,require_original=False)
        with self.assertRaises(TemporalGroundRefused):
            self.verify(source=replaced)
        cached={self.response['certificate']['digest']:'different-content'}
        with self.assertRaises(TemporalGroundRefused):
            self.verify(checked=cached)

    @unittest.skipUnless(importlib.util.find_spec('mailcpu') is not None,
                         'actual authenticated transport needs native E-CPU')
    def test_real_multi_receiver_hard_kill_on_original_dataset(self):
        from distributed_run import run
        path=Path(__file__).resolve().parents[2]/'data'/'herm_full_edgelist.csv'
        self.assertTrue(path.is_file(),'full original source mandatory in native hosted check')
        report=run(path,requests=4)
        self.assertEqual(report['verified_host_observations'],12)
        self.assertTrue(report['replacement_used_after_loss'])
        self.assertEqual(report['lost_worker'],1)
        self.assertEqual(report['transport'],'actual-E-CPU-mutual-TLS-ReliableChannel-over-loopback')
        self.assertGreaterEqual(report['independently_verified_certificates'],3)
        self.assertEqual(report['node_count'],448)


if __name__=='__main__':unittest.main()
