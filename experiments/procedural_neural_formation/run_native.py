"""PNF-003: transfer a generated capsule, then execute receiver-owned native cuts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform

import numpy as np

from .capsule import pack_pair
from .formation import FormationError, procedural_block, widen
from .native_execution import execute_capsule
from .run_transfer import observe_source
from .transfer import transfer_pair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--live", action="store_true")
    source.add_argument("--capsule", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--expected-source")
    parser.add_argument("--expected-generated")
    parser.add_argument("--direct", action="store_true", help="local native execution without transport")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.capsule and not (args.policy and args.expected_source and args.expected_generated):
        parser.error("saved capsule requires --policy and independently configured --expected-source/--expected-generated")
    pairs = []
    for activation in ("relu", "gelu_tanh"):
        parent = procedural_block(8, 1024, 8, activation=activation)
        child, certificate = widen(parent, 2048)
        pairs.append(("procedural-" + activation, pack_pair(
            parent, child, certificate, {"kind": "procedural", "seed": 31}, [[.5] * 8])))
    if args.live:
        parent, provenance = observe_source()
        child, certificate = widen(parent, 4096)
        pairs.append(("fresh-observed-gpt2", pack_pair(parent, child, certificate, provenance,
            [[((i * 7 + k * 3) % 19 - 9) / 16 for i in range(768)] for k in range(2)])))
    if args.capsule:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        if policy["source_digest"] != args.expected_source or policy["generated_digest"] != args.expected_generated:
            raise FormationError("saved policy differs from independently configured model identities")
        pairs.append(("previously-exported-capsule", (args.capsule.read_bytes(), policy)))
    cases = []
    for name, (raw, policy) in pairs:
        if args.direct:
            native = execute_capsule(raw, policy)
            case = {"name": name, "native_execution": native}
        else:
            transport = transfer_pair(raw, policy, native_execution=True)
            report = transport["receiver"]["report"]
            if report["status"] != "verified":
                raise FormationError("receiver rejected native realization: " + str(report))
            native = report["native_execution"]
            case = {"name": name, "transfer": transport}
        if native["status"] != "executed":
            raise FormationError("native execution was not admitted")
        cases.append(case)
        print(json.dumps({"case": name, "status": native["status"],
            "handler_calls": native["native_handler_calls"], "capsule_bytes": len(raw),
            "output_coordinates_checked": native["output_coordinates_checked"],
            "max_abs_parent_dense_error": native["max_abs_parent_dense_error"],
            "max_abs_parent_scalar_error": native["max_abs_parent_scalar_error"],
            "network_transport_performed": not args.direct}), flush=True)
    raw, policy = pairs[0][1]
    if args.direct:
        denial = execute_capsule(raw, policy, grant_compute=False)
    else:
        denial = transfer_pair(raw, policy, native_execution=True, grant_compute=False)["receiver"]["report"]["native_execution"]
    if denial["status"] != "denied" or denial["native_handler_calls"] != 0:
        raise FormationError("negative authority control failed")
    result = {"schema": "ifs.pnf003.experiment.v1", "cases": cases, "denial_control": denial,
              "network_transport_performed": not args.direct,
              "native_cuts_scope": "four receiver-owned runtimes in one process on one physical host",
              "environment": {"python": platform.python_version(), "numpy": np.__version__,
                              "platform": platform.platform()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
