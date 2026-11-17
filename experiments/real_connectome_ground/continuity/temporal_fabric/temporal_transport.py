"""RCG-004 observer-host transport using existing E-CPU mTLS and ReliableChannel.

A tested mathematical Ground travels as a source-bound intention.  The actual
receiver owns the original source bytes and the observation method. Peer SAN
identity is authenticated by E-CPU. Hypervisor/M3 authority is NOT simulated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve()
if str(HERE.parents[2]) not in sys.path:
    sys.path.insert(0, str(HERE.parents[2]))

from connectome_ground import ConnectomeGround, canonical
from experiments.real_connectome_ground.continuity.temporal_fabric.temporal_ground import (
    SparseTransfer, TemporalGroundRefused, prepare, verify_preparation,
    navigate_verified, hash_object, MAX_TICK,
)
from experiments.tensor_cut_realization.transit_tensor import ssl_context
from mailcpu import ReliabilityPolicy, ReliableChannel
from mailcpu.mtls_transport import accept_mutual_tls, connect_mutual_tls
from mailcpu.socket_transport import SocketTransport

SCHEMA = 'ifs.rcg004.temporal-transit.v1'
ORIGIN = 'tcr002-origin'
CHANNEL = SCHEMA + '.demand'
RETURN = SCHEMA + '.return'
MAX_WIRE = 1 << 20
DEADLINE = 20.0


def worker_name(i: int) -> str:
    if type(i) is not int or not 0 <= i <= 7:
        raise TemporalGroundRefused('unknown worker identity')
    return f'tcr002-worker-{i}'


def channels(transport, *, index: int, serving: bool):
    local = worker_name(index) if serving else ORIGIN
    peer = ORIGIN if serving else worker_name(index)
    policy = ReliabilityPolicy(lease_ticks=4, max_attempts=7, window_size=2)
    tx = ReliableChannel(transport, source=local, destination=peer, peer=peer,
                         channel=RETURN if serving else CHANNEL, policy=policy)
    rx = ReliableChannel(transport, source=local, destination=local, peer=peer,
                         channel=CHANNEL if serving else RETURN, policy=policy)
    return tx, rx


def poll_ack(tx, sequence: int, deadline: float):
    last = time.monotonic()
    while time.monotonic() < deadline:
        tx.process_ack()
        if sequence not in tx.pending_sequences():
            return
        if time.monotonic()-last > .1:
            if sequence in tx.tick():
                raise TemporalGroundRefused('ReliableChannel retransmission exhausted')
            last = time.monotonic()
        time.sleep(.005)
    raise TemporalGroundRefused('ReliableChannel ack deadline')


class TemporalHost:
    """Receiver-owned Ground, policy and application-level replay fence."""
    def __init__(self, raw: bytes, *, allowed_source: str, allowed_target: str,
                 source_sha256: str, require_original: bool = True,
                 native_ecpu: bool = True, queue_delay_ms: int = 0):
        if hashlib.sha256(raw).hexdigest() != source_sha256:
            raise TemporalGroundRefused('receiver source bytes do not match pin')
        self.ground = ConnectomeGround.from_csv(raw, require_original=require_original)
        self._source_sha256 = source_sha256
        self.native_ecpu = native_ecpu
        if type(queue_delay_ms) is not int or not 0 <= queue_delay_ms <= 250:
            raise TemporalGroundRefused('receiver queue-delay fixture outside bounds')
        self.queue_delay_ms = queue_delay_ms
        self.allowed_source = allowed_source
        self.allowed_target = allowed_target
        self.prepared = {}
        self.replayed = {}
        self.executions = 0

    def handle(self, request: object) -> dict:
        if type(request) is not dict or set(request) != {
            'schema', 'request_id', 'ground', 'source', 'target', 'kind', 'tick'
        } or request.get('schema') != SCHEMA+'.request.v1' or \
                request.get('ground') != self.ground.fingerprint or \
                request.get('source') != self.allowed_source or \
                request.get('target') != self.allowed_target or \
                request.get('kind') not in ('chemical', 'electrical') or \
                type(request.get('tick')) is not int or not 0 <= request['tick'] <= MAX_TICK or \
                type(request.get('request_id')) is not str or not 1 <= len(request['request_id']) <= 100:
            raise TemporalGroundRefused('receiver policy refuses query or changed Ground')
        request_id = request['request_id']
        intent = hash_object(request)
        if request_id in self.replayed:
            original_intent, response = self.replayed[request_id]
            if original_intent != intent:
                raise TemporalGroundRefused('application idempotency key reused with changed intention')
            replayed = {**response, 'replayed': True}
            return {**replayed, 'digest': hash_object(
                {k:v for k,v in replayed.items() if k!='digest'})}
        key = request['kind']
        before = time.perf_counter_ns()
        if self.queue_delay_ms:
            time.sleep(self.queue_delay_ms/1000)
        if key not in self.prepared:
            operator = SparseTransfer.from_ground(
                self.ground,request['source'],request['target'],kind=key)
            cert = prepare(operator,native_ecpu=self.native_ecpu)
            verify_preparation(operator,cert)
            self.prepared[key] = cert
        cert = self.prepared[key]
        result = navigate_verified(cert,request['tick'])
        cost = time.perf_counter_ns()-before
        self.executions += 1
        body = {
            'schema': SCHEMA+'.response.v1', 'request_id':request_id,
            'ground':self.ground.fingerprint, 'source_sha256':self._source_sha256,
            'intention_digest':intent, 'certificate':cert,'result':result,
            'receiver_compute_ns_local':cost,'receiver_pid':os.getpid(),
            'receiver_execution_count':self.executions,'replayed':False,
        }
        response = {**body,'digest':hash_object(body)}
        self.replayed[request_id] = (intent,response)
        return response


def send_once(host: str, port: int, index: int, request: dict,
              ca: Path, cert: Path, key: Path) -> tuple[dict, dict]:
    started = time.perf_counter_ns()
    tls = connect_mutual_tls(
        host,port,ORIGIN,worker_name(index),
        ssl_context(ca,cert,key,server=False),
        server_hostname=worker_name(index),timeout=8,max_frame_size=MAX_WIRE)
    connected = time.perf_counter_ns()
    try:
        tx,rx = channels(tls,index=index,serving=False)
        sequence = tx.send(request)
        deadline = time.monotonic()+DEADLINE
        received = None
        last = time.monotonic()
        while time.monotonic()<deadline:
            tx.process_ack()
            if sequence not in tx.pending_sequences():
                received = rx.receive()
                if received is not None: break
            if time.monotonic()-last>.1:
                if sequence in tx.tick():
                    raise TemporalGroundRefused('request retry exhausted')
                last = time.monotonic()
            time.sleep(.005)
        if received is None:
            raise TemporalGroundRefused('authenticated receiver did not return result')
        payload = received[1]
        if type(payload) is not dict or payload.get('request_id')!=request['request_id']:
            raise TemporalGroundRefused('receiver returned unbound request')
        finished = time.perf_counter_ns()
        time.sleep(.06)
        return payload, {
            'sender_tls_connect_ns':connected-started,
            'sender_request_roundtrip_ns':finished-connected,
            'sender_total_ns':finished-started,
            'tls_version':tls.socket.version(),
            'peer_certificate_sha256':hashlib.sha256(
                tls.socket.getpeercert(binary_form=True)).hexdigest(),
            'application_request_bytes':len(canonical(request)),
            'application_response_bytes':len(canonical(payload)),
        }
    finally:
        tls.close()


def serve_one(listener, worker: TemporalHost, index: int,
              ca: Path,cert:Path,key:Path) -> dict:
    tls = accept_mutual_tls(
        listener,worker_name(index),ORIGIN,
        ssl_context(ca,cert,key,server=True),expected_peer_dns=ORIGIN,
        max_frame_size=MAX_WIRE)
    try:
        tx,rx = channels(tls,index=index,serving=True)
        deadline = time.monotonic()+DEADLINE
        recorded = {}
        while time.monotonic()<deadline:
            def apply(seq,payload):
                try:
                    recorded['value'] = worker.handle(payload)
                except (TemporalGroundRefused,ValueError,TypeError,KeyError) as exc:
                    recorded['value'] = {
                        'schema':SCHEMA+'.refused.v1',
                        'reason':str(exc),
                        'request_id':payload.get('request_id') if type(payload) is dict else None}
            received = rx.receive(commit=apply)
            if received is not None: break
            time.sleep(.005)
        if 'value' not in recorded:
            raise TemporalGroundRefused('no authenticated request received')
        sequence = tx.send(recorded['value'])
        poll_ack(tx,sequence,deadline)
        return {'accepted':recorded['value'].get('schema')==SCHEMA+'.response.v1',
                'receiver_execution_count':worker.executions,
                'tls_version':tls.socket.version()}
    finally: tls.close()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action',required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--source-file',type=Path,required=True)
    serve.add_argument('--source-sha256',required=True)
    serve.add_argument('--from-node',required=True)
    serve.add_argument('--to-node',required=True)
    serve.add_argument('--index',type=int,required=True)
    serve.add_argument('--sessions',type=int,default=64)
    serve.add_argument('--delay-ms',type=int,default=0)
    for item in ('ca','cert','key'):
        serve.add_argument('--'+item,type=Path,required=True)
    args = parser.parse_args()
    if args.action=='serve':
        if not 1 <= args.sessions <= 1024:
            raise TemporalGroundRefused('session cap refused')
        worker = TemporalHost(
            args.source_file.read_bytes(),allowed_source=args.from_node,
            allowed_target=args.to_node,source_sha256=args.source_sha256,
            queue_delay_ms=args.delay_ms)
        listener = SocketTransport.listen('127.0.0.1',0)
        try:
            print(json.dumps({'port':listener.getsockname()[1],
                              'pid':os.getpid(),
                              'worker':worker_name(args.index)}),flush=True)
            for _ in range(args.sessions):
                result = serve_one(listener,worker,args.index,args.ca,args.cert,args.key)
                print(json.dumps(result,sort_keys=True),flush=True)
        finally:
            listener.close()


if __name__=='__main__':
    main()
