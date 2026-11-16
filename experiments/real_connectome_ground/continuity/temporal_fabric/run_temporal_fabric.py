"""RCG-004: measured multi-observer E-CPU mTLS placement and host-loss test.

Authenticated TLS is real, on loopback among separate Python processes.
Queue delays are artificial, advertised and measured, not inferred network
properties. No Hypervisor, quorum or independent physical trust is claimed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import ssl
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve()
if str(ROOT.parents[2]) not in sys.path:
    sys.path.insert(0,str(ROOT.parents[2]))

from connectome_ground import ConnectomeGround
from experiments.real_connectome_ground.continuity.temporal_fabric.temporal_ground import (
    SparseTransfer,TemporalGroundRefused,verify_preparation,navigate_verified,hash_object,
)
from experiments.real_connectome_ground.continuity.temporal_fabric.temporal_transport import (
    SCHEMA,send_once,worker_name,
)
from experiments.tensor_cut_realization.run_transit_local import certificates


class OnlineHostPolicy:
    """Fixed-size per-host EWMA trained only from actual sender clock spans."""
    def __init__(self,count:int):
        self.mean_ns={}
        self.samples={i:0 for i in range(count)}
        self.steps=0

    def choose(self,available:list[int])->int:
        if not available:
            raise TemporalGroundRefused('no authenticated host is eligible')
        self.steps+=1
        never=[i for i in available if self.samples[i]==0]
        if never:
            return min(never)
        if self.steps%7==0:
            return min(available,key=lambda i:(self.samples[i],i))
        return min(available,key=lambda i:(self.mean_ns[i],i))

    def observe(self,index:int,duration_ns:int)->None:
        if type(duration_ns) is not int or duration_ns<=0 or index not in self.samples:
            raise TemporalGroundRefused('invalid actual sender timing')
        count=self.samples[index]
        self.samples[index]=count+1
        self.mean_ns[index]=(duration_ns if count==0 else
                             .75*self.mean_ns[index]+.25*duration_ns)


def cert_sha256(file:Path)->str:
    return hashlib.sha256(
        ssl.PEM_cert_to_DER_cert(file.read_text())).hexdigest()


def start_worker(index:int,root:Path,source:Path,source_sha:str,certs,
                 *,sessions:int,source_node:str,target_node:str,delay_ms:int):
    name=worker_name(index)
    cert,key=certs[name]
    command=[
        sys.executable,'-m',
        'experiments.real_connectome_ground.continuity.temporal_fabric.temporal_transport',
        'serve','--source-file',str(source),'--source-sha256',source_sha,
        '--from-node',source_node,'--to-node',target_node,'--index',str(index),
        '--sessions',str(sessions),'--delay-ms',str(delay_ms),
        '--ca',str(root/'tls/ca.crt'),'--cert',str(cert),'--key',str(key),
    ]
    proc=subprocess.Popen(
        command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    ready,_,_=select.select([proc.stdout],[],[],25)
    if not ready:
        proc.kill()
        out,err=proc.communicate(timeout=5)
        raise TemporalGroundRefused('receiver startup failed '+err[-2000:]+out[-1000:])
    first=proc.stdout.readline()
    try:
        info=json.loads(first)
    except (ValueError,TypeError) as exc:
        proc.kill()
        out,err=proc.communicate(timeout=5)
        raise TemporalGroundRefused('receiver readiness malformed '+err[-1000:]) from exc
    if info.get('pid')!=proc.pid or info.get('worker')!=name or \
            type(info.get('port')) is not int or not 0<info['port']<65536:
        proc.kill()
        proc.communicate(timeout=5)
        raise TemporalGroundRefused('receiver readiness identity mismatch')
    return proc,info['port']


def run(source:Path,*,requests:int=24,workers:int=3,
        source_node:str='ASHL',target_node:str='AVAL',
        seed_tick:int=2**56+73)->dict:
    if not 2<=workers<=4 or not 8<=requests<=512:
        raise TemporalGroundRefused('host or request count outside declared limits')
    original=source.read_bytes()
    ground=ConnectomeGround.from_csv(original,require_original=True)
    operator=SparseTransfer.from_ground(ground,source_node,target_node)
    source_sha=hashlib.sha256(original).hexdigest()
    with tempfile.TemporaryDirectory(prefix='rcg004-mtls-') as temporary:
        root=Path(temporary)
        certs=certificates(root/'tls',workers)
        processes={}
        ports={}
        alive=set()
        records=[]
        checked={}
        policy=OnlineHostPolicy(workers)
        try:
            for index in range(workers):
                artificial_delay=[160,0,70,100][index]
                proc,port=start_worker(
                    index,root,source,source_sha,certs,sessions=requests+4,
                    source_node=source_node,target_node=target_node,
                    delay_ms=artificial_delay)
                processes[index]=proc
                ports[index]=port
                alive.add(index)
            for step in range(requests):
                # Real abrupt process loss; original source remains on disk.
                if step==requests//2:
                    failed=1
                    processes[failed].kill()
                    processes[failed].wait(timeout=6)
                    alive.discard(failed)
                chosen=policy.choose(sorted(alive))
                tick=seed_tick+101*step
                if tick>(1<<63)-1:
                    raise TemporalGroundRefused('logical clock exceeds contract')
                request={
                    'schema':SCHEMA+'.request.v1',
                    'request_id':f'rcg004-{step:04d}',
                    'ground':ground.fingerprint,
                    'source':source_node,
                    'target':target_node,
                    'kind':'chemical',
                    'tick':tick,
                }
                origin_cert,origin_key=certs[worker_name(0)]
                answer,telemetry=send_once(
                    '127.0.0.1',ports[chosen],chosen,request,
                    root/'tls/ca.crt',origin_cert,origin_key)
                if answer.get('schema')!=SCHEMA+'.response.v1' or \
                        answer.get('request_id')!=request['request_id'] or \
                        answer.get('intention_digest')!=hash_object(request) or \
                        answer.get('ground')!=ground.fingerprint or \
                        answer.get('source_sha256')!=source_sha or \
                        answer.get('receiver_pid')!=processes[chosen].pid or \
                        answer.get('digest')!=hash_object({
                            k:v for k,v in answer.items() if k!='digest'
                        }):
                    raise TemporalGroundRefused('sender refused unbound temporal result')
                receiver_cert=certs[worker_name(chosen)][0]
                if telemetry['peer_certificate_sha256']!=cert_sha256(receiver_cert):
                    raise TemporalGroundRefused('TLS peer differs from pinned host')
                receipt=answer['certificate']
                if receipt['digest'] != hash_object(
                        {a:b for a,b in receipt.items() if a!='digest'}):
                    raise TemporalGroundRefused('altered source certificate body')
                if receipt['digest'] not in checked:
                    verify_preparation(operator,receipt)
                    checked[receipt['digest']]=json.dumps(receipt,sort_keys=True)
                elif json.dumps(receipt,sort_keys=True)!=checked[receipt['digest']]:
                    raise TemporalGroundRefused('cached certificate identity collision')
                expected=navigate_verified(receipt,tick)
                if answer['result']!=expected:
                    raise TemporalGroundRefused('independent distant-time result differs')
                policy.observe(chosen,telemetry['sender_total_ns'])
                records.append({
                    'host':chosen,'tick':tick,
                    'value_mod_p':expected['value_mod_p'],
                    'sender_total_ns':telemetry['sender_total_ns'],
                    'sender_tls_connect_ns':telemetry['sender_tls_connect_ns'],
                    'sender_request_roundtrip_ns':telemetry['sender_request_roundtrip_ns'],
                    'receiver_compute_ns_local':answer['receiver_compute_ns_local'],
                    'application_request_bytes':telemetry['application_request_bytes'],
                    'application_response_bytes':telemetry['application_response_bytes'],
                    'tls_version':telemetry['tls_version'],
                    'certificate_digest':receipt['digest'],
                    'receiver_pid':answer['receiver_pid'],
                })
            latencies=[r['sender_total_ns'] for r in records]
            report={
                'schema':SCHEMA+'.study.v1',
                'source_blob':ground.source_blob,
                'ground':ground.fingerprint,
                'field':operator.field,
                'source':source_node,'target':target_node,
                'node_count':operator.n,
                'edge_count':operator.sparse_edge_count,
                'requests':requests,
                'worker_count':workers,
                'real_authenticated_loopback':True,
                'replaceable_processes':True,
                'different_physical_hosts':False,
                'real_tls_protocol':sorted(set(r['tls_version'] for r in records)),
                'synthetic_queue_delay_ms':[160,0,70,100][:workers],
                'failed_worker':1,
                'failed_worker_not_selected_after_death':all(
                    r['host']!=1 for r in records[requests//2:]),
                'verified_query_count':len(records),
                'unique_verified_certificate_count':len(checked),
                'host_selection_counts':{
                    str(i):sum(r['host']==i for r in records)
                    for i in range(workers)},
                'measured_sender_p50_ns':int(statistics.median(latencies)),
                'measured_sender_max_ns':max(latencies),
                'measured_sender_min_ns':min(latencies),
                'measured_sender_total_ns':sum(latencies),
                'total_wire_application_bytes':sum(
                    r['application_request_bytes']+
                    r['application_response_bytes'] for r in records),
                'records':records,
                'scope':'actual mTLS loopback with synthetic service queues; no physical multi-host, Hypervisor or quorum claim',
            }
            return {**report,'digest':hash_object(report)}
        finally:
            for proc in processes.values():
                if proc.poll() is None:
                    proc.kill()
            for proc in processes.values():
                try:
                    proc.communicate(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate(timeout=3)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument(
        '--source',type=Path,
        default=ROOT.parents[2]/'data'/'herm_full_edgelist.csv')
    parser.add_argument('--requests',type=int,default=24)
    parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    result=run(args.source,requests=args.requests,workers=args.workers)
    text=json.dumps(result,sort_keys=True,indent=2)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(text)
    else:
        print(text)


if __name__=='__main__':
    main()
