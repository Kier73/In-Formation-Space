"""PGT-003 reproducible local neural experiment and signed observer handoff."""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,tempfile,secrets
from pathlib import Path
import numpy as np
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from decision_experiment import (ALL,N,H,context,out_of_family_audit,features,indices,sampled_initial,terminal,
                                 greedy_action,optimal_action,rollout,split,canonical,fingerprint)
from train_policy import restore,propose,benchmark
from signed_query_path import SignedObserverPath,Host,HostProcess,recover

ROOT=Path(__file__).resolve().parent

def make_worker(root,name,output,flip=-1):
    key=Ed25519PrivateKey.generate()
    pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    loc=root/(name+'.pem');loc.write_bytes(pem);loc.chmod(0o600)
    pub=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    h=Host(name,pub,1)
    command=[sys.executable,str(ROOT/'query_worker.py'),'--name',name,'--key',str(loc),'--source',str(output),'--fault',str(flip)]
    return HostProcess(h,command,timeout=3)

def signed_demo(output=ROOT/'results',seed=711):
    rng=np.random.default_rng(seed);r=Path(output);r.mkdir(exist_ok=True,parents=True)
    with tempfile.TemporaryDirectory(prefix='pgt003-') as tmp:
        folder=Path(tmp)
        truth=int(rng.integers(N));actual=H[truth].tolist()
        source={'schema':'ifs.pgt003.query.source.v1','outputs':actual,'salt':secrets.token_hex(32)}; source['root']=hashlib.sha256(canonical(source)).hexdigest()
        path=folder/'private-source.json';path.write_bytes(canonical(source))
        peers=[make_worker(folder,name,path,flip=(2 if name=='beta' else -1)) for name in ('alpha','beta','gamma')]
        for peer in peers:peer.start()
        try:
            fabric=SignedObserverPath(source['root'],peers)
            # A novel ground's exact source function is never given to the receiver.
            # Two enrolled keys agree on first chosen coordinate; recover a dispute
            # with a third host after a genuine kill / restart.
            first=fabric.read(1)
            peers[2].stop(kill=True)
            try:fabric.read(2)
            except ValueError:unresolved=True
            else:raise AssertionError('unresolved conflicting testimony was accepted')
            peers[2].start()
            after=fabric.read(2)
            assert after==actual[2] and first==actual[1]
            # Neural advice determines a query sequence, but the source outcomes
            # are learned exclusively via signed observer process calls.
            model,_=restore(r)
            ctx=context(rng)
            mask=ALL;used=0;events=[]
            for q,val in sorted(fabric.observed.items()):
                mask=split(mask,q)[val];used|=(1<<q)
            for _ in range(5):
                if not mask or terminal(ctx,mask):break
                q=propose(model,ctx,mask,used)
                if q is None:break
                try:v=fabric.read(q)
                except ValueError:break
                mask=split(mask,q)[v];used|=(1<<q);events.append({'coordinate':q,'value':v})
            bundle=fabric.export()
            trust={'source_root':source['root'],'roster_digest':fabric.roster_digest,'head':fabric.head,
                   'hosts':[{'name':h.name,'key':h.public_key_pem,'cost':h.cost} for h in fabric.roster]}
            (r/'signed-ledger.json').write_bytes(canonical(bundle))
            (r/'trusted-pins.json').write_bytes(canonical(trust))
            verify=recover(bundle,trust['source_root'],[p.host for p in peers],trust['roster_digest'],trust['head'])
            assert verify['qualified_observations']==fabric.observed
            # A signed reading is accepted as an observation reported by hosts;
            # it is NOT proof that the shared hidden source is mathematically true.
            return {'schema':'ifs.pgt003.direct-signed-demo.v1',
                    'private_source_not_sent_to_advisory_policy':True,'hard_kill_occurred':True,
                    'conflict_yielded_unknown':unresolved,
                    'replacement_resolved':after==actual[2],
                    'signed_receipts':len(fabric.events),'unique_observed_features':len(fabric.observed),
                    'neural_selected_queries':events,'fresh_recovered_calls':verify['process_source_calls'],
                    'fabric_head':fabric.head,'roster_digest':fabric.roster_digest,
                    'source_root':source['root'],'private_keys_in_export':False,'private_source_salt_in_export':False,
                    'claims':'local-separate-process-signed-source-reports-not-mtls-or-source-truth'}
        finally:
            for peer in peers:peer.stop(kill=True)

def independent_recovery(r):
    doc=json.loads((r/'signed-ledger.json').read_bytes());trust=json.loads((r/'trusted-pins.json').read_bytes())
    hosts=[Host(x['name'],x['key'],x['cost']) for x in trust['hosts']]
    result=recover(doc,trust['source_root'],hosts,trust['roster_digest'],trust['head'])
    return {'verified_signatures':result['signed_receipt_count'],
            'source_calls':result['process_source_calls'],
            'evidence_head':result['head'],
            'readings':result['qualified_observations']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=ROOT/'results');p.add_argument('--mode',choices=['audit','receiver'],default='audit');p.add_argument('--cases',type=int,default=1200)
    a=p.parse_args()
    if a.mode=='receiver':
        print(json.dumps(independent_recovery(a.results),sort_keys=True));return
    model,_=restore(a.results)
    eval={'heldout':benchmark(model,9012,a.cases),'prior_shift':benchmark(model,9013,a.cases,True)}
    ood=out_of_family_audit(model,lambda c,m,u:propose(model,c,m,u),seed=9045,cases=a.cases)
    direct=signed_demo(a.results)
    own=independent_recovery(a.results)
    report={'schema':'ifs.pgt003.full-audit.v1','evaluation':eval,'out_of_family':ood,'signed_demo':direct,'receiver':own,
            'admitted_hypothesis_predictions':0,'candidate_not_source_proof':True}
    (a.results/'audit.json').write_bytes(canonical(report));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
