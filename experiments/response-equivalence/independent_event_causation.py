"""RE-005: an independent event witness does not establish physical causation.

A finite, exact synthetic model. HMAC authenticates only to a *pre-enrolled*
shared key; the protocol does not authenticate a physical event or independent
host origin. No remote clock offset is converted to causality.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "in-formation.response-re005/0.1"
SESSION = "re005-independent-witness-v1"
EPISODES = (
    ("passive-positive", "passive", 1, 1),
    ("passive-negative", "passive", 0, 0),
    ("controlled-negative", "controlled", 0, 1),
)
TRUTHS = ("event_causal", "common_cause_marker", "common_cause_alias")


class EvidenceError(ValueError):
    """The declared evidence contract was not satisfied."""


def canonical(x: object) -> bytes:
    return json.dumps(x, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(x: object) -> str:
    return hashlib.sha256(canonical(x)).hexdigest()


def _fields(record: Mapping[str, Any], fields: set[str]) -> None:
    if not isinstance(record, dict) or set(record) != fields:
        raise EvidenceError("unexpected record fields")


def _digest_verified(record: dict[str, Any]) -> None:
    given = record.get("digest")
    if not isinstance(given, str) or not hmac.compare_digest(sha({k: v for k, v in record.items() if k != "digest"}), given):
        raise EvidenceError("record digest mismatch")


def _seal(record: dict[str, Any]) -> dict[str, Any]:
    record["digest"] = sha(record)
    return record


def _episode(name: str) -> tuple[str, str, int, int]:
    for value in EPISODES:
        if value[0] == name:
            return value
    raise EvidenceError("unknown episode")


def plant_value(truth: str, episode_name: str) -> int:
    """Synthetic outcomes. In the controlled arm U stays at 1 as E changes.

    This *stipulates* the controlled-exclusion assumption. The witness cannot
    attest that assumption, and alternative hidden mechanisms remain possible.
    """
    _, _, event, latent = _episode(episode_name)
    if truth == "event_causal":
        return 1 + event
    if truth in ("common_cause_marker", "common_cause_alias"):
        return 1 + latent
    raise ValueError("unknown hypothesis")


def enroll() -> dict[str, str]:
    """Only the enrolment authority and witness/verifier receive the key.

    The public key *identifier* alone cannot verify an HMAC; hosted workflow
    artifacts do not secure this key against actors with artifact read access.
    """
    key = secrets.token_hex(32)
    return {"key_hex": key, "key_id": hashlib.sha256(bytes.fromhex(key)).hexdigest()}


def _key(key_hex: str) -> bytes:
    if not isinstance(key_hex, str) or len(key_hex) != 64:
        raise EvidenceError("missing or malformed enrolled key")
    try:
        return bytes.fromhex(key_hex)
    except ValueError as exc:
        raise EvidenceError("invalid enrolled key") from exc


def sign_witness(record: dict[str, Any], key_hex: str) -> dict[str, Any]:
    """MAC covers the entire witness assertion including event, role and frame."""
    key = _key(key_hex)
    if record.get("role") != "C" or record.get("schema") != SCHEMA:
        raise EvidenceError("witness role invalid")
    body = copy.deepcopy(record)
    body.pop("mac", None)
    body.pop("digest", None)
    record["mac"] = hmac.new(key, canonical(body), hashlib.sha256).hexdigest()
    return _seal(record)


def verify_witness(record: dict[str, Any], key_hex: str, key_id: str) -> None:
    _fields(record, {"schema", "session", "role", "episode", "status", "event",
                     "local_tick", "causal", "key_id", "mac", "digest"})
    _digest_verified(record)
    if (record["schema"] != SCHEMA or record["session"] != SESSION
            or record["role"] != "C" or record["episode"] not in [e[0] for e in EPISODES]):
        raise EvidenceError("witness identity mismatch")
    if not isinstance(key_id, str) or record["key_id"] != key_id:
        raise EvidenceError("witness not enrolled under expected key")
    key = _key(key_hex)
    if hashlib.sha256(key).hexdigest() != key_id:
        raise EvidenceError("enrollment fingerprint mismatch")
    mac = record["mac"]
    if not isinstance(mac, str):
        raise EvidenceError("missing witness MAC")
    body = {k: v for k, v in record.items() if k not in ("mac", "digest")}
    expected = hmac.new(key, canonical(body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, mac):
        raise EvidenceError("witness authentication failed")
    if record["status"] not in ("observed", "refused"):
        raise EvidenceError("unknown witness status")
    if record["status"] == "refused" and record["event"] is not None:
        raise EvidenceError("refusal cannot carry an event")
    if record["status"] == "observed" and type(record["event"]) is not int:
        raise EvidenceError("witness event must be an exact integer")
    if type(record["local_tick"]) is not int:
        raise EvidenceError("witness local clock invalid")


def make_source(stamp_factory) -> dict[str, Any]:
    """Stamp factory is backed by real E-CPU in hosted mode, fixture in unit mode."""
    records = []
    for k, (episode, kind, _, _) in enumerate(EPISODES):
        records.append(_seal({"schema": SCHEMA, "session": SESSION, "role": "A",
                             "episode": episode, "command": "apply", "protocol": kind,
                             "local_tick": 1000 + 17 * k, "causal": stamp_factory()}))
    return {"role": "A", "records": records}


def make_witness(stamp_factory, key_hex: str, key_id: str, *, permitted: bool = True) -> dict[str, Any]:
    records = []
    for k, (episode, _, event, _) in enumerate(EPISODES):
        records.append(sign_witness({"schema": SCHEMA, "session": SESSION,
                            "role": "C", "episode": episode,
                            "status": "observed" if permitted else "refused",
                            "event": event if permitted else None,
                            "local_tick": -90000 + 31 * k, "causal": stamp_factory(),
                            "key_id": key_id}, key_hex))
    return {"role": "C", "records": records}


def make_receiver(truth: str, stamp_factory, source: dict[str, Any],
                  witness: dict[str, Any]) -> dict[str, Any]:
    if truth not in TRUTHS:
        raise ValueError("unknown truth")
    verify_source(source)
    # The receiver must NOT receive the witness shared authentication secret.
    # A separate verifier validates the witness MAC.
    if witness.get("role") != "C" or len(witness.get("records", [])) != len(EPISODES):
        raise EvidenceError("witness evidence unavailable to receiver")
    records = []
    for k, (episode, _, _, _) in enumerate(EPISODES):
        records.append(_seal({"schema": SCHEMA, "session": SESSION, "role": "B",
                             "episode": episode, "readout": plant_value(truth, episode),
                             "source_digest": source["records"][k]["digest"],
                             "witness_digest": witness["records"][k]["digest"],
                             "local_tick": 200 + 43 * k, "causal": stamp_factory()}))
    return {"role": "B", "records": records}


def verify_source(bundle: dict[str, Any]) -> None:
    _fields(bundle, {"role", "records"})
    if bundle["role"] != "A" or not isinstance(bundle["records"], list) or len(bundle["records"]) != len(EPISODES):
        raise EvidenceError("source schedule missing")
    for k, (rec, (ep, kind, _, _)) in enumerate(zip(bundle["records"], EPISODES)):
        _fields(rec, {"schema", "session", "role", "episode", "command",
                      "protocol", "local_tick", "causal", "digest"})
        _digest_verified(rec)
        if (rec["schema"], rec["session"], rec["role"], rec["episode"], rec["command"], rec["protocol"]) != (SCHEMA, SESSION, "A", ep, "apply", kind):
            raise EvidenceError("source schedule mismatch")
        if rec["local_tick"] != 1000 + 17 * k:
            raise EvidenceError("source local tick mismatch")


def verify_witness_bundle(bundle: dict[str, Any], key_hex: str, key_id: str) -> None:
    _fields(bundle, {"role", "records"})
    if bundle["role"] != "C" or not isinstance(bundle["records"], list) or len(bundle["records"]) != len(EPISODES):
        raise EvidenceError("witness schedule missing")
    for k, (rec, (ep, _, _, _)) in enumerate(zip(bundle["records"], EPISODES)):
        verify_witness(rec, key_hex, key_id)
        if rec["episode"] != ep or rec["local_tick"] != -90000 + 31 * k:
            raise EvidenceError("witness schedule mismatch")


def verify_receiver(bundle: dict[str, Any], source: dict[str, Any], witness: dict[str, Any]) -> None:
    _fields(bundle, {"role", "records"})
    if bundle["role"] != "B" or not isinstance(bundle["records"], list) or len(bundle["records"]) != len(EPISODES):
        raise EvidenceError("receiver schedule missing")
    for k, (rec, (ep, _, _, _)) in enumerate(zip(bundle["records"], EPISODES)):
        _fields(rec, {"schema", "session", "role", "episode", "readout", "source_digest",
                      "witness_digest", "local_tick", "causal", "digest"})
        _digest_verified(rec)
        if (rec["schema"], rec["session"], rec["role"], rec["episode"]) != (SCHEMA, SESSION, "B", ep):
            raise EvidenceError("receiver episode mismatch")
        if rec["source_digest"] != source["records"][k]["digest"] or rec["witness_digest"] != witness["records"][k]["digest"]:
            raise EvidenceError("receiver uses different evidence")
        if type(rec["readout"]) is not int or rec["local_tick"] != 200 + 43 * k:
            raise EvidenceError("receiver readout or clock invalid")


def infer(source: dict[str, Any], witness: dict[str, Any], receiver: dict[str, Any],
          key_hex: str, key_id: str, *, controlled_exclusion_assured: bool = False) -> dict[str, Any]:
    verify_source(source)
    verify_witness_bundle(witness, key_hex, key_id)
    verify_receiver(receiver, source, witness)
    survivors = set(TRUTHS)
    episode_results = []
    for i, (episode, protocol, declared_event, _) in enumerate(EPISODES):
        observed_event = witness["records"][i]["event"]
        observed_output = receiver["records"][i]["readout"]
        if observed_event is not None and observed_event != declared_event:
            # This fixed fixture has declared ground-truth event schedule, not a
            # general mechanism for reconstructing arbitrary event signals.
            raise EvidenceError("fixture event differs from declared environment")
        was_admitted = observed_event is not None
        # Without event observation, there is no event-specific inference.
        # Without independent control-assurance, a controlled result could be
        # explained by an unmodelled disturbance: do not overclaim.
        scope = "not_identifiable"
        if was_admitted and (protocol == "passive" or controlled_exclusion_assured):
            for truth in list(survivors):
                if plant_value(truth, episode) != observed_output:
                    survivors.remove(truth)
            scope = "controlled_assumption" if protocol == "controlled" else "passive_association"
        episode_results.append({"episode": episode, "protocol": protocol,
                                "witness_status": witness["records"][i]["status"],
                                "observation_scope": scope,
                                "candidate_count": len(survivors)})
    if not survivors:
        raise EvidenceError("data inconsistent with all declared candidate laws")
    return {"schema": SCHEMA, "survivors": sorted(survivors),
            "episodes": episode_results,
            "controlled_exclusion_assured": controlled_exclusion_assured,
            "event_source_authentication": "HMAC-valid relative to enrolled shared secret",
            "physical_event_authentication": False,
            "physical_causation_proved": False,
            "external_clock_alignment": None}


def fixture_stamp_factory(actor: str):
    counter = [0]
    def stamp():
        counter[0] += 1
        return {"actor_id": actor, "lamport": counter[0],
                "vector": {"A": counter[0] if actor == "A" else 0,
                           "B": counter[0] if actor == "B" else 0,
                           "C": counter[0] if actor == "C" else 0}}
    return stamp


def demonstration() -> dict[str, Any]:
    # Deterministic report, with fixed TEST key only for local report reproducibility.
    # Hosted mode uses randomly generated one-run key instead.
    key_hex = "ab" * 32
    key_id = hashlib.sha256(bytes.fromhex(key_hex)).hexdigest()
    a = make_source(fixture_stamp_factory("A"))
    c = make_witness(fixture_stamp_factory("C"), key_hex, key_id)
    b = make_receiver("common_cause_marker", fixture_stamp_factory("B"), a, c)
    return {"without_control_assurance": infer(a, c, b, key_hex, key_id),
            "with_control_assurance": infer(a, c, b, key_hex, key_id,
                                             controlled_exclusion_assured=True)}

if __name__ == "__main__":
    print(json.dumps(demonstration(), indent=2, sort_keys=True))
