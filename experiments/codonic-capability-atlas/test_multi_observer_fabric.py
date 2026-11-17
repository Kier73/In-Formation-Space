"""Live separate-process, Ed25519-pinned observer integration and refusal gates."""
from __future__ import annotations
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cognitive_grounds import GroundRefused, digest
from predictive_state import source_fixture, Teacher, conformance
from types import SimpleNamespace
from partial_observation import ObservedOracle, experimental_revision, checkpoint, recover
from multi_observer_fabric import Host,HostProcess,SignedFabric,FrozenFabric,verify_signed,_request

ROOT=Path(__file__).resolve().parent

class LiveFabricTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.teacher=Teacher(*source_fixture(4,2),named=False)
        self.clients=[];self.hosts=[]
        for name,cost,fault in [('alpha',1,'none'),('beta',2,'target'),('gamma',3,'none')]:
            private=Ed25519PrivateKey.generate()
            path=Path(self.temp.name)/f'{name}.pem'
            path.write_bytes(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            pem=private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')
            host=Host(name,pem,cost);self.hosts.append(host)
            command=(sys.executable,'-u',str(ROOT/'observer_worker.py'),'--id',name,'--key',str(path),
                     '--subjects','4','--durations','2','--fault',fault)
            client=HostProcess(host,command,timeout=4)
            client.start();self.clients.append(client)
        self.addCleanup(lambda: [client.stop(kill=True) for client in self.clients])
        self.fabric=SignedFabric(self.teacher.source_root,self.teacher.alphabet,self.clients)

    def qualify(self):
        for host in self.hosts:self.assertTrue(self.fabric.qualify(host.name))

    def frozen(self):
        doc=self.fabric.document()
        frozen=FrozenFabric(doc,expected_digest=doc['digest'],expected_head=self.fabric.head,
                            expected_roster_root=self.fabric.source_root,trusted_hosts=self.hosts)
        return doc,frozen

    def test_live_qualification_two_signed_peers_direct_math(self):
        self.qualify()
        word=('mention:topic_0002','minutes')
        output=self.fabric.query(word)
        self.assertEqual(output,self.teacher.query(word))
        self.assertEqual(len(self.fabric.votes[word]),2)
        doc,frozen=self.frozen();self.assertEqual(frozen.query(word),output)
        self.assertEqual(frozen.external_calls,0)
        self.assertEqual(len(doc['qualified']),3)

    def test_signed_disagreement_kept_then_resolved_by_independent_third(self):
        self.qualify()
        word=('mention:topic_0003','minutes')
        expected=self.teacher.query(word)
        output=self.fabric.query(word)
        self.assertEqual(output,expected)
        self.assertEqual(len(self.fabric.votes[word]),3)
        self.assertNotEqual(self.fabric.votes[word]['beta'],expected)
        dissent=self.fabric.dispute(word)
        self.assertEqual(dissent['different_results'],2)
        self.assertEqual(dissent['status'],'provisional_agreement')
        doc,frozen=self.frozen();self.assertEqual(frozen.query(word),expected)
        self.assertEqual(len(self.fabric.events),9) # 6 qualification, 3 membership

    def test_insufficient_agreement_remains_unknown_and_does_not_fabricate(self):
        self.qualify()
        self.clients[2].stop(kill=True)
        path=('mention:topic_0003','minutes')
        with self.assertRaisesRegex(GroundRefused,'unknown:'):
            self.fabric.query(path)
        self.assertEqual(self.fabric.dispute(path)['status'],'unknown')
        doc,frozen=self.frozen()
        with self.assertRaisesRegex(GroundRefused,'unknown:'):frozen.query(path)
        self.clients[2].start()
        self.assertEqual(self.fabric.query(path),self.teacher.query(path))
        self.assertEqual(len(self.fabric.votes[path]),3)

    def test_process_death_rehome_and_durable_signed_restore(self):
        self.qualify()
        one=('mention:topic_0001','minutes')
        self.fabric.query(one)
        before=self.fabric.head
        calls_before=self.fabric.external_calls
        self.clients[0].stop(kill=True)
        two=('mention:topic_0003','minutes')
        with self.assertRaisesRegex(GroundRefused,'unknown:'):
            self.fabric.query(two) # only beta (wrong) and gamma (right) while alpha is dead
        self.assertEqual(self.fabric.query(one),self.teacher.query(one))
        self.assertEqual(self.fabric.external_calls,calls_before+2) # beta + gamma, no replay of one
        unknown_doc,unknown_frozen=self.frozen()
        with self.assertRaisesRegex(GroundRefused,'unknown:'):unknown_frozen.query(two)
        self.clients[0].start() # actual replacement child process, same enrolled signing identity
        self.assertEqual(self.fabric.query(two),self.teacher.query(two))
        doc,frozen=self.frozen()
        self.assertEqual(frozen.head,self.fabric.head)
        self.assertNotEqual(frozen.head,before)
        three=('mention:topic_0000','seconds')
        self.assertEqual(self.fabric.query(three),self.teacher.query(three))
        self.assertEqual(frozen.query(two),self.teacher.query(two))

    def test_signature_forgery_even_if_outer_chain_rehashed(self):
        self.qualify();word=('mention:topic_0001','minutes');self.fabric.query(word)
        doc,_=self.frozen();tampered=copy.deepcopy(doc)
        event=tampered['events'][-1]
        event['signed_receipt']['body']['outputs'][-1]=['minutes',999]
        event['digest']=digest({k:v for k,v in event.items() if k!='digest'})
        tampered['head']=event['digest'];tampered['digest']=digest({k:v for k,v in tampered.items() if k!='digest'})
        with self.assertRaisesRegex(GroundRefused,'signature'):
            FrozenFabric(tampered,expected_digest=tampered['digest'],expected_head=tampered['head'],
                        expected_roster_root=self.fabric.source_root,trusted_hosts=self.hosts)

    def test_self_supplied_or_swapped_key_does_not_establish_identity(self):
        self.qualify();self.fabric.query(('mention:topic_0000','minutes'))
        doc,_=self.frozen()
        untrusted=[Host('alpha',self.hosts[1].public_key_pem),self.hosts[1],self.hosts[2]]
        with self.assertRaisesRegex(GroundRefused,'independent trust pins'):
            FrozenFabric(doc,expected_digest=doc['digest'],expected_head=doc['head'],
                         expected_roster_root=doc['source_root'],trusted_hosts=untrusted)
        with self.assertRaisesRegex(GroundRefused,'stale'):
            FrozenFabric(doc,expected_digest='0'*64,expected_head=doc['head'],
                         expected_roster_root=doc['source_root'],trusted_hosts=self.hosts)

    def test_request_correlation_replay_is_rejected(self):
        self.qualify()
        host=self.hosts[0];client=self.clients[0]
        a=_request(self.teacher.source_root,'alpha',('minutes',),self.teacher.alphabet)
        frame=client.request(a)
        b=_request(self.teacher.source_root,'alpha',('minutes',),self.teacher.alphabet)
        with self.assertRaisesRegex(GroundRefused,'request'):
            verify_signed(frame,b,host,self.teacher.source_root,self.teacher.alphabet)
        self.assertEqual(verify_signed(frame,a,host,self.teacher.source_root,self.teacher.alphabet),(('unknown',),))

    def test_signed_majority_of_colluding_sources_is_not_mathematical_truth(self):
        # Both cheapest independently signed workers can agree on a WRONG value.
        # Only a separate ground-truth audit, unavailable in the open world,
        # can expose it. The fabric must never call agreement global truth.
        alpha=self.clients[0]
        alpha.stop(kill=True)
        command=list(alpha.command)
        command[command.index('none')]='target'
        alpha.command=tuple(command)
        alpha.start()
        self.qualify()  # deliberately weak qualification challenge cannot see the lie
        path=('mention:topic_0003','minutes')
        observed=self.fabric.query(path)
        self.assertNotEqual(observed,self.teacher.query(path))
        self.assertEqual(self.fabric.dispute(path)['status'],'provisional_agreement')
        self.assertEqual(len(self.fabric.votes[path]),2)
        _,frozen=self.frozen();self.assertEqual(frozen.query(path),observed)

    def test_restarted_qualified_observer_cannot_equivocate_at_same_epoch(self):
        self.qualify()
        path=('mention:topic_0003','minutes')
        self.fabric._poll('alpha',path,phase='membership')
        alpha=self.clients[0];alpha.stop(kill=True)
        command=list(alpha.command);command[command.index('none')]='target'
        alpha.command=tuple(command);alpha.start()
        with self.assertRaisesRegex(GroundRefused,'equivocated'):
            self.fabric._poll('alpha',path,phase='membership')

    def test_cog008_learner_directly_uses_signed_multi_host_observations(self):
        self.qualify()
        obs=ObservedOracle(self.fabric,max_queries=20000)
        learning,machine,report=experimental_revision(obs,max_challenges=200)
        self.assertEqual(report['status'],'provisional_finitely_challenged')
        # Complete finite conformance is an independent audit, never a learning oracle.
        check=conformance(SimpleNamespace(ground=self.teacher.ground,
                                         alphabet=self.teacher.alphabet,
                                         source_root=self.fabric.source_root),machine)
        self.assertTrue(check.equivalent)
        self.assertGreater(check.checked_edges,0)
        self.assertEqual(machine.run(('mention:topic_0003','minutes')),
                         self.teacher.query(('mention:topic_0003','minutes')))
        self.assertEqual(machine.run(('mention:topic_0002','seconds')),
                         self.teacher.query(('mention:topic_0002','seconds')))
        data=checkpoint(obs,learning,machine,report)
        rebuilt,frozen_obs=recover(data,expected_checkpoint_digest=data['digest'],
                                   expected_ledger_head=obs.head,expected_source_root=obs.source_root)
        self.assertEqual(rebuilt.fingerprint,machine.fingerprint)
        self.assertEqual(frozen_obs.external_calls,0)
        self.assertGreater(self.fabric.external_calls,20)
        _,frozen=self.frozen()
        self.assertEqual(frozen.query(('mention:topic_0003','minutes')),
                         self.teacher.query(('mention:topic_0003','minutes')))

if __name__=='__main__':unittest.main()
