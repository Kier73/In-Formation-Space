"""IGC-003: one intention-built DFA step over native E-CPU reliable mTLS operation channels.

The receiver runs a *locally installed fixed handler*, with its own HeadlessOS,
admitted Virtual Ground, source identity and expected checkpoint. The sender
can request a typed token only. This file introduces no transport or Hypervisor.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import ssl
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from construct import canonical, digest
from native_execution import (
    NativeGroundError,copy_json,operator_spec,read_json,validate_source,verify_checkpoint,
)

from mailcpu import (
    Capability,HeadlessOS,HypervisorPolicy,LexicalDecisionModel,
    SystemIdentity,SystemSeed,SystemSeedEnvelope,VirtualGroundRef,
    OperatorRegistry,VirtualLayerRuntime,VirtualLayerWorkload,VirtualOperatorRef,
    VirtualBudget,HypervisorOperationChannel,HypervisorOperationResultChannel,
    ReliabilityPolicy,ReliableChannel,SocketTransport,
)
from mailcpu.mtls_transport import accept_mutual_tls,connect_mutual_tls
from mailcpu.semantic_translation import canonical_value_digest


SCHEMA="ifs.igc003.authenticated-ground-transition.v1"
ORIGIN="igc003-origin"
REQUEST_CHANNEL="igc003.operation"
RESULT_CHANNEL="igc003.operation.result"


def require(condition,message):
    """Require a pinned mathematical identity or authenticated native outcome."""
    if not condition:
        raise NativeGroundError("IGC-003: "+message)


def policy():
    """Re-use E-CPU's bounded reliable delivery policy."""
    return ReliabilityPolicy(lease_ticks=1,max_attempts=3,window_size=4)


def client_tls(directory):
    """Owner client context must authenticate the server and present a real identity."""
    ctx=ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,cafile=str(directory/"ca.pem"))
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(directory/"A.pem"),str(directory/"A.key"))
    return ctx


def server_tls(directory,member):
    """Certificate-pinned native server context accepting only owner certificate."""
    require(member in ("B","C"),"unrecognized receiver host certificate")
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(directory/(member+".pem")),
                        str(directory/(member+".key")))
    ctx.load_verify_locations(cafile=str(directory/"ca.pem"))
    ctx.verify_mode=ssl.CERT_REQUIRED
    return ctx


def workload_for(advertisement,source_sha,ground,checkpoint,token):
    """Construct one data-only typed E-CPU workload for a specifically pinned peer."""
    host=advertisement["node_id"]
    require(host in ("igc003-B","igc003-C")
            and advertisement["source_sha256"]==source_sha
            and advertisement["mathematical_ground_sha256"]==ground["ground_sha256"]
            and advertisement["expected_checkpoint_sha256"]==checkpoint["sha256"]
            and advertisement["operator_contract_digest"]==operator_spec().digest,
            "host advertisement or fixed operator identity differs")
    c,state,head=verify_checkpoint(checkpoint,ground,source_sha)
    require(c<32 and token in ground["alphabet"],"requested operation not in Ground")
    step=c+1
    system=SystemIdentity.from_snapshot(advertisement["system"])
    native_ground=VirtualGroundRef.from_dict(advertisement["native_ground"])
    value={"intention_sha256":source_sha,
           "ground_sha256":ground["ground_sha256"],
           "previous_head":head,"before":state,"token":token,"index":step}
    goal={"intention_sha256":source_sha,
          "ground_sha256":ground["ground_sha256"],
          "previous_head":head}
    workload=VirtualLayerWorkload(
        "igc003-"+source_sha[:16]+"-"+str(step),
        system,native_ground,{"goal":goal},
        (VirtualOperatorRef(operator_spec().operator_id,1,"cpu",host),),
        value,VirtualBudget(100000,100000,1000),step,(host,),1)
    return workload


def serve_once(intention_path,receipt_path,source_sha,checkpoint_path,
               expected_checkpoint_sha,host_member,tls_dir,ready_file,record_file,
               *,grant_compute):
    """Listen with mTLS, admit one E-CPU native Hypervisor event and answer reliably."""
    require(host_member in ("B","C"),"unrecognized mTLS computation peer")
    _,_,ground=validate_source(intention_path,receipt_path,source_sha)
    checkpoint=read_json(checkpoint_path)
    require(checkpoint["sha256"]==expected_checkpoint_sha,
            "receiver was given a stale or foreign recovery root")
    count,state,head=verify_checkpoint(checkpoint,ground,source_sha)
    require(count<32,"no further transitions admitted")
    host="igc003-"+host_member
    osystem=HeadlessOS()
    osystem.hypervisor.classifier=LexicalDecisionModel()
    osystem.hypervisor.policy=HypervisorPolicy(embedding_review_confidence=1.0)
    identity=SystemIdentity("igc003-host-"+host_member,1)
    envelope=SystemSeedEnvelope(identity,"executor","igc003",
                                SystemSeed.from_system(osystem))
    require(osystem.seed_admission.admit(envelope).accepted,
            "peer local system Ground refused")
    native_ground=VirtualGroundRef.from_envelope(envelope)
    calls=[]
    def handler(value,workload):
        """Apply only receiver-installed mathematics to a proof-checked previous state."""
        data=copy_json(value)
        require(type(data) is dict and set(data)=={
            "intention_sha256","ground_sha256","previous_head",
            "before","token","index"},"unexpected token operation fields")
        token=data["token"]
        require(token in ground["alphabet"],"token outside proved mathematical language")
        require(data=={"intention_sha256":source_sha,
                       "ground_sha256":ground["ground_sha256"],
                       "previous_head":head,"before":state,
                       "token":token,"index":count+1},
                "network workload cannot alter receiver-owned historical state")
        require(dict(workload.intention["goal"])=={
            "intention_sha256":source_sha,
            "ground_sha256":ground["ground_sha256"],
            "previous_head":head},
            "network operator intention binding changed")
        destination=ground["transitions"][state][ground["alphabet"].index(token)]
        calls.append(True)
        return {"after":destination,"accepting":ground["accepting"][destination],
                "ground_sha256":ground["ground_sha256"],"step":count+1}

    registry=OperatorRegistry()
    spec=operator_spec()
    registry.register(spec,handler)
    runtime=VirtualLayerRuntime(registry,host,frozenset({"cpu"}))
    caps=(Capability("/virtual-layer/operators",frozenset({"compute"}))
          if grant_compute else Capability("/not-allowed",frozenset({"read"})))
    pid=osystem.environment.kernel.spawn(
        "igc003-native-"+host_member,capabilities=(caps,),
        parent_pid=osystem.environment.init_pid)
    listener=SocketTransport.listen("127.0.0.1",0)
    listener.settimeout(12)
    ready={"schema":SCHEMA,"node_id":host,
           "source_sha256":source_sha,
           "mathematical_ground_sha256":ground["ground_sha256"],
           "expected_checkpoint_sha256":expected_checkpoint_sha,
           "operator_contract_digest":spec.digest,
           "system":identity.snapshot(),"native_ground":native_ground.to_dict(),
           "host_member":host_member,"host_pid":os.getpid(),
           "host":"127.0.0.1","port":listener.getsockname()[1],
           "peer_server_dns":"member-"+host_member.lower()+".mailcpu.test"}
    ready_file.write_bytes(canonical(ready))
    connection=None
    try:
        connection=accept_mutual_tls(
            listener,host,ORIGIN,server_tls(tls_dir,host_member),
            expected_peer_dns="owner-a.mailcpu.test",handshake_timeout=7)
        request=HypervisorOperationChannel(
            ReliableChannel(connection,host,host,REQUEST_CHANNEL,policy(),peer=ORIGIN))
        response=HypervisorOperationResultChannel(
            ReliableChannel(connection,host,ORIGIN,RESULT_CHANNEL,policy()),
            ORIGIN,REQUEST_CHANNEL)
        deadline=time.monotonic()+10
        outcome=None
        while time.monotonic()<deadline:
            outcome=runtime.receive_and_execute(request,osystem,pid)
            if outcome is not None:
                response.send(outcome)
                break
            time.sleep(.003)
        require(outcome is not None,"timed out waiting for native reliable operation")
        response_acked=False
        while time.monotonic()<deadline:
            if response.channel.process_ack():
                response_acked=True
                break
            time.sleep(.003)
        require(response_acked,"native result was not reliably acknowledged")
        require(osystem.environment.kernel.journal.verify(),
                "native kernel journal not verifiable")
        state_record={"schema":SCHEMA,"host_member":host_member,
                      "host":host,"host_pid":os.getpid(),
                      "local_hypervisor_action":outcome.action.value,
                      "native_effect_sha256":(
                          digest(copy_json(outcome.effect))
                          if outcome.effect is not None else None),
                      "handler_invocations":len(calls),
                      "mutual_tls_client_dns":"owner-a.mailcpu.test",
                      "result_acknowledged":True,
                      "scope":"real mTLS loopback and E-CPU reliable operations on one host"}
        record_file.write_bytes(canonical(state_record))
        return state_record
    finally:
        listener.close()
        if connection is not None and not connection.closed:
            connection.close()


def request_once(intention_path,receipt_path,source_sha,checkpoint_path,
                 expected_checkpoint_sha,advertisement_path,tls_dir,token,
                 *,expected_member):
    """Transmit a math-bound native workload to pinned TLS host and verify effect."""
    _,_,ground=validate_source(intention_path,receipt_path,source_sha)
    checkpoint=read_json(checkpoint_path)
    require(checkpoint["sha256"]==expected_checkpoint_sha,
            "origin checkpoint differs from externally pinned high-water")
    count,state,head=verify_checkpoint(checkpoint,ground,source_sha)
    ready=read_json(advertisement_path)
    require(expected_member in ("B","C") and
            ready.get("host_member")==expected_member
            and ready.get("peer_server_dns")==
                "member-"+expected_member.lower()+".mailcpu.test"
            and ready.get("host")=="127.0.0.1"
            and type(ready.get("port")) is int,
            "expected receiver endpoint not pinned")
    workload=workload_for(ready,source_sha,ground,checkpoint,token)
    registry=OperatorRegistry()
    registry.register(operator_spec(),lambda v,w: None)
    runtime=VirtualLayerRuntime(registry,ready["node_id"],frozenset({"cpu"}))
    event=runtime.build_event(ORIGIN,REQUEST_CHANNEL,count+1,count+1,
                              workload,operator_spec().operator_id)
    conn=connect_mutual_tls(
        ready["host"],ready["port"],ORIGIN,ready["node_id"],
        client_tls(tls_dir),server_hostname=ready["peer_server_dns"],
        timeout=5,handshake_timeout=5)
    try:
        request=HypervisorOperationChannel(
            ReliableChannel(conn,ORIGIN,ready["node_id"],
                            REQUEST_CHANNEL,policy()))
        reply=HypervisorOperationResultChannel(
            ReliableChannel(conn,ORIGIN,ORIGIN,
                            RESULT_CHANNEL,policy(),peer=ready["node_id"]),
            ORIGIN,REQUEST_CHANNEL)
        request.send(event)
        deadline=time.monotonic()+12
        returned=None
        while time.monotonic()<deadline:
            returned=reply.receive()
            if returned is not None:break
            time.sleep(.003)
        require(returned is not None,"network receiver result missing")
        require(returned.source==ORIGIN and returned.channel==REQUEST_CHANNEL
                and returned.sequence==count+1
                and returned.logical_time==count+1,
                "remote operation identity or sequence changed")
        require(returned.executed and returned.action.value=="allow"
                and type(returned.effect) is dict,
                "remote E-CPU Hypervisor refused executable intention")
        effect=copy_json(returned.effect)
        expected=ground["transitions"][state][ground["alphabet"].index(token)]
        require(effect.get("kind")=="virtual_layer.operator_result"
                and effect.get("node_id")==ready["node_id"]
                and effect.get("ground")==workload.ground.to_dict()
                and effect.get("workload_digest")==workload.digest
                and effect.get("operator_contract_digest")==operator_spec().digest
                and effect.get("input_digest")==
                    canonical_value_digest(copy_json(workload.input_value))
                and effect.get("result")=={
                    "after":expected,"accepting":ground["accepting"][expected],
                    "ground_sha256":ground["ground_sha256"],"step":count+1},
                "native authenticated result differs from Ground")
        record={"index":count+1,"host_id":ready["node_id"],"token":token,
                "before":state,"after":expected,
                "accepting":ground["accepting"][expected],
                "previous_head":head,"native_effect":effect,
                "native_workload_digest":workload.digest}
        record["head"]=digest(record)
        payload=copy_json(checkpoint["payload"])
        payload["events"].append(record)
        payload["state"]=expected
        payload["head"]=record["head"]
        updated={"payload":payload,"sha256":digest(payload)}
        verify_checkpoint(updated,ground,source_sha)
        # Flush result ACK before closing the authenticated socket.
        request.channel.process_ack()
        conn.service()
        return {"schema":SCHEMA,"status":"native_mtls_hypervisor_executed",
                "from_server_dns":ready["peer_server_dns"],
                "server_host_pid":ready["host_pid"],
                "result_sha256":digest(effect),
                "network_peer_mathematically_requalified":True,
                "current_execution_authorized_for_future":False,
                "checkpoint":updated}
    finally:
        if not conn.closed:conn.close()


def main():
    """Use trust-provisioned source paths; TLS identities are fixed per role."""
    p=argparse.ArgumentParser()
    p.add_argument("role",choices=("server","client"))
    p.add_argument("--intention",type=Path,required=True)
    p.add_argument("--receipt",type=Path,required=True)
    p.add_argument("--expected-intention-sha256",required=True)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--expected-checkpoint-sha256",required=True)
    p.add_argument("--tls-dir",type=Path,required=True)
    p.add_argument("--host-member",choices=("B","C"))
    p.add_argument("--ready-file",type=Path)
    p.add_argument("--record-file",type=Path)
    p.add_argument("--advertisement",type=Path)
    p.add_argument("--token")
    p.add_argument("--no-compute-right",action="store_true")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    common=(args.intention,args.receipt,args.expected_intention_sha256,
            args.checkpoint,args.expected_checkpoint_sha256)
    if args.role=="server":
        require(args.host_member is not None and args.ready_file is not None
                and args.record_file is not None,"server provisioning incomplete")
        report=serve_once(*common,args.host_member,args.tls_dir,
                          args.ready_file,args.record_file,
                          grant_compute=not args.no_compute_right)
    else:
        require(args.advertisement is not None and args.token is not None
                and args.host_member is not None and args.output is not None,
                "origin selection incomplete")
        report=request_once(*common,args.advertisement,args.tls_dir,args.token,
                            expected_member=args.host_member)
        args.output.write_bytes(canonical(report))
    print(json.dumps({k:v for k,v in report.items() if k!="checkpoint"},
                     sort_keys=True))


if __name__=="__main__":
    main()
