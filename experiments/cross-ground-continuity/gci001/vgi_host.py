"""GCI-001 VGI realizer: independently execute 2D and quotient affine maps."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import continuity as g
from vgi.affine import ModularAffineMap


def run(directory: Path) -> dict:
    signed = g.cag.read(directory / "signed-intent.json")
    trust = g.cag.read(directory / "issuer-trust.json")
    statement = g.cag.verify_intent(signed, trust)
    law = statement["law"]
    m, x0 = law["modulus"], law["initial"]
    p, q = law["projection_multiplier"], law["projection_increment"]
    full_descriptor, reduced_descriptor = g.expected_maps(statement)
    full_map = ModularAffineMap(
        modulus=m,
        matrix=tuple(tuple(row) for row in full_descriptor["matrix"]),
        offset=tuple(full_descriptor["offset"]),
    )
    coarse_map = ModularAffineMap(
        modulus=g.QUOTIENT_MODULUS,
        matrix=tuple(tuple(row) for row in reduced_descriptor["matrix"]),
        offset=tuple(reduced_descriptor["offset"]),
    )
    g.require(full_map.to_dict() == full_descriptor and
              coarse_map.to_dict() == reduced_descriptor,
              "runtime normalized a different mathematical Ground")
    started = time.perf_counter_ns()
    rows = []
    for job in statement["jobs"]:
        t = job["coordinate"]
        x, y = full_map.power((x0, (p * x0 + q) % m), t)
        (qx,) = coarse_map.power((x0 % g.QUOTIENT_MODULUS,), t)
        g.require(y == (p * x + q) % m and
                  qx == x % g.QUOTIENT_MODULUS,
                  "observer projections are not compatible with the actual VGI transforms")
        rows.append({
            "job_id": job["job_id"], "coordinate": t,
            "state_value": x, "result_value": y,
            "coarse_state_value": qx,
            "coarse_result_value": (p * qx + q) % g.QUOTIENT_MODULUS,
            "semantic_result_digest": g.cag.semantic_result(job, y, statement),
        })
    body = {
        "schema": g.SCHEMA, "source_digest": g.cag.digest(statement),
        "vgi_revision": g.VGI_REFERENCE,
        "execution_method": "vgi.affine.ModularAffineMap.power",
        "full_map": full_map.to_dict(), "coarse_map": coarse_map.to_dict(),
        "observer_contexts": g.OBSERVERS,
        "observations": rows,
        "quotient_counterexample": g.expected_counterexample(statement),
        "closed_orbit_certificate_claimed": False,
        "independent_physical_observers_claimed": False,
        "local_elapsed_ns": time.perf_counter_ns() - started,
        "boundaries": g.SCOPE,
    }
    report = g.seal(body)
    g.verify_vgi(report, signed, trust)
    g.cag.persist(directory / "vgi-report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.directory)
        print("VGI full/coarse observations:", len(report["observations"]),
              report["report_digest"])
    except (g.ContinuityError, g.cag.TopologyError, ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"GCI-001 VGI refused: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
