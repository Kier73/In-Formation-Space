"""IGC-002: independently admitted IGC-001 Ground in E-CPU's native Virtual Layer.

A receiver reconstructs the intention proof with the independent Node NFA
verifier, binds its *own* expected source and checkpoint heads, then runs a
fixed pure transition operator through an actual HeadlessOS/Hypervisor.
Each invocation is a new OS process. No arbitrary sender program is executed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from construct import canonical, digest  # noqa: E402

SCHEMA = "ifs.igc002.native-ground-checkpoint.v1"
OPERATOR_ID = "igc002.verified_dfa_step"
GROUND_SCHEMA = "ifs.igc001.minimal-dfa-ground.v1"
RECEIPT_SCHEMA = "ifs.igc001.construction-receipt.v1"
MAX_EVENTS = 32
_NODE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,39}\Z")


class NativeGroundError(ValueError):
    """A mathematical source, receiver authority, or native observation was refused."""


def require(condition: Any, message: str) -> None:
    """Reject non-current descriptions without creating an executable handler."""
    if not condition:
        raise NativeGroundError(message)


def copy_json(value: Any) -> Any:
    """Detach one strictly finite JSON value."""
    return json.loads(canonical(value))


def read_json(path: Path) -> dict[str, Any]:
    """Read bounded, strict JSON; duplicate keys cannot create ambiguous authority."""
    raw = path.read_bytes()
    require(len(raw) <= 1024 * 1024, "oversized source or checkpoint")
    def object_pairs(pairs):
        obj={}
        for key,value in pairs:
            if key in obj:
                raise NativeGroundError("ambiguous duplicate JSON key")
            obj[key]=value
        return obj
    data=json.loads(raw.decode("utf8"), object_pairs_hook=object_pairs,
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        NativeGroundError("nonfinite JSON refused")))
    require(type(data) is dict, "expected document object")
    return data


def validate_source(intention_path: Path, receipt_path: Path,
                    expected_intention_sha256: str) -> tuple[dict,dict,dict]:
    """Run an independent full-language verifier on receiver-provisioned source."""
    require(type(expected_intention_sha256) is str
            and re.fullmatch(r"[0-9a-f]{64}", expected_intention_sha256) is not None,
            "missing receiver-owned intention identity")
    intention=read_json(intention_path)
    receipt=read_json(receipt_path)
    require(digest(intention)==expected_intention_sha256,
            "receiver-owned intention revision mismatch")
    command=["node", str(HERE/"verify.mjs"), str(intention_path),str(receipt_path)]
    try:
        result=subprocess.run(command,capture_output=True,text=True,
                              timeout=30,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise NativeGroundError("independent mathematical verifier unavailable") from exc
    require(result.returncode==0, "independent mathematical verification refused: "
            + result.stderr[:500])
    verified=json.loads(result.stdout)
    require(verified.get("verified") is True
            and verified.get("status")=="realized_under_declared_capacity"
            and verified.get("host_execution_authorized") is False,
            "mathematical receipt is not a feasible non-authoritative Ground")
    payload=receipt.get("payload")
    require(type(payload) is dict and payload.get("schema")==RECEIPT_SCHEMA
            and payload.get("intention_sha256")==expected_intention_sha256
            and payload.get("authority")==
                "mathematical_only_no_host_execution_rights",
            "construction cannot grant runtime authority")
    ground=payload.get("ground")
    require(type(ground) is dict and ground.get("schema")==GROUND_SCHEMA
            and type(ground.get("state_count")) is int
            and ground["state_count"]<=intention["max_states"],
            "unsupported or oversized constructed Ground")
    return intention,receipt,ground


def operator_spec():
    """A trusted receiver-local fixed finite state transition contract."""
    from mailcpu import OperatorSpec
    return OperatorSpec(
        operator_id=OPERATOR_ID,version=1,
        description="IGC-002 independent-proof-bound finite state transition",
        input_kind="object",output_kind="object",substrates=("cpu",),
        required_rights=frozenset({"compute"}),base_energy=2,
        energy_per_byte=1,max_input_bytes=4096,max_output_bytes=2048,
        deterministic=True,effect_mode="pure",
    )


def initial_checkpoint(intention_sha: str, ground_sha: str) -> dict[str, Any]:
    """Start a purely mathematical, content-addressed observation prefix."""
    genesis=digest({"schema":SCHEMA,"intention_sha256":intention_sha,
                    "ground_sha256":ground_sha,"kind":"genesis"})
    payload={"schema":SCHEMA,"intention_sha256":intention_sha,
             "ground_sha256":ground_sha,"initial_state":0,
             "state":0,"events":[],"head":genesis}
    return {"payload":payload,"sha256":digest(payload)}


def verify_checkpoint(checkpoint: Mapping[str,Any],ground: Mapping[str,Any],
                      intention_sha256: str) -> tuple[int,int,str]:
    """Replay *all* old transitions; hashes are continuity, not host attestation."""
    from mailcpu.semantic_translation import canonical_value_digest
    require(type(checkpoint) is dict and set(checkpoint)=={"payload","sha256"}
            and type(checkpoint["payload"]) is dict
            and checkpoint["sha256"]==digest(checkpoint["payload"]),
            "checkpoint envelope mismatch")
    payload=checkpoint["payload"]
    require(set(payload)=={"schema","intention_sha256","ground_sha256",
                           "initial_state","state","events","head"}
            and payload["schema"]==SCHEMA
            and payload["intention_sha256"]==intention_sha256
            and payload["ground_sha256"]==ground["ground_sha256"]
            and type(payload["initial_state"]) is int and payload["initial_state"]==0
            and type(payload["events"]) is list
            and len(payload["events"])<=MAX_EVENTS,
            "checkpoint not bound to the admitted mathematical Ground")
    genesis=initial_checkpoint(intention_sha256,ground["ground_sha256"])
    head=genesis["payload"]["head"]
    state=0
    spec=operator_spec()
    for i,record in enumerate(payload["events"],1):
        require(type(record) is dict and set(record)=={
            "index","host_id","token","before","after","accepting",
            "previous_head","native_effect","native_workload_digest","head"
        },"unexpected historical stage schema")
        oldhead=record["head"]
        event={k:v for k,v in record.items() if k!="head"}
        require(type(oldhead) is str and oldhead==digest(event)
                and record["previous_head"]==head
                and type(record["index"]) is int and record["index"]==i
                and type(record["before"]) is int and record["before"]==state
                and type(record["host_id"]) is str and
                    _NODE.fullmatch(record["host_id"]) is not None,
                "checkpoint sequence or evidence lineage changed")
        token=record["token"]
        require(type(token) is str and token in ground["alphabet"],
                "checkpoint token is not in the mathematical Ground")
        expected=ground["transitions"][state][ground["alphabet"].index(token)]
        require(type(record["after"]) is int and record["after"]==expected
                and type(record["accepting"]) is bool
                and record["accepting"]==ground["accepting"][expected],
                "mathematical transition differs from independently checked Ground")
        effect=record["native_effect"]
        result={"after":expected,"accepting":ground["accepting"][expected],
                "ground_sha256":ground["ground_sha256"],"step":i}
        input_value={"intention_sha256":intention_sha256,
                     "ground_sha256":ground["ground_sha256"],"previous_head":head,
                     "before":state,"token":token,"index":i}
        require(type(effect) is dict
                and effect.get("kind")=="virtual_layer.operator_result"
                and effect.get("operator_id")==OPERATOR_ID
                and effect.get("operator_version")==1
                and effect.get("operator_contract_digest")==spec.digest
                and effect.get("node_id")==record["host_id"]
                and effect.get("substrate")=="cpu"
                and effect.get("logical_time")==i
                and effect.get("result")==result
                and effect.get("result_digest")==canonical_value_digest(result)
                and effect.get("input_digest")==canonical_value_digest(input_value)
                and effect.get("workload_digest")==record["native_workload_digest"],
                "historical native effect inconsistent with its mathematical step")
        head,state=oldhead,expected
    require(payload["head"]==head and type(payload["state"]) is int
            and payload["state"]==state,"checkpoint terminal state/root differs")
    return len(payload["events"]),state,head


def execute_stage(*, intention_path: Path, receipt_path: Path,
                  expected_intention_sha256: str, checkpoint_path: Path | None,
                  expected_checkpoint_sha256: str | None, token: str,
                  host_id: str, grant_compute: bool) -> dict[str,Any]:
    """Execute exactly one step on a separately bootstrapped native Hypervisor."""
    from mailcpu import (
        Capability,HeadlessOS,HypervisorPolicy,LexicalDecisionModel,
        OperatorRegistry,SystemIdentity,SystemSeed,SystemSeedEnvelope,
        VirtualGroundRef,VirtualBudget,VirtualLayerWorkload,VirtualOperatorRef,
        VirtualLayerRuntime,
    )
    from mailcpu.semantic_translation import canonical_value_digest

    require(type(host_id) is str and _NODE.fullmatch(host_id) is not None,
            "invalid receiver host identifier")
    intention,_,ground=validate_source(intention_path,receipt_path,
                                      expected_intention_sha256)
    require(type(token) is str and token in intention["alphabet"],
            "requested token not admitted by the intention")
    checkpoint=(initial_checkpoint(expected_intention_sha256,ground["ground_sha256"])
                if checkpoint_path is None else read_json(checkpoint_path))
    require(type(expected_checkpoint_sha256) is str
            and re.fullmatch(r"[0-9a-f]{64}",expected_checkpoint_sha256) is not None
            and checkpoint["sha256"]==expected_checkpoint_sha256,
            "receiver-owned expected recovery high-water mismatch")
    count,state,head=verify_checkpoint(checkpoint,ground,expected_intention_sha256)
    require(count<MAX_EVENTS,"native stage bound reached")
    step=count+1
    destination=ground["transitions"][state][intention["alphabet"].index(token)]
    expected={"after":destination,"accepting":ground["accepting"][destination],
              "ground_sha256":ground["ground_sha256"],"step":step}
    input_value={"intention_sha256":expected_intention_sha256,
                 "ground_sha256":ground["ground_sha256"],"previous_head":head,
                 "before":state,"token":token,"index":step}
    calls=[]
    def handler(argument, workload):
        """Use fixed locally loaded transition data, not supplied executable code."""
        require(dict(argument)==input_value
                and dict(workload.intention["goal"])=={
                    "intention_sha256":expected_intention_sha256,
                    "ground_sha256":ground["ground_sha256"],
                    "previous_head":head,
                },"foreign workload substituted")
        calls.append(True)
        return expected

    system=HeadlessOS()
    system.hypervisor.classifier=LexicalDecisionModel()
    system.hypervisor.policy=HypervisorPolicy(embedding_review_confidence=1.0)
    identity=SystemIdentity("igc002-"+host_id,1)
    envelope=SystemSeedEnvelope(identity,"executor","igc002",SystemSeed.from_system(system))
    require(system.seed_admission.admit(envelope).accepted,
            "receiver did not admit native seed")
    native_ground=VirtualGroundRef.from_envelope(envelope)
    registry=OperatorRegistry()
    spec=operator_spec()
    registry.register(spec,handler)
    runtime=VirtualLayerRuntime(registry,host_id,frozenset({"cpu"}))
    caps=(Capability("/virtual-layer/operators",frozenset({"compute"}))
          if grant_compute else Capability("/unrelated",frozenset({"read"})))
    pid=system.environment.kernel.spawn(
        "igc002-"+host_id,capabilities=(caps,),parent_pid=system.environment.init_pid)
    workload=VirtualLayerWorkload(
        workload_id="igc002-"+expected_intention_sha256[:16]+"-"+str(step),
        system=identity,ground=native_ground,
        intention={"goal":{"intention_sha256":expected_intention_sha256,
                           "ground_sha256":ground["ground_sha256"],
                           "previous_head":head}},
        operators=(VirtualOperatorRef(OPERATOR_ID,1,"cpu",host_id),),
        input_value=input_value,
        budget=VirtualBudget(100000,100000,1000),logical_time=step,
        eligible_nodes=(host_id,),max_hops=1,
    )
    outcome=runtime.execute_operator(
        system,pid,"igc002-origin","igc002.native",step,step,workload,OPERATOR_ID)
    diagnostics={"os_process_id":os.getpid(),"host_id":host_id,
                 "hypervisor_action":outcome.action.value,
                 "handler_invocations":len(calls),
                 "native_operator_contract_digest":spec.digest}
    if not outcome.executed or outcome.action.value!="allow":
        require(not calls and outcome.effect is None,
                "unprivileged host executed handler")
        return {"status":"refused_receiver_authority","diagnostics":diagnostics,
                "checkpoint":checkpoint}
    require(len(calls)==1 and type(outcome.effect) is dict,
            "native execution did not produce one effect")
    effect=copy_json(outcome.effect)
    require(effect.get("result")==expected
            and effect.get("workload_digest")==workload.digest
            and effect.get("ground")==native_ground.to_dict()
            and effect.get("node_id")==host_id
            and effect.get("operator_contract_digest")==spec.digest
            and effect.get("input_digest")==canonical_value_digest(input_value)
            and system.environment.kernel.journal.verify(),
            "native effect, Ground, or journal mismatch")
    record={"index":step,"host_id":host_id,"token":token,
            "before":state,"after":destination,
            "accepting":ground["accepting"][destination],
            "previous_head":head,"native_effect":effect,
            "native_workload_digest":workload.digest}
    record["head"]=digest(record)
    payload=copy_json(checkpoint["payload"])
    payload["events"].append(record)
    payload["state"]=destination
    payload["head"]=record["head"]
    updated={"payload":payload,"sha256":digest(payload)}
    verify_checkpoint(updated,ground,expected_intention_sha256)
    return {"status":"executed_on_receiver_native_hypervisor",
            "diagnostics":diagnostics,"checkpoint":updated}


def main() -> None:
    """One-shot fresh receiver process; external manifest pins source and high-water."""
    parser=argparse.ArgumentParser()
    parser.add_argument("--intention",type=Path,required=True)
    parser.add_argument("--receipt",type=Path,required=True)
    parser.add_argument("--expected-intention-sha256",required=True)
    parser.add_argument("--checkpoint",type=Path)
    parser.add_argument("--expected-checkpoint-sha256",required=True)
    parser.add_argument("--token",required=True)
    parser.add_argument("--host-id",required=True)
    parser.add_argument("--grant-compute",action="store_true")
    parser.add_argument("--output",type=Path,required=True)
    arguments=parser.parse_args()
    try:
        result=execute_stage(
            intention_path=arguments.intention,
            receipt_path=arguments.receipt,
            expected_intention_sha256=arguments.expected_intention_sha256,
            checkpoint_path=arguments.checkpoint,
            expected_checkpoint_sha256=arguments.expected_checkpoint_sha256,
            token=arguments.token,host_id=arguments.host_id,
            grant_compute=arguments.grant_compute,
        )
    except (NativeGroundError,ValueError,KeyError,TypeError) as exc:
        parser.exit(1,"REFUSED: "+str(exc)+"\n")
    arguments.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                                encoding="utf8")
    print(json.dumps({"status":result["status"],
                      "native":result["diagnostics"],
                      "head":result["checkpoint"]["sha256"]},sort_keys=True))


if __name__=="__main__":
    main()
