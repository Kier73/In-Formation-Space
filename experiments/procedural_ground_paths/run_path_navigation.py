"""Reproduce PGT-004 across actual HTTP and stdio observer processes."""
from __future__ import annotations
import argparse,hashlib,json,secrets,subprocess,sys,tempfile
from pathlib import Path
import numpy as np
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cognitive_grounds import canonical
from decision_experiment import Context,H,context,ALL,terminal
from train_policy import restore
from run_experiment import make_worker
from signed_query_path import Host,recover
from path_navigator import HTTPPeer,StdioPeer,MixedPathGround,navigate,recover_paths

ROOT=Path(__file__).resolve().parent
WEIGHTS=Path(__import__('train_policy').__file__).resolve().parent/'results'

def http_peer(folder,name,source,price,flip=-1):
    key=Ed25519PrivateKey.generate()
    pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    loc=folder/(name+'.pem');loc.write_bytes(pem);loc.chmod(0o600)
    pub=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    host=Host(name,pub,1)
    cmd=[sys.executable,str(ROOT/'http_observer_worker.py'),'--name',name,'--key',str(loc),'--source',str(source),'--fault',str(flip)]
    return HTTPPeer(host,cmd,price=price)

def create_peers(folder,actual,fault_beta=-1):
    source={'schema':'ifs.pgt003.query.source.v1','outputs':list(map(int,actual)),
            'salt':secrets.token_hex(32)}
    source['root']=hashlib.sha256(canonical(source)).hexdigest()
    src=folder/'private.json';src.write_bytes(canonical(source));src.chmod(0o600)
    alpha=http_peer(folder,'alpha',src,price=lambda q:2+(q%4))
    beta=StdioPeer(make_worker(folder,'beta',src,flip=fault_beta),price=lambda q:4+(q//4))
    gamma=http_peer(folder,'gamma',src,price=lambda q:2+(q%3))
    return source,(alpha,beta,gamma)

def save_bundle(ground,output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    trust={'source_root':ground.source_root,'roster_digest':ground.roster_digest,'head':ground.head,
            'hosts':[{'name':h.name,'key':h.public_key_pem,'cost':h.cost} for h in ground.roster]}
    bundle=ground.export_paths()
    (out/'bundle.json').write_bytes(canonical(bundle));(out/'trust.json').write_bytes(canonical(trust))
    return bundle,trust

def demo(output,seed=9):
    model,manifest=restore(WEIGHTS)
    rng=np.random.default_rng(seed);truth=int(rng.integers(len(H)));actual=H[truth].tolist()
    with tempfile.TemporaryDirectory(prefix='pgt004-') as td:
        folder=Path(td);source,peers=create_peers(folder,actual)
        for p in peers:p.start()
        try:
            ground=MixedPathGround(source['root'],peers)
            ctx=context(rng)
            def advice():
                prices=ground.prices()
                routed=Context(ctx.target,tuple(min(40,ctx.costs[q]+prices[q]) for q in range(8)),ctx.weights)
                return __import__('train_policy').propose(model,routed,ALL,0)
            advice_initial=advice()
            # The trained policy sees route-conditioned costs and intention,
            # but never the hidden source law or source salt.
            report=navigate(model,ctx,ground)
            assert report['status']=='WITNESSED_NOT_GROUND_ADMITTED'
            assert report['result']==actual[ctx.target]
            paths={x['transport'] for x in ground.transport_log}
            # Make sure both transport contracts are actually observed.
            for q in (3,5):ground.read(q)
            paths={x['transport'] for x in ground.transport_log}
            assert paths=={'http-observer','signed-stdio'},paths
            # HTTP host fails; remaining enrolled live paths still supply one
            # corroborating HTTP and one stdio vote.
            peers[0].stop(kill=True)
            advice_after_failure=advice()
            for q in (4,7):ground.read(q)
            bundle,trust=save_bundle(ground,output)
            offline=recover_paths(bundle,trust)
            assert offline['qualified_observations']==ground.observed
            report_out={'schema':'ifs.pgt004.direct-audit.v1','model_sha256':manifest['weights_sha256'],
                        'intention_coordinate':ctx.target,'target_status':report['status'],
                        'candidate':report['candidate'],'target_result':report['result'],
                        'expected_target_for_independent_synthetic_audit':actual[ctx.target],
                        'route_sensitive_neural_queries':report['queries'],
                        'initial_neural_coordinate_advice':advice_initial,
                        'changed_path_neural_coordinate_advice':advice_after_failure,
                        'http_calls':offline['http_reads'],'stdio_calls':offline['stdio_reads'],
                        'signed_receipts':offline['signed_receipt_count'],
                        'actual_transport_bytes':offline['bytes_observed'],
                        'response_time_ns_total':offline['elapsed_ns_observed'],
                        'observer_host_killed':True,'offline_host_calls':offline['process_source_calls'],
                        'source_salt_exported':False,'private_keys_exported':False,
                        'ground_admitted':False,
                        'claim':'local signed HTTP and stdio observer paths; no mTLS or Hypervisor authority'}
            (Path(output)/'audit.json').write_bytes(canonical(report_out))
            return report_out
        finally:
            for p in peers:p.stop(kill=True)

def disagreement_case(seed=304):
    rng=np.random.default_rng(seed);truth=int(rng.integers(len(H)));actual=H[truth].tolist()
    with tempfile.TemporaryDirectory(prefix='pgt004-neg-') as td:
        folder=Path(td);source,peers=create_peers(folder,actual,fault_beta=2)
        for p in peers:p.start()
        try:
            ground=MixedPathGround(source['root'],peers)
            peers[0].stop(kill=True)
            try:ground.read(2)
            except Exception as exc:reason=str(exc)
            else:raise AssertionError('one failed and one dissenting host should not resolve')
            assert 2 not in ground.observed
            peers[0].start()
            assert ground.read(2)==actual[2]
            return {'unknown_on_divergence':True,'resolved_after_new_http_host':True,
                    'signed_receipts':len(ground.events),'source_trust_status':'provisional'}
        finally:
            for p in peers:p.stop(kill=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'results');p.add_argument('--mode',choices=('demo','verify'),default='demo');a=p.parse_args()
    if a.mode=='verify':
        trust=json.loads((a.output/'trust.json').read_bytes());doc=json.loads((a.output/'bundle.json').read_bytes())
        x=recover_paths(doc,trust)
        print(json.dumps({'verified_signatures':x['signed_receipt_count'],'http':x['http_reads'],
                          'stdio':x['stdio_reads'],'source_calls':0,'status':'witnesses-only-not-ground-admitted'}));return
    result=demo(a.output);result['disagreement']=disagreement_case()
    (a.output/'audit.json').write_bytes(canonical(result))
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
