"""TCR-003: four native Hypervisor-authorized tensor cuts with DAG verification.

This is one local-process aggregation of four separately admitted E-CPU
receiver Grounds; it is not a network or separate-machine execution claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from . import tensor_cut as tcr
from . import transit_tensor as tr
from .native_admission import NativeCut, accept_partition


def execute_four(prepared: Path, results: Path, report: Path, *, replay: bool = True) -> dict:
    manifest = tcr._validated_manifest(tcr._read_json(prepared / "manifest.json"))
    if len(manifest["partitions"]) != 4:
        raise ValueError("TCR-003 experiment requires exactly four admitted cuts")
    with np.load(prepared / "reference.npz", allow_pickle=False) as archive:
        inputs = archive["inputs"].copy()
    decisions = []
    for index in range(4):
        request = tr.request_for(
            manifest, index, inputs, request_id=f"tcr003-native-part-{index}"
        )
        receiver = NativeCut(prepared / f"shard-{index}")
        first = receiver.execute(request, sequence=1)
        if (first["accepted"] is not True
                or first["hypervisor_action"] != "allow"
                or first["native_replayed"]
                or receiver.calls != 1):
            raise ValueError(f"native receiver {index} did not execute once")
        accept_partition(manifest, request, first, results)
        replayed = False
        if replay:
            second = receiver.execute(request, sequence=1)
            if (second["accepted"] is not True or not second["native_replayed"]
                    or receiver.calls != 1
                    or second["event_fingerprint"] != first["event_fingerprint"]):
                raise ValueError(f"native receiver {index} failed exact replay")
            replayed = True
        decisions.append({
            "index": index,
            "contract_digest": first["operator_contract_digest"],
            "ground_digest": first["ground_digest"],
            "event_fingerprint": first["event_fingerprint"],
            "native_replay_confirmed": replayed,
            "handler_calls": receiver.calls,
        })
    numerical = tcr.aggregate(prepared, results, report)
    if numerical["verification"]["status"] != "passed" or not numerical["dag_restoration_equal"]:
        raise ValueError("four native tensor cuts did not pass independent DAG verification")
    result = {
        "schema": "ifs.tcr003.four-native-receivers.v1",
        "status": "native-hypervisor-and-numeric-reference-passed",
        "manifest_digest": manifest["digest"],
        "source_kind": manifest["source_provenance"]["kind"],
        "decisions": decisions,
        "numerical_verification": numerical["verification"],
        "reference_output_coordinates": numerical["counts"]["output_coordinates_checked"],
        "separate_receiver_ground_count": 4,
        "network_transport_performed": False,
        "separate_physical_hosts_attested": False,
        "sqlite_recovery_tested": False,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--detail", required=True, type=Path)
    args = parser.parse_args()
    result = execute_four(args.prepared, args.results, args.detail)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "status": result["status"],
        "receivers": len(result["decisions"]),
        "max_abs_dense_error": result["numerical_verification"]["max_abs_dense_error"],
        "max_abs_scalar_error": result["numerical_verification"]["max_abs_scalar_error"],
        "physical_hosts_attested": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
