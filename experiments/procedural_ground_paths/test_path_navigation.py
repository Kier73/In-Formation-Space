"""Real HTTP source observation, mixed transport navigation and strict evidence tests."""
from __future__ import annotations
import copy,hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import numpy as np
from cognitive_grounds import canonical,GroundRefused
from decision_experiment import H,ALL,Context,context
from train_policy import restore,propose
from run_path_navigation import create_peers,save_bundle,demo,disagreement_case
from path_navigator import MixedPathGround,recover_paths
from signed_query_path import verify_frame
from query_worker import KIND

WEIGHTS=Path(__import__('train_policy').__file__).resolve().parent/'results'

class LivePathTests(unittest.TestCase):
    def test_cross_path_real_process_result_and_independent_offline_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);out=demo(p,seed=9)
            self.assertEqual(out['intention_coordinate'],6)
            self.assertEqual(out['initial_neural_coordinate_advice'],1)
            self.assertEqual(out['changed_path_neural_coordinate_advice'],2)
            self.assertEqual(out['target_result'],out['expected_target_for_independent_synthetic_audit'])
            self.assertGreater(out['http_calls'],0);self.assertGreater(out['stdio_calls'],0)
            self.assertTrue(out['observer_host_killed']);self.assertFalse(out['ground_admitted'])
            proc=subprocess.run([sys.executable,str(Path(__file__).parent/'run_path_navigation.py'),'--mode','verify','--output',str(p)],capture_output=True,text=True,check=True)
            result=json.loads(proc.stdout)
            self.assertEqual(result['source_calls'],0)
            self.assertEqual(result['verified_signatures'],out['signed_receipts'])

    def test_unknown_until_replacement_http_host_resolves_dissent(self):
        self.assertTrue(disagreement_case()['unknown_on_divergence'])

    def test_http_get_is_a_real_observer_not_static_weights(self):
        with tempfile.TemporaryDirectory() as td:
            src,peers=create_peers(Path(td),H[7].tolist());http=peers[0];http.start()
            try:
                req={'kind':KIND,'host':http.host.name,'nonce':'a'*32,'root':src['root'],'coordinate':3}
                frame=http.request(req)
                self.assertEqual(verify_frame(frame,req,http.host),H[7,3])
                self.assertEqual(http.evidence[-1]['transport'],'http-observer')
                self.assertGreater(http.evidence[-1]['body_bytes'],300)
                self.assertGreater(http.evidence[-1]['elapsed_ns'],0)
                with self.assertRaises(HTTPError):urlopen('http://127.0.0.1:'+str(http.port)+'/unregistered',timeout=2)
                request=Request('http://127.0.0.1:'+str(http.port)+'/v1/observe',data=b'unexpected',method='POST')
                with self.assertRaises(HTTPError):urlopen(request,timeout=2)
            finally:http.stop(kill=True)

    def test_replay_nonce_and_key_substitution_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src,peers=create_peers(Path(td),H[11].tolist())
            for p in peers:p.start()
            try:
                http=peers[0]
                a={'kind':KIND,'host':http.host.name,'nonce':'b'*32,'root':src['root'],'coordinate':3}
                original=http.request(a)
                b={**a,'nonce':'c'*32}
                with self.assertRaises(ValueError):verify_frame(original,b,http.host)
                with self.assertRaises(ValueError):verify_frame(original,a,peers[2].host)
                for corruption in ('signature','value'):
                    altered=copy.deepcopy(original)
                    if corruption=='signature':altered['signature']='A'+altered['signature'][1:]
                    else:altered['body']['value']^=1
                    with self.assertRaises(ValueError):verify_frame(altered,a,http.host)
            finally:
                for p in peers:p.stop(kill=True)

    def test_path_receipts_refuse_even_after_resigning_outer_hash(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);src,peers=create_peers(d,H[12].tolist())
            for p in peers:p.start()
            try:
                g=MixedPathGround(src['root'],peers);g.read(3)
                bundle,pins=save_bundle(g,d/'results')
                self.assertGreaterEqual(len(bundle['events']),2)
                for field in ('etag','frame_sha256','host','transport'):
                    altered=copy.deepcopy(bundle)
                    record=altered['events'][0]
                    record[field]='nonsense' if field=='transport' else '0'*64
                    altered['digest']=__import__('cognitive_grounds').digest({k:v for k,v in altered.items() if k!='digest'})
                    with self.assertRaises(ValueError,msg=field):recover_paths(altered,pins)
                wrong_pins={**pins,'head':'0'*64}
                with self.assertRaises(ValueError):recover_paths(bundle,wrong_pins)
                forged=copy.deepcopy(bundle);forged['witness_ledger']['events'][0]['frame']['body']['value']^=1
                forged['digest']=__import__('cognitive_grounds').digest({k:v for k,v in forged.items() if k!='digest'})
                with self.assertRaises(ValueError):recover_paths(forged,pins)
            finally:
                for p in peers:p.stop(kill=True)

    def test_advice_is_host_topology_relative_not_source_truth(self):
        model,_=restore(WEIGHTS);rng=np.random.default_rng(9);rng.integers(len(H));ctx=context(rng)
        full=tuple(sum(sorted((2+q%4,4+q//4,2+q%3))[:2]) for q in range(8))
        fail=tuple(4+q//4+2+q%3 for q in range(8))
        def choose(p):
            c=Context(ctx.target,tuple(min(40,ctx.costs[q]+p[q]) for q in range(8)),ctx.weights)
            return propose(model,c,ALL,0)
        self.assertEqual(choose(full),1)
        self.assertEqual(choose(fail),2)
        self.assertEqual(ctx.target,6)

    def test_cheap_but_colluding_signatures_not_equal_to_truth(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);true=H[4].tolist();src,peers=create_peers(d,true,fault_beta=2)
            # Two separate signing keys can be wrong; the code must never
            # classify their agreement as independent Ground certification.
            peers[0].command[-1]='2'  # alpha faults at q=2 as well
            for p in peers:p.start()
            try:
                g=MixedPathGround(src['root'],peers)
                v=g.read(2)
                # Both cheapest signers lie identically; matching signatures
                # only establish their agreement, not the source law.
                self.assertNotEqual(v,true[2])
                self.assertEqual(len(g.events),2)
                verified=recover_paths(g.export_paths(),{'head':g.head,'source_root':src['root'],
                    'roster_digest':g.roster_digest,'hosts':[{'name':h.name,'key':h.public_key_pem,'cost':h.cost} for h in g.roster]})
                self.assertEqual(verified['qualified_observations'][2],v)
                self.assertFalse(verified['admitted'])
            finally:
                for p in peers:p.stop(kill=True)

    def test_source_salt_not_serialized_and_source_commitment_secret(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);src,peers=create_peers(d,H[15].tolist())
            for p in peers:p.start()
            try:
                g=MixedPathGround(src['root'],peers);g.read(0)
                doc,pins=save_bundle(g,d/'out');raw=canonical(doc)+canonical(pins)
                self.assertNotIn(src['salt'].encode(),raw)
                self.assertNotIn(b'private.json',raw)
            finally:
                for p in peers:p.stop(kill=True)

if __name__=='__main__':unittest.main()
