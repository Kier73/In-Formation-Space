"""GCI-003 receiver-side authorized feature readings, no phase disclosure."""
from __future__ import annotations

import argparse
from pathlib import Path

import intention_model as m
from mailcpu.law_certifier import lcg_navigate


def run(directory: Path) -> dict:
    binding = m.certificate_binding(directory)
    public = m.cag.read(directory / "gci003-public.json")
    private = m.cag.read(directory / "gci003-private.json")
    requested = m.cag.read(directory / "gci003-plan.json")
    state = m.validate_private(private, public, binding)
    statement = m.cag.verify_intent(
        m.cag.read(directory / "signed-intent.json"),
        m.cag.read(directory / "issuer-trust.json"))
    law = statement["law"]
    actual = lcg_navigate(law["multiplier"], law["increment"],
                          law["modulus"], law["initial"], private["tick"]) % 8
    m.require(actual == state, "receiver-owned E-CPU phase mismatches source")
    report = m.measure(public, private, requested, binding)
    m.cag.persist(directory / "gci003-measurements.json", report)
    print("Authorized feature observations:", report["report_digest"])
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, required=True)
    args = p.parse_args()
    run(args.directory)


if __name__ == "__main__":
    main()
