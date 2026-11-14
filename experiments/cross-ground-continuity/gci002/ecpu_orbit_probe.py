"""GCI-002 independent E-CPU host: observe eight calculated orbit edges.

An exact signed mathematical request, not a sensor experiment. The host
uses the actual pinned E-CPU law navigator and exports its own observations.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import contract as c
from mailcpu.law_certifier import lcg_navigate


def run(directory: Path) -> dict:
    signed = c.cag.read(directory / "signed-intent.json")
    trust = c.cag.read(directory / "issuer-trust.json")
    statement = c.cag.verify_intent(signed, trust)
    law = statement["law"]
    started = time.perf_counter_ns()
    rows = []
    for t in range(8):
        state = lcg_navigate(law["multiplier"], law["increment"],
                             law["modulus"], law["initial"], t)
        following = lcg_navigate(law["multiplier"], law["increment"],
                                 law["modulus"], law["initial"], t+1)
        c.require(following == (law["multiplier"] * state + law["increment"]) % law["modulus"],
                  "E-CPU pure oracle contradicts one-step law")
        rows.append({"coordinate": t, "full_state": state,
                     "full_next_state": following,
                     "state": state % 8, "next_state": following % 8})
    report = c.seal({
        "schema": c.PROBE_SCHEMA, "source_digest": c.cag.digest(statement),
        "ecpu_revision": c.ECPU_REVISION, "method": "mailcpu.law_certifier.lcg_navigate",
        "observation_kind": c.EVIDENCE_SCOPE,
        "observations": rows, "local_elapsed_ns": time.perf_counter_ns() - started,
    })
    c.verified_probe(report, statement)
    c.cag.persist(directory / "orbit-probe.json", report)
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, required=True)
    a = p.parse_args()
    result = run(a.directory)
    print("E-CPU observed orbit:", len(result["observations"]), result["report_digest"])


if __name__ == "__main__":
    main()
