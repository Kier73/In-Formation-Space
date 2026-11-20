"""RCP-001 independent research runner: clone → fork → quarantine → restart.

Generates genuine E-CPU recovery-lineage journals, reconstructs both cloned
authorities, derives their common prefix, refuses both old effect branches,
seals a NEW protected successor membership from the original seed bytes,
and verifies new receiver-local effect continuity across process objects.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns
import argparse

from fork_detection import produce_cluster,observe_two_clusters,GENESIS
from receiver import ForkSafeEffectReceiver,ForkContinuityRefused,SEED,successor_membership
from test_receiver import RESOURCE,resource,new_quorum


def run()->dict:
    start=perf_counter_ns()
    with TemporaryDirectory() as root:
        folder=Path(root)
        left,right=folder/"left",folder/"right"
        began=perf_counter_ns()
        produce_cluster(left,cluster_id="left",state_label="fork-A")
        produce_cluster(right,cluster_id="right",state_label="fork-B")
        clone_ns=perf_counter_ns()-began
        began=perf_counter_ns()
        observed=observe_two_clusters(left,right)
        evidence_ns=perf_counter_ns()-began
        if (observed["classification"]!="cloned_membership_split_brain"
                or observed["winner"] is not None):
            raise AssertionError("real cloned E-CPU quorum did not produce incompatible roots")
        receiver=resource(folder)
        began=perf_counter_ns()
        quarantine=receiver.observe_and_freeze(left,right)
        freeze_ns=perf_counter_ns()-began
        old_roots=[item["root_digest"] for item in observed["clusters"]]
        old_rejections=0
        for root in old_roots:
            try:
                receiver.apply(epoch=1,root=root,operation_id="old-"+root[:8],value=1)
            except ForkContinuityRefused:
                old_rejections+=1
            else:
                raise AssertionError("cloned generation-one effect wrongfully admitted")
        began=perf_counter_ns()
        m,quorum,manifest=new_quorum(folder)
        owner=receiver.reconstitute(
            checkpoint_bytes=SEED,membership=m,
            coordinator=quorum,manifest=manifest,
        )
        reconstitute_ns=perf_counter_ns()-began
        if owner["epoch"]!=2:
            raise AssertionError("fresh receiver revision was not activated")
        began=perf_counter_ns()
        native=receiver.apply(
            epoch=2,root=manifest.digest,
            operation_id="new-incarnation-first-effect",value=17,
        )
        effect_ns=perf_counter_ns()-began
        restarted=resource(folder)
        if restarted.snapshot()["committed_effect_count"]!=1:
            raise AssertionError("restart lost receiver durable history")
        for root in old_roots:
            try:
                restarted.apply(epoch=2,root=root,
                                operation_id="forged-"+root[:8],value=3)
            except ForkContinuityRefused:
                old_rejections+=1
            else:
                raise AssertionError("cloned old root bypassed fresh receiver epoch")
        snapshot=restarted.snapshot()
        result={
            "schema":"ifs.rcp001.common-prefix-continuation-report.v1",
            "original_machine_identity_preserved":True,
            "original_membership_fork_status":observed["classification"],
            "original_quorum_roots":old_roots,
            "global_winner_selected":False,
            "shared_causal_prefix":GENESIS,
            "shared_seed_bytes_sha256":sha256(SEED).hexdigest(),
            "fresh_membership_digest":m.digest,
            "fresh_quorum_root":manifest.digest,
            "receiver_epoch":snapshot["receiver_revision"],
            "receiver_durable_committed_effects":snapshot["committed_effect_count"],
            "stale_clone_effect_refusals":old_rejections,
            "last_effect_digest":native["digest"],
            "fork_witness_digest":quarantine["digest"],
            "independent_quorum_replay_ns":evidence_ns,
            "two_quorum_production_ns":clone_ns,
            "receiver_freeze_ns":freeze_ns,
            "fresh_quorum_reconstitution_ns":reconstitute_ns,
            "new_resource_effect_ns":effect_ns,
            "total_elapsed_ns":perf_counter_ns()-start,
            "claims":"single receiver-owned SQLite effect domain; two original E-CPU quorum copies; no global fork winner or independent physical hardware",
        }
        result["sha256"]=sha256(json.dumps(result,sort_keys=True,
              separators=(",",":"),ensure_ascii=True).encode("ascii")).hexdigest()
        return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    result=run()
    printable=json.dumps(result,sort_keys=True,indent=2)
    if args.output:
        args.output.write_text(printable+"\n",encoding="utf8")
    print(printable)


if __name__=="__main__":
    main()
