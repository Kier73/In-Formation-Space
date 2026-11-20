"""IGC-002 evidence runner: four fresh real E-CPU Hypervisor receiver processes.

The runner is not a network dispatcher or recovery authority. Every step is
executed in a new OS process with independently provisioned local capabilities.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns

from construct import digest, synthesize
from native_execution import initial_checkpoint, verify_checkpoint

HERE=Path(__file__).resolve().parent


def run(output: Path) -> dict:
    """Produce and verify a reproducible four-host process-handoff evidence trail."""
    output.mkdir(parents=True,exist_ok=True)
    intention=json.loads((HERE/"intention.json").read_text(encoding="utf8"))
    receipt=synthesize(intention)
    if receipt["payload"]["status"]!="realized_under_declared_capacity":
        raise ValueError("mathematical intention not realizable")
    source_sha=digest(intention)
    ground=receipt["payload"]["ground"]
    intention_path=output/"trusted-intention.json"
    receipt_path=output/"constructed-ground.json"
    intention_path.write_text(json.dumps(intention,sort_keys=True,indent=2)+"\n",encoding="utf8")
    receipt_path.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n",encoding="utf8")
    checkpoint=initial_checkpoint(source_sha,ground["ground_sha256"])
    history=[]
    for index,token in enumerate(("0","1","0","1"),1):
        current=output/("checkpoint-"+str(index-1)+".json")
        current.write_text(json.dumps(checkpoint,sort_keys=True,indent=2)+"\n",encoding="utf8")
        host="native-receiver-"+str(index)
        result_path=output/("receiver-"+str(index)+".json")
        command=[
            sys.executable,str(HERE/"native_execution.py"),
            "--intention",str(intention_path),
            "--receipt",str(receipt_path),
            "--expected-intention-sha256",source_sha,
            "--checkpoint",str(current),
            "--expected-checkpoint-sha256",checkpoint["sha256"],
            "--token",token,"--host-id",host,
            "--grant-compute","--output",str(result_path)
        ]
        start=perf_counter_ns()
        result=subprocess.run(command,capture_output=True,text=True,timeout=35)
        elapsed=perf_counter_ns()-start
        if result.returncode:
            raise ValueError("native receiver process refused: "+result.stderr[:800])
        payload=json.loads(result_path.read_text(encoding="utf8"))
        if (payload["status"]!="executed_on_receiver_native_hypervisor" or
                payload["diagnostics"]["hypervisor_action"]!="allow" or
                payload["diagnostics"]["handler_invocations"]!=1):
            raise ValueError("new receiver did not execute through authorized Hypervisor")
        checkpoint=payload["checkpoint"]
        length,state,head=verify_checkpoint(checkpoint,ground,source_sha)
        if length!=index:
            raise ValueError("native Ground checkpoint failed to advance")
        event=checkpoint["payload"]["events"][-1]
        history.append({
            "stage":index,"token":token,"receiver_host":host,
            "separate_os_pid":payload["diagnostics"]["os_process_id"],
            "new_receiver_native_hypervisor":True,
            "state":state,"accepting":event["accepting"],
            "checkpoint_sha256":checkpoint["sha256"],
            "source_sha256":source_sha,
            "mathematical_ground_sha256":ground["ground_sha256"],
            "native_operator_contract_digest":
                payload["diagnostics"]["native_operator_contract_digest"],
            "native_effect_sha256":digest(event["native_effect"]),
            "checkpoint_bytes":len(json.dumps(checkpoint,sort_keys=True,
                                              separators=(",",":")).encode()),
            "complete_new_process_elapsed_ns":elapsed,
            "claim":"same-runner OS process and file handoff; not remote mTLS",
        })
    final=output/"checkpoint-4.json"
    final.write_text(json.dumps(checkpoint,sort_keys=True,indent=2)+"\n",encoding="utf8")
    if ([item["state"] for item in history]!=[1,2,1,2] or
            [item["accepting"] for item in history]!=[False,True,False,True]):
        raise ValueError("constructed Ground did not meet imposed trace intention")
    evidence={
        "schema":"ifs.igc002.native-process-evidence.v1",
        "source_intention_sha256":source_sha,
        "mathematical_ground_sha256":ground["ground_sha256"],
        "status":"four_native_hypervisor_process_steps_reconstructed",
        "steps":history,
        "native_transport":"filesystem-hand-off_only",
        "checkpoint_high_water":"externally_pinned_per_step_not_quorum",
        "existing_execution_engine":"E-CPU HeadlessOS VirtualLayerRuntime Hypervisor",
        "future_execution_authorized":False,
    }
    (output/"summary.json").write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n",encoding="utf8")
    return evidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    opts=parser.parse_args()
    result=run(opts.output)
    print(json.dumps({"status":result["status"],
                      "states":[s["state"] for s in result["steps"]],
                      "accepting":[s["accepting"] for s in result["steps"]],
                      "source_sha256":result["source_intention_sha256"]},
                     sort_keys=True))


if __name__=="__main__":
    main()
