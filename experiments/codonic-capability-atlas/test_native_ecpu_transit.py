"""COG-010: ACTUAL IOS-001+002+003 mutual-TLS measured cognitive intention.

Runs only when E-CPU is available; hosted CI MUST run with pinned E-CPU and
pytest. Source Ground is obtained through COG-009 signed observation and replay;
the provider's private cognitive state remains behind the native TLS service.
"""
from __future__ import annotations
import importlib.util
import json
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from hashlib import sha256
from pathlib import Path
from cognitive_grounds import GroundRefused
from partial_observation import recover
from run_multi_observer_fabric import prepare,resume
from intention_transit import CognitiveProjection,NativeIOSPlanner,FiniteCognitiveOrbit,execute_intention

HERE=Path(__file__).resolve().parent


def tls_contexts(path:Path):
    if shutil.which('openssl') is None:raise RuntimeError('openssl is required for native E-CPU TLS')
    def cmd(*args):
        p=subprocess.run(['openssl',*args],cwd=path,capture_output=True,text=True,timeout=15)
        if p.returncode:raise RuntimeError(p.stderr)
    ca_key,ca_cert=path/'ca.key',path/'ca.pem'
    cmd('req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(ca_key),
        '-out',str(ca_cert),'-days','1','-subj','/CN=COG010 experiment CA',
        '-addext','basicConstraints=critical,CA:TRUE',
        '-addext','keyUsage=critical,keyCertSign,cRLSign')
    certs={}
    for name,dns in [('provider','provider-b.fabric.test'),('receiver','receiver-a.fabric.test')]:
        key,csr,cert,ext=(path/f'{name}.{suffix}' for suffix in ('key','csr','pem','ext'))
        cmd('req','-new','-newkey','rsa:2048','-nodes','-keyout',str(key),
            '-out',str(csr),'-subj',f'/CN={dns}')
        ext.write_text(f'subjectAltName=DNS:{dns}\nextendedKeyUsage=clientAuth,serverAuth\n'
                       'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n')
        cmd('x509','-req','-in',str(csr),'-CA',str(ca_cert),'-CAkey',str(ca_key),
            '-CAcreateserial','-out',str(cert),'-days','1','-extfile',str(ext))
        certs[name]=(cert,key)
    server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.minimum_version=ssl.TLSVersion.TLSv1_2
    server.load_cert_chain(*map(str,certs['provider']))
    server.load_verify_locations(cafile=str(ca_cert))
    server.verify_mode=ssl.CERT_REQUIRED
    client=ssl.create_default_context(ssl.Purpose.SERVER_AUTH,cafile=str(ca_cert))
    client.minimum_version=ssl.TLSVersion.TLSv1_2
    client.load_cert_chain(*map(str,certs['receiver']))
    return server,client

@unittest.skipUnless(importlib.util.find_spec('mailcpu') is not None,
                     'native E-CPU required; CI runs this job with pinned real MailCPU')
class NativeCognitiveTransit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work=tempfile.TemporaryDirectory(prefix='cog010-native-')
        root=Path(cls.work.name)
        cls.root=root
        cls.bundle=root/'source.json';cls.trust=root/'enrolled-public.json';cls.pins=root/'pinned-heads.json'
        prepare(cls.bundle,cls.trust,cls.pins,private_dir=root/'operator-private',subjects=4,durations=2)
        pins=json.loads(cls.pins.read_bytes())
        check=resume(cls.bundle,cls.trust,pins)
        if check['external_host_calls']!=0:raise AssertionError('prior machine cannot be recovered offline')
        doc=json.loads(cls.bundle.read_bytes())
        cls.machine,_=recover(doc['cognitive_checkpoint'],
                              expected_checkpoint_digest=pins['cognitive_digest'],
                              expected_ledger_head=pins['observation_head'],
                              expected_source_root=pins['source_root'])
        cls.server_ctx,cls.client_ctx=tls_contexts(root)

    @classmethod
    def tearDownClass(cls):cls.work.cleanup()

    def test_authenticated_native_measurement_projects_learned_ground(self):
        from mailcpu.intention_measurement_fabric import (
            HostedMeasurement, MeasurementPeerClient, MeasurementPeerServer, MeasurementReceiptLedger)
        from mailcpu.intention_sufficiency import plan_sufficiency,MeasurementCapability
        from mailcpu.temporal import SchedulerReading
        from mailcpu.semantic_translation import canonical_value_digest
        from mailcpu.socket_transport import SocketTransport

        p=CognitiveProjection(self.machine,'seconds')
        contract=p.native_observer_contract('minutes')
        planner=NativeIOSPlanner(sha256(b'COG010-receiver-policy').hexdigest(),
                                 native_contracts={'minutes':contract})
        model=p.native();public='anchored';features=('minutes',)
        plan=planner.plan(p,public,features)
        self.assertEqual(plan['status'],'MEASURE')
        offers=planner.offers(p,features)
        subject,ground,_,_=p.native_descriptors()
        self.assertEqual(ground.content_digest,model.ground_digest)
        self.assertEqual(contract.interpretation.content_digest,model.ground_digest)
        self.assertEqual(offers[0].contract_digest,contract.digest)
        self.assertEqual(contract.subject,subject)

        private_state=self.machine.state_after(('mention:topic_0001',))
        value=p.feature(private_state,'minutes')
        self.assertEqual(value,['minutes',24])
        observation_reads=[];admissions=[]
        def authorize(request,peer):
            admissions.append((request['request_digest'],peer))
            return peer=='receiver-a' and request['model_digest']==model.digest
        def read(request):
            observation_reads.append(request['request_digest'])
            return value # ONLY the duration projection, not the hidden source identity.
        domain=tuple({tuple(p.feature(i,'minutes')):p.feature(i,'minutes')
                      for i in range(len(self.machine.representatives))}.values())
        installed={'minutes':HostedMeasurement(
            contract,model.digest,lambda:planner.authority_digest,authorize,read,domain)}
        listener=SocketTransport.listen('127.0.0.1',0)
        listener.settimeout(5)
        failures=[];stop=threading.Event();ready=threading.Event()
        def server():
            ledger=MeasurementReceiptLedger(self.root/'cognitive-native-ledger.sqlite')
            service=None
            try:
                service=MeasurementPeerServer.accept_mutual_tls(
                    listener,self.server_ctx,'provider-b','receiver-a',
                    'receiver-a.fabric.test',installed,ledger)
                ready.set()
                while not stop.is_set() and not service.transport.closed:
                    service.service_once();time.sleep(0.002)
            except BaseException as e:failures.append(e)
            finally:
                if service:service.close()
                ledger.close()
        thread=threading.Thread(target=server,daemon=True);thread.start()
        client=None
        try:
            client=MeasurementPeerClient.connect_mutual_tls(
                '127.0.0.1',listener.getsockname()[1],self.client_ctx,
                'receiver-a','provider-b','provider-b.fabric.test',timeout=5.0)
            self.assertTrue(ready.wait(5.0))
            report,receipts=client.resolve(
                model,public,offers,planner.authority_digest,plan,{'minutes':contract},
                subject,SchedulerReading('cognitive-orbit',37),
                canonical_value_digest({'nonce':'COG010-distinct-native-measurement-001'}))
            self.assertEqual(report['resolution']['result'],['seconds',1440])
            self.assertEqual(receipts['minutes'].projection,['minutes',24])
            self.assertEqual(len(observation_reads),1)
            self.assertEqual(len(admissions),1)
            self.assertEqual(admissions[0][1],'receiver-a')
            self.assertNotIn('topic_0001',str(report))
            self.assertNotIn('topic_0001',str(receipts['minutes'].to_dict()))
        finally:
            if client:client.close()
            stop.set();thread.join(timeout=6);listener.close()
            if failures:raise failures[0]
            self.assertFalse(thread.is_alive())

        # No-movement gates do not send anything over TLS or read a private host state.
        ready_result=execute_intention(CognitiveProjection(self.machine,'has_anchor'),
                                       'anchored',NativeIOSPlanner(planner.authority_digest))
        refuse_result=execute_intention(CognitiveProjection(self.machine,'repeat'),
                                        'anchored',NativeIOSPlanner(planner.authority_digest),features=('minutes',))
        self.assertEqual(ready_result['status'],'RESOLVED_WITHOUT_MEASUREMENT')
        self.assertEqual(refuse_result['status'],'REFUSE')
        self.assertEqual(len(observation_reads),1)

        orbit=FiniteCognitiveOrbit.compile(self.machine,
               ('mention:topic_0000','minutes','repeat','clear','mention:topic_0001','seconds','clear'))
        self.assertTrue(orbit.independent_validate())
        self.assertEqual(orbit.native_at(10**30+11),orbit.at(10**30+11))

if __name__=='__main__':unittest.main()
