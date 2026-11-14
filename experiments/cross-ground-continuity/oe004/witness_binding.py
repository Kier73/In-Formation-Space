"""OE-004: turn a real GCI-004 E-CPU mTLS receipt into a finite witness.

The existing GCI-004 independent auditor validates the actual TLS-derived
leaf identity, request-bound ECDSA signature, admitted peer advertisement,
authorized feature, and independently held mathematical phase. This adapter
consumes that *already executed* evidence. It never creates a simulated signer
or re-labels a proposed plan as an execution.

One real observation filters a hypothesis fiber; it cannot realize both
counterfactual states and does not identify a unique phase unless the
authorized observation is actually sufficient to do so.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "bridges" / "observation-equivalence"))
sys.path.insert(0, str(ROOT / "experiments" / "cross-ground-continuity" / "gci004"))

from costed_navigation import CostedDistinctionNavigator
from witness_realization import build_plan, verify_plan

SCHEMA = "in-formation.oe004-authenticated-observation-witness/0.1"
SCOPE = (
    "GCI-004 real E-CPU loopback mTLS receiver process, ephemeral single-run "
    "test-CA and leaf-key ECDSA receipt, independent CI-job source-and-private-"
    "phase audit; selected result is model-relative candidate filtering, "
    "not proof of an external sensor or separate administrative federation"
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def plan_parity_distinction(candidates: list[int], policy_digest: str) -> dict[str, Any]:
    """Use OE-003's existing model/policy-pinned minimum-cost witness checker.

    The given candidate states must be drawn from a separately verified Ground
    and observation fiber. There is no action word: the requested parity read
    directly distinguishes one even from one odd *candidate*. Other candidates
    of the same parity remain unresolved.
    """
    if (not isinstance(candidates, list) or not candidates
        or any(type(x) is not int or x not in range(8) for x in candidates)
        or len(set(candidates)) != len(candidates)
        or candidates != sorted(candidates)):
        raise ValueError("candidates must be sorted, distinct Z/8Z integers")
    if type(policy_digest) is not str or not policy_digest:
        raise ValueError("source policy identity is required")
    even = next((s for s in candidates if s % 2 == 0), None)
    odd = next((s for s in candidates if s % 2 == 1), None)
    if even is None or odd is None:
        raise ValueError("parity does not distinguish any pair in this observation fiber")
    states = tuple(str(s) for s in candidates)
    nav = CostedDistinctionNavigator(
        states, (), ("parity",),
        lambda state, test: int(state) % 2,
        lambda state, action: state,
    )
    plan = build_plan(
        nav, str(even), str(odd),
        request_id="gci004-far-y-parity-hypothesis-witness",
        source_policy_digest=policy_digest,
        action_costs=(), test_costs=(1,),
    )
    verify_plan(
        plan, expected_model_digest=plan["model_digest"],
        expected_source_policy_digest=policy_digest,
    )
    if (plan["selected"]["actions"] != [] or plan["selected"]["test"] != "parity"
        or plan["selected"]["expected"]["left"]["value"] != 0
        or plan["selected"]["expected"]["right"]["value"] != 1):
        raise ValueError("unexpected witness planner result")
    return plan


def filter_parity_candidates(candidates: list[int], reading: int) -> tuple[list[int], list[int]]:
    if type(reading) is not int or reading not in (0, 1):
        raise ValueError("signed parity reading must be exactly 0 or 1")
    matching = [s for s in candidates if s % 2 == reading]
    rejected = [s for s in candidates if s % 2 != reading]
    if not matching or not rejected:
        raise ValueError("reading does not discriminate the declared candidate fiber")
    return matching, rejected


def build_live_binding(directory: Path) -> dict[str, Any]:
    """Re-audit original GCI-004 artifacts before admitting any receipt reading."""
    import fabric_contract as fabric

    directory = Path(directory)
    audit = fabric.verified_report(directory)
    from intention_model import current_candidates
    from fabric_contract import cag

    public = cag.read(directory / "gci003-public.json")
    source_plan = cag.read(directory / "gci003-plan.json")
    network = cag.read(directory / "gci004-network.json")
    matching_cases = [case for case in source_plan["cases"]
                      if case["case_id"] == "far-y-parity" and case["selected"] == ["parity"]
                      and case["status"] in ("READY", "MEASURE")]
    if len(matching_cases) != 1:
        raise ValueError("GCI-003 has no uniquely authorized parity measurement case")
    case = matching_cases[0]
    receipts = [item for item in network["requests"]
                if item["request"]["task_id"] == case["case_id"]
                and item["request"]["feature"] == "parity"]
    if len(receipts) != 1:
        raise ValueError("missing or ambiguous E-CPU signed parity receipt")
    signed = receipts[0]
    reading = signed["payload"]["value"]
    candidates = current_candidates(public)
    # A real GCI-004 signed value selects a *fiber* rather than executing
    # or proving the two counterfactual model states in the OE-003 plan.
    model_plan = plan_parity_distinction(candidates, source_plan["report_digest"])
    matching, rejected = filter_parity_candidates(candidates, reading)

    discovery = [item for item in network["discovery"] if item["peer_id"] == signed["peer_id"]]
    if len(discovery) != 1:
        raise ValueError("signed receipt has no unique mTLS discovery identity")
    peer = discovery[0]
    if peer["feature"] != "parity":
        raise ValueError("signed parity receipt refers to a non-parity observer")
    core = {
        "schema": SCHEMA,
        "status": "authenticated-single-observation-filters-candidate-ground",
        "scope": SCOPE,
        "source_policy_digest": source_plan["report_digest"],
        "source_ground_binding": dict(network["binding"]),
        "source_phase_commitment": public["phase_commitment"],
        "gci004_network_digest": network["report_digest"],
        "gci004_independent_audit_digest": audit["report_digest"],
        "gci004_case_id": case["case_id"],
        "oe003_witness_plan": model_plan,
        "observation": {
            "feature": "parity",
            "peer_id": signed["peer_id"],
            "tls_leaf_certificate_sha256": hashlib.sha256(
                peer["certificate_pem"].encode("utf-8")).hexdigest(),
            "snapshot_digest": peer["snapshot_digest"],
            "request_digest": fabric.jdigest(signed["request"]),
            "request_challenge": signed["request"]["challenge"],
            "signed_receipt_digest": digest({
                "payload": signed["payload"],
                "signature_b64": signed["signature_b64"],
            }),
            "reading": reading,
            "measured_observation_rtt_ns": signed["observation_rtt_ns"],
        },
        "candidate_ground_states_before": candidates,
        "candidate_ground_states_compatible": matching,
        "candidate_ground_states_excluded": rejected,
        "authority_effect": "none-new",
        "ground_effect": "none-new",
        "interpretation": "retrospective-evidence-checked-filter-not-two-executed-lanes",
    }
    return {**core, "binding_digest": digest(core)}


def verify_live_binding(directory: Path, claim: Mapping[str, Any]) -> dict[str, Any]:
    """Independently reconstruct exact report from original signed artifacts."""
    if not isinstance(claim, Mapping):
        raise ValueError("OE-004 binding must be a mapping")
    expected = build_live_binding(directory)
    if dict(claim) != expected:
        raise ValueError("OE-004 binding disagrees with independently audited source evidence")
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        claim = json.loads(args.verify.read_text(encoding="utf-8"))
        result = verify_live_binding(args.directory, claim)
    else:
        result = build_live_binding(args.directory)
    output = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
