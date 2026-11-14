"""GCI-002: instantiate an evidence-admitted VGI quotient Ground and closed orbit.

Source rows come from a *separate, pinned actual E-CPU host*. The typed VGI
evidence uses declared synthetic identifiers, NOT authenticated channel
frames or physical sensors. A GitHub job attestation is checked by the host
workflow on main before consuming the upstream artifact.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import contract as c
from vgi.affine import AffineOrbitCertificate, ModularAffineMap
from vgi.evidence import (
    ObservedOutcome, TransitionEvidencePolicy, TransitionEvidence,
    TransitionEvidenceLedger, GroundReconstructionVerifier,
)
from vgi.orbit import OrbitPolicy, OrbitNavigator, OrbitTimeCoordinate


def make_evidence(row: dict, context_digest: str) -> TransitionEvidence:
    t = row["coordinate"]
    return TransitionEvidence(
        evidence_id=f"gci002-evidence-{t}",
        encounter_id=f"gci002-encounter-{t}",
        message_id=f"gci002-derived-message-{t}",
        channel_id="gci002-calculated-orbit",
        protocol_id="gci002-derived-evidence.v1",
        transport_id="github-artifact-identifier-not-delivery-proof",
        frame_id=f"gci002-derived-frame-{t}",
        transport_sequence=t + 1, source=c.SOURCE,
        ground_id=c.GROUND_ID, context_digest=context_digest,
        source_state=f"r{row['state']}", action=c.ACTION,
        status="known",
        outcomes=(ObservedOutcome(f"r{row['next_state']}", (row["next_state"],)),),
        payload_digest=c.cag.digest(row),
        correlation_id=None, source_model_fingerprint=context_digest,
    )


def make_ground(ledger: TransitionEvidenceLedger, context: str, probe_digest: str):
    return ledger.build_ground(
        states=tuple(f"r{i}" for i in range(8)),
        actions=(c.ACTION,), initial_state="r7",
        channels=("next_state",),
        metadata={"gci002_intent_digest": context,
                  "gci002_probe_digest": probe_digest},
    )


def run(directory: Path) -> dict:
    signed = c.cag.read(directory / "signed-intent.json")
    trust = c.cag.read(directory / "issuer-trust.json")
    statement = c.cag.verify_intent(signed, trust)
    source = c.cag.read(directory / "orbit-probe.json")
    c.verified_probe(source, statement)
    context = c.cag.digest(statement)

    policy = TransitionEvidencePolicy(
        c.GROUND_ID, context, (c.SOURCE,), quorum=1, strict=True,
    )
    ledger = TransitionEvidenceLedger(policy)
    for row in source["observations"]:
        ledger = ledger.ingest(make_evidence(row, context))
    # QUORUM is not AUTHORIZED until a separate explicit finalization.
    unadmitted = make_ground(ledger, context, source["report_digest"])
    empty_before_finalization = (
        len(unadmitted.observations) == 0 and not unadmitted.complete
        and all(ledger.status(f"r{row['state']}", c.ACTION).status == "QUORUM"
                for row in source["observations"])
    )
    c.require(empty_before_finalization,
              "raw evidence was silently promoted into a VGI Ground")

    # Deliberately withhold one authorized edge: the fixed-policy orbit must
    # stop at the unknown transition, not claim a closed cycle.
    short_ledger = ledger
    for row in source["observations"][:-1]:
        short_ledger = short_ledger.finalize(f"r{row['state']}", c.ACTION)
    partial = make_ground(short_ledger, context, source["report_digest"])
    partial_policy = OrbitPolicy.derive(partial)
    partial_orbit = OrbitNavigator.compile(
        partial, partial_policy,
        start_state="r7", start_time=OrbitTimeCoordinate(c.CLOCK, 0),
    )
    missing_edge_blocks_closure = (
        not partial.complete and not partial_orbit.closed
        and partial_orbit.stop_status == "blocked_unknown"
    )
    c.require(missing_edge_blocks_closure,
              "missing admitted edge was not fail-closed")

    for row in source["observations"]:
        ledger = ledger.finalize(f"r{row['state']}", c.ACTION)
    c.require(all(ledger.decision(f"r{i}", c.ACTION).status == "AUTHORIZED"
                  for i in range(8)), "at least one source edge was not finalized")
    ground = make_ground(ledger, context, source["report_digest"])
    c.require(ground.complete and len(ground.observations) == 8,
              "closed Ground requires eight complete admitted transitions")
    policy_orbit = OrbitPolicy.derive(ground)
    orbit = OrbitNavigator.compile(
        ground, policy_orbit, start_state="r7",
        start_time=OrbitTimeCoordinate(c.CLOCK, 0),
    )
    c.require(orbit.closed and orbit.cycle_start_index == 0
              and orbit.cycle_period == 8 and len(orbit.steps) == 8,
              "eight-state Ground did not form a replay-checked closed orbit")

    affine = ModularAffineMap(8, ((5,),), (1,))
    certificate = AffineOrbitCertificate.certify(
        orbit, affine, {f"r{i}": (i,) for i in range(8)},
    )
    c.require(all(x["matched"] for x in certificate.to_dict()["verified_edges"]),
              "VGI did not independently certify every retained edge")

    # A finite compiler/replay witness is separately bound to this admitted Ground.
    witness_lengths = (1, 2, 8, 16)
    checker = GroundReconstructionVerifier()
    reconstruction = checker.certify(
        ground, [(c.ACTION,) * n for n in witness_lengths], context_digest=context,
    )
    reconstruction_replay_verified = checker.verify(
        ground, reconstruction, context_digest=context,
    )
    c.require(reconstruction_replay_verified,
              "VGI finite witness replay failed")

    # Exhaustive within the 8-state Ground: parity does respect its transition.
    parity = {str(x): (5 * x + 1) % 2 for x in (0, 1)}
    c.require(all(((5*x+1)%8)%2 == parity[str(x%2)] for x in range(8)),
              "parity quotient is not transition-preserving")
    parity_map = {
        "observer": "parity", "source_modulus": 8, "target_modulus": 2,
        "transition": parity, "congruent": True,
    }
    witness = c.noncongruent_witness()
    c.require(witness["observed_a"] == witness["observed_b"] and
              witness["observed_next_a"] != witness["observed_next_b"],
              "threshold witness does not distinguish successor behavior")

    observed = []
    for job in statement["jobs"]:
        result = certificate.state_at(OrbitTimeCoordinate(c.CLOCK, job["coordinate"]))
        c.require(result.status == "located" and result.vector is not None
                  and result.materialized_intermediate_states == 0,
                  "VGI closed-orbit navigation failed")
        x = result.vector[0]
        observed.append({
            "job_id": job["job_id"], "coordinate": job["coordinate"],
            "state_id": result.state, "state_mod8": x,
            "projected_mod8": (3*x + 11) % 8,
            "closed_certificate_fingerprint": certificate.fingerprint,
        })

    report = c.seal({
        "schema": c.VGI_SCHEMA, "source_digest": context,
        "orbit_source_report_digest": source["report_digest"],
        "vgi_revision": c.VGI_REVISION,
        "observer_source": c.SOURCE, "observation_kind": c.EVIDENCE_SCOPE,
        "evidence_policy": policy.to_dict(),
        "evidence_records": [e.to_dict() for e in ledger.evidence],
        "finalizations": [f.to_dict() for f in ledger.finalizations],
        "ground_fingerprint": ground.fingerprint,
        "orbit_fingerprint": orbit.fingerprint,
        "orbit_certificate": certificate.to_dict(),
        "orbit_certificate_fingerprint": certificate.fingerprint,
        "reconstruction_certificate": reconstruction.to_dict(),
        "reconstruction_digest": reconstruction.digest,
        "partial_ground_empty_before_finalization": empty_before_finalization,
        "missing_edge_blocks_closure": missing_edge_blocks_closure,
        "reconstruction_replay_verified": reconstruction_replay_verified,
        "observations": observed,
        "preserving_parity_map": parity_map,
        "noncongruent_witness": witness,
        "boundaries": c.SCOPE,
    })
    c.verify_vgi(report, source, statement)
    c.cag.persist(directory / "closed-orbit-report.json", report)
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, required=True)
    a = p.parse_args()
    try:
        report = run(a.directory)
        print("Evidence-admitted VGI closed orbit:", len(report["orbit_certificate"]["verified_edges"]),
              "edges;", len(report["observations"]), "coordinates;",
              report["report_digest"])
    except (c.ContinuityRefusal, c.cag.TopologyError, ValueError, TypeError, KeyError, OSError) as exc:
        p.exit(1, f"GCI-002 VGI refused: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
