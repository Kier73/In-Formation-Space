"""CGS-007 — historical E-CPU observer receipts as intention-scoped Ground constraints.

The source is not manufactured by this experiment. A successful GCI-005
GitHub-hosted run produced actual E-CPU loopback-mTLS leaf-key signatures.
This bridge independently rechecks the original signed intention, admitted
VGI orbit and GCI-005 signed receipts *at a GH-run-supplied historical time*,
and then uses only the signed parity result to narrow an eight-state Ground.

The GitHub CLI workflow MUST separately verify artifact attestations and the
exact run/head identity. This file cannot authenticate GitHub metadata alone.
It never restores current credential authority from an old certificate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve()
GCI_ROOT = HERE.parents[1] / "cross-ground-continuity"
sys.path.insert(0, str(GCI_ROOT / "gci005"))
import honesty_contract as h  # noqa: E402

gci3 = h.gci3
cag = h.cag
c = h.c

SOURCE_RUN = 43616685083
SOURCE_SHA = "90e719ae6efab12107ee8de2b77afe5e73dd35b2"
SOURCE_WORKFLOW = ".github/workflows/cag004-topology-neutral.yml"
SCHEMA = "ifs.cgs007-historical-observer-constraint/0.1"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("CGS-007 refused: " + message)


def parse_utc(s: Any) -> dt.datetime:
    require(type(s) is str and re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z", s) is not None,
        "UTC timestamps must have explicit Z suffix")
    return dt.datetime.fromisoformat(s[:-1] + "+00:00")


def anchored_time(metadata: Mapping[str, Any]) -> dt.datetime:
    """Validate declared GitHub run metadata shape, not GH API authenticity."""
    require(type(metadata) is dict and all(
        metadata.get(key) == value for key, value in {
            "id": SOURCE_RUN, "head_sha": SOURCE_SHA,
            "event": "push", "head_branch": "main",
            "path": SOURCE_WORKFLOW, "status": "completed",
            "conclusion": "success"}.items()), "source run identity differs")
    started = parse_utc(metadata.get("run_started_at"))
    finished = parse_utc(metadata.get("updated_at"))
    require(started <= finished <= started + dt.timedelta(hours=24),
            "source run chronology invalid")
    return finished


def project_rounds(public: Mapping[str, Any],
                   verified: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Pure intention-relative projection; does not handle keys or certificates."""
    candidates = gci3.current_candidates(public)
    require(len(candidates) > 0, "no original threshold candidates")
    task = next(t for t in gci3.TASKS if t["id"] == h.TASK)
    require(task["target"] == "y-parity" and
            gci3.HUGE_ODD == task["horizon"], "source task shifted")
    rows = verified.get("rounds")
    require(type(rows) is list and len(rows) == 2, "two receipt rounds required")
    output = []
    for index, round_ in enumerate(rows):
        status = round_["verdict"]
        values = round_["peer_readings"]
        require(type(values) is list and len(values) == 2 and
                all(type(x) is int and x in (0, 1) for x in values),
                "strict paired parity bits required")
        require(status == ("ADMITTED_AGREEMENT" if index == 0
                           else "REFUSED_DISAGREEMENT") and
                ((values[0] == values[1]) == (index == 0)),
                "historical scenario or verdict differs")
        filtered = ([s for s in candidates if gci3.feature("parity", s) == values[0]]
                    if index == 0 else list(candidates))
        answers = sorted(set(gci3.intention_value(task, s) for s in filtered))
        require(filtered and answers, "empty verified phase fiber")
        if index == 0:
            require(len(answers) == 1, "signed parity does not determine intention")
        output.append({
            "scenario": h.SCENARIOS[index],
            "receipt_status": status,
            "prior_phase_count": len(candidates),
            "admissible_phase_candidates": filtered,
            "allowed_intention_values": answers,
            "mathematically_determined": len(answers) == 1,
            "measurement_used": index == 0,
            "current_execution_authorized": False,
            "reason": ("historical signed parity narrows a certified Ground"
                       if index == 0 else
                       "signed conflict: refuse to choose a peer's value"),
        })
    return output


def replay(directory: Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Historical cryptographic replay and a new phase-blind Ground projection."""
    validation_time = anchored_time(metadata)
    binding, public, plan = h.get_binding(directory)  # signed intention + VGI Ground
    gci3.validate_public(public, binding)
    report = cag.read(directory / "gci005-quorum.json")
    network = cag.read(directory / "gci004-network.json")
    gci3.check_sealed(network, {
        "schema", "binding", "public_digest", "plan_digest",
        "origin", "ca_certificate_pem", "client_certificate_pem",
        "discovery", "requests", "measurements", "realization", "scope",
        "transport_kind", "bad_hostname_refused", "forbidden_feature_refused",
        "replay_refused"}, c.SCHEMA)
    require(network["report_digest"] == report["source_gci004_report_digest"],
            "network and signed quorum report not linked")
    summary = h.verify_record(report, binding, public, plan,
                              certificate_time=validation_time)
    expected = c.sealed({
        "schema": h.AUDIT_SCHEMA,
        "status": "authenticated_disagreement_refused_without_phase",
        "ground_fingerprint": binding["ground_fingerprint"],
        "source_digest": binding["source_digest"],
        "public_digest": public["report_digest"],
        "gci004_report_digest": network["report_digest"],
        "gci005_report_digest": report["report_digest"],
        "rounds": summary["rounds"],
        "blind_auditor_received_phase": False,
        "scope": h.SCOPE,
    })
    blind = cag.read(directory / "gci005-blind-audit.json")
    require(blind == expected, "independent phase-blind audit differs")
    rows = project_rounds(public, summary)
    require(not (directory / "gci003-private.json").exists(),
            "private phase accidentally present in blind bridge directory")
    return {
        "schema": SCHEMA,
        "source_run": SOURCE_RUN, "source_commit": SOURCE_SHA,
        "evidence_validation_time": validation_time.isoformat(),
        "source_ground_fingerprint": binding["ground_fingerprint"],
        "source_intention_digest": binding["source_digest"],
        "source_signed_report_digest": report["report_digest"],
        "source_blind_audit_digest": blind["report_digest"],
        "source_public_digest": public["report_digest"],
        "initial_threshold_bit": public["observer"]["value"],
        "source_task": h.TASK,
        "rounds": rows,
        "historical_signature_check": "passed",
        "historical_authority_scope": "one-run ephemeral CA and E-CPU loopback peers",
        "current_authority": False,
        "private_phase_consumed": False,
        "provenance_requirement":
            "caller must independently verify GitHub artifact attestations and run SHA",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata = json.loads(args.run_metadata.read_text(encoding="utf8"))
    report = replay(args.directory, metadata)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2)+"\n", encoding="utf8")
    print("historical-signed-constraint-reconstructed",
          report["source_signed_report_digest"])


if __name__ == "__main__":
    main()
