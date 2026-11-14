"""GCI-004 actual E-CPU mutual-TLS socket and typed fabric-directory experiment.

Three observer processes share a loopback CI runner. Their locally generated
X.509 certificates authenticate TLS and sign separate exact request receipts.
The coordinator is not given the receiver phase artifact as a protocol input;
servers can read it under their experimental local authority.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

import fabric_contract as c
from mailcpu.model import Message
from mailcpu.mtls_transport import (accept_mutual_tls, connect_mutual_tls,
                                     MutualTLSTransportError)
from mailcpu.socket_transport import SocketTransport, _encode_frame
from mailcpu.computational_fabric import (ComputationalHostAdvertisement,
    ComputationalPeerEndpoint, ComputationalPeerSnapshot,
    ComputationalFabricDirectory)
from mailcpu.evidence_path_resolver import RouteMetric
from mailcpu.virtual_layer import OperatorSpec


class LiveObserverError(ValueError):
    pass


def check(condition: bool, why: str) -> None:
    if not condition:
        raise LiveObserverError(why)


def save_pem(path: Path, value: bytes) -> None:
    path.write_bytes(value)
    os.chmod(path, 0o600)


def write_identity_files(path: Path) -> dict[str, Any]:
    """Ephemeral in-run CA, three independent leaf keys, client leaf key."""
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'GCI004 ephemeral local test CA')])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-datetime.timedelta(minutes=5))
          .not_valid_after(now+datetime.timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
          .sign(ca_key,hashes.SHA256()))
    save_pem(path/'ca.pem', ca.public_bytes(serialization.Encoding.PEM))
    def issue(peer_id: str, dns: str, server: bool):
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,dns)])
        leaf = (x509.CertificateBuilder().subject_name(name).issuer_name(ca_name)
          .public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-datetime.timedelta(minutes=5))
          .not_valid_after(now+datetime.timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
          .add_extension(x509.SubjectAlternativeName([x509.DNSName(dns)]),critical=False)
          .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if server
                                                 else ExtendedKeyUsageOID.CLIENT_AUTH]),critical=False)
          .sign(ca_key,hashes.SHA256()))
        save_pem(path/f'{peer_id}.pem',leaf.public_bytes(serialization.Encoding.PEM))
        save_pem(path/f'{peer_id}.key',key.private_bytes(
            serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
    issue('coordinator',c.DNS_CLIENT,False)
    for peer,(_feature,dns) in c.PEERS.items():
        issue(peer,dns,True)
    return {'ca_pem':(path/'ca.pem').read_text(),
            'client_pem':(path/'coordinator.pem').read_text()}


def tls_client(cert_dir: Path) -> ssl.SSLContext:
    context=ssl.create_default_context(ssl.Purpose.SERVER_AUTH,
                                       cafile=str(cert_dir/'ca.pem'))
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert_dir/'coordinator.pem'),
                            str(cert_dir/'coordinator.key'))
    return context


def tls_server(peer: str, cert_dir: Path) -> ssl.SSLContext:
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.verify_mode=ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(cert_dir/'ca.pem'))
    context.load_cert_chain(str(cert_dir/f'{peer}.pem'),
                            str(cert_dir/f'{peer}.key'))
    return context


def frame_bytes(transport: SocketTransport, message: Message) -> int:
    return len(_encode_frame(message,transport.max_frame_size))


def send(transport: SocketTransport, endpoint: str, op: str,
         payload: Mapping[str, Any]) -> int:
    message=transport.send(endpoint,Message(sender=transport.local_endpoint,
                       recipient=endpoint,op=op,body=(dict(payload),)))
    return frame_bytes(transport,message)


def receive(transport: SocketTransport, expected: str,
            timeout: float=7.0) -> tuple[str, dict[str, Any], int] | None:
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        message=transport.poll(transport.local_endpoint)
        if message is not None:
            check(expected=='*' or message.op==expected or message.op=='REJECT',
                  'unexpected MailCPU transport message operator')
            check(len(message.body)==1 and isinstance(message.body[0],dict),
                  'received MailCPU body is not a one-object record')
            return message.op,message.body[0],frame_bytes(transport,message)
        if transport.closed:
            return None
        time.sleep(.005)
    raise LiveObserverError('authenticated MailCPU response timed out')


def advertisement(peer: str,feature: str,port: int,binding: Mapping[str,str]):
    endpoint=ComputationalPeerEndpoint(peer,c.PEERS[peer][1],'127.0.0.1',port)
    spec=OperatorSpec(operator_id=c.OPERATOR[feature],version=1,
       description='Bounded GCI004 receiver-controlled observation '+feature,
       input_kind='object',output_kind='object',substrates=('cpu',),
       required_rights=frozenset({'compute'}),deterministic=True,effect_mode='pure')
    host=ComputationalHostAdvertisement(host_id=peer+'-feature',node_id=peer+'-node',
       peer_id=peer,operator_spec=spec,substrates=('cpu',),
       computational_ground_fingerprints=(binding['ground_fingerprint'],),
       program_fingerprints=(),supports_ground_program_compilation=False,
       supports_structural_memory=False,implementation_fingerprint=None,
       costs=(RouteMetric('latency','ticks',1),),virtual_capacity=1,
       max_energy=100000,max_bytes=100000,max_virtual_ticks=100000)
    return ComputationalPeerSnapshot(endpoint,revision=1,lease_seconds=60,
                                     hosts=(host,),links=())


def server(peer: str, directory: Path, cert_dir: Path, ready_path: Path,
           *, diagnostic_false_reading: bool = False) -> None:
    feature, _dns=c.PEERS[peer]
    # Isolated adversarial test mode: an authenticated signer lies about a
    # parity reading. The ordinary GCI-004 host path never enables this.
    check(not diagnostic_false_reading or peer == 'observer-b',
          'only GCI-005 diagnostic observer-b may sign an altered reading')
    binding=c.gci3.certificate_binding(directory)
    public=c.cag.read(directory/'gci003-public.json')
    private=c.cag.read(directory/'gci003-private.json')
    plan=c.cag.read(directory/'gci003-plan.json')
    c.gci3.validate_plan(plan,public,binding)
    state=c.gci3.validate_private(private,public,binding)
    private_key=serialization.load_pem_private_key(
        (cert_dir/f'{peer}.key').read_bytes(),password=None)
    check(isinstance(private_key,ec.EllipticCurvePrivateKey),'server signing key must be EC')
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('127.0.0.1',0))
    listener.listen(5)
    listener.settimeout(10.0)
    snapshot=advertisement(peer,feature,listener.getsockname()[1],binding)
    ready_path.write_text(json.dumps({'port':snapshot.endpoint.port,'peer_id':peer}))
    seen_challenges=set()
    good_session=False
    try:
        for _attempt in range(4):
            try:
                t=accept_mutual_tls(listener,peer,'coordinator',tls_server(peer,cert_dir),
                      expected_peer_dns=c.DNS_CLIENT,handshake_timeout=6.0)
            except (MutualTLSTransportError,TimeoutError,OSError):
                continue
            try:
                while True:
                    received=receive(t,'*',timeout=9.0)
                    if received is None:
                        break
                    op,body,_received_size=received
                    if op=='REJECT':
                        raise LiveObserverError('peer client sent unexpected reject')
                    if op=='DISCOVER':
                        if body!={'schema':'gci004.discovery-request.v1',
                                  'ground_fingerprint':binding['ground_fingerprint']}:
                            send(t,'coordinator','REJECT',{'code':'invalid-discovery'})
                            continue
                        send(t,'coordinator','SNAPSHOT',snapshot.to_dict())
                        good_session=True
                    elif op=='OBSERVE':
                        case_id=body.get('task_id')
                        chosen=next((item for item in plan['cases']
                              if item['case_id']==case_id),None)
                        if chosen is None or feature not in chosen['selected'] or \
                                body.get('feature')!=feature or \
                                body.get('binding')!=binding or \
                                body.get('public_digest')!=public['report_digest'] or \
                                body.get('plan_digest')!=plan['report_digest'] or \
                                body.get('phase_commitment')!=public['phase_commitment'] or \
                                body.get('schema')!=c.REQUEST:
                            send(t,'coordinator','REJECT',{'code':'forbidden-feature-or-context'})
                            continue
                        challenge=body.get('challenge')
                        if not isinstance(challenge,str) or len(challenge)!=32 or \
                                any(x not in '0123456789abcdef' for x in challenge):
                            send(t,'coordinator','REJECT',{'code':'invalid-challenge'})
                            continue
                        if challenge in seen_challenges:
                            send(t,'coordinator','REJECT',{'code':'challenge-replay'})
                            continue
                        seen_challenges.add(challenge)
                        observed=c.gci3.feature(feature,state)
                        if diagnostic_false_reading:
                            observed ^= 1
                        payload=c.signed_payload(body,peer,snapshot.digest,observed)
                        receipt={'payload':payload,
                                 'signature_b64':c.sign_receipt(private_key,payload)}
                        send(t,'coordinator','RECEIPT',receipt)
                    elif op=='CLOSE':
                        # Keep the actual E-CPU framed stream open for the
                        # coordinator to consume CLOSED before any EOF. The
                        # transport services bytes before parsing frames, so
                        # peer EOF with queued complete bytes can be refused.
                        send(t,'coordinator','CLOSED',{'done':True})
                    elif op=='BYE':
                        # The coordinator does not close this stream until the
                        # observer process has consumed this final token.
                        check(body=={'done':True},'invalid final close token')
                        break
                    else:
                        send(t,'coordinator','REJECT',{'code':'unknown-operator'})
            finally:
                t.close()
            if good_session:
                return
    finally:
        listener.close()
    raise LiveObserverError('observer did not serve any authenticated session')


def run(directory: Path) -> dict[str, Any]:
    # Plan exists from a separate earlier job; the coordinator never loads
    # the private phase artifact as a protocol input.
    binding=c.gci3.certificate_binding(directory)
    public=c.cag.read(directory/'gci003-public.json')
    plan=c.cag.read(directory/'gci003-plan.json')
    c.gci3.validate_plan(plan,public,binding)
    with tempfile.TemporaryDirectory(prefix='gci004-mtls-') as temp:
        keys=Path(temp)
        identity=write_identity_files(keys)
        sessions: dict[str, SocketTransport]={}
        observers=[]
        processes=[]
        try:
            for peer in c.PEERS:
                ready=keys/f'{peer}-ready.json'
                proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),
                        '--serve',peer,'--directory',str(directory),
                        '--cert-dir',str(keys),'--ready-path',str(ready)],
                        stdout=(keys/f'{peer}.stdout').open('w'),
                        stderr=(keys/f'{peer}.stderr').open('w'))
                processes.append((peer,proc))
            endpoints={}
            for peer,proc in processes:
                ready=keys/f'{peer}-ready.json'
                deadline=time.monotonic()+12
                while time.monotonic()<deadline and not ready.exists():
                    check(proc.poll() is None,
                        'server '+peer+' terminated: '+(keys/f'{peer}.stderr').read_text())
                    time.sleep(.02)
                check(ready.exists(),'server '+peer+' was never ready')
                endpoints[peer]=json.loads(ready.read_text())['port']
            # Real TLS hostname rejection, before the correct TLS handshake.
            wrong_dns_refused=False
            try:
                t=connect_mutual_tls('127.0.0.1',endpoints['observer-a'],
                    'coordinator','observer-a',tls_client(keys),
                    server_hostname='forged-observer.gci004.invalid',timeout=2,handshake_timeout=2)
            except MutualTLSTransportError:
                wrong_dns_refused=True
            else:
                t.close()
            check(wrong_dns_refused,'TLS accepted a deliberately wrong peer DNS name')
            directory_fabric=ComputationalFabricDirectory('coordinator',
                      {peer:dns for peer,(_,dns) in c.PEERS.items()},
                      max_peer_lease_seconds=60)
            for peer,(feature,dns) in c.PEERS.items():
                start=time.perf_counter_ns()
                transport=connect_mutual_tls('127.0.0.1',endpoints[peer],
                    'coordinator',peer,tls_client(keys),server_hostname=dns,
                    timeout=5.0,handshake_timeout=5.0)
                handshake_ns=time.perf_counter_ns()-start
                sessions[peer]=transport
                tls_peer=transport.socket.getpeercert(binary_form=True)
                expected_leaf=x509.load_pem_x509_certificate(
                    (keys/f'{peer}.pem').read_bytes()).public_bytes(serialization.Encoding.DER)
                check(tls_peer==expected_leaf,'live TLS peer certificate fingerprint differs from expected host')
                payload={'schema':'gci004.discovery-request.v1',
                         'ground_fingerprint':binding['ground_fingerprint']}
                start=time.perf_counter_ns()
                nreq=send(transport,peer,'DISCOVER',payload)
                received=receive(transport,'SNAPSHOT')
                rtt=time.perf_counter_ns()-start
                check(received is not None,'missing authenticated peer snapshot')
                op,body,nresp=received
                check(op=='SNAPSHOT','peer refused directory discovery')
                snapshot=ComputationalPeerSnapshot.from_dict(body)
                directory_fabric.merge_authenticated_snapshot(
                    snapshot,authenticated_transport=transport)
                check(snapshot.peer_id==peer,'authenticated peer advert wrong identity')
                c.check_fabric_snapshot(body,peer,feature,dns,binding)
                observers.append({'peer_id':peer,'feature':feature,'dns':dns,
                    'certificate_pem':(keys/f'{peer}.pem').read_text(),
                    'snapshot':body,'snapshot_digest':snapshot.digest,
                    'discovery_rtt_ns':rtt,'handshake_ns':handshake_ns,
                    'request_payload_bytes':nreq,'response_payload_bytes':nresp,
                    'negotiated_tls':transport.socket.version(),
                    'channel_binding_verified':True})
            check(len(directory_fabric.active_snapshots)==3 and
                len(directory_fabric.hosts)==3,
                'actual E-CPU authenticated fabric directory did not admit all three peers')
            # Deliberately disallowed feature. It must be rejected by peer's
            # receiver-local exact plan check, *not* routed to a generic probe.
            probe_peer='observer-a'
            forbidden={'schema':c.REQUEST,'task_id':'restricted-far-y-mod8',
                  'feature':'full-state','binding':binding,
                  'public_digest':public['report_digest'],
                  'plan_digest':plan['report_digest'],
                  'phase_commitment':public['phase_commitment'],
                  'challenge':secrets.token_hex(16)}
            send(sessions[probe_peer],probe_peer,'OBSERVE',forbidden)
            refused=receive(sessions[probe_peer],'REJECT')
            forbidden_refused=refused is not None and refused[0]=='REJECT' and \
                 refused[1]=={'code':'forbidden-feature-or-context'}
            check(forbidden_refused,'server executed an unlicensed observer capability')
            measurements=[]
            reports=[]
            replay_refused=False
            for row in plan['cases']:
                readings=[]
                for feature in row['selected']:
                    suitable=[e for e in observers if e['feature']==feature]
                    check(suitable,'no authenticated host offers required feature')
                    winner=min(suitable,key=lambda e:(e['discovery_rtt_ns'],e['peer_id']))
                    peer=winner['peer_id']
                    transport=sessions[peer]
                    request=c.expected_request(row['case_id'],feature,
                                               public,plan,binding,secrets.token_hex(16))
                    start=time.perf_counter_ns()
                    nreq=send(transport,peer,'OBSERVE',request)
                    received=receive(transport,'RECEIPT')
                    elapsed=time.perf_counter_ns()-start
                    check(received is not None,'no signed receipt from selected host')
                    op,record,nresp=received
                    check(op=='RECEIPT' and set(record)=={'payload','signature_b64'},
                          'observer returned no signed receipt')
                    c.verify_receipt(x509.load_pem_x509_certificate(
                        (keys/f'{peer}.pem').read_bytes()),record['payload'],record['signature_b64'])
                    check(record['payload']['request_digest']==c.jdigest(request),
                          'received signed receipt is for a different request')
                    readings.append({'name':feature,'value':record['payload']['value']})
                    reports.append({'peer_id':peer,'request':request,
                         'payload':record['payload'],'signature_b64':record['signature_b64'],
                         'observation_rtt_ns':elapsed,
                         'request_payload_bytes':nreq,'response_payload_bytes':nresp})
                    # E-CPU receives exactly the same challenge a second time:
                    # a fresh signed observation must not be minted on replay.
                    if not replay_refused:
                        send(transport,peer,'OBSERVE',request)
                        rejected=receive(transport,'REJECT')
                        replay_refused=rejected is not None and rejected[0]=='REJECT' and \
                            rejected[1]=={'code':'challenge-replay'}
                measurements.append({'case_id':row['case_id'],'readings':readings})
            check(replay_refused,'actual receiver failed to refuse repeated nonce')
            real_measurement=c.gci3.sealed({
                'schema':c.gci3.SCHEMA_MEASUREMENT,'binding':dict(binding),
                'public_digest':public['report_digest'],
                'plan_digest':plan['report_digest'],
                'producer':c.gci3.PROVIDER,
                'phase_commitment':public['phase_commitment'],
                'entries':measurements,'state_or_phase_disclosed':False})
            result=c.gci3.resolve(public,plan,real_measurement,binding)
            report=c.sealed({'schema':c.SCHEMA,'binding':dict(binding),
                'public_digest':public['report_digest'],
                'plan_digest':plan['report_digest'],
                'origin':'gci004-real-ecpu-mtls-socket-transport',
                'ca_certificate_pem':identity['ca_pem'],
                'client_certificate_pem':identity['client_pem'],
                'discovery':observers,'requests':reports,
                'measurements':measurements,'realization':result['results'],
                'scope':c.SCOPE,'transport_kind':'127.0.0.1-tcp-tlsv1.2+',
                'bad_hostname_refused':wrong_dns_refused,
                'forbidden_feature_refused':forbidden_refused,
                'replay_refused':replay_refused})
            c.cag.persist(directory/'gci004-network.json',report)
            print('Live E-CPU mTLS peers:',len(observers),
                  'signed observation receipts:',len(reports),
                  'report:',report['report_digest'])
            return report
        finally:
            clean_closes = []
            for peer,t in sessions.items():
                try:
                    send(t,peer,'CLOSE',{'done':True})
                    reply=receive(t,'CLOSED',timeout=5.0)
                    if reply is None or reply[0]!='CLOSED' or reply[1]!={'done':True}:
                        clean_closes.append(peer + ': no explicit MailCPU close receipt')
                    else:
                        # Release the observer only after CLOSED was already
                        # decoded, but keep the socket open until its exit.
                        send(t,peer,'BYE',{'done':True})
                except Exception as exc:
                    clean_closes.append(peer + ': ' + str(exc))
            host_failures = []
            for peer,proc in processes:
                try: proc.wait(timeout=4.0)
                except subprocess.TimeoutExpired:
                    proc.kill();proc.wait(timeout=4.0)
                if proc.returncode:
                    detail = (keys/f'{peer}.stderr').read_text()[-2000:]
                    host_failures.append(peer + ' (' + str(proc.returncode) + '): ' + detail)
            for t in sessions.values():
                try: t.close()
                except Exception: pass
            if (host_failures or clean_closes) and sys.exc_info()[0] is None:
                raise LiveObserverError('authenticated observers did not terminate cleanly: ' +
                                        '; '.join(host_failures + clean_closes))
            for detail in host_failures:
                print('Observer process failure: ' + detail, file=sys.stderr)


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--serve',choices=tuple(c.PEERS))
    p.add_argument('--cert-dir',type=Path)
    p.add_argument('--ready-path',type=Path)
    p.add_argument('--gci005-diagnostic-false-reading',action='store_true')
    args=p.parse_args()
    try:
        if args.serve:
            check(args.cert_dir is not None and args.ready_path is not None,
                  'observer needs configured certificate directory and readiness file')
            server(args.serve,args.directory,args.cert_dir,args.ready_path,
                   diagnostic_false_reading=args.gci005_diagnostic_false_reading)
        else:
            check(not args.gci005_diagnostic_false_reading,
                  'diagnostic false reading only supported for an observer server')
            run(args.directory)
    except Exception as e:
        import traceback
        traceback.print_exc()
        p.exit(1,f'GCI-004 live fabric error: {type(e).__name__}: {e}\n')


if __name__=='__main__':
    main()





