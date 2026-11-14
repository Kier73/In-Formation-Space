"""GCI-002: runtime-free cross-Ground certificate and observer-partition audit.

Reuses GCI-001's separately signed, attested CAG-004 source and full
topology audit; neither E-CPU nor VGI is imported in this verifier.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "gci001"))
import continuity as gci1

cag = gci1.cag
PROBE_SCHEMA = "in-formation.gci002-ecpu-orbit-probe/0.1"
VGI_SCHEMA = "in-formation.gci002-vgi-closed-orbit/0.1"
AUDIT_SCHEMA = "in-formation.gci002-evidence-orbit-audit/0.1"
ECPU_REVISION = gci1.cag.ECPU_RECEIVER_REFERENCE
VGI_REVISION = gci1.VGI_REFERENCE
SOURCE = "gci002-mathematical-ecpu-probe"
GROUND_ID = "gci002-quotient-eight"
CLOCK = "gci002-quotient-logical-clock"
ACTION = "ADVANCE"
EVIDENCE_SCOPE = "derived-mathematical-observation-not-physical-sensor-or-authenticated-channel"
SCOPE = [
    "E-CPU observations were computed by the actual pinned law navigator on a separate GitHub job; not sensed physical dynamics.",
    "VGI evidence records have synthetic declared message/frame IDs for traceability; they are not authenticated transport receipts.",
    "The one-source VGI quorum and explicit finalization authorize an experimentally declared Ground only.",
    "The closed VGI affine certificate checks all eight edges of this finite quotient orbit, not the entire 65536-state source.",
    "The source law algebraically commutes with modulo eight; a threshold observer fails forward congruence.",
    "The verifier independently reconstructs source values and certificate edge claims, but does not run VGI or E-CPU.",
    "Separate GitHub Actions jobs share GitHub's administrative and physical infrastructure; main is not branch-protected.",
    "This is neither a universal observation invariant nor a general hardware, energy or network-compute performance claim.",
]


class ContinuityRefusal(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ContinuityRefusal(reason)


def source_rows(statement: Mapping[str, Any]) -> list[dict[str, int]]:
    rows = []
    for t in range(8):
        current = cag.state_at(t)
        following = cag.state_at(t + 1)
        rows.append({
            "coordinate": t, "full_state": current, "full_next_state": following,
            "state": current % 8, "next_state": following % 8,
        })
    return rows


def seal(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "report_digest": cag.digest(body)}


def verified_probe(source: Mapping[str, Any], statement: Mapping[str, Any]) -> None:
    require(type(source) is dict and set(source) == {
        "schema", "source_digest", "ecpu_revision", "method", "observation_kind",
        "observations", "local_elapsed_ns", "report_digest",
    }, "unexpected E-CPU orbit probe schema")
    require(source["report_digest"] == cag.digest({k:v for k,v in source.items() if k!="report_digest"}),
            "E-CPU orbit report hash failed")
    require(source["schema"] == PROBE_SCHEMA and
            source["source_digest"] == cag.digest(statement) and
            source["ecpu_revision"] == ECPU_REVISION and
            source["method"] == "mailcpu.law_certifier.lcg_navigate" and
            source["observation_kind"] == EVIDENCE_SCOPE and
            type(source["local_elapsed_ns"]) is int and source["local_elapsed_ns"] >= 0,
            "E-CPU probe source identity or methodological scope failed")
    rows = source.get("observations")
    require(type(rows) is list and len(rows) == 8, "E-CPU probe must report eight transitions")
    expected = source_rows(statement)
    for row, wanted in zip(rows, expected):
        require(type(row) is dict and set(row) == set(wanted) and
                all(type(v) is int for v in row.values()) and row == wanted,
                "E-CPU orbit transition differs from independent exact oracle")
    require({r["state"] for r in rows} == set(range(8)), "source orbit lacks complete state coverage")


def noncongruent_witness() -> dict[str, Any]:
    first, second = 0, 1
    f = lambda x: (5*x + 1) % 8
    g = lambda x: int(x >= 4)
    return {
        "observer": "threshold-at-four",
        "state_a": first, "state_b": second,
        "observed_a": g(first), "observed_b": g(second),
        "next_a": f(first), "next_b": f(second),
        "observed_next_a": g(f(first)), "observed_next_b": g(f(second)),
        "congruent": False,
    }


def expected_cert_rows(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = source["observations"]
    return [
        {"source_state": f"r{row['state']}", "action": ACTION,
         "target_state": f"r{row['next_state']}",
         "predicted_vector": [row["next_state"]],
         "target_vector": [row["next_state"]], "matched": True}
        for row in rows
    ]


def expected_affine_map() -> dict[str, Any]:
    return {
        "format": "VGI-ModularAffineMap-1",
        "domain": {"ring": "Z/modulus Z", "modulus": 8, "dimension": 1},
        "matrix": [[5]], "offset": [1],
        "equation": "x_next = M*x + b (mod modulus)",
    }


def verify_vgi(vgi: Mapping[str, Any], source: Mapping[str, Any],
               statement: Mapping[str, Any]) -> list[dict[str, Any]]:
    verified_probe(source, statement)
    require(type(vgi) is dict and set(vgi) == {
        "schema", "source_digest", "orbit_source_report_digest",
        "vgi_revision", "observer_source", "observation_kind",
        "evidence_policy", "evidence_records", "finalizations",
        "ground_fingerprint", "orbit_fingerprint",
        "orbit_certificate", "orbit_certificate_fingerprint",
        "reconstruction_certificate", "reconstruction_digest",
        "partial_ground_empty_before_finalization", "missing_edge_blocks_closure",
        "reconstruction_replay_verified", "observations",
        "preserving_parity_map", "noncongruent_witness", "boundaries",
        "report_digest",
    }, "unexpected VGI report schema")
    require(vgi["report_digest"] == cag.digest({k:v for k,v in vgi.items()
                                               if k != "report_digest"}),
            "VGI orbit report hash failed")
    require(vgi["schema"] == VGI_SCHEMA and
            vgi["source_digest"] == cag.digest(statement) and
            vgi["orbit_source_report_digest"] == source["report_digest"] and
            vgi["vgi_revision"] == VGI_REVISION and
            vgi["observer_source"] == SOURCE and
            vgi["observation_kind"] == EVIDENCE_SCOPE and
            vgi["boundaries"] == SCOPE and
            vgi["partial_ground_empty_before_finalization"] is True and
            vgi["missing_edge_blocks_closure"] is True and
            vgi["reconstruction_replay_verified"] is True,
            "VGI report identity or admitted evidence claims not supported")
    context = cag.digest(statement)
    require(vgi["evidence_policy"] == {
        "ground_id": GROUND_ID, "context_digest": context,
        "allowed_sources": [SOURCE], "quorum": 1, "strict": True,
    }, "VGI policy does not bind one source and exact signed Ground context")

    # Independently audit every synthetic VGI evidence assertion against the
    # separately executed E-CPU mathematical observation. The assertions' frame
    # identifiers are explicitly NOT independent transport authentications.
    records = vgi["evidence_records"]
    final = vgi["finalizations"]
    require(type(records) is list and len(records) == 8 and
            type(final) is list and len(final) == 8,
            "all eight VGI evidences and explicit finalizations required")
    seen_events = set()
    for srcrow, record in zip(source["observations"], records):
        t = srcrow["coordinate"]
        expected = {
            "evidence_id": f"gci002-evidence-{t}",
            "encounter_id": f"gci002-encounter-{t}",
            "message_id": f"gci002-derived-message-{t}",
            "channel_id": "gci002-calculated-orbit",
            "protocol_id": "gci002-derived-evidence.v1",
            "transport_id": "github-artifact-identifier-not-delivery-proof",
            "frame_id": f"gci002-derived-frame-{t}",
            "transport_sequence": t + 1,
            "source": SOURCE, "ground_id": GROUND_ID,
            "context_digest": context,
            "source_state": f"r{srcrow['state']}", "action": ACTION,
            "status": "known",
            "outcomes": [{"target":f"r{srcrow['next_state']}",
                          "output":[srcrow["next_state"]]}],
            "payload_digest": cag.digest(srcrow), "correlation_id": None,
            "source_model_fingerprint": context,
        }
        require(record == expected, "VGI evidence record contradicts exact observed transition")
        seen_events.add(record["source_state"])
    require(seen_events == {f"r{x}" for x in range(8)},
            "not all eight quotient states have unique evidence")
    require(all(type(f) is dict and
                f.get("status") == "AUTHORIZED" and
                f.get("source_state") in seen_events and
                f.get("action") == ACTION and
                f.get("evidence_ids") == [next(r["evidence_id"] for r in records
                     if r["source_state"] == f.get("source_state"))]
                for f in final), "finalizations are missing or not authorized")
    require(len({f["source_state"] for f in final}) == 8,
            "multiple finalizations for one state")

    cert = vgi["orbit_certificate"]
    require(type(cert) is dict and cert.get("format") == "VGI-AffineOrbitCertificate-1"
            and cert.get("claim") == "the affine map generates this exact closed fixed-policy OrbitIndex"
            and cert.get("transform") == expected_affine_map()
            and cert.get("start_state") == "r7"
            and cert.get("clock_id") == CLOCK
            and cert.get("start_time") == {
                "clock_id": CLOCK, "tick": 0, "basis": "logical_transition_coordinate"}
            and type(cert.get("cycle_start_index")) is int
            and cert["cycle_start_index"] == 0
            and type(cert.get("cycle_period")) is int and cert["cycle_period"] == 8
            and cert.get("ground_fingerprint") == vgi["ground_fingerprint"]
            and cert.get("orbit_fingerprint") == vgi["orbit_fingerprint"],
            "closed affine orbit claim is malformed or not bound to the Ground")
    expected_vectors = [{"state":f"r{x}", "vector":[x]} for x in range(8)]
    require(cert.get("state_vectors") == expected_vectors and
            cert.get("verified_edges") == expected_cert_rows(source) and
            type(vgi["orbit_certificate_fingerprint"]) is str and
            len(vgi["orbit_certificate_fingerprint"]) == 64,
            "closed VGI certificate must cover exactly the eight source edges")

    reconstruction = vgi["reconstruction_certificate"]
    require(type(reconstruction) is dict and
            reconstruction.get("schema") == "vgi.ground-reconstruction-certificate.v1" and
            reconstruction.get("scope") == "finite_action_sequence_replay" and
            reconstruction.get("compiler_id") == "vgi.transition-compiler" and
            reconstruction.get("compiler_version") == 1 and
            reconstruction.get("ground_fingerprint") == vgi["ground_fingerprint"] and
            reconstruction.get("context_digest") == context and
            reconstruction.get("action_sequences") ==
                [[ACTION] * t for t in (1, 2, 8, 16)] and
            reconstruction.get("witness_count") == 4 and
            reconstruction.get("max_horizon") == 16 and
            type(reconstruction.get("witness_digest")) is str and
            len(reconstruction["witness_digest"]) == 64 and
            vgi["reconstruction_digest"] == cag.digest(reconstruction),
            "finite reconstruction certificate or witness scope differs")

    require(vgi["preserving_parity_map"] ==
            {"observer": "parity", "source_modulus": 8,
             "target_modulus": 2, "transition": {"0": 1, "1": 0},
             "congruent": True}, "preserving parity witness differs")
    require(vgi["noncongruent_witness"] == noncongruent_witness(),
            "noncongruent observer was silently admitted")

    observations = vgi["observations"]
    require(type(observations) is list and len(observations) == len(statement["jobs"]),
            "missing VGI orbit observations")
    out = []
    for job, row in zip(statement["jobs"], observations):
        t = job["coordinate"]
        residue = cag.state_at(t) % 8
        projected = (3 * residue + 11) % 8
        wanted = {
            "job_id": job["job_id"], "coordinate": t,
            "state_id": f"r{residue}", "state_mod8": residue,
            "projected_mod8": projected,
            "closed_certificate_fingerprint": vgi["orbit_certificate_fingerprint"],
        }
        require(row == wanted and
                all(type(row[k]) is int for k in
                    ("coordinate", "state_mod8", "projected_mod8")),
                "affine-certificate navigation output does not match signed source")
        out.append(row)
    return out


def verify_all(directory: Path) -> dict[str, Any]:
    # Enforce the *complete* GCI-001 and CAG-004 cross-repo verification chain.
    previous = gci1.verify_all(directory)
    signed = cag.read(directory / "signed-intent.json")
    trust = cag.read(directory / "issuer-trust.json")
    statement = cag.verify_intent(signed, trust)
    source = cag.read(directory / "orbit-probe.json")
    vgi = cag.read(directory / "closed-orbit-report.json")
    matched = verify_vgi(vgi, source, statement)
    for old, new in zip(previous["matched_results"], matched):
        require(old["coordinate"] == new["coordinate"] and
                old["coarse_state"] == new["state_mod8"] and
                old["coarse_result"] == new["projected_mod8"],
                "closed VGI certificate differs from previously accepted cross-Ground result")
    return seal({
        "schema": AUDIT_SCHEMA,
        "status": "eight_edge_evidence_admitted_orbit_with_noncongruence_refusal",
        "source_digest": cag.digest(statement),
        "gci001_audit_digest": previous["report_digest"],
        "probe_report_digest": source["report_digest"],
        "vgi_orbit_report_digest": vgi["report_digest"],
        "verified_logical_states": 8, "verified_orbit_edges": 8,
        "matched_coordinates": matched,
        "noncongruent_observer": noncongruent_witness(),
        "boundaries": SCOPE,
    })


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["verify"])
    p.add_argument("--directory", type=Path, required=True)
    a = p.parse_args()
    try:
        report = verify_all(a.directory)
        cag.persist(a.directory / "gci002-audit.json", report)
        print(report["status"], report["report_digest"])
    except (ContinuityRefusal, gci1.ContinuityError, cag.TopologyError,
            OSError, KeyError, TypeError, ValueError) as exc:
        p.exit(1, f"GCI-002 refused: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
