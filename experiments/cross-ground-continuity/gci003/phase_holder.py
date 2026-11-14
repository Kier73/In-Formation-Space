"""GCI-003 receiver-owned phase: public threshold, privately retained phase."""
from __future__ import annotations

import argparse
import secrets
from pathlib import Path

import intention_model as m
from mailcpu.law_certifier import lcg_navigate


def run(directory: Path) -> tuple[dict, dict]:
    binding = m.certificate_binding(directory)
    statement = m.cag.verify_intent(
        m.cag.read(directory / "signed-intent.json"),
        m.cag.read(directory / "issuer-trust.json"))
    law = statement["law"]
    tick = secrets.randbelow(8)
    x = lcg_navigate(law["multiplier"], law["increment"],
                     law["modulus"], law["initial"], tick)
    state = x % 8
    m.require(state == m.cag.state_at(tick) % 8,
              "E-CPU navigator differs from independent source oracle")
    public, private = m.make_context(binding, tick, state, secrets.token_hex(32))
    m.validate_private(private, public, binding)
    m.cag.persist(directory / "gci003-public.json", public)
    m.cag.persist(directory / "gci003-private.json", private)
    print("Public coarse observation:", public["report_digest"],
          "private phase commitment:", private["report_digest"])
    return public, private


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, required=True)
    args = p.parse_args()
    run(args.directory)


if __name__ == "__main__":
    main()
