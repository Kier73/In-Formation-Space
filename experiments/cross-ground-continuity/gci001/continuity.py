"""GCI-001: independent cross-Ground continuity auditor.

This verifier deliberately imports no E-CPU or VGI runtime. CAG-004 owns
the signed source and three topology claims; this module checks the distinct
VGI state/observer representation against that same source.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping

CAG_DIR = Path(__file__).resolve().parents[2] / "convergent-ground-fabric" / "cag004"
sys.path.insert(0, str(CAG_DIR))
import contract as cag

SCHEMA = "in-formation.gci001-vgi-ground/0.1"
AUDIT_SCHEMA = "in-formation.gci001-cross-ground-audit/0.1"
VGI_REFERENCE = "093f11e458aff1c223d639ede413000619767ba6"
QUOTIENT_MODULUS = 8
OBSERVERS = [
    {"id": "state", "projection": "x", "modulus": 65536},
    {"id": "result", "projection": "3*x+11", "modulus": 65536},
    {"id": "coarse", "projection": "x mod 8", "modulus": 8},
]
SCOPE = [
    "Two mathematical observer projections and one lossy quotient, not three independent physical sensors.",
    "VGI ModularAffineMap.power is exact arithmetic, not a certified closed VGI OrbitIndex.",
    "CAG-004 checks declared E-CPU logical topology and receiver authority, not a physical one/two-port chip.",
    "The cross-Ground verifier checks signed source and independently reported execution, not host execution by direct observation.",
    "The quotient preserves the projected result modulo eight, but cannot identify the full result without additional context.",
    "No general neural, universal Ground, arbitrary host, or wall-clock performance claim is made.",
]


class ContinuityError(ValueError):
    pass


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ContinuityError(why)


def expected_maps(statement: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive two distinct VGI maps from the separately signed CAG law."""
    law = statement["law"]
    m, a, b = law["modulus"], law["multiplier"], law["increment"]
    p, q = law["projection_multiplier"], law["projection_increment"]
    full = {
        "format": "VGI-ModularAffineMap-1",
        "domain": {"ring": "Z/modulus Z", "modulus": m, "dimension": 2},
        "matrix": [[a % m, 0], [(p * a) % m, 0]],
        "offset": [b % m, (p * b + q) % m],
        "equation": "x_next = M*x + b (mod modulus)",
    }
    reduced = {
        "format": "VGI-ModularAffineMap-1",
        "domain": {"ring": "Z/modulus Z", "modulus": QUOTIENT_MODULUS, "dimension": 1},
        "matrix": [[a % QUOTIENT_MODULUS]],
        "offset": [b % QUOTIENT_MODULUS],
        "equation": "x_next = M*x + b (mod modulus)",
    }
    return full, reduced


def expected_counterexample(statement: Mapping[str, Any]) -> dict[str, Any]:
    """Two *reachable* coordinates collide under q8 when time is withheld."""
    law = statement["law"]
    a = cag.state_at(0)
    b = cag.state_at(8)
    m = law["modulus"]
    p, q = law["projection_multiplier"], law["projection_increment"]
    require(a != b and a % 8 == b % 8, "quotient counterexample is not discriminating")
    return {
        "coordinate_a": 0, "coordinate_b": 8,
        "state_a": a, "state_b": b,
        "coarse_a": a % 8, "coarse_b": b % 8,
        "result_a": (p * a + q) % m,
        "result_b": (p * b + q) % m,
        "coordinate_observed": False,
        "full_result_identifiable_from_coarse_alone": False,
    }


def seal(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "report_digest": cag.digest(body)}


def verify_vgi(report: Mapping[str, Any], signed: Mapping[str, Any],
               trust: Mapping[str, Any]) -> list[dict[str, Any]]:
    """No VGI imports: recalculate oracle and audit every claimed observer."""
    statement = cag.verify_intent(signed, trust)
    require(type(report) is dict and set(report) == {
        "schema", "source_digest", "vgi_revision", "execution_method",
        "full_map", "coarse_map", "observer_contexts", "observations",
        "quotient_counterexample", "closed_orbit_certificate_claimed",
        "independent_physical_observers_claimed", "local_elapsed_ns",
        "boundaries", "report_digest",
    }, "unexpected VGI report schema")
    body = {k: v for k, v in report.items() if k != "report_digest"}
    require(report["report_digest"] == cag.digest(body), "VGI report digest mismatch")
    require(report["schema"] == SCHEMA and
            report["source_digest"] == cag.digest(statement) and
            report["vgi_revision"] == VGI_REFERENCE and
            report["execution_method"] == "vgi.affine.ModularAffineMap.power" and
            report["closed_orbit_certificate_claimed"] is False and
            report["independent_physical_observers_claimed"] is False and
            type(report["local_elapsed_ns"]) is int and report["local_elapsed_ns"] >= 0 and
            report["boundaries"] == SCOPE, "unsupported VGI execution or scope claim")
    full, reduced = expected_maps(statement)
    require(report["full_map"] == full and report["coarse_map"] == reduced and
            report["observer_contexts"] == OBSERVERS,
            "Ground representation or observer contract diverged from signed law")
    require(report["quotient_counterexample"] == expected_counterexample(statement),
            "coarse quotient was promoted into full semantic equality")

    rows = report["observations"]
    require(type(rows) is list and len(rows) == len(statement["jobs"]),
            "missing or extra VGI observations")
    results = []
    for job, row in zip(statement["jobs"], rows):
        coordinate = job["coordinate"]
        expected_x = cag.state_at(coordinate)
        expected_y = cag.observed_at(coordinate)
        expected = {
            "job_id": job["job_id"], "coordinate": coordinate,
            "state_value": expected_x, "result_value": expected_y,
            "coarse_state_value": expected_x % QUOTIENT_MODULUS,
            "coarse_result_value": expected_y % QUOTIENT_MODULUS,
            "semantic_result_digest": cag.semantic_result(job, expected_y, statement),
        }
        require(type(row) is dict and set(row) == set(expected),
                "unexpected VGI observation fields")
        require(all(type(row[k]) is int for k in
                    ("coordinate", "state_value", "result_value",
                     "coarse_state_value", "coarse_result_value")),
                "noninteger observer value")
        require(row == expected, "VGI observation or intention identity disagrees")
        results.append({"job_id": job["job_id"], "coordinate": coordinate,
                        "semantic_result_digest": expected["semantic_result_digest"],
                        "full_state": expected_x, "full_result": expected_y,
                        "coarse_state": expected_x % 8,
                        "coarse_result": expected_y % 8})
    return results


def verify_all(directory: Path) -> dict[str, Any]:
    """Apply existing CAG-004 independent audit, then cross-check VGI Ground."""
    signed = cag.read(directory / "signed-intent.json")
    trust = cag.read(directory / "issuer-trust.json")
    internal = cag.read(directory / "internal-report.json")
    receiver = cag.read(directory / "receiver-report.json")
    vgi = cag.read(directory / "vgi-report.json")
    topology = cag.verify(internal, receiver, signed, trust)
    results = verify_vgi(vgi, signed, trust)
    require(len(results) == len(topology["results"]), "topology count differs")
    for left, right in zip(results, topology["results"]):
        require(left["semantic_result_digest"] == right["semantic_result_digest"] and
                left["coordinate"] == right["coordinate"] and
                left["full_result"] == right["observed_value"],
                "cross-Ground semantic mismatch")
    return seal({
        "schema": AUDIT_SCHEMA,
        "status": "bounded_cross_ground_continuity_verified",
        "source_digest": cag.digest(signed["statement"]),
        "topology_report_digest": topology["report_digest"],
        "internal_report_digest": internal["report_digest"],
        "receiver_report_digest": receiver["report_digest"],
        "vgi_report_digest": vgi["report_digest"],
        "matched_results": results,
        "observer_distinction": "full affine projection preserved; lossy quotient only modulo 8",
        "boundaries": SCOPE,
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["verify"])
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_all(args.directory)
        cag.persist(args.directory / "continuity-audit.json", result)
        print(result["status"], result["report_digest"])
    except (cag.TopologyError, ContinuityError, KeyError, TypeError, OSError, ValueError) as exc:
        parser.exit(1, f"GCI-001 refused: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
