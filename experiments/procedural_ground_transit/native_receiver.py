"""PGT-005 independent receiver: learned query proposal, exact IOS-001,
native IOS-003 mTLS measurement, conditional Ground and independent direct witness.
"""
from __future__ import annotations
import argparse,hashlib,json,ssl,time,secrets
from pathlib import Path
from cognitive_grounds import canonical
from decision_experiment import H,ALL,Context,indices,split,terminal
from train_policy import restore,propose
from native_contract import (authority_for,subject_for,probe_contract,exact_target_status)
from mailcpu.intention_measurement_fabric import MeasurementPeerClient
from mailcpu.temporal import SchedulerReading


def observe_once(client,coordinate,source_root,nonce=None):
    from mailcpu.intention_sufficiency import verify_sufficiency_resolution
    from mailcpu.intention_observer_bridge import verify_observer_resolution
    model,offers,plan,contracts=probe_contract(coordinate,source_root)
    authority=authority_for(source_root);subject=subject_for(source_root)
    challenge=hashlib.sha256((nonce or secrets.token_hex(32)).encode()).hexdigest()
    scheduler=SchedulerReading('pgt005-read-coordinates',int(time.time_ns() % 1_000_000_000))
    begun=time.monotonic_ns()
    report,receipts=client.resolve(model,0,offers,authority,plan,contracts,subject,scheduler,challenge)
    native_elapsed=time.monotonic_ns()-begun
    # Receiver rechecks the entire native contract and exact result.
    fid='q'+str(coordinate)
    projection=receipts[fid].projection
    verify_observer_resolution(report,model,0,offers,authority,plan,
        contracts,subject,scheduler,challenge,receipts,
        receiver_verify=lambda request,contract,receipt: (
          receipt.digest == receipts[request['feature_id']].digest and
          receipt.contract_digest == contract.digest))
    if report['resolution']['result']!=projection or type(projection) is not int or projection not in (0,1):
        raise ValueError('native receipt and resolved projection differ')
    return int(projection),{'coordinate':coordinate,'value':int(projection),
                           'native_receipt':receipts[fid].to_dict(),
                           'native_report_digest':report['bridge_digest'],
                           'plan_digest':plan['plan_digest'],
                           'request_count':len(report['measurement_receipts']),
                           'native_mtls_exchange_elapsed_ns':native_elapsed,
                           'native_receipt_payload_bytes':len(canonical(receipts[fid].to_dict()))}


def run(root:Path,port:int,target:int,source_root:str,mode:str='normal')->dict:
    model,manifest=restore(Path(__import__('train_policy').__file__).resolve().parent/'results')
    import numpy as np
    rng=np.random.default_rng(9)
    rng.integers(len(H))
    ctx=__import__('decision_experiment').context(rng)
    # The target is selected by the supervisor, not inferred from the fixture.
    ctx=Context(target,ctx.costs,ctx.weights)
    tls=ssl.create_default_context(ssl.Purpose.SERVER_AUTH,cafile=str(root/'tls/ca.pem'))
    tls.minimum_version=ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(str(root/'tls/receiver.pem'),str(root/'tls/receiver.key'))
    client=MeasurementPeerClient.connect_mutual_tls('127.0.0.1',port,tls,
        'receiver-a','provider-b','provider-b.fabric.test',timeout=5.0)
    observed={};trace=[];attempts=[];mask=ALL;used=0
    try:
        for _ in range(6):
            if mask and terminal(ctx,mask):break
            q=propose(model,ctx,mask,used) if mask else None
            if q is None:break
            try:
                value,receipt=observe_once(client,q,source_root)
            except Exception as exc:
                attempts.append({'coordinate':q,'outcome':'REFUSED','reason':str(exc)[:240]})
                # A failed measurement has not narrowed the Ground. Retry a
                # fresh challenge once (e.g., after source process recovery).
                if mode!='fail-then-recover':break
                try:value,receipt=observe_once(client,q,source_root)
                except Exception as again:
                    attempts.append({'coordinate':q,'outcome':'REFUSED_AGAIN','reason':str(again)[:240]})
                    break
            observed[q]=value;trace.append(receipt);used|=1<<q
            mask=split(mask,q)[value] if mask else 0
            if mask==0:break
        conditional=exact_target_status(target,observed,source_root)
        # Uncertified finite candidate membership cannot authorize publishing
        # a hidden result. Read the exact intended coordinate through the
        # same native mTLS path even if the model believes it is determined.
        if target not in observed:
            try:
                value,receipt=observe_once(client,target,source_root)
                observed[target]=value;trace.append(receipt)
            except Exception as exc:
                attempts.append({'coordinate':target,'outcome':'DIRECT_REFUSED','reason':str(exc)[:240]})
        witnessed=target in observed
        final={'schema':'ifs.pgt005.receiver.v1','intention_coordinate':target,
               'pinned_source_root':source_root,
               'candidate_before_direct':conditional['candidate'],
               'conditional_status':conditional['status'],
               'terminal_status':'WITNESSED_NOT_GROUND_ADMITTED' if witnessed else 'UNKNOWN',
               'result':observed.get(target),'readings':{str(q):v for q,v in observed.items()},
               'native_receipts':trace,'refusals':attempts,
               'neural_model_sha256':manifest['weights_sha256'],
               'language_source_proven':False,
               'native_receiver_tls':True,
               'native_receiver_host_authority':'installed-allowlist-test-hook-not-production-hypervisor',
               'source_qualified_agreement_not_truth':True}
        (root/'receiver-report.json').write_bytes(canonical(final))
        return final
    finally:client.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--port',type=int,required=True);p.add_argument('--target',type=int,default=6)
    p.add_argument('--source-root',required=True)
    p.add_argument('--mode',choices=('normal','fail-then-recover'),default='normal')
    a=p.parse_args();print(json.dumps(run(a.root,a.port,a.target,a.source_root,a.mode)))
