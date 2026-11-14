"""OE-004 negative controls against the actual GCI-004 live network artifact.

Run only after the independent GCI-004 job has downloaded and checked
the original artifacts. This test restores each mutated file byte-for-byte.
It does NOT create or impersonate a new mTLS receiver.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from witness_binding import build_live_binding, verify_live_binding, digest
import fabric_contract as fabric


def require_refused(label: str, operation) -> None:
    try:
        operation()
    except (AssertionError, ValueError, TypeError, KeyError, RuntimeError):
        return
    raise AssertionError(f"OE-004 auditor silently accepted: {label}")


def run(directory: Path) -> None:
    original = build_live_binding(directory)
    assert verify_live_binding(directory, original) == original
    assert original["observation"]["feature"] == "parity"
    assert len(original["candidate_ground_states_compatible"]) >= 1
    assert len(original["candidate_ground_states_excluded"]) >= 1
    assert (
        len(original["candidate_ground_states_compatible"]) +
        len(original["candidate_ground_states_excluded"]) ==
        len(original["candidate_ground_states_before"])
    )

    forged = copy.deepcopy(original)
    forged["candidate_ground_states_compatible"] = list(original["candidate_ground_states_before"])
    forged["binding_digest"] = digest({k: v for k, v in forged.items() if k != "binding_digest"})
    require_refused("self-consistently rehashed fabricated Ground filter",
                    lambda: verify_live_binding(directory, forged))

    forged = copy.deepcopy(original)
    forged["oe003_witness_plan"]["selected"]["test"] = "low2"
    forged["oe003_witness_plan"]["plan_digest"] = digest({
        k: v for k, v in forged["oe003_witness_plan"].items() if k != "plan_digest"
    })
    forged["binding_digest"] = digest({k: v for k, v in forged.items() if k != "binding_digest"})
    require_refused("resealed plan substituted after mTLS observation",
                    lambda: verify_live_binding(directory, forged))

    path = directory / "gci004-network.json"
    original_bytes = path.read_bytes()
    network = json.loads(original_bytes)
    positions = [i for i, r in enumerate(network["requests"])
                 if r["request"]["task_id"] == "far-y-parity"
                 and r["request"]["feature"] == "parity"]
    assert len(positions) == 1
    index = positions[0]

    def mutate(label, operation):
        changed = copy.deepcopy(network)
        operation(changed)
        changed["report_digest"] = fabric.jdigest({
            k: v for k, v in changed.items() if k != "report_digest"
        })
        try:
            path.write_text(json.dumps(changed, sort_keys=True, indent=2), encoding="utf-8")
            require_refused(label, lambda: build_live_binding(directory))
        finally:
            path.write_bytes(original_bytes)

    mutate("signed receiver lies about parity", lambda doc:
           doc["requests"][index]["payload"].__setitem__(
               "value", 1 - doc["requests"][index]["payload"]["value"]))
    other_challenges = [
        entry["request"]["challenge"]
        for position, entry in enumerate(network["requests"]) if position != index
    ]
    assert other_challenges and other_challenges[0] != network["requests"][index]["request"]["challenge"]
    mutate("replayed request challenge", lambda doc:
           doc["requests"][index]["request"].__setitem__("challenge", other_challenges[0]))
    mutate("wrong TLS leaf signer", lambda doc:
           doc["discovery"][0].__setitem__(
               "certificate_pem", doc["discovery"][1]["certificate_pem"]))

    assert path.read_bytes() == original_bytes
    assert verify_live_binding(directory, original) == original


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    run(args.directory)
    print("OE-004 rejected changed signed payload, challenge, leaf credential, plan and Ground filter")
