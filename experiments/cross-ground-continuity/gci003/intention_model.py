"""GCI-003: bounded intention-relative observation sufficiency.

The planner is intentionally blind to the receiver's private phase. It reads
only the signed CAG-004 source, independently audited GCI-002 closed Ground,
and a coarse observer value. Measurement selection is exact finite quotient
refinement, NOT a claimed general optimizer or a real-cost benchmark.
"""
from __future__ import annotations

import argparse
import itertools
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gci002"))
import ground_contract as gci2

cag = gci2.cag
SCHEMA_PUBLIC = "in-formation.gci003-public-context/0.1"
SCHEMA_PRIVATE = "in-formation.gci003-private-phase/0.1"
SCHEMA_PLAN = "in-formation.gci003-observation-plan/0.1"
SCHEMA_MEASUREMENT = "in-formation.gci003-controlled-measurement/0.1"
SCHEMA_RESULT = "in-formation.gci003-blind-realization/0.1"
SCHEMA_AUDIT = "in-formation.gci003-independent-sufficiency-audit/0.1"
SAMPLE = "receiver-owned-sampled-orbit-001"
SCOPE = "logical-mathematical-phase-withheld-from-planner-and-resolver"
PROVIDER = "receiver-owned-pinned-ecpu-measurement-simulator"
HUGE_ODD = 10**15 + 137
HUGE_MULTIPLE_EIGHT = 10**15 + 136

# Costs are declared symbolic observation units. Neither network nor energy
# measurements are inferred from them. All features are receiver-owned.
FEATURES = {
    "parity": {"cost": 1, "range": (0, 1)},
    "bit1": {"cost": 1, "range": (0, 1)},
    "low2": {"cost": 2, "range": (0, 1, 2, 3)},
}
TASKS = (
    {"id": "period-threshold", "target": "threshold", "horizon": HUGE_MULTIPLE_EIGHT,
     "permitted": ()},
    {"id": "far-y-parity", "target": "y-parity", "horizon": HUGE_ODD,
     "permitted": ("parity", "low2")},
    {"id": "next-threshold", "target": "threshold", "horizon": 1,
     "permitted": ("parity", "bit1", "low2")},
    {"id": "restricted-far-y-mod8", "target": "y-mod8", "horizon": HUGE_ODD,
     "permitted": ("parity",)},
)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class SufficiencyRefused(ValueError):
    pass


def require(condition: bool, why: str) -> None:
    if not condition:
        raise SufficiencyRefused(why)


def strict_hash(value: Any, label: str) -> None:
    require(type(value) is str and HEX64.fullmatch(value) is not None, label)


def sealed(body: Mapping[str, Any]) -> dict[str, Any]:
    return gci2.seal(dict(body))


def check_sealed(record: Mapping[str, Any], fields: set[str], schema: str) -> None:
    require(type(record) is dict and set(record) == fields | {"report_digest"},
            f"{schema} field set differs")
    require(record.get("schema") == schema, "wrong schema")
    require(record.get("report_digest") ==
            cag.digest({k: v for k, v in record.items() if k != "report_digest"}),
            "report content digest differs")


def certificate_binding(directory: Path) -> dict[str, str]:
    signed = cag.read(directory / "signed-intent.json")
    trust = cag.read(directory / "issuer-trust.json")
    statement = cag.verify_intent(signed, trust)
    probe = cag.read(directory / "orbit-probe.json")
    vgi = cag.read(directory / "closed-orbit-report.json")
    # Runtime-free reproduction: not simply accepting a certificate-shaped JSON.
    gci2.verify_vgi(vgi, probe, statement)
    return {
        "source_digest": cag.digest(statement),
        "ground_fingerprint": vgi["ground_fingerprint"],
        "orbit_certificate_fingerprint": vgi["orbit_certificate_fingerprint"],
        "gci002_report_digest": vgi["report_digest"],
    }


def check_binding(binding: Any) -> None:
    require(type(binding) is dict and set(binding) == {
        "source_digest", "ground_fingerprint",
        "orbit_certificate_fingerprint", "gci002_report_digest",
    }, "certificate binding fields differ")
    for key, value in binding.items():
        strict_hash(value, key)


def feature(name: str, state: int) -> int:
    require(name in FEATURES and type(state) is int and 0 <= state < 8,
            "unsupported feature or state")
    return {"parity": state % 2, "bit1": (state >> 1) & 1,
            "low2": state % 4}[name]


def threshold(state: int) -> int:
    require(type(state) is int and 0 <= state < 8, "invalid finite state")
    return int(state >= 4)


def jump_mod8(state: int, steps: int) -> int:
    """Independent O(log steps) powering of the GCI-002 affine transition."""
    require(type(state) is int and 0 <= state < 8 and
            type(steps) is int and 0 <= steps <= 10**18, "invalid jump")
    a, b, pa, pb, t = 1, 0, 5, 1, steps
    while t:
        if t & 1:
            a, b = (pa * a) % 8, (pa * b + pb) % 8
        pa, pb = (pa * pa) % 8, (pa * pb + pb) % 8
        t >>= 1
    return (a * state + b) % 8


def intention_value(task: Mapping[str, Any], state: int) -> int:
    future = jump_mod8(state, task["horizon"])
    if task["target"] == "threshold":
        return threshold(future)
    if task["target"] == "y-parity":
        return (3 * future + 11) % 2
    if task["target"] == "y-mod8":
        return (3 * future + 11) % 8
    raise SufficiencyRefused("unknown intention target")


def private_commitment(binding: Mapping[str, str], tick: int, state: int,
                       nonce_hex: str) -> str:
    return cag.digest({
        "sample_id": SAMPLE, "source_digest": binding["source_digest"],
        "tick": tick, "state": state, "nonce_hex": nonce_hex,
    })


def make_context(binding: Mapping[str, str], tick: int, state: int,
                 nonce_hex: str) -> tuple[dict[str, Any], dict[str, Any]]:
    check_binding(binding)
    require(type(tick) is int and 0 <= tick < 8 and
            type(state) is int and state == cag.state_at(tick) % 8,
            "held state does not correspond to source orbit coordinate")
    strict_hash(nonce_hex, "private nonce")
    commitment = private_commitment(binding, tick, state, nonce_hex)
    public = sealed({
        "schema": SCHEMA_PUBLIC, "binding": dict(binding), "sample_id": SAMPLE,
        "observer": {"name": "threshold", "value": threshold(state)},
        "phase_commitment": commitment, "scope": SCOPE,
    })
    private = sealed({
        "schema": SCHEMA_PRIVATE, "public_digest": public["report_digest"],
        "tick": tick, "state": state, "nonce_hex": nonce_hex,
        "phase_commitment": commitment, "scope": SCOPE,
    })
    return public, private


def validate_public(public: Mapping[str, Any], binding: Mapping[str, str]) -> None:
    check_binding(binding)
    check_sealed(public, {"schema", "binding", "sample_id", "observer",
                          "phase_commitment", "scope"}, SCHEMA_PUBLIC)
    require(public["binding"] == binding and public["sample_id"] == SAMPLE and
            public["scope"] == SCOPE and
            type(public["observer"]) is dict and
            set(public["observer"]) == {"name", "value"} and
            public["observer"]["name"] == "threshold" and
            type(public["observer"]["value"]) is int and
            public["observer"]["value"] in (0, 1),
            "public information or observer is not admitted")
    strict_hash(public["phase_commitment"], "phase commitment")


def validate_private(private: Mapping[str, Any], public: Mapping[str, Any],
                     binding: Mapping[str, str]) -> int:
    validate_public(public, binding)
    check_sealed(private, {"schema", "public_digest", "tick", "state",
                           "nonce_hex", "phase_commitment", "scope"}, SCHEMA_PRIVATE)
    tick, state = private["tick"], private["state"]
    require(type(tick) is int and 0 <= tick < 8 and
            type(state) is int and 0 <= state < 8 and
            state == cag.state_at(tick) % 8 and
            type(private["nonce_hex"]) is str,
            "held phase does not match exact original source")
    strict_hash(private["nonce_hex"], "phase nonce")
    require(private["public_digest"] == public["report_digest"] and
            private["phase_commitment"] ==
            private_commitment(binding, tick, state, private["nonce_hex"]) ==
            public["phase_commitment"] and
            private["scope"] == SCOPE and
            threshold(state) == public["observer"]["value"],
            "public-private observation commitment mismatch")
    return state


def current_candidates(public: Mapping[str, Any]) -> list[int]:
    value = public["observer"]["value"]
    return [s for s in range(8) if threshold(s) == value]


def suffices(task: Mapping[str, Any], states: list[int],
             selected: tuple[str, ...]) -> tuple[bool, tuple[int, int] | None]:
    """For every current observation fiber, T must be constant."""
    groups: dict[tuple[int, ...], tuple[int, int]] = {}
    for state in states:
        key = tuple(feature(name, state) for name in selected)
        result = intention_value(task, state)
        previous = groups.get(key)
        if previous is not None and previous[1] != result:
            return False, (previous[0], state)
        groups.setdefault(key, (state, result))
    return True, None


def choose_task(task: Mapping[str, Any], public: Mapping[str, Any]) -> dict[str, Any]:
    """Choose the lowest symbolic-cost sufficient available measurement set."""
    states = current_candidates(public)
    allow = tuple(task["permitted"])
    require(len(allow) == len(set(allow)) and
            all(name in FEATURES for name in allow), "invalid capability policy")
    choices = []
    for width in range(len(allow) + 1):
        for combo in itertools.combinations(sorted(allow), width):
            works, _ = suffices(task, states, combo)
            if works:
                choices.append((sum(FEATURES[x]["cost"] for x in combo),
                                len(combo), combo))
    if not choices:
        _, witness = suffices(task, states, tuple(sorted(allow)))
        require(witness is not None, "refusal lacks a discriminating witness")
        a, b = witness
        return {
            "case_id": task["id"], "status": "REFUSE",
            "target": task["target"], "horizon": task["horizon"],
            "permitted": list(allow), "selected": [], "symbolic_cost": 0,
            "candidate_count": len(states), "result": None,
            "counterexample": {
                "a": a, "b": b,
                "same_public": threshold(a) == threshold(b),
                "same_permitted": all(feature(name, a) == feature(name, b)
                                      for name in allow),
                "different_target": [intention_value(task, a),
                                     intention_value(task, b)],
            },
        }
    cost, count, combo = min(choices)
    ready = count == 0
    return {
        "case_id": task["id"], "status": "READY" if ready else "MEASURE",
        "target": task["target"], "horizon": task["horizon"],
        "permitted": list(allow), "selected": list(combo),
        "symbolic_cost": cost, "candidate_count": len(states),
        "result": intention_value(task, states[0]) if ready else None,
        "counterexample": None,
    }


def plan(public: Mapping[str, Any], binding: Mapping[str, str]) -> dict[str, Any]:
    validate_public(public, binding)
    return sealed({
        "schema": SCHEMA_PLAN, "binding": dict(binding),
        "public_digest": public["report_digest"],
        "method": "exhaustive-eight-state-fiber-minimum-declared-cost",
        "cost_scope": "symbolic-declared-cost-not-elapsed-time",
        "cases": [choose_task(task, public) for task in TASKS],
    })


def validate_plan(report: Mapping[str, Any], public: Mapping[str, Any],
                  binding: Mapping[str, str]) -> None:
    check_sealed(report, {"schema", "binding", "public_digest", "method",
                          "cost_scope", "cases"}, SCHEMA_PLAN)
    require(report == plan(public, binding),
            "planner failed exact minimum sufficient projection reconstruction")


def measure(public: Mapping[str, Any], private: Mapping[str, Any],
            requested: Mapping[str, Any], binding: Mapping[str, str]) -> dict[str, Any]:
    state = validate_private(private, public, binding)
    validate_plan(requested, public, binding)
    entries = []
    for task, row in zip(TASKS, requested["cases"]):
        # No unrequested features or full state may appear in the response.
        names = row["selected"]
        require(set(names).issubset(set(task["permitted"])),
                "measurement not authorized for this intention")
        entries.append({
            "case_id": task["id"],
            "readings": [{"name": name, "value": feature(name, state)}
                         for name in names],
        })
    return sealed({
        "schema": SCHEMA_MEASUREMENT, "binding": dict(binding),
        "public_digest": public["report_digest"],
        "plan_digest": requested["report_digest"],
        "producer": PROVIDER, "phase_commitment": public["phase_commitment"],
        "entries": entries, "state_or_phase_disclosed": False,
    })


def resolve(public: Mapping[str, Any], requested: Mapping[str, Any],
            measurements: Mapping[str, Any], binding: Mapping[str, str]) -> dict[str, Any]:
    validate_plan(requested, public, binding)
    check_sealed(measurements, {"schema", "binding", "public_digest",
                  "plan_digest", "producer", "phase_commitment", "entries",
                  "state_or_phase_disclosed"}, SCHEMA_MEASUREMENT)
    require(measurements["binding"] == binding and
            measurements["public_digest"] == public["report_digest"] and
            measurements["plan_digest"] == requested["report_digest"] and
            measurements["producer"] == PROVIDER and
            measurements["phase_commitment"] == public["phase_commitment"] and
            measurements["state_or_phase_disclosed"] is False,
            "measurement origin/authority/identity mismatch")
    rows = measurements["entries"]
    require(type(rows) is list and len(rows) == len(TASKS),
            "missing or extra intentions in receiver reply")
    results = []
    for task, row, answer in zip(TASKS, requested["cases"], rows):
        names = row["selected"]
        require(type(answer) is dict and set(answer) == {"case_id", "readings"}
                and answer["case_id"] == task["id"] and
                type(answer["readings"]) is list and
                len(answer["readings"]) == len(names),
                "unexpected measurement count or identity")
        candidates = current_candidates(public)
        for name, measurement in zip(names, answer["readings"]):
            require(type(measurement) is dict and
                    set(measurement) == {"name", "value"} and
                    measurement["name"] == name and
                    type(measurement["value"]) is int and
                    measurement["value"] in FEATURES[name]["range"],
                    "unexpected, disallowed, or invalid measurement value")
            candidates = [s for s in candidates
                          if feature(name, s) == measurement["value"]]
        if row["status"] == "REFUSE":
            require(not names and not answer["readings"], "refused intention performed measurement")
            value = None
            status = "REFUSED_INSUFFICIENT_CONTEXT"
        else:
            outcomes = {intention_value(task, s) for s in candidates}
            require(candidates and len(outcomes) == 1,
                    "measurement does not resolve intended output")
            value = next(iter(outcomes))
            require(row["status"] != "READY" or value == row["result"],
                    "ready intention changed after resolution")
            status = "RESOLVED_WITHOUT_QUERY" if row["status"] == "READY" else "RESOLVED_AFTER_QUERY"
        results.append({
            "case_id": task["id"], "status": status, "result": value,
            "remaining_candidates": len(candidates),
            "query_names": names,
        })
    return sealed({
        "schema": SCHEMA_RESULT, "binding": dict(binding),
        "public_digest": public["report_digest"],
        "plan_digest": requested["report_digest"],
        "measurements_digest": measurements["report_digest"],
        "phase_visible_to_resolver": False, "results": results,
    })


def audit(directory: Path) -> dict[str, Any]:
    # Entire GCI-001 and GCI-002 chain before this independent result.
    prior = gci2.verify_all(directory)
    binding = certificate_binding(directory)
    public = cag.read(directory / "gci003-public.json")
    private = cag.read(directory / "gci003-private.json")
    requested = cag.read(directory / "gci003-plan.json")
    response = cag.read(directory / "gci003-measurements.json")
    result = cag.read(directory / "gci003-result.json")
    state = validate_private(private, public, binding)
    validate_plan(requested, public, binding)
    expected_response = measure(public, private, requested, binding)
    require(response == expected_response,
            "measurement receiver did not reveal exact permitted observation")
    expected_result = resolve(public, requested, response, binding)
    require(result == expected_result, "blind receiver did not realize certified intention")
    for task, item in zip(TASKS, result["results"]):
        if item["status"] != "REFUSED_INSUFFICIENT_CONTEXT":
            require(item["result"] == intention_value(task, state),
                    "recovered result differs from held source Ground state")
    return sealed({
        "schema": SCHEMA_AUDIT, "status": "intention_relative_context_sufficiency_verified",
        "source_digest": binding["source_digest"],
        "gci002_audit_digest": prior["report_digest"],
        "public_digest": public["report_digest"],
        "private_digest": private["report_digest"],
        "plan_digest": requested["report_digest"],
        "measurements_digest": response["report_digest"],
        "result_digest": result["report_digest"],
        "outcomes": result["results"],
        "private_phase_was_hidden_from_planner_and_resolver_inputs": True,
        "scope": [
            "Exact finite eight-state mathematical Ground with externally reported GCI-002 certificate.",
            "The receiver samples a local logical phase and exposes only the declared threshold observation to the planner.",
            "The planner never receives the receiver-private phase artifact; this is process-level input separation, not cryptographic secrecy.",
            "Requests select minimum symbolic observation cost, not measured speed, latency or network overhead.",
            "A receiver-controlled software observer returns only authorized parity/bit1/low2 information.",
            "The independent auditor reads the private phase AFTER blind realization to verify the witness; the blind resolver does not.",
            "GitHub workflow attestation verifies provenance under a single GitHub authority, not independent physical providers.",
        ],
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("plan", "resolve", "audit"))
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory
    try:
        if args.role == "audit":
            report = audit(directory)
            target = "gci003-audit.json"
        else:
            binding = certificate_binding(directory)
            public = cag.read(directory / "gci003-public.json")
            if args.role == "plan":
                report, target = plan(public, binding), "gci003-plan.json"
            else:
                requested = cag.read(directory / "gci003-plan.json")
                readings = cag.read(directory / "gci003-measurements.json")
                report, target = resolve(public, requested, readings, binding), "gci003-result.json"
        cag.persist(directory / target, report)
        print(report["schema"], report["report_digest"])
    except (SufficiencyRefused, gci2.ContinuityRefusal,
            gci2.gci1.ContinuityError, cag.TopologyError,
            KeyError, TypeError, ValueError, OSError) as exc:
        parser.exit(1, f"GCI-003 refused: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
