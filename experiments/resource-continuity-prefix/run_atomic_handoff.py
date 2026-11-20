"""RCP-003: measured real OS crash-recovery at seven atomic handoff cuts.

This is a development benchmark, not a physical effect or liveness guarantee.
Each scenario creates actual VL-I source observations and actual E-CPU quorum
journal forks. A separate Python worker dies via os._exit with local database
and quorum files retained; the parent resumes and verifies no double effect.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns
import argparse

from atomic_semantic_effect import load_workspace,open_receiver
from test_atomic_semantic_effect import (
    CUTS,test_hard_crash_at_every_durable_cut_recovers_without_duplicate_effect,
)


def run()->dict:
    started=perf_counter_ns()
    scenarios=[]
    for cut in CUTS:
        with TemporaryDirectory() as temp:
            root=Path(temp)
            t=perf_counter_ns()
            test_hard_crash_at_every_durable_cut_recovers_without_duplicate_effect(root,cut)
            elapsed=perf_counter_ns()-t
            source=load_workspace(root).evidence
            observer=open_receiver(root).snapshot()
            if (observer["committed_effects"]!=1 or observer["receiver_revision"]!=2
                    or observer["old_fork_winner"] is not None):
                raise AssertionError("hard-crash scenario did not preserve uniqueness")
            scenarios.append({
                "crash_cut":cut,
                "real_os_hard_crash":True,
                "source_common_observation_count":source.meet["common_event_count"],
                "source_common_quorum_root":source.shared_manifest.digest,
                "original_forked_roots":[source.left_manifest.digest,
                                         source.right_manifest.digest],
                "receiver_epoch_after_recovery":observer["receiver_revision"],
                "qualified_processor_digest":observer["processor_digest"],
                "receiver_effect_count":observer["committed_effects"],
                "observed_no_election":observer["old_fork_winner"] is None,
                "verified_elapsed_ns":elapsed,
            })
    report={
        "schema":"ifs.rcp003.atomic-interpretation-effect-crash-benchmark.v1",
        "cases":scenarios,
        "crash_cuts_covered":len(scenarios),
        "real_quorum_journal_forks":len(scenarios),
        "fresh_recovery_authority_instances":len(scenarios),
        "committed_effects_per_receiver":[x["receiver_effect_count"] for x in scenarios],
        "common_temporal_observations":[x["source_common_observation_count"] for x in scenarios],
        "global_fork_winner_elected":False,
        "resource":"single receiver-owned SQLite derived-value register",
        "external_physical_effect_attested":False,
        "total_elapsed_ns":perf_counter_ns()-started,
    }
    report["sha256"]=sha256(json.dumps(report,sort_keys=True,
          separators=(",",":"),ensure_ascii=True).encode("ascii")).hexdigest()
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    body=json.dumps(run(),sort_keys=True,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(body+"\n",encoding="utf8")
    print(body)


if __name__=="__main__":
    main()
