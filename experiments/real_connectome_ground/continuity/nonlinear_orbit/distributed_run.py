"""RCG-005: compose independently verified nonlinear latent coordinates over
RCG-004's *existing* E-CPU mTLS/ReliableChannel observer-host workers.

A protocol adapter, not an alternative network stack. Each worker admits the
original source and one target coordinate; the coordinator also verifies the
shared vector certificate and independently reconstructs the nonlinear answer.
One worker is hard-killed and its logical readout is rehomed. No M3 recovery,
Hypervisor grant, multi-machine deployment or actual biological behavior claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
from typing import Any

from connectome_ground import ConnectomeGround, canonical
from temporal_ground import SparseTransfer, TemporalGroundRefused, hash_object, \
    verify_preparation, navigate_verified
from conjugate_ground import ConjugatedGround, prepare_shared, verify_shared, navigate

SCHEMA='ifs.rcg005.nonlin-multi-host.v1'


def verify_reply(*, source:ConnectomeGround, model:ConjugatedGround, original_sha:str,
                 request:dict,response:dict,telemetry:dict,
                 receiver_pid:int,peer_sha:str,checked:dict[str,str]) -> int:
    """Original source is an explicit receiver-owned argument, not a monkeypatch."""
    if not isinstance(source,ConnectomeGround) or source.fingerprint!=model.operator.ground:
        raise TemporalGroundRefused('sender original source Ground mismatched')
    if request.get('schema')!='ifs.rcg004.temporal-transit.v1.request.v1' or \
            request.get('ground')!=source.fingerprint or \
            request.get('source')!=model.operator.source or \
            request.get('target') not in model.coordinates or \
            request.get('kind')!=model.operator.kind or \
            type(request.get('tick')) is not int:
        raise TemporalGroundRefused('request is outside the nonlinear/source observation contract')
    if type(response) is not dict or response.get('schema')!='ifs.rcg004.temporal-transit.v1.response.v1' or \
            response.get('request_id')!=request.get('request_id') or \
            response.get('ground')!=source.fingerprint or \
            response.get('source_sha256')!=original_sha or \
            response.get('intention_digest')!=hash_object(request) or \
            response.get('receiver_pid')!=receiver_pid or \
            response.get('digest')!=hash_object({k:v for k,v in response.items() if k!='digest'}):
        raise TemporalGroundRefused('receiver identity, source pin or request identity mismatch')
    if type(telemetry) is not dict or telemetry.get('peer_certificate_sha256')!=peer_sha or \
            telemetry.get('tls_version') not in ('TLSv1.2','TLSv1.3') or \
            type(telemetry.get('sender_total_ns')) is not int or telemetry['sender_total_ns']<=0:
        raise TemporalGroundRefused('authenticated transport evidence rejected')
    certificate=response.get('certificate')
    if type(certificate) is not dict or type(certificate.get('digest')) is not str:
        raise TemporalGroundRefused('missing independent receiver recurrence proof')
    digest=certificate['digest']
    if digest not in checked:
        op=SparseTransfer.from_ground(source,request['source'],request['target'],kind=request['kind'])
        verify_preparation(op,certificate)
        checked[digest]=json.dumps(certificate,sort_keys=True)
    elif json.dumps(certificate,sort_keys=True)!=checked[digest]:
        raise TemporalGroundRefused('certificate reused after alteration')
    expected=navigate_verified(certificate,request['tick'])
    if response.get('result')!=expected or type(response.get('receiver_compute_ns_local')) is not int or \
            response['receiver_compute_ns_local']<0 or response.get('replayed') is not False:
        raise TemporalGroundRefused('receiver arithmetic or execution receipt disagrees')
    return expected['value_mod_p']


def run(source_file:Path, *, requests:int=6, coordinates:tuple[str,...]=('ASHL','AVAL','AVBL'),
        seed:str='rcg005-procedural-neural-v1',tick:int=2**56+73)->dict[str,Any]:
    if type(requests) is not int or not 4<=requests<=24 or len(coordinates)!=3:
        raise TemporalGroundRefused('native study must use 3 readouts and 4..24 observations')
    # Native E-CPU and original TCR-002 mTLS SAN certificate generation are
    # deliberately imported only inside this real-network study.
    from experiments.real_connectome_ground.continuity.temporal_fabric.temporal_transport import (
        SCHEMA as TRANSIT_SCHEMA, send_once, worker_name,
    )
    from experiments.real_connectome_ground.continuity.temporal_fabric.run_temporal_fabric import (
        certificates,cert_sha256,start_worker,OnlineHostPolicy,
    )
    import tempfile
    original=source_file.read_bytes()
    source_sha=hashlib.sha256(original).hexdigest()
    source=ConnectomeGround.from_csv(original,require_original=True)
    model=ConjugatedGround(SparseTransfer.from_ground(source,coordinates[0],coordinates[0]),
                           tuple(coordinates),seed)
    shared_certificate=prepare_shared(model)
    verify_shared(model,shared_certificate)
    with tempfile.TemporaryDirectory(prefix='rcg005-tls-') as tmp:
        root=Path(tmp)
        creds=certificates(root/'tls',4)
        # Worker 3 is a distinct authenticated standby for coordinate[1].
        targets={0:coordinates[0],1:coordinates[1],2:coordinates[2],3:coordinates[1]}
        processes={};ports={};alive=set()
        policy=OnlineHostPolicy(4)
        checked={};records=[];killed=None
        try:
            for i,target in targets.items():
                proc,port=start_worker(i,root,source_file,source_sha,creds,
                    sessions=requests+2,source_node=coordinates[0],target_node=target,
                    delay_ms=[30,65,15,5][i])
                processes[i]=proc;ports[i]=port;alive.add(i)
            for k in range(requests):
                if k==requests//2:
                    processes[1].kill()
                    processes[1].wait(timeout=8)
                    alive.remove(1)
                    killed=1
                wanted_tick=tick+97*k
                expected=navigate(model,shared_certificate,wanted_tick,trusted_certificate=True)
                answers={};seen=set();routes=[]
                for j,target in enumerate(coordinates):
                    candidate={0:[0],1:[1,3],2:[2]}[j]
                    options=sorted(i for i in candidate if i in alive)
                    chosen=policy.choose(options)
                    name=worker_name(chosen)
                    req={'schema':TRANSIT_SCHEMA+'.request.v1',
                        'request_id':f'rcg005-{k:03d}-{j:02d}',
                        'ground':source.fingerprint,'source':coordinates[0],
                        'target':target,'kind':'chemical','tick':wanted_tick}
                    sender_cert,sender_key=creds['tcr002-origin']
                    response,telemetry=send_once('127.0.0.1',ports[chosen],chosen,req,
                        root/'tls/ca.crt',sender_cert,sender_key)
                    actual=verify_reply(source=source,model=model,original_sha=source_sha,
                        request=req,response=response,telemetry=telemetry,
                        receiver_pid=processes[chosen].pid,
                        peer_sha=cert_sha256(creds[name][0]),checked=checked)
                    if actual!=expected['latent_readouts'][target]:
                        raise TemporalGroundRefused('separately hosted latent value disagrees with shared vector proof')
                    policy.observe(chosen,telemetry['sender_total_ns'])
                    answers[target]=actual;seen.add(chosen)
                    routes.append({'coordinate':target,'worker':chosen,'receiver_pid':response['receiver_pid'],
                        'latency_ns':telemetry['sender_total_ns'],
                        'compute_ns_local':response['receiver_compute_ns_local'],
                        'tls_version':telemetry['tls_version'],
                        'certificate_digest':response['certificate']['digest'],
                        'request_bytes':telemetry['application_request_bytes'],
                        'response_bytes':telemetry['application_response_bytes']})
                decoded=model.readout_decode(answers)
                if decoded!=expected['nonlinear_readout']:
                    raise TemporalGroundRefused('host-composed nonlinear observation disagrees with source Ground')
                records.append({'tick':wanted_tick,'nonlinear_readout':decoded,'host_receipts':routes,
                                'shared_certificate_digest':shared_certificate['digest'],
                                'reconstructed_after_hardkill':k>=requests//2})
            latencies=[r['latency_ns'] for event in records for r in event['host_receipts']]
            body={'schema':SCHEMA+'.report.v1','model_digest':model.fingerprint,
                  'ground':source.fingerprint,'source_sha256':source_sha,
                  'source_blob':source.source_blob,'field':model.operator.field,
                  'node_count':model.operator.n,'edge_count':model.operator.sparse_edge_count,
                  'nonlinear_depth':model.dimension-1,'requests':requests,'latent_coordinates':list(coordinates),
                  'worker_processes':4,'verified_host_observations':len(latencies),
                  'independently_verified_certificates':len(checked),
                  'shared_vector_certificate_digest':shared_certificate['digest'],
                  'lost_worker':killed,'replacement_worker':3,
                  'replacement_used_after_loss':all(
                        next(z for z in r['host_receipts'] if z['coordinate']==coordinates[1])['worker']==3
                        for r in records[requests//2:]),
                  'measured_sender_p50_ns':int(statistics.median(latencies)),
                  'measured_sender_min_ns':min(latencies),'measured_sender_max_ns':max(latencies),
                  'recorded_application_bytes':sum(z['request_bytes']+z['response_bytes']
                    for r in records for z in r['host_receipts']),
                  'transport':'actual-E-CPU-mutual-TLS-ReliableChannel-over-loopback',
                  'trust_scope':'one physical host; test CA; separate authenticated processes; no M3 persistence or Hypervisor authorization',
                  'queue_delay_fixture_ms':[30,65,15,5],
                  'records':records}
            return {**body,'digest':hash_object(body)}
        finally:
            for proc in processes.values():
                if proc.poll() is None:proc.kill()
            for proc in processes.values():
                try:proc.communicate(timeout=5)
                except Exception:
                    if proc.poll() is None:proc.kill()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[2]/'data'/'herm_full_edgelist.csv')
    parser.add_argument('--requests',type=int,default=6)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    report=run(args.source,requests=args.requests)
    value=json.dumps(report,indent=2,sort_keys=True)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(value)
    else:print(value)

if __name__=='__main__':main()
