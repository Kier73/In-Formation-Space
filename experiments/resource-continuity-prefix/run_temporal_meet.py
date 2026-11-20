"""RCP-002 real VL-I/E-CPU late-fork reconstitution benchmark."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns
import argparse

from temporal_meet import (
    construct_real_temporal_quorum_fork,verify_forked_quorums,
    reconstitute_semantic_interpreter,observe_new_environment,
)


def run()->dict:
    began=perf_counter_ns()
    with TemporaryDirectory() as d:
        root=Path(d)
        x=perf_counter_ns()
        evidence=construct_real_temporal_quorum_fork(root)
        production=perf_counter_ns()-x
        x=perf_counter_ns()
        branch_evidence=verify_forked_quorums(evidence)
        verification=perf_counter_ns()-x
        x=perf_counter_ns()
        recovered,manifest=reconstitute_semantic_interpreter(evidence,root)
        reconstruction=perf_counter_ns()-x
        old_processor=recovered.compile_epoch(0,expected_head=recovered.head)
        x=perf_counter_ns()
        continued=observe_new_environment(recovered)
        new_observation=perf_counter_ns()-x
        latest_old=continued.compile_epoch(0,expected_head=continued.head)
        latest_new=continued.compile_epoch(1,expected_head=continued.head)
        if old_processor["rate"]!=latest_old["rate"]:
            raise AssertionError("environment's original learned processor was lost")
        if latest_old["rate"]!=["2/1"] or latest_new["rate"]!=["1/1"]:
            raise AssertionError("continued interpretation lacks separately qualified epochs")
        report={
            "schema":"ifs.rcp002.nontrivial-causal-meet-report.v1",
            "source_repositories":["Kier73/VL-I","Kier73/E-CPU"],
            "same_interpreter_identity":True,
            "original_quorum_generation":1,
            "fork_quorum_generation":2,
            "original_quorum_membership_digest":evidence.original_membership.digest,
            "diverged_quorum_roots":[
                evidence.left_manifest.digest,evidence.right_manifest.digest,
            ],
            "old_fork_winner_selected":False,
            "longest_common_observation_events":evidence.meet["common_event_count"],
            "original_qualified_rate":old_processor["rate"],
            "old_interpolation_values":evidence.meet["verified_interpolation"]["values"],
            "old_interpolation_status":evidence.meet["verified_interpolation"]["status"],
            "recovered_common_quorum_root":evidence.shared_manifest.digest,
            "fresh_independent_quorum_root":manifest.digest,
            "fresh_quorum_incarnation":manifest.incarnation,
            "discarded_disputed_observations":[
                evidence.meet["discarded_left_events"],
                evidence.meet["discarded_right_events"],
            ],
            "fresh_observer_host":continued.events[-1]["host"],
            "fresh_observation_count":len(continued.events)-evidence.meet["common_event_count"],
            "fresh_qualified_epoch_rate":latest_new["rate"],
            "original_qualified_epoch_still_reconstructable":True,
            "actual_fork_production_ns":production,
            "quorum_replay_ns":verification,
            "source_interpreter_reconstitution_ns":reconstruction,
            "fresh_observation_and_qualification_ns":new_observation,
            "total_elapsed_ns":perf_counter_ns()-began,
            "effects":"no external effect attempted; RCP-001 separately qualifies resource effects",
            "scope":"original E-CPU quorum journals; source-observed VL-I rational time; same-runner local files",
        }
        body=json.dumps(report,sort_keys=True,separators=(",",":"),
                        ensure_ascii=True).encode("ascii")
        report["sha256"]=sha256(body).hexdigest()
        return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    body=json.dumps(run(),sort_keys=True,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(body+"\n",encoding="utf8")
    print(body)


if __name__=="__main__":
    main()
