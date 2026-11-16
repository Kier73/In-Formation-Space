"""IWI-006: reuse GCI-005 signed E-CPU receiver observations, VGI native
TransitionEvidenceLedger, and E-CPU SAB-007 durable/lineage primitives.

The GCI-005 report is phase-blind and validated with the *original* independent
GCI-005 X.509/ECDSA auditor. We project authenticated readings into VGI as
request-bound OBSERVATION EVENTS. They are not machine transition laws.

VGI TransportFrameReceipts here bind the IMPORTED ChannelMessages; they are
not original E-CPU TLS frames. Original signed leaf receipts are retained in
the sealed source report and always reverified on recovery.

Recovery is fixed-membership native RecoveryLineage (separate on-disk journals
on the same machine), not distributed independent hardware/Byzantine quorum.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

# Reuse the existing GCI-005 verifier. No duplicated certificate/receipt checker.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "cross-ground-continuity" / "gci005"))
import honesty_contract as h

from vgi.channels import ChannelContract, ChannelExchangeLedger, ChannelMessage
from vgi.encounters import EncounterProvenance
from vgi.evidence import (
    TransitionEvidenceLedger, TransitionEvidencePolicy, TransportFrameReceipt,
)
from vgi.transitions import GroundTransitionSystem
from mailcpu.federated_ground_continuity import AtomicGroundEvidenceStore
from mailcpu.recovery_lineage import (
    RecoveryLineageAuthority, RecoveryLineageCoordinator,
    RecoveryStateManifest, RecoveryLineageProof,
)
from mailcpu.seed_commit_quorum import SeedCommitMembership

SCHEMA = "IWI-006/native-signed-receipt-lineage-v1"
CUT = "iwi006.gci005-vgi-finalized-sample-only"
_CHANNEL = ChannelContract(
    "iwi006.imported-gci005-signed-feature", "iwi006.imported-receipt/1",
    observation_schema="vgi.transition-observation/1",
)
_HEX = re.compile(r"^[a-f0-9]{64}$")


class NativeReuseRefused(ValueError):
    """Unverified, unpinned or stale cryptographic/semantic evidence."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class VerifiedSourcePins:
    """External verifiers must pin these bytes/identities, not trust the report.

    For synthetic unit tests, make_test_pins derives them from the report.
    In real hosting, pin provenance and keys from a separately verified source.
    """
    ground_fingerprint: str
    source_digest: str
    public_digest: str
    plan_digest: str
    gci004_digest: str
    gci005_digest: str
    ca_digest_honest: str
    ca_digest_disagree: str

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if type(value) is not str or _HEX.fullmatch(value) is None:
                raise NativeReuseRefused(f"invalid pinned {name}")

    def as_dict(self) -> dict[str, str]:
        return dict(vars(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> "VerifiedSourcePins":
        if type(data) is not dict or set(data) != set(cls.__dataclass_fields__):
            raise NativeReuseRefused("expected exact externally pinned evidence roots")
        return cls(**data)


def make_test_pins(report: dict, binding: dict, public: dict, plan: dict) -> VerifiedSourcePins:
    """TEST FIXTURE ONLY: convenient derivation, not independent trust."""
    return VerifiedSourcePins(
        binding["ground_fingerprint"], binding["source_digest"],
        public["report_digest"], plan["report_digest"],
        report["source_gci004_report_digest"], report["report_digest"],
        *(_sha(round_["ca_certificate_pem"].encode("utf-8"))
          for round_ in report["rounds"]),
    )


def _source_check(
    report: dict, binding: dict, public: dict, plan: dict,
    network: dict, pins: VerifiedSourcePins,
) -> dict:
    if not isinstance(pins, VerifiedSourcePins):
        raise NativeReuseRefused("a separately pinned source policy is required")
    if (binding["ground_fingerprint"] != pins.ground_fingerprint
            or binding["source_digest"] != pins.source_digest
            or public["report_digest"] != pins.public_digest
            or plan["report_digest"] != pins.plan_digest
            or report["report_digest"] != pins.gci005_digest
            or report["source_gci004_report_digest"] != pins.gci004_digest):
        raise NativeReuseRefused("source, context, upstream network or report identity changed")
    if (len(report["rounds"]) != 2
            or _sha(report["rounds"][0]["ca_certificate_pem"].encode()) != pins.ca_digest_honest
            or _sha(report["rounds"][1]["ca_certificate_pem"].encode()) != pins.ca_digest_disagree):
        raise NativeReuseRefused("caller-pinned test CA roots differ")
    # Previous GCI-004 auditing is REQUIRED in the hosted workflow; here we
    # recheck its exact sealed source identity but do not claim to redo its
    # withheld-private-phase witness audit.
    h.gci3.check_sealed(network, {
        "schema", "binding", "public_digest", "plan_digest", "origin",
        "ca_certificate_pem", "client_certificate_pem", "discovery",
        "requests", "measurements", "realization", "scope",
        "transport_kind", "bad_hostname_refused",
        "forbidden_feature_refused", "replay_refused",
    }, h.c.SCHEMA)
    if (network["report_digest"] != pins.gci004_digest
            or network["binding"] != binding
            or network["public_digest"] != pins.public_digest
            or network["plan_digest"] != pins.plan_digest):
        raise NativeReuseRefused("GCI-004 upstream provenance is not the pinned source")
    # The real GCI-005 phase-blind cryptographic verifier checks BOTH rounds:
    # certificate chains, peer SAN, two distinct leaf keys, typed native
    # snapshot, signed reply/request binding and both expected verdicts.
    return h.verify_record(report, binding, public, plan)


def _vgi_round(round_: dict, source_report_digest: str, binding: dict,
               index: int) -> dict[str, Any]:
    peers = h.TWO
    requests = [x["request"] for x in round_["receipts"]]
    challenge = requests[0]["challenge"]
    if requests[1]["challenge"] != challenge:
        raise NativeReuseRefused("two receiver receipts came from separate requests")
    # A state name here denotes ONE request event, not the phase's reusable
    # physical state. This VGI Ground must not become a persistent source law.
    state = "measurement-request:" + challenge
    obs_states = ("observed-parity:0", "observed-parity:1")
    context = _sha(_canonical({
        "source": source_report_digest, "scenario": round_["scenario"],
        "request": requests[0], "ground_fingerprint": binding["ground_fingerprint"],
        "adapter_kind": "request-scoped-observation-not-machine-transition",
    }))
    ground_id = f"iwi006.gci005-observation-round-{index}"
    exchange = ChannelExchangeLedger()
    messages = []
    for i, peer in enumerate(peers):
        receipt = round_["receipts"][i]
        value = receipt["payload"]["value"]
        signed_receipt_id = _sha(_canonical(receipt))
        msg = ChannelMessage(
            f"gci005:{source_report_digest}:{index}:{peer}:{signed_receipt_id}",
            _CHANNEL.channel_id, _CHANNEL.protocol_id, "observation",
            {
                "status": "known", "source_state": state,
                "action": "observe.parity", "target": obs_states[value],
                "output": [value], "ground_fingerprint": binding["ground_fingerprint"],
                "signed_receipt_digest": signed_receipt_id,
                "gci005_request_digest": receipt["payload"]["request_digest"],
                "observation_scope": "single-signed-feature-measurement",
            },
            EncounterProvenance(
                peer, source_ref="gci005-signed-receipt:" + signed_receipt_id,
                collector="iwi006-verified-import",
                content_digest=signed_receipt_id,
            ),
        )
        messages.append(msg)
        exchange = exchange.record_observation(_CHANNEL, msg)
    encounters = exchange.to_encounter_ledger()
    policy = TransitionEvidencePolicy(ground_id, context, peers, 2, True)
    ledger = TransitionEvidenceLedger(policy)
    for i, msg in enumerate(messages, 1):
        # This is a VGI IMPORT frame, not a claim that an original E-CPU
        # SocketTransport frame was itself a VGI ChannelMessage.
        frame = TransportFrameReceipt.capture(
            msg, transport_id=f"gci005-verified-report-import-{index}",
            sequence=i,
        )
        ledger = ledger.ingest_channel_message(
            exchange, msg.message_id, frame, encounters,
        )
    pre = ledger.status(state, "observe.parity").status
    ledger = ledger.finalize(state, "observe.parity")
    decision = ledger.decision(state, "observe.parity")
    ground = ledger.build_ground(
        states=(state,) + obs_states, actions=("observe.parity",),
        initial_state=state, channels=("parity",),
    )
    rebuilt = GroundTransitionSystem.from_json(ground.to_json())
    if rebuilt.fingerprint != ground.fingerprint:
        raise NativeReuseRefused("native VGI Ground reconstruction changed")
    expected = "AUTHORIZED" if index == 0 else "CONFLICT"
    if decision.status != expected:
        raise NativeReuseRefused("VGI admission differs from signed-source verdict")
    if expected == "AUTHORIZED":
        if (pre != "QUORUM" or ground.status(state, "observe.parity") != "known"
                or len(decision.agreeing_sources) != 2):
            raise NativeReuseRefused("VGI agreement was not independently finalized")
    elif (pre != "CONFLICT" or ground.status(state, "observe.parity") != "unknown"
          or ground.observations):
        raise NativeReuseRefused("a signed conflict became an authorized transition")
    return {
        "scenario": round_["scenario"], "phase_blind": True,
        "vgi_status_before_finalization": pre,
        "vgi_finalization": decision.status,
        "native_vgi_ledger": ledger.to_dict(),
        "native_vgi_ground": ground.to_dict(),
        "native_vgi_ground_fingerprint": ground.fingerprint,
        "native_vgi_ledger_fingerprint": ledger.fingerprint,
        "ground_complete": False,
        "original_tls_frame_reconstructed": False,
        "persistent_phase_law_proven": False,
        "receiver_keys_test_ca_only": True,
    }


def reconstruct(
    report: dict, binding: dict, public: dict, plan: dict,
    network: dict, *, pins: VerifiedSourcePins,
) -> dict:
    """Re-evaluate source authentication BEFORE VGI semantic interpretation."""
    blind = _source_check(report, binding, public, plan, network, pins)
    observed = [_vgi_round(round_, report["report_digest"], binding, i)
                for i, round_ in enumerate(report["rounds"])]
    if [x["vgi_finalization"] for x in observed] != ["AUTHORIZED", "CONFLICT"]:
        raise NativeReuseRefused("VGI failed the authenticated disagreement test")
    if [x["verdict"] for x in blind["rounds"]] != [
        "ADMITTED_AGREEMENT", "REFUSED_DISAGREEMENT",
    ]:
        raise NativeReuseRefused("phase-blind source audit changed")
    return {
        "schema": SCHEMA, "pins": pins.as_dict(),
        "gci004_network": network, "gci005_report": report,
        "ground_binding": binding, "public_context": public,
        "intention_plan": plan, "phase_blind_source_audit": blind,
        "vgi_observation_events": observed,
        "external_source_law_proven": False,
        "external_operation_authorized": False,
        "original_tls_frame_reconstructed": False,
        "held_private_phase_used": False,
    }


def verify_artifact(artifact: dict, *, pins: VerifiedSourcePins) -> dict:
    """Recompute every source signature and every native VGI finalization."""
    if type(artifact) is not dict or artifact.get("schema") != SCHEMA:
        raise NativeReuseRefused("unknown saved result")
    if artifact.get("pins") != pins.as_dict():
        raise NativeReuseRefused("recovery must use the original external pins")
    reconstructed = reconstruct(
        artifact["gci005_report"], artifact["ground_binding"],
        artifact["public_context"], artifact["intention_plan"],
        artifact["gci004_network"], pins=pins,
    )
    if reconstructed != artifact:
        raise NativeReuseRefused("stored result differs from independent reconstruction")
    return {
        "status": "SIGNED_OBSERVATION_FINALIZATION_VERIFIED",
        "decisions": [x["vgi_finalization"]
                      for x in reconstructed["vgi_observation_events"]],
        "source_report_digest": artifact["gci005_report"]["report_digest"],
        "vgi_ledger_fingerprints": [
            x["native_vgi_ledger_fingerprint"]
            for x in reconstructed["vgi_observation_events"]
        ],
        "source_phase_stationarity_proven": False,
    }


def native_coordinator(root: Path) -> RecoveryLineageCoordinator:
    """Reuse actual E-CPU majority journals, not another homemade quorum."""
    root.mkdir(parents=True, exist_ok=True)
    membership = SeedCommitMembership(
        "iwi006-observation-machine", 1,
        ("anchor-a", "anchor-b", "anchor-c"),
        "anchor-a", 1, "f" * 64,
    )
    authorities = {
        member: RecoveryLineageAuthority(
            membership, member, root / (member + ".jsonl"),
        )
        for member in membership.member_ids
    }
    return RecoveryLineageCoordinator(membership, authorities)


def seal_artifact(artifact: dict, *, pins: VerifiedSourcePins,
                  coordinator: RecoveryLineageCoordinator,
                  storage: AtomicGroundEvidenceStore, generation: int,
                  predecessor_digest: str) -> tuple[RecoveryStateManifest, RecoveryLineageProof]:
    verify_artifact(artifact, pins=pins)
    if type(generation) is not int or generation <= 0:
        raise NativeReuseRefused("invalid recovery generation")
    raw = _canonical(artifact)
    address = storage.put(raw)  # Existing E-CPU fsync/atomic/immutable store
    members = coordinator.membership
    manifest = RecoveryStateManifest(
        machine_id=members.system_id, incarnation=members.incarnation,
        owner_id=members.owner_id, owner_term=members.owner_term,
        membership_digest=members.digest, generation=generation,
        predecessor_digest=predecessor_digest, state_digest=address,
        capture_cut=CUT,
    )
    manifest.verify_payload(storage.get(address))
    proof = coordinator.seal(manifest)
    if coordinator.verify_state(manifest).snapshot() != proof.snapshot():
        raise NativeReuseRefused("non-current quorum proof cannot authorize acceptance")
    return manifest, proof


def recover_artifact(*, pins: VerifiedSourcePins,
                     coordinator: RecoveryLineageCoordinator,
                     storage: AtomicGroundEvidenceStore,
                     manifest: RecoveryStateManifest,
                     proof: RecoveryLineageProof) -> dict:
    """No receiver retry: verify majority high-water and cryptographic reports anew."""
    if not isinstance(manifest, RecoveryStateManifest) or not isinstance(proof, RecoveryLineageProof):
        raise NativeReuseRefused("typed original manifest and quorum proof required")
    if manifest.capture_cut != CUT:
        raise NativeReuseRefused("wrong recovery capture cut")
    accepted = coordinator.verify_state(manifest)
    if accepted.snapshot() != proof.snapshot():
        raise NativeReuseRefused("supplied proof differs from latest accepted lineage")
    raw = storage.get(manifest.state_digest)
    manifest.verify_payload(raw)
    artifact = json.loads(raw)
    if _canonical(artifact) != raw:
        raise NativeReuseRefused("noncanonical recovered payload")
    report = verify_artifact(artifact, pins=pins)
    return {
        "schema": "IWI-006/recovered-v1", "status": "RECOVERED_SIGNED_OBSERVATIONS",
        **report, "state_digest": manifest.state_digest,
        "reexecuted_receivers": False,
        "reexecuted_observations": False,
        "source_phase_stationarity_proven": False,
        "independent_machine_quorum_proven": False,
    }


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("seal", "recover"))
    ap.add_argument("--directory", type=Path, help="phase-blind GCI-005 evidence root")
    ap.add_argument("--durable", required=True, type=Path)
    ap.add_argument("--pins", required=True, type=Path,
                    help="caller-supplied independently verified pinned source identity")
    args = ap.parse_args()
    pins = VerifiedSourcePins.from_dict(_read(args.pins))
    coordinator = native_coordinator(args.durable / "journals")
    storage = AtomicGroundEvidenceStore(args.durable / "evidence")
    if args.command == "seal":
        if args.directory is None:
            ap.error("--directory required for sealing original source receipts")
        binding, public, plan = h.get_binding(args.directory)
        report = _read(args.directory / "gci005-quorum.json")
        network = _read(args.directory / "gci004-network.json")
        artifact = reconstruct(report, binding, public, plan, network, pins=pins)
        m, proof = seal_artifact(
            artifact, pins=pins, coordinator=coordinator, storage=storage,
            generation=1,
            predecessor_digest=coordinator.membership.genesis_state_digest,
        )
        _write(args.durable / "manifest.json", m.snapshot())
        _write(args.durable / "proof.json", proof.snapshot())
        print(json.dumps({"status": "SEALED_SIGNED_VGI_OBSERVATIONS",
                          "state_digest": m.state_digest,
                          "report": verify_artifact(artifact, pins=pins)},
                         sort_keys=True))
        return
    # Separate restart process: never read original evidence/cag004 files.
    m = RecoveryStateManifest.from_snapshot(_read(args.durable / "manifest.json"))
    proof = RecoveryLineageProof.from_snapshot(_read(args.durable / "proof.json"))
    print(json.dumps(recover_artifact(
        pins=pins, coordinator=coordinator, storage=storage,
        manifest=m, proof=proof,
    ), sort_keys=True))


if __name__ == "__main__":
    main()

