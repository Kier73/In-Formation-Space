"""RCP-004: independently execute native authenticated receiver rehome benchmark.

The core test actually executes IPS-008's original mTLS service, original
FencedGroundLineage quorum, genuine native pure operator, and separate OS
receiver restart + hard-crash after SQLite semantic effect COMMIT/before ACK.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from temporal_meet import initial_ground
from test_ips008_semantic_bridge import (
    test_native_authenticated_rehome_qualifies_and_fences_temporal_effect,
    test_signed_identity_does_not_override_native_pinned_host_or_proof,
)


def run():
    evidence=[]
    start=perf_counter_ns()
    for label,test in (
        ("native_mtls_prepare_barrier_receiver_restart_publish_semantic_effect_lost_ack",
         test_native_authenticated_rehome_qualifies_and_fences_temporal_effect),
        ("authenticated_owner_rejected_without_correct_native_quorum_proof",
         test_signed_identity_does_not_override_native_pinned_host_or_proof),
    ):
        with TemporaryDirectory() as directory:
            began=perf_counter_ns()
            test(Path(directory))
            evidence.append({
                "scenario":label,
                "original_e_cpu_tls_and_quorum_exercised":True,
                "verified":True,
                "elapsed_ns":perf_counter_ns()-began,
            })
    source=initial_ground()
    summary={
        "schema":"ifs.rcp004.original-ips008-semantic-mtls-continuity.v1",
        "native_transport":"E-CPU mutual TLS SocketTransport typed Messages with response ACK",
        "semantic_source":"original VL-I TIME-001 source Ground",
        "source_identity":source.identity,
        "original_causal_head":source.head,
        "original_qualified_source_events":len(source.events),
        "native_receiver":"original IPS-008 AuthenticatedGroundEffectService, inherited dispatch",
        "resource_authority":"one noncloned shared receiver-owned SQLite database",
        "scenarios":evidence,
        "real_receiver_process_restarts":True,
        "real_transport_lost_response_after_durable_effect":True,
        "native_pending_barrier_fences_semantic_effects":True,
        "external_physical_effect_attested":False,
        "global_duplicate_identity_resolved":False,
        "total_elapsed_ns":perf_counter_ns()-start,
    }
    summary["sha256"]=sha256(json.dumps(
        summary,sort_keys=True,separators=(",",":"),ensure_ascii=True,
    ).encode("ascii")).hexdigest()
    return summary


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    output=json.dumps(run(),sort_keys=True,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(output+"\n",encoding="utf8")
    print(output)


if __name__=="__main__":
    main()
