"""RCG-007: verified quotient atlas on the EXISTING E-CPU M1 and mTLS channels.

This is an application protocol over RCG-004's existing socket mTLS,
ReliableChannel identities, and TCR-002 test certificate generation. No new
TLS stack, route admission authority, scheduler, or M3 quorum is fabricated.
"""
from __future__ import annotations
import argparse,hashlib,json,os,select,subprocess,sys,tempfile,time
from pathlib import Path
from typing import Any

from connectome_ground import ConnectomeGround,canonical
from observer_quotient import ExpandedSyntheticGround,QuotientRefused
from temporal_ground import hash_object
from atlas import verify_atlas,execute_batch,verify_batch
from m1_bridge import NativeM1Atlas
from experiments.real_connectome_ground.continuity.temporal_fabric.temporal_transport import (
    SCHEMA as RCG004_SCHEMA, ORIGIN, DEADLINE, worker_name, channels,
    send_once,poll_ack,
)
from experiments.tensor_cut_realization.transit_tensor import ssl_context
from experiments.tensor_cut_realization.run_transit_local import certificates
from mailcpu.mtls_transport import accept_mutual_tls
from mailcpu.socket_transport import SocketTransport

SCHEMA='ifs.rcg007.native-observer-m1.v1'
MAX_SESSIONS=128


def require(ok:bool,reason:str)->None:
    if not ok:raise QuotientRefused(reason)


class AtlasReceiver:
    def __init__(self,raw:bytes,source_pin:str,expected_atlas:str,*,
                 groups:int,copies:int,seed:int,require_original:bool=True,
                 checkpoint:dict|None=None,checkpoint_head:str|None=None):
        require(hashlib.sha256(raw).hexdigest()==source_pin,
                'receiver-owned source SHA-256 differs')
        require(type(expected_atlas) is str and len(expected_atlas)==64,
                'receiver lacks trusted atlas identity')
        self.source,self.source_pin,self.expected_atlas=raw,source_pin,expected_atlas
        self.groups,self.copies,self.seed=groups,copies,seed
        self.require_original=require_original
        self.m1=None
        self.replay={}
        self.executions=0
        if checkpoint is not None:
            require(checkpoint_head is not None,'checkpoint lacks external high-water')
            self.m1=NativeM1Atlas.restore(raw,checkpoint,checkpoint_head,
                                           require_original=require_original)
            self._check_admission(self.m1)

    def _check_admission(self,container:NativeM1Atlas):
        require(container.atlas['digest']==self.expected_atlas and
                (container.operator.groups,container.operator.copies,container.operator.seed)==
                (self.groups,self.copies,self.seed),
                'host policy rejects certified Ground or atlas')

    def handle(self,request:object)->dict:
        require(type(request) is dict and set(request)=={
            'schema','request_id','source_sha256','atlas_digest','batch','provision'},
            'malformed native atlas request')
        require(request['schema']==SCHEMA+'.request.v1' and
                request['source_sha256']==self.source_pin and
                request['atlas_digest']==self.expected_atlas and
                type(request['request_id']) is str and 1<=len(request['request_id'])<=96,
                'unadmitted source, atlas or request identity')
        key=request['request_id'];intent=hash_object(request)
        if key in self.replay:
            saved_intent,response=self.replay[key]
            require(saved_intent==intent,'request-id conflict with changed intention')
            return {**response,'replayed':True,
                    'digest':hash_object({**{k:v for k,v in response.items() if k!='digest'},'replayed':True})}
        started=time.perf_counter_ns()
        cold=self.m1 is None
        if cold:
            provision=request['provision']
            require(type(provision) is dict and set(provision)=={'certificate','atlas'},
                    'cold receiver requires source-bound original capability capsule')
            # The receiver independently reads its ORIGINAL pinned source; neither
            # the connectome bytes nor authority originate from the request.
            m1=NativeM1Atlas(self.source,self.source_pin,provision['certificate'],
                             provision['atlas'],require_original=self.require_original)
            self._check_admission(m1)
            self.m1=m1
        else:
            require(request['provision'] is None,
                    'warm receiver refuses unsolicited replacement of admitted atlas')
        answer=self.m1.run(request['batch'])
        self.executions+=1
        body={
            'schema':SCHEMA+'.response.v1','request_id':key,
            'source_sha256':self.source_pin,
            'atlas_digest':self.expected_atlas,
            'intention_digest':intent,'m1_manifest_digest':self.m1.identity,
            'batch':answer,'cold_admission':cold,'replayed':False,
            'receiver_execution_count':self.executions,
            'receiver_pid':os.getpid(),
            'receiver_compute_ns_local':time.perf_counter_ns()-started,
            'scope':'authenticated-loopback-app-receipt-M1-no-M3-quorum',
        }
        response={**body,'digest':hash_object(body)}
        self.replay[key]=(intent,response)
        return response


def authenticated_serve_one(listener,receiver:AtlasReceiver,index:int,ca:Path,cert:Path,key:Path):
    """Protocol-specific callback on existing mTLS + RCG-004 channel helpers."""
    tls=accept_mutual_tls(listener,worker_name(index),ORIGIN,
        ssl_context(ca,cert,key,server=True),expected_peer_dns=ORIGIN,max_frame_size=1<<20)
    try:
        tx,rx=channels(tls,index=index,serving=True)
        deadline=time.monotonic()+DEADLINE
        record={}
        while time.monotonic()<deadline:
            def commit(seq,payload):
                try:record['response']=receiver.handle(payload)
                except (QuotientRefused,ValueError,TypeError,KeyError) as exc:
                    record['response']={'schema':SCHEMA+'.refused.v1',
                       'request_id':payload.get('request_id') if type(payload) is dict else None,
                       'reason':str(exc)}
            if rx.receive(commit=commit) is not None:break
            time.sleep(.005)
        require('response' in record,'missing authenticated request')
        seq=tx.send(record['response'])
        poll_ack(tx,seq,deadline)
        return record['response']
    finally:tls.close()


def launch_worker(index:int,src:Path,pin:str,atlas_digest:str,certs,root:Path,
                  *,groups:int,copies:int,seed:int,sessions:int,
                  checkpoint_file:Path|None=None,checkpoint_head:str|None=None,
                  checkpoint_out:Path|None=None,fixture:bool=False)->tuple[subprocess.Popen,int]:
    cert,key=certs[worker_name(index)]
    command=[sys.executable,'-m',
        'experiments.real_connectome_ground.continuity.observer_quotient.native_handoff',
        'serve','--source',str(src),'--source-pin',pin,'--expected-atlas',atlas_digest,
        '--index',str(index),'--groups',str(groups),'--copies',str(copies),
        '--seed',str(seed),'--sessions',str(sessions),
        '--ca',str(root/'tls/ca.crt'),'--cert',str(cert),'--key',str(key)]
    if checkpoint_file is not None:
        command.extend(['--checkpoint',str(checkpoint_file),'--expected-head',checkpoint_head])
    if checkpoint_out is not None:command.extend(['--checkpoint-out',str(checkpoint_out)])
    if fixture:command.append('--fixture')
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    ready,_,_=select.select([proc.stdout],[],[],90)
    if not ready:
        proc.kill();out,err=proc.communicate(timeout=5)
        raise QuotientRefused('worker startup failed '+err[-1500:]+out[-500:])
    line=proc.stdout.readline()
    try:doc=json.loads(line)
    except (ValueError,TypeError) as exc:
        proc.kill();proc.communicate(timeout=5)
        raise QuotientRefused('malformed worker readiness '+line[:250]) from exc
    require(doc.get('pid')==proc.pid and doc.get('worker')==worker_name(index) and
            type(doc.get('port')) is int and 0<doc['port']<65536,
            'wrong receiver identity or TCP port')
    return proc,doc['port']


def run_experiment(source_path:Path,cert_path:Path,atlas_path:Path,*,
                   source_pin:str,groups:int=16,copies:int=8192,seed:int=73,
                   fixture:bool=False,requests:int=8)->dict:
    """Cold provision, warm queries, hard kill, process restart from pinned M1."""
    require(type(requests) is int and 4<=requests<=32,'invalid native test workload')
    source=source_path.read_bytes()
    require(hashlib.sha256(source).hexdigest()==source_pin,'source pin changed')
    base=ConnectomeGround.from_csv(source,require_original=not fixture)
    qcert=json.loads(cert_path.read_bytes())
    atlas=json.loads(atlas_path.read_bytes())
    op=ExpandedSyntheticGround(base,groups=groups,copies=copies,seed=seed)
    trusted=verify_atlas(op,qcert,atlas,deep=True)
    with tempfile.TemporaryDirectory(prefix='rcg007-authenticated-') as tmp:
        root=Path(tmp)
        certs=certificates(root/'tls',2)
        origin_cert,origin_key=certs[ORIGIN]
        processes=[];records=[]
        try:
            process,port=launch_worker(0,source_path,source_pin,atlas['digest'],certs,root,
                        groups=groups,copies=copies,seed=seed,sessions=requests+2,
                        checkpoint_out=root/'checkpoint.json',fixture=fixture)
            processes.append(process)
            checkpoint_path=root/'checkpoint.json'
            checkpoint_head=None
            for step in range(requests):
                if step==requests//2:
                    # Hard kill the current independent Python interpreter.
                    process.kill();process.wait(timeout=6)
                    # Re-home receiver's real native M1 page backing, using a
                    # separately held pinned checkpoint head. No quorum claim.
                    require(checkpoint_head is not None and checkpoint_path.exists(),
                            'receiver died without a separately pinned M1 checkpoint')
                    process,port=launch_worker(1,source_path,source_pin,atlas['digest'],certs,root,
                             groups=groups,copies=copies,seed=seed,sessions=requests+2,
                             checkpoint_file=checkpoint_path,checkpoint_head=checkpoint_head,fixture=fixture)
                    processes.append(process)
                micro=(step*1231)%op.n
                batch=[{'sources':[[micro,3],[((micro+93)%op.n),7]],
                        'tick':2**56+73+step,
                        'readout':{'kind':'shear_pair','left':step%groups,
                                   'right':(step+1)%groups,'gain':step+11}}]
                # Only the first receiver is cold. The replacement restores
                # the M1 pages; no certificate bytes are resent after hard loss.
                cold=step==0
                req={'schema':SCHEMA+'.request.v1','request_id':f'rcg007-{step}',
                     'source_sha256':source_pin,'atlas_digest':atlas['digest'],
                     'batch':batch,'provision':{'certificate':qcert,'atlas':atlas} if cold else None}
                idx=0 if step<requests//2 else 1
                answer,telemetry=send_once('127.0.0.1',port,idx,req,
                                            root/'tls/ca.crt',origin_cert,origin_key)
                require(answer.get('schema')==SCHEMA+'.response.v1' and
                        answer.get('request_id')==req['request_id'] and
                        answer.get('intention_digest')==hash_object(req) and
                        answer.get('atlas_digest')==atlas['digest'] and
                        answer.get('source_sha256')==source_pin and
                        answer.get('receiver_pid')==process.pid and
                        answer.get('cold_admission')==cold and
                        answer.get('digest')==hash_object({k:v for k,v in answer.items() if k!='digest'}),
                        'sender refused unbound authenticated result')
                verify_batch(op,qcert,atlas,batch,answer['batch'],trusted=trusted)
                require(telemetry['peer_certificate_sha256']==hashlib.sha256(
                    __import__('ssl').PEM_cert_to_DER_cert(certs[worker_name(idx)][0].read_text())).hexdigest(),
                    'TLS server certificate differs from pinned peer')
                if step==0:
                    # Pin the receiver-created checkpoint separately in the
                    # driver BEFORE killing that receiver.
                    deadline=time.monotonic()+8
                    while not checkpoint_path.exists() and time.monotonic()<deadline:
                        time.sleep(.02)
                    require(checkpoint_path.exists(),'no native M1 checkpoint file')
                    frozen=json.loads(checkpoint_path.read_bytes())
                    checkpoint_head=frozen['digest']
                    require(checkpoint_head==hash_object({k:v for k,v in frozen.items() if k!='digest'}),
                            'native M1 checkpoint content changed')
                records.append({'worker':idx,'cold':cold,'sender_total_ns':telemetry['sender_total_ns'],
                                'sender_tls_connect_ns':telemetry['sender_tls_connect_ns'],
                                'receiver_compute_ns_local':answer['receiver_compute_ns_local'],
                                'request_bytes':telemetry['application_request_bytes'],
                                'response_bytes':telemetry['application_response_bytes'],
                                'digest':answer['batch']['digest']})
            return {'schema':SCHEMA+'.experiment.v1','source_ground':base.fingerprint,
                    'atlas_digest':atlas['digest'],'requests':requests,
                    'verified_answers':len(records),'cold_admissions':1,
                    'recovered_native_m1_after_hard_loss':True,
                    'externally_pinned_local_checkpoint_head':checkpoint_head,
                    'hard_killed_worker':0,'replacement_worker':1,
                    'real_tls_loopback':True,'actual_network_bytes':sum(x['request_bytes']+x['response_bytes'] for x in records),
                    'measurements':records,'no_M3_quorum_or_remote_host_attestation':True}
        finally:
            for process in processes:
                if process.poll() is None:process.kill()
                process.communicate(timeout=8)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    server=sub.add_parser('serve')
    for flag in ('source','source-pin','expected-atlas','index','groups','copies','seed','sessions',
                 'ca','cert','key','checkpoint','expected-head','checkpoint-out'):
        server.add_argument('--'+flag,required=flag not in ('checkpoint','expected-head','checkpoint-out'))
    server.add_argument('--fixture',action='store_true')
    args=parser.parse_args()
    if args.command=='serve':
        require(1<=int(args.sessions)<=MAX_SESSIONS,'session limit exceeded')
        checkpoint=json.loads(Path(args.checkpoint).read_bytes()) if args.checkpoint else None
        receiver=AtlasReceiver(Path(args.source).read_bytes(),args.source_pin,args.expected_atlas,
                groups=int(args.groups),copies=int(args.copies),seed=int(args.seed),
                require_original=not args.fixture,checkpoint=checkpoint,checkpoint_head=args.expected_head)
        index=int(args.index)
        cert,key,ca=Path(args.cert),Path(args.key),Path(args.ca)
        listener=SocketTransport.listen('127.0.0.1',0)
        try:
            print(json.dumps({'worker':worker_name(index),'pid':os.getpid(),
                              'port':listener.getsockname()[1]}),flush=True)
            for i in range(int(args.sessions)):
                response=authenticated_serve_one(listener,receiver,index,ca,cert,key)
                if args.checkpoint_out and receiver.m1 is not None:
                    output=Path(args.checkpoint_out)
                    if not output.exists():
                        snapshot=receiver.m1.checkpoint()
                        with output.open('xb') as stream:
                            stream.write(canonical(snapshot)+b'\n')
                            stream.flush();os.fsync(stream.fileno())
                print(json.dumps({'session':i+1,'accepted':response.get('schema')==SCHEMA+'.response.v1'}),flush=True)
        finally:listener.close()
if __name__=='__main__':main()