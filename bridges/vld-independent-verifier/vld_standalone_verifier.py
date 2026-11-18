"""Standalone zero-dependency Python verifier for Virtual Layer Dynamics receipts & capsules (VIV-001).

Shares ZERO imports with `vld`: uses only Python standard library (`fractions`, `hashlib`, `hmac`, `json`, `math`).
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import hmac
import json
import math
from typing import Any, Mapping, Sequence

GENESIS_DIGEST = "0" * 64


class VerificationError(ValueError):
    """Raised when an audited digest, quorum certificate, continuity receipt, or capsule fails verification."""


def _no_dup_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise VerificationError(f"Duplicate JSON key {k!r}.")
        out[k] = v
    return out


def _clean(val: Any) -> Any:
    if val is None or isinstance(val, (bool, int)):
        return val
    if isinstance(val, float):
        if not math.isfinite(val):
            raise VerificationError("Non-finite float rejected.")
        return 0.0 if val == 0.0 else val
    if isinstance(val, str):
        val.encode("utf-8", errors="strict")
        return val
    if isinstance(val, (list, tuple)):
        return [_clean(x) for x in val]
    if isinstance(val, Mapping):
        return {str(k): _clean(v) for k, v in val.items()}
    raise VerificationError(f"Unsupported type {type(val).__name__}.")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(_clean(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def parse_strict_json(raw: str | bytes) -> Any:
    text = raw.decode("utf-8", errors="strict") if isinstance(raw, (bytes, bytearray)) else raw
    return _clean(
        json.loads(
            text,
            object_pairs_hook=_no_dup_keys,
            parse_constant=lambda c: (_ for _ in ()).throw(VerificationError(f"Forbidden constant {c!r}")),
        )
    )


def domain_digest(domain: str, payload: Any) -> str:
    if not domain or "\x00" in domain:
        raise VerificationError("Invalid domain tag.")
    h = hashlib.sha256()
    h.update(domain.encode("utf-8"))
    h.update(b"\x00")
    h.update(canonical_bytes(payload))
    return h.hexdigest()


def verify_quorum_certificate(
    cert_dict: Mapping[str, Any],
    *,
    member_ids: Sequence[str],
    member_secrets: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    members_sorted = sorted(set(str(m) for m in member_ids))
    n_total = len(members_sorted)
    if n_total == 0 or len(members_sorted) != len(member_ids):
        raise VerificationError("Invalid quorum membership.")
    q_min = (n_total // 2) + 1

    prop = cert_dict["proposal"]
    exp_mem_dg = domain_digest("vld.quorum-membership.v1", {"lineage_id": str(prop["lineage_id"]), "member_ids": members_sorted})
    if prop["membership_digest"] != exp_mem_dg:
        raise VerificationError("membership_digest mismatch.")

    prop_body = {
        "lineage_id": str(prop["lineage_id"]),
        "membership_digest": str(prop["membership_digest"]),
        "operation_id": str(prop["operation_id"]),
        "predecessor_manifest_digest": str(prop["predecessor_manifest_digest"]),
        "proposer_id": str(prop["proposer_id"]),
        "schema": "vld.quorum-proposal.v1",
        "slot": int(prop["slot"]),
        "state_manifest_digest": str(prop["state_manifest_digest"]),
        "term": int(prop["term"]),
    }
    prop_dg = domain_digest("vld.quorum-proposal.v1", prop_body)
    if prop.get("proposal_digest") != prop_dg:
        raise VerificationError("proposal_digest mismatch.")

    votes = list(cert_dict["votes"])
    seen: set[str] = set()
    for v in votes:
        vid = str(v["voter_id"])
        if vid not in members_sorted or vid in seen:
            raise VerificationError(f"Invalid or duplicate voter {vid!r}.")
        if (
            v["proposal_digest"] != prop_dg
            or str(v["lineage_id"]) != str(prop["lineage_id"])
            or int(v["slot"]) != int(prop["slot"])
            or int(v["term"]) != int(prop["term"])
        ):
            raise VerificationError("Vote coordinates mismatch proposal.")
        seen.add(vid)
        if member_secrets is not None:
            if vid not in member_secrets:
                raise VerificationError(f"Missing verification secret for voter {vid!r}.")
            msg = canonical_bytes(
                {
                    "domain": "vld.quorum-vote.v1",
                    "lineage_id": str(v["lineage_id"]),
                    "proposal_digest": str(v["proposal_digest"]),
                    "slot": int(v["slot"]),
                    "term": int(v["term"]),
                    "voter_id": vid,
                }
            )
            sig = hmac.new(member_secrets[vid], msg, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(str(v["signature_hmac"]), sig):
                raise VerificationError(f"HMAC signature mismatch for {vid!r}.")

    if 2 * len(seen) <= n_total:
        raise VerificationError("Quorum strict majority 2q > N failed.")

    cert_body = {
        "membership": {
            "lineage_id": str(prop["lineage_id"]),
            "member_ids": members_sorted,
            "membership_digest": exp_mem_dg,
            "quorum_size": q_min,
        },
        "proposal": {**prop_body, "proposal_digest": prop_dg},
        "schema": "vld.quorum-certificate.v1",
        "votes": sorted(
            [
                {
                    "lineage_id": str(v["lineage_id"]),
                    "proposal_digest": str(v["proposal_digest"]),
                    "signature_hmac": str(v["signature_hmac"]),
                    "slot": int(v["slot"]),
                    "term": int(v["term"]),
                    "voter_id": str(v["voter_id"]),
                }
                for v in votes
            ],
            key=lambda item: item["voter_id"],
        ),
    }
    cert_dg = domain_digest("vld.quorum-certificate.v1", cert_body)
    if cert_dict.get("certificate_digest") != cert_dg:
        raise VerificationError("certificate_digest mismatch.")
    return {"certificate_digest": cert_dg, "votes_verified": len(seen)}


def verify_continuity_chain(
    receipts: Sequence[Mapping[str, Any]],
    *,
    pipeline_id: str,
    initial_input: Mapping[str, Any],
    expected_stages: Sequence[Mapping[str, str]] | None = None,
    quorum_member_ids: Sequence[str] | None = None,
    quorum_member_secrets: Mapping[str, bytes] | None = None,
    require_verified_tag: bool = True,
) -> dict[str, Any]:
    if not receipts:
        raise VerificationError("Empty receipt chain.")
    clean_init = parse_strict_json(canonical_bytes(dict(initial_input)))
    prev_ground_fp = domain_digest("vld.pipeline-genesis.v1", {"input": clean_init, "pipeline_id": pipeline_id})
    prev_cont_dg = GENESIS_DIGEST
    prev_slot_dg = GENESIS_DIGEST

    for idx, rcpt in enumerate(receipts):
        if str(rcpt["pipeline_id"]) != pipeline_id or int(rcpt["stage_index"]) != idx:
            raise VerificationError(f"Stage {idx} identity mismatch.")
        if str(rcpt["prev_continuity_digest"]) != prev_cont_dg:
            raise VerificationError(f"Stage {idx} broken prev_continuity_digest.")
        if str(rcpt["source_ground_fingerprint"]) != prev_ground_fp:
            raise VerificationError(f"Stage {idx} source_ground_fingerprint mismatch (genesis or upstream Ground altered).")
        verdict = str(rcpt["oracle_verdict"])
        if not verdict.startswith("PASS") or (require_verified_tag and "|VERIFIED:" not in verdict):
            raise VerificationError(f"Stage {idx} lacks independent verifier attestation: {verdict!r}")

        if expected_stages is not None:
            exp = expected_stages[idx]
            if (
                str(rcpt["stage_id"]) != exp["stage_id"]
                or str(rcpt["target_ground_fingerprint"]) != exp["ground_fingerprint"]
                or str(rcpt["source_representation"]) != exp["input_representation"]
                or str(rcpt["target_representation"]) != exp["output_representation"]
            ):
                raise VerificationError(f"Stage {idx} stage specification mismatch.")

        q_cert = rcpt["quorum_certificate"]
        if quorum_member_ids is not None:
            verify_quorum_certificate(q_cert, member_ids=quorum_member_ids, member_secrets=quorum_member_secrets)

        state_m = rcpt["state_manifest"]
        slot_dg = domain_digest(
            "vld.stage-slot.v1",
            {
                "pipeline_id": pipeline_id,
                "stage_id": str(rcpt["stage_id"]),
                "stage_index": idx,
                "state_manifest_digest": str(state_m["manifest_digest"]),
            },
        )
        prop = q_cert["proposal"]
        if int(prop["slot"]) != idx + 1 or prop["state_manifest_digest"] != slot_dg or prop["predecessor_manifest_digest"] != prev_slot_dg:
            raise VerificationError(f"Stage {idx} quorum slot/predecessor binding mismatch.")

        body = {
            "clock_bridge_digest": rcpt["clock_bridge_digest"],
            "host_id": str(rcpt["host_id"]),
            "oracle_verdict": verdict,
            "pipeline_id": pipeline_id,
            "prev_continuity_digest": prev_cont_dg,
            "quorum_cert_digest": str(q_cert["certificate_digest"]),
            "scheduler_id": str(rcpt["scheduler_id"]),
            "schema": "vld.cross-ground-continuity-receipt.v1",
            "source_ground_fingerprint": str(rcpt["source_ground_fingerprint"]),
            "source_representation": str(rcpt["source_representation"]),
            "stage_cost": dict(rcpt["stage_cost"]),
            "stage_id": str(rcpt["stage_id"]),
            "stage_index": idx,
            "state_manifest": dict(state_m),
            "target_ground_fingerprint": str(rcpt["target_ground_fingerprint"]),
            "target_representation": str(rcpt["target_representation"]),
            "temporal": dict(rcpt["temporal"]),
        }
        cont_dg = domain_digest("vld.cross-ground-continuity-receipt.v1", body)
        if str(rcpt["continuity_digest"]) != cont_dg:
            raise VerificationError(f"Stage {idx} continuity_digest mismatch.")
        prev_cont_dg = cont_dg
        prev_slot_dg = slot_dg
        prev_ground_fp = str(rcpt["target_ground_fingerprint"])

    return {"final_continuity_digest": prev_cont_dg, "stages_verified": len(receipts), "status": "VERIFIED"}


def verify_snc_1d_capsule(capsule: Mapping[str, Any]) -> dict[str, Any]:
    if capsule.get("schema") != "vld.snc-relu-capsule.v1":
        raise VerificationError("Invalid 1D SNC schema.")
    body = {k: v for k, v in capsule.items() if k != "capsule_digest"}
    if capsule.get("capsule_digest") != domain_digest("vld.snc-relu-capsule.v1", body):
        raise VerificationError("capsule_digest mismatch.")
    atlas = list(capsule["source_atlas"])
    if not atlas or capsule.get("source_atlas_digest") != domain_digest("vld.semantic-atlas.v1", atlas):
        raise VerificationError("source_atlas_digest mismatch or empty atlas.")
    net = capsule["network"]
    if not isinstance(net, Mapping) or net.get("hidden_activation") != "relu":
        raise VerificationError("1D SNC capsule requires hidden_activation == 'relu'.")
    raw_w1, raw_b1 = net.get("hidden_weight"), net.get("hidden_bias")
    raw_w2, raw_b2 = net.get("output_weight"), net.get("output_bias")
    if (
        not isinstance(raw_w1, (list, tuple))
        or not raw_w1
        or any(not isinstance(r, (list, tuple)) or len(r) != 1 for r in raw_w1)
        or not isinstance(raw_b1, (list, tuple))
        or len(raw_b1) != len(raw_w1)
        or not isinstance(raw_b2, (list, tuple))
        or not raw_b2
        or not isinstance(raw_w2, (list, tuple))
        or len(raw_w2) != len(raw_b2)
        or any(not isinstance(r, (list, tuple)) or len(r) != len(raw_w1) for r in raw_w2)
    ):
        raise VerificationError("Invalid 1D SNC layer geometry.")
    w1 = [Fraction(row[0]) for row in raw_w1]
    b1 = [Fraction(v) for v in raw_b1]
    w2 = [[Fraction(v) for v in row] for row in raw_w2]
    b2 = [Fraction(v) for v in raw_b2]

    parsed_regions: list[tuple[Fraction | None, Fraction | None, list[tuple[Fraction, Fraction]]]] = []
    for idx, reg in enumerate(atlas):
        if not isinstance(reg, Mapping) or set(reg.keys()) != {"left", "right", "affines"}:
            raise VerificationError("Invalid atlas region keys.")
        l_v = None if reg["left"] == "-inf" else Fraction(reg["left"])
        r_v = None if reg["right"] == "+inf" else Fraction(reg["right"])
        if (l_v is None) != (idx == 0) or (r_v is None) != (idx == len(atlas) - 1):
            raise VerificationError("Atlas must partition (-inf, +inf).")
        if l_v is not None and r_v is not None and l_v >= r_v:
            raise VerificationError("Inverted or empty atlas interval.")
        affs = [(Fraction(a[0]), Fraction(a[1])) for a in reg["affines"]]
        if len(affs) != len(b2):
            raise VerificationError("Inconsistent output arity in atlas.")
        if parsed_regions:
            _, prev_r, prev_affs = parsed_regions[-1]
            if prev_r != l_v:
                raise VerificationError("Gap or overlap in 1D SNC source_atlas.")
            assert l_v is not None
            for (m1, c1), (m2, c2) in zip(prev_affs, affs):
                if m1 * l_v + c1 != m2 * l_v + c2:
                    raise VerificationError(f"Discontinuous 1D SNC atlas at {l_v}.")
        parsed_regions.append((l_v, r_v, affs))

    kinks = sorted(
        {
            *(l_v for l_v, _, _ in parsed_regions if l_v is not None),
            *(r_v for _, r_v, _ in parsed_regions if r_v is not None),
            *(-b / w for w, b in zip(w1, b1) if w != 0),
        }
    )
    pts = [Fraction(-1), Fraction(1)] if not kinks else [kinks[0] - 2, kinks[0] - 1, *kinks, kinks[-1] + 1, kinks[-1] + 2]
    for a, b in zip(kinks, kinks[1:]):
        pts.extend([a + (b - a) / 3, a + 2 * (b - a) / 3])

    for x in pts:
        h = [max(Fraction(0), w * x + b) for w, b in zip(w1, b1)]
        y_net = [b2[o] + sum(w2[o][j] * h[j] for j in range(len(h))) for o in range(len(b2))]
        y_ref = None
        for l_v, r_v, affs in parsed_regions:
            if (l_v is None or x >= l_v) and (r_v is None or x <= r_v):
                y_ref = [m * x + c for m, c in affs]
                break
        if y_ref is None or y_net != y_ref:
            raise VerificationError(f"SNC capsule disagrees at x={x}.")
    return {"points_checked": len(pts), "status": "VERIFIED"}
