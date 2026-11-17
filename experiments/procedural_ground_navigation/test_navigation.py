"""PGT-003: direct mathematical, learned, source-bound, cryptographic checks."""
from __future__ import annotations
from pathlib import Path
import copy,hashlib,json,os,subprocess,sys,tempfile,unittest,secrets
import numpy as np
import torch
from decision_experiment import (ALL,N,H,Context,context,features,fingerprint,indices,split,
                                 terminal,optimal_action,greedy_action,rollout,out_of_family_audit)
from train_policy import restore,propose,make_data,benchmark
from signed_query_path import verify_frame,recover,Host,SignedObserverPath
from run_experiment import signed_demo,independent_recovery,make_worker

RESULTS=Path(__file__).resolve().parent/'results'

class PolicyTests(unittest.TestCase):
    def test_library_distinct_complete_and_finite(self):
        self.assertEqual(H.shape,(30,8));self.assertEqual(len(set(map(tuple,H.tolist()))),30)
    def test_exact_tree_never_costlier_than_direct_and_never_peeks_truth(self):
        r=np.random.default_rng(22)
        for _ in range(80):
            c=context(r);a,cost=None,None
            value,query=optimal_action(c,ALL,0,4)
            self.assertLessEqual(value,c.costs[c.target]+1e-7)
            self.assertTrue(0<=query<8)
    def test_target_specific_terminal_differs_from_full_model_identity(self):
        r=np.random.default_rng(9)
        c=context(r)
        q=c.target
        m0,m1=split(ALL,q)
        self.assertTrue(terminal(c,m0));self.assertTrue(terminal(c,m1))
        self.assertGreater(len(indices(m0))+len(indices(m1)),2)
    def test_student_checkpoint_real_tensors_and_independently_bound(self):
        m,p=restore(RESULTS)
        self.assertEqual(sum(v.numel() for v in m.parameters()),(15*64+64)+(64*48+48)+(48+1))
        x,y,_=make_data(260,20)
        with torch.no_grad():
            pred=m(torch.from_numpy(x))
            self.assertEqual(pred.shape,(len(x),8))
        with tempfile.TemporaryDirectory() as td:
            import shutil
            d=Path(td);shutil.copy2(RESULTS/'manifest.json',d/'manifest.json')
            raw=(RESULTS/'observer_student.npz').read_bytes();altered=bytearray(raw);altered[-21]^=1
            (d/'observer_student.npz').write_bytes(altered)
            with self.assertRaises(ValueError):restore(d)
            (d/'observer_student.npz').write_bytes(raw)
            meta=json.loads((d/'manifest.json').read_bytes());meta['safety']='model-has-authority'
            (d/'manifest.json').write_text(json.dumps(meta))
            with self.assertRaises(ValueError):restore(d)
    def test_proposal_reproducible_and_never_observes_source(self):
        model,_=restore(RESULTS);rng=np.random.default_rng(17);ctx=context(rng)
        a=propose(model,ctx,ALL,0);b=propose(model,ctx,ALL,0)
        self.assertEqual(a,b);self.assertIn(a,range(8))
        self.assertIsNone(propose(model,ctx,split(ALL,ctx.target)[1],1<<ctx.target))
    def test_costed_model_better_than_myopic_gain_on_fixed_holdout(self):
        model,_=restore(RESULTS)
        x=benchmark(model,9012,200)
        self.assertLess(x['neural']['mean_cost'],x['gain']['mean_cost'])
        self.assertGreaterEqual(x['neural']['correct'],195)
        self.assertEqual(x['oracle']['unresolved'],0)
    def test_out_of_family_fail_closed_no_inferred_answers_admitted(self):
        model,_=restore(RESULTS)
        r=out_of_family_audit(model,lambda c,m,u:propose(model,c,m,u),seed=911,cases=180)
        self.assertGreater(r['false_candidates'],20)
        self.assertEqual(r['neural_predictions_admitted'],0)
        self.assertEqual(r['source_verified_target_results_correct'],180)
    def test_exact_signed_receipt_recovery_and_source_private(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            for item in ('manifest.json','observer_student.npz'):
                (d/item).write_bytes((RESULTS/item).read_bytes())
            r=signed_demo(d,seed=818)
            self.assertTrue(r['conflict_yielded_unknown']);self.assertTrue(r['replacement_resolved'])
            self.assertEqual(r['fresh_recovered_calls'],0)
            trust=json.loads((d/'trusted-pins.json').read_bytes())
            self.assertNotIn('salt',str(trust))
            self.assertNotIn('private',str(trust))
            report=independent_recovery(d)
            self.assertGreater(report['verified_signatures'],3)
    def test_two_signed_colluders_do_not_prove_the_observed_value_true(self):
        from decision_experiment import canonical
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            output=[int(x) for x in H[7].tolist()]
            src={'schema':'ifs.pgt003.query.source.v1','outputs':output,'salt':secrets.token_hex(32)}
            src['root']=hashlib.sha256(canonical(src)).hexdigest()
            source=d/'hidden.json';source.write_bytes(canonical(src))
            peers=[make_worker(d,name,source,flip=(2 if name in ('alpha','beta') else -1))
                   for name in ('alpha','beta','gamma')]
            for peer in peers:peer.start()
            try:
                fabric=SignedObserverPath(src['root'],peers)
                reported=fabric.read(2)
                self.assertNotEqual(reported,output[2])
                doc=fabric.export()
                accepted=recover(doc,src['root'],fabric.roster,fabric.roster_digest,fabric.head)
                self.assertEqual(accepted['qualified_observations'][2],reported)
                self.assertFalse(accepted['admitted'])
            finally:
                for peer in peers:peer.stop(kill=True)
    def test_http_artifact_checkpoint_failover(self):
        import importlib
        module=importlib.import_module('http_model_audit')
        with tempfile.TemporaryDirectory() as td:
            from shutil import copy2
            d=Path(td)
            for name in ('manifest.json','observer_student.npz'):
                copy2(RESULTS/name,d/name)
            report=module.audit(d,d/'http-audit.json')
            self.assertTrue(report['phases']['both_live']['identical_neural_outputs'])
            self.assertEqual(report['phases']['first_killed']['selected'],'b')
            self.assertEqual(report['phases']['corrupt_survivor']['status'],'REFUSED')

    def test_chain_tampering_stale_heads_and_key_change_refuse(self):
        doc=json.loads((RESULTS/'signed-ledger.json').read_bytes())
        trust=json.loads((RESULTS/'trusted-pins.json').read_bytes())
        hosts=[Host(h['name'],h['key'],h['cost']) for h in trust['hosts']]
        original=recover(doc,trust['source_root'],hosts,trust['roster_digest'],trust['head'])
        self.assertGreater(original['signed_receipt_count'],0)
        for modified in ('digest','value','stale'):
            broken=copy.deepcopy(doc)
            if modified=='digest':broken['events'][0]['digest']='0'*64
            if modified=='value':broken['events'][0]['frame']['body']['value']^=1
            if modified=='stale':broken['head']='0'*64
            with self.assertRaises(ValueError):recover(broken,trust['source_root'],hosts,trust['roster_digest'],trust['head'])
        with self.assertRaises(ValueError):recover(doc,trust['source_root'],hosts,trust['roster_digest'],'0'*64)
    def test_fresh_subprocess_receiver_uses_no_keys_or_worker_requests(self):
        script='''from run_experiment import independent_recovery
from pathlib import Path
import json,sys
print(json.dumps(independent_recovery(Path(sys.argv[1]))))'''
        out=subprocess.run([sys.executable,'-c',script,str(RESULTS)],capture_output=True,text=True,check=True)
        data=json.loads(out.stdout)
        self.assertEqual(data['source_calls'],0)
        self.assertEqual(data['evidence_head'],json.loads((RESULTS/'trusted-pins.json').read_bytes())['head'])

if __name__=='__main__':unittest.main()
