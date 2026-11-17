"""PGT-005 native IOS-003 process: mTLS provider backed by signed HTTP/stdio.

Observer workers are separate child processes. This provider has installed
read-only callbacks, an explicit local (test) policy and a SQLite ledger.
There is no claim that its local policy hook is a production Hypervisor grant.
"""
from __future__ import annotations
import argparse,json,signal,sys,time
from pathlib import Path
from cognitive_grounds import canonical,GroundRefused
import hashlib
from decision_experiment import H
from run_path_navigation import http_peer, save_bundle
from run_experiment import make_worker
from path_navigator import StdioPeer
from path_navigator import MixedPathGround
from native_contract import authority_for,model_at,contract_at
from mailcpu.intention_measurement_fabric import (HostedMeasurement,
    MeasurementPeerServer,MeasurementReceiptLedger)
from mailcpu.socket_transport import SocketTransport
import ssl


def server(root:Path,private_index:int,source_salt:str,fault_coordinate:int|None=None, source_bits:str|None=None)->None:
    if type(private_index) is not int or not 0<=private_index<len(H):
        raise ValueError('bad synthetic fixture index')
    root.mkdir(parents=True,exist_ok=True)
    private=root/'private';private.mkdir(exist_ok=True)
    if source_bits is not None and (len(source_bits)!=8 or set(source_bits)-{'0','1'}):
        raise ValueError('source override must be eight binary observations')
    actual=([int(x) for x in source_bits] if source_bits is not None else H[private_index].tolist())
    if len(source_salt)!=64 or any(c not in '0123456789abcdef' for c in source_salt):
        raise ValueError('supervisor source salt must be high-entropy canonical hex')
    source={'schema':'ifs.pgt003.query.source.v1','outputs':list(map(int,actual)),
            'salt':source_salt}
    source['root']=hashlib.sha256(canonical(source)).hexdigest()
    src=private/'private.json';src.write_bytes(canonical(source));src.chmod(0o600)
    alpha=http_peer(private,'alpha',src,price=lambda q:2+(q%4))
    beta=StdioPeer(make_worker(private,'beta',src,flip=fault_coordinate if fault_coordinate is not None else -1),price=lambda q:4+(q//4))
    gamma=http_peer(private,'gamma',src,price=lambda q:2+(q%3))
    peers=(alpha,beta,gamma)
    for p in peers:p.start()
    ground=MixedPathGround(source['root'],peers)
    authority=authority_for(source['root'])
    stats={'native_reader_calls':0,'native_policy_calls':0,'native_policy_refusals':0,
           'injected_dissent':0,'restarted_observers':0}
    fault_done=False

    def policy(req,peer):
        stats['native_policy_calls']+=1
        allowed=(peer=='receiver-a' and req['feature_id'] in tuple('q'+str(x) for x in range(8))
                 and req['authority_digest']==authority)
        if not allowed:stats['native_policy_refusals']+=1
        return allowed

    def reading(q):
        def read(request):
            nonlocal fault_done
            stats['native_reader_calls']+=1
            # Simulate a crashed HTTP endpoint plus a contradictory signed
            # stdio observer. The native provider must refuse this attempt.
            if fault_coordinate == q and not fault_done:
                fault_done=True
                peers[0].stop(kill=True)
                try:
                    return ground.read(q)
                finally:
                    peers[0].start()
                    stats['injected_dissent']+=1
                    stats['restarted_observers']+=1
            return ground.read(q)
        return read

    installed={f'q{q}':HostedMeasurement(
        contract_at(q,source['root']),model_at(q,source['root']).digest,lambda:authority,policy,reading(q),(0,1))
        for q in range(8)}
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(root/'tls/provider.pem'),str(root/'tls/provider.key'))
    ctx.load_verify_locations(cafile=str(root/'tls/ca.pem'))
    ctx.verify_mode=ssl.CERT_REQUIRED
    listener=SocketTransport.listen('127.0.0.1',0)
    listener.settimeout(12)
    ledger=MeasurementReceiptLedger(root/'completion.sqlite')
    running=True
    def terminate(*_):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,terminate)
    report={'source_root':source['root'],'server_pid':__import__('os').getpid()}
    print('READY '+json.dumps({'port':listener.getsockname()[1],**report}),flush=True)
    service=None
    try:
        service=MeasurementPeerServer.accept_mutual_tls(
            listener,ctx,'provider-b','receiver-a','receiver-a.fabric.test',installed,ledger)
        while running and not service.transport.closed:
            service.service_once()
            time.sleep(.002)
    finally:
        if service is not None:service.close()
        listener.close()
        bundle,trust=save_bundle(ground,root/'evidence')
        status={**report,**stats,
                'http_observer_response_bytes':sum(x['body_bytes'] for x in ground.transport_log if x['transport']=='http-observer'),
                'http_observer_response_elapsed_ns':sum(x['elapsed_ns'] for x in ground.transport_log if x['transport']=='http-observer'),
                'signed_receipts':len(ground.events),
                'signed_http_reads':sum(x['transport']=='http-observer' for x in ground.transport_log),
                'signed_stdio_reads':sum(x['transport']=='signed-stdio' for x in ground.transport_log),
                'ground_admitted':False}
        (root/'provider-report.json').write_bytes(canonical(status))
        ledger.close()
        for p in peers:p.stop(kill=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--index',type=int,required=True);p.add_argument('--fault-coordinate',type=int)
    p.add_argument('--source-bits');p.add_argument('--salt',required=True)
    a=p.parse_args();server(a.root,a.index,a.salt,a.fault_coordinate,a.source_bits)
