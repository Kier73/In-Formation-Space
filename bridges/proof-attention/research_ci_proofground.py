"""USM-011: navigate an actual failed research invariant with VGI and IFS.

The observation is a real Python 3.11 GitHub Actions failure of the
branching-morphology self-cross identity. The *existing* VGI ProofGround
records mathematical intentions without inventing kernel receipts; the
*existing* IFS proof-attention planner selects unresolved verification work.
The experiment uses repaired IFS exact integer sine-frequency cancellation
directly, but does not promote a numerical regression test to Lean proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from vgi.proof import (
    ProofEnvironment, ProofGround, ProofHyperTransition, ProofObligation,
)
from proof_attention import build_proof_attention_plan
from mailcpu.computation_dag import ComputationNode, NavigableComputationDAG

MORPH_DIR = Path(__file__).resolve().parents[2] / "experiments" / "branching-morphology"
if str(MORPH_DIR) not in sys.path:
    sys.path.insert(0, str(MORPH_DIR))

from angular_support_cone import (
    cross_from_histograms, cross_sine_coefficients, guaranteed_angle,
    nested_tip_headings,
)

SCHEMA = "in-formation-space.usm011.real-invariant-navigation.v1"
SOURCE_SCHEMA = "in-formation-space.real-ci-invariant-observation.v1"
SOURCE_FILE = Path(__file__).resolve().parent / "evidence" / (
    "ifs_branching_morphology_ci_failure_20261114.json"
)


class RealInvariantError(ValueError):
    """The observed CI failure or its reconstructed obligation is invalid."""


def _digest(payload: Any) -> str:
    """Preserve the exact canonical evidence behind the research decision."""
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _check_source(observation: Any) -> dict[str, Any]:
    """Require exact source provenance and do not invent a failed loop depth."""
    if (not isinstance(observation, dict)
            or set(observation) != {"schema", "source", "classification"}
            or observation["schema"] != SOURCE_SCHEMA):
        raise RealInvariantError("unrecognized real CI invariant observation")
    source, classification = observation["source"], observation["classification"]
    if (not isinstance(source, dict) or not isinstance(classification, dict)
            or source.get("repository") != "Kier73/In-Formation-Space"
            or source.get("workflow") != "Branching morphology"
            or source.get("run_id") != 43629648833
            or source.get("job_id") != 132553219461
            or source.get("head_sha") != "7e7f86d7074eb676e2e022cd620b4b1a814c5873"
            or source.get("python_version") != "3.11.18"
            or source.get("job_conclusion") != "failure"
            or source.get("test_name") != (
                "test_angular_support_cone.AngularSupportingConeTests."
                "test_fake_path_counterexample_is_not_in_grammar_cone"
            )
            or source.get("test_path") != (
                "experiments/branching-morphology/test_angular_support_cone.py"
            )
            or source.get("assertion_line") != 94
            or source.get("expected") != "0.0"
            or source.get("observed") != "8.881784197001252e-16"
            or source.get("inspected_depths") != [1, 2, 3, 4, 5, 6]
            or source.get("failing_depth") != "not emitted by unittest"
            or source.get("run_url") != (
                "https://github.com/Kier73/In-Formation-Space/actions/runs/43629648833"
            )
            or source.get("job_url") != (
                "https://github.com/Kier73/In-Formation-Space/actions/runs/"
                "43629648833/job/132553219461"
            )
            or classification.get("external_kernel_receipt_available") is not False
            or classification.get("planned_method") != (
                "Pair equal-and-opposite sine-frequency terms in exact integer "
                "arithmetic before floating evaluation"
            )):
        raise RealInvariantError("CI evidence does not match the inspected failure")
    # This is a reproducible observation transcription, not a signature
    # issued by GitHub or a VGI kernel-verified proof receipt.
    return observation


def build_ground(observation: Mapping[str, Any]) -> tuple[ProofGround, str]:
    """Represent the *real* failure as VGI proof obligations without claims."""
    _check_source(observation)
    source = observation["source"]
    environment = ProofEnvironment(
        assistant="Python unittest",
        assistant_version=source["python_version"],
        environment_fingerprint=_digest({
            "repository": source["repository"],
            "run_id": source["run_id"],
            "head_sha": source["head_sha"],
            "job_id": source["job_id"],
        }),
        imports_fingerprint=_digest({
            "test_path": source["test_path"],
            "repair_source": "experiments/branching-morphology/angular_support_cone.py",
        }),
        options_fingerprint=_digest({
            "proof_mode": "separate-ci-observation-and-symbolic-cancellation",
            "kernel_receipts": [],
        }),
    )
    origin = ({
        "source_test": source["test_name"],
        "source_sha": source["head_sha"],
        "source_run": source["run_url"],
    },)
    root = ProofObligation(
        environment,
        goal={
            "kind": "exact_identity",
            "statement": "cross(H,H,theta)=0",
            "domain": "integer heading histograms and finite theta",
        },
        local_context=origin,
    )
    count = ProofObligation(
        environment,
        goal={
            "kind": "integer_antisymmetry",
            "statement": "for all d>0: N(d;H,H)=N(-d;H,H)",
        },
        local_context=origin,
    )
    projection = ProofObligation(
        environment,
        goal={
            "kind": "symbolic_evaluation",
            "statement": "zero signed coefficients produce float 0 without sin calls",
        },
        local_context=origin,
    )
    transitions = (
        ProofHyperTransition(
            root.fingerprint, "decompose-by-exact-sine-frequency",
            (count.fingerprint, projection.fingerprint),
            "elaborated",
            "experiments/branching-morphology/angular_support_cone.py:"
            "cross_sine_coefficients",
        ),
        ProofHyperTransition(
            count.fingerprint, "verify-integer-antisymmetry",
            (), "candidate",
            "experiments/branching-morphology/test_angular_support_cone.py:"
            "test_self_cross_exactly_zero_for_repeated_heading_multiplicities",
        ),
        ProofHyperTransition(
            projection.fingerprint, "verify-zero-term-projection",
            (), "candidate",
            "experiments/branching-morphology/test_angular_support_cone.py:"
            "test_fake_path_counterexample_is_not_in_grammar_cone",
        ),
    )
    ground = ProofGround(
        environment,
        (root, count, projection),
        transitions,
        receipts=(),  # No external proof-kernel checker was run.
        observed_kernel_claims=({
            "kind": "untrusted-CI-observation",
            "source_job": source["job_url"],
            "observed_float": source["observed"],
            "expected_float": source["expected"],
            "interpretation": "floating summation error, not formal theorem rejection",
        },),
    )
    return ground, root.fingerprint


def _navigate_native_research_dag(
    observation: Mapping[str, Any],
    root_id: str,
    plan: Mapping[str, Any],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Commit checked stages through E-CPU, leaving external authority pending.

    The graph proves the ordered source/evidence *workflow* can be
    reconstructed; it is not a theorem-proving oracle or a kernel receipt.
    """
    context = _digest(observation)
    source = observation["source"]
    steps = [
        ("ci-observation", (), "research.observe-ci-failure", {
            "source_job": source["job_url"],
            "source_sha": source["head_sha"],
            "actual": source["observed"],
        }),
        ("integer-antisymmetry", ("ci-observation",),
         "research.check-exact-difference-coefficients", {
            "checks_digest": _digest(checks),
            "all_coefficients_cancelled": all(
                item["exact_sine_coefficients"] == [] for item in checks
            ),
        }),
        ("numerical-projection", ("integer-antisymmetry",),
         "research.check-zero-term-evaluation", {
            "checks_digest": _digest(checks),
            "all_crosses_exactly_zero": all(
                item["numerical_cross"] == 0.0 for item in checks
            ),
        }),
        ("proof-attention", ("numerical-projection",),
         "research.navigate-vgi-proof-ground", {
            "root_obligation_id": root_id,
            "plan_digest": plan["plan_digest"],
            "unverified_reachable": plan["summary"]["unverified_reachable_count"],
        }),
        ("python-ci-regression", ("proof-attention",),
         "research.require-python-3.11-and-3.13-verification", {
            "required_interpreters": ["3.11", "3.13"],
            "previous_failed_job": source["job_url"],
            "check_status": "not-executed-in-this-evidence",
        }),
        ("external-proof-kernel", ("python-ci-regression",),
         "research.require-independent-proof-receipt", {
            "checker_receipt_available": False,
            "kernel_authority": "external",
        }),
    ]
    nodes = [
        ComputationNode(
            node_id=node_id,
            revision=1,
            operation=operation,
            resource=source["test_path"],
            context_digest=context,
            dependencies=parents,
            payload=payload,
        )
        for node_id, parents, operation, payload in steps
    ]
    graph = NavigableComputationDAG(nodes)
    checked = steps[:4]
    for node_id, _parents, operation, payload in checked:
        if node_id not in {item.node_id for item in graph.ready_nodes()}:
            raise RealInvariantError("native E-CPU research dependency was not ready")
        if graph.commit(node_id, {
            "operation": operation,
            "evidence_digest": _digest(payload),
            "source_observation_digest": context,
        }):
            raise RealInvariantError("unexpected duplicate evidence commit")
    snapshot = graph.snapshot()
    restored = NavigableComputationDAG.from_snapshot(snapshot)
    if (restored.snapshot() != snapshot
            or set(restored.committed_nodes) != {item[0] for item in checked}
            or {item.node_id for item in restored.ready_nodes()}
            != {"python-ci-regression"}):
        raise RealInvariantError("native E-CPU research evidence cannot be reconstructed")
    return {
        "snapshot": snapshot,
        "committed_observation_steps": list(restored.committed_nodes),
        "next_ready_operation": "python-ci-regression",
        "external_kernel_status": "receipt-absent-uncommitted",
    }


def investigate(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Exercise repaired exact computation and ask IFS to navigate the proof."""
    source = _check_source(observation)
    ground, root = build_ground(source)
    plan = build_proof_attention_plan(ground, (root,))
    if (
        plan["summary"]["active_root_count"] != 1
        or plan["summary"]["reachable_obligation_count"] != 3
        or plan["summary"]["candidate_action_count"] != 2
        or plan["summary"]["kernel_accepted_reachable_count"] != 0
        or plan["summary"]["unverified_reachable_count"] != 3
        or plan["interpretation"]["kernel_authority"] != (
            "external_verified_receipt_required"
        )
    ):
        raise RealInvariantError("VGI/IFS planner unexpectedly promoted proof evidence")
    # Direct operational use of the repaired source: navigation evaluates
    # the integer algebra first and the bounded floating projection second.
    checks = []
    for depth in source["source"]["inspected_depths"]:
        hist = nested_tip_headings(depth)
        coeffs = cross_sine_coefficients(hist, hist)
        numerical = cross_from_histograms(hist, hist, guaranteed_angle(depth))
        if coeffs or numerical != 0.0:
            raise RealInvariantError("source self-cross failed exact cancellation")
        checks.append({
            "depth": depth,
            "steps": sum(count for _, count in hist),
            "exact_sine_coefficients": [],
            "numerical_cross": numerical,
            "identity_holds_at_test_angle": True,
        })
    native_research = _navigate_native_research_dag(source, root, plan, checks)
    core = {
        "schema": SCHEMA,
        "observation_digest": _digest(source),
        "source_run_url": source["source"]["run_url"],
        "source_head_sha": source["source"]["head_sha"],
        "failing_test": source["source"]["test_name"],
        "diagnosis": "nonassociative floating sum vs exact antisymmetric identity",
        "ground_environment": ground.environment.to_dict(),
        "root_obligation_id": root,
        "ground_summary": ground.summary(),
        "proof_attention_plan": plan,
        "native_research_dag": native_research,
        "repair_checks": checks,
        "checked_interpreter": sys.version.split()[0],
        "external_kernel_receipt_admitted": False,
        "source_attestation": "transcribed public CI log, not a signed GitHub receipt",
        "native_research_execution": "E-CPU computation DAG + VGI ProofGround + IFS proof attention + repaired source call",
        "research_action": "run-regression-tests-on-python-3.11-and-3.13",
        "merge_authorized": False,
    }
    return {**core, "report_digest": _digest(core)}


def verify_report(observation: Mapping[str, Any], report: Mapping[str, Any]) -> bool:
    """Recreate the exact case from the fixed source and current local implementation."""
    try:
        return (isinstance(report, Mapping)
                and report["report_digest"] == _digest({
                    k: v for k, v in report.items() if k != "report_digest"
                })
                and investigate(observation) == report)
    except (KeyError, TypeError, ValueError):
        return False


def main() -> None:
    """Construct an evidence-linked VGI/IFS research navigation receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_FILE)
    parser.add_argument("--output", type=Path, default=Path("usm011-proof-attention.json"))
    args = parser.parse_args()
    observed = json.loads(args.source.read_text(encoding="utf-8"))
    result = investigate(observed)
    if not verify_report(observed, result):
        raise RealInvariantError("proof attention report could not be reconstructed")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "failure": result["source_run_url"],
        "unverified_obligations": result["ground_summary"]["unverified_obligations"],
        "candidate_next_actions": result["proof_attention_plan"]["summary"][
            "candidate_action_count"
        ],
        "exact_test_depths_rechecked": len(result["repair_checks"]),
        "external_kernel_receipt_admitted": False,
        "report_digest": result["report_digest"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
