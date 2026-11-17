"""CGS-008 independent Python evidence checker for public-only Ed25519 transcripts.

This separately rechecks actual signatures, role continuity, receiver checkpoint
and two observation rounds. A pinned bootstrap and trusted receiver checkpoint
are explicit assumptions: signatures do not prove sensor truth or physical time.
"""
from __future__ import annotations
import base64
import hashlib
import json
import sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

PREFIX = b"IFS-CGS008-SIGNED\0"
ZERO = "0" * 64

def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError("CGS-008 independent verifier refused: " + why)

def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")

def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()

def loadkey(text: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(text.encode("ascii"))
    require(isinstance(key, Ed25519PublicKey), "expected Ed25519 source")
    return key

def keyid(pem: str) -> str:
    return hashlib.sha256(loadkey(pem).public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()

def signed(doc: dict, keys: list[str], threshold: int) -> str:
    require(type(doc) is dict and set(doc) == {"body", "signatures"}, "bad envelope")
    require(type(doc["signatures"]) is list, "missing signatures")
    authorized = {keyid(pem): loadkey(pem) for pem in keys}
    require(len(authorized) == len(keys), "duplicate trust key")
    seen: set[str] = set()
    for entry in doc["signatures"]:
        require(set(entry) == {"key_id", "signature"}, "bad signature entry")
        kid = entry["key_id"]
        require(kid in authorized and kid not in seen, "unrecognized/reused signer")
        seen.add(kid)
        raw = base64.b64decode(entry["signature"], validate=True)
        require(len(raw) == 64 and base64.b64encode(raw).decode("ascii") == entry["signature"],
                "noncanonical signature")
        try:
            authorized[kid].verify(raw, PREFIX + canonical(doc["body"]))
        except InvalidSignature as exc:
            raise ValueError("CGS-008 independent verifier refused: invalid signature") from exc
    require(len(seen) >= threshold, "signature threshold unmet")
    return digest(doc["body"])

def checkpoint(trust: dict, document: dict) -> str:
    body = document["body"]
    require(body["schema"] == "ifs.cgs008-receiver-checkpoint/0.1" and
            body["ground"] == trust["ground"] and body["realm"] == trust["realm"] and
            type(body["counter"]) is int and body["counter"] >= 0 and
            type(body["policy_version"]) is int and body["policy_version"] >= 0 and
            type(body["last_time"]) is int and body["last_time"] >= 0,
            "receiver checkpoint invalid")
    signed(document, [trust["receiver"]], 1)
    return digest(body)

def ledger(trust: dict, policies: list[dict]) -> list[str]:
    require(trust["schema"] == "ifs.cgs008-trust/0.1" and
            trust["threshold"] == 2 and len(trust["roots"]) == 2 and
            len({keyid(x) for x in trust["roots"]}) == 2,
            "bootstrap must pin 2 distinct authorities")
    previous = ZERO
    all_digests = []
    previous_active: dict[str, str] = {}
    for n, manifest in enumerate(policies, 1):
        b = manifest["body"]
        require(b["schema"] == "ifs.cgs008-policy/0.1" and b["version"] == n and
                b["previous"] == previous and b["ground"] == trust["ground"] and
                b["realm"] == trust["realm"] and
                type(b["valid_from"]) is int and type(b["expires"]) is int and
                b["valid_from"] < b["expires"], "policy history forked")
        actual = signed(manifest, trust["roots"], 2)
        grants = {g["observer"]: keyid(g["public_key"]) for g in b["grants"]}
        require(len(grants) == len(b["grants"]) and len(set(grants.values())) == len(grants) and
                len(grants) >= 2, "observer identity reused")
        require(not (set(grants) & set(b["revoked"])), "revoked grant still active")
        if n > 1:
            require(set(previous_active)-set(grants) <= set(b["revoked"]),
                    "missing explicit observer revocation")
        previous_active = grants
        previous = actual
        all_digests.append(actual)
    return all_digests

def verify_round(trust: dict, log: list[dict], policy_digest: str,
                 earlier: dict, before: dict, request: dict, responses: list[dict],
                 after: dict, now: int) -> dict:
    checkpoint(trust, earlier)
    checkpoint(trust, before)
    checkpoint(trust, after)
    e, b = earlier["body"], before["body"]
    require(e["counter"] == b["counter"] and
            e["last_receipt"] == b["last_receipt"] and
            e["policy_version"] <= b["policy_version"] and
            e["last_time"] <= b["last_time"],
            "receiver checkpoint ancestry mismatch")
    signed(request, [trust["receiver"]], 1)
    policy = next(p for p in log if digest(p["body"]) == policy_digest)
    b, q = before["body"], request["body"]
    require(q["schema"] == "ifs.cgs008-receiver-challenge/0.1" and
            q["checkpoint_digest"] == digest(b) and
            q["policy_digest"] == policy_digest and
            q["ground"] == trust["ground"] and q["realm"] == trust["realm"] and
            q["policy_version"] == policy["body"]["version"] == b["policy_version"] and
            b["policy_digest"] == policy_digest and
            q["counter"] == b["counter"] + 1 and
            b["last_time"] <= q["issued_at"] <= now < q["expires_at"] <= q["issued_at"]+10 and
            policy["body"]["valid_from"] <= now < policy["body"]["expires"],
            "stale receiver authorization")
    grants = {g["observer"]: g["public_key"] for g in policy["body"]["grants"]}
    require(len(responses) == 2, "two independent responses required")
    seen: set[str] = set()
    values=[]
    for envelope in responses:
        r = envelope["body"]
        require(r["observer"] in grants and r["observer"] not in seen,
                "unapproved or duplicated observer")
        seen.add(r["observer"])
        signed(envelope, [grants[r["observer"]]], 1)
        require(r["schema"] == "ifs.cgs008-observation/0.1" and
                r["policy_digest"] == q["policy_digest"] and
                r["policy_version"] == q["policy_version"] and
                r["ground"] == q["ground"] and r["realm"] == q["realm"] and
                r["counter"] == q["counter"] and r["nonce"] == q["nonce"] and
                r["challenge_digest"] == digest(q) and
                r["feature"] == q["feature"] == "parity" and
                type(r["value"]) is int and r["value"] in (0, 1),
                "forged/incorrect observation binding")
        values.append(r["value"])
    verdict = "ADMITTED_AGREEMENT" if values[0] == values[1] else "REFUSED_DISAGREEMENT"
    final = after["body"]
    require(final["counter"] == q["counter"] and
            final["policy_digest"] == policy_digest and
            final["policy_version"] == b["policy_version"] and
            final["last_time"] == now and
            final["last_receipt"] == digest({"request":q,
                "signatures":[{"body":x["body"],"signatures":x["signatures"]} for x in responses]}),
            "receipt checkpoint not committed")
    return {"verdict": verdict, "peer_values": values,
            "current_authority": True, "sensor_truth_established": False}

def verify_bundle(bundle: dict) -> dict:
    trust, log = bundle["trust"], bundle["policies"]
    digests = ledger(trust, log)
    checkpoint(trust,bundle["checkpoint0"])
    checkpoint(trust,bundle["checkpoint1"])
    checkpoint(trust,bundle["checkpoint2"])
    require(bundle["checkpoint1"]["body"]["policy_digest"] == digests[0] and
            bundle["checkpoint2"]["body"]["policy_digest"] == digests[1],
            "receiver's pinned policy differs")
    one = verify_round(trust, log, digests[0],bundle["checkpoint0"],
        bundle["checkpoint1"],bundle["request1"],bundle["receipts1"],
        bundle["checkpoint_after1"],161)
    two = verify_round(trust, log, digests[1],bundle["checkpoint_after1"],
        bundle["checkpoint2"],bundle["request2"],bundle["receipts2"],
        bundle["checkpoint_after2"],262)
    require(one["verdict"] == "ADMITTED_AGREEMENT" and
            two["verdict"] == "REFUSED_DISAGREEMENT", "unexpected experimental outcomes")
    require(bundle["outcomes"]["history"]["current_authority"] is False and
            bundle["outcomes"]["history"]["event_time_proven"] is False,
            "unjustified historical claim")
    return {"independent_verification":"passed","policies":len(log),
        "distinct_root_signers":2,"signed_active_receipts":4,
        "rounds":[one,two],"historical_evidence_current_authority":False}

if __name__ == "__main__":
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf8"))
    print(json.dumps(verify_bundle(data),sort_keys=True,indent=2))
