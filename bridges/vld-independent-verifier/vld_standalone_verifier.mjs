// Standalone Zero-Dependency Node.js Cross-Language Verifier for VLD Continuity Receipts (VIV-001).
// Uses ONLY Node.js built-in `node:crypto` and `node:fs` modules.

import crypto from "node:crypto";
import fs from "node:fs";

const GENESIS_DIGEST = "0".repeat(64);

export function canonicalJson(val) {
  if (val === null || typeof val === "boolean") return JSON.stringify(val);
  if (typeof val === "number") {
    if (!Number.isFinite(val)) throw new Error("Non-finite number rejected");
    if (Object.is(val, -0)) return "0.0";
    // Match Python json.dumps float formatting on integer-valued vs fractional floats where needed
    return JSON.stringify(val);
  }
  if (typeof val === "string") return JSON.stringify(val);
  if (Array.isArray(val)) return "[" + val.map(canonicalJson).join(",") + "]";
  if (typeof val === "object") {
    const keys = Object.keys(val).sort();
    return (
      "{" +
      keys.map((k) => JSON.stringify(k) + ":" + canonicalJson(val[k])).join(",") +
      "}"
    );
  }
  throw new Error("Unsupported value type");
}

// Python json.dumps formats float 1.0 as "1.0" whereas JS JSON.stringify(1.0) formats as "1".
// For cross-language float fields (`stage_cost`), preserve exact numeric tokens from JSON or format explicit float fields!
function formatStageCostCanonical(sc) {
  const fmtFloat = (x) => {
    if (!Number.isFinite(x)) throw new Error("Non-finite cost");
    const s = String(Object.is(x, -0) ? 0 : x);
    return s.includes(".") || s.includes("e") || s.includes("E") ? s : s + ".0";
  };
  return (
    '{"bytes_moved":' +
    fmtFloat(sc.bytes_moved) +
    ',"compute_ops":' +
    fmtFloat(sc.compute_ops) +
    ',"latency_ms":' +
    fmtFloat(sc.latency_ms) +
    ',"verification_ops":' +
    fmtFloat(sc.verification_ops) +
    "}"
  );
}

export function domainDigestRaw(domain, utf8Body) {
  const h = crypto.createHash("sha256");
  h.update(Buffer.from(domain, "utf8"));
  h.update(Buffer.from([0x00]));
  h.update(Buffer.from(utf8Body, "utf8"));
  return h.digest("hex");
}

export function domainDigest(domain, payload) {
  return domainDigestRaw(domain, canonicalJson(payload));
}

export function verifyContinuityChain(bundle) {
  const { pipeline_id, initial_input, receipts, quorum_member_ids, quorum_member_secrets_utf8 } = bundle;
  if (!Array.isArray(receipts) || receipts.length === 0) {
    throw new Error("Empty receipts");
  }
  const membersSorted = [...quorum_member_ids].sort();
  const qMin = Math.floor(membersSorted.length / 2) + 1;

  let prevGroundFp = domainDigest("vld.pipeline-genesis.v1", {
    input: initial_input,
    pipeline_id,
  });
  let prevContDg = GENESIS_DIGEST;
  let prevSlotDg = GENESIS_DIGEST;

  for (let idx = 0; idx < receipts.length; idx++) {
    const rcpt = receipts[idx];
    if (rcpt.pipeline_id !== pipeline_id || rcpt.stage_index !== idx) {
      throw new Error(`Stage ${idx} identity mismatch`);
    }
    if (rcpt.prev_continuity_digest !== prevContDg) {
      throw new Error(`Stage ${idx} broken prev_continuity_digest`);
    }
    if (rcpt.source_ground_fingerprint !== prevGroundFp) {
      throw new Error(`Stage ${idx} source_ground_fingerprint mismatch`);
    }
    if (!String(rcpt.oracle_verdict).startsWith("PASS") || !String(rcpt.oracle_verdict).includes("|VERIFIED:")) {
      throw new Error(`Stage ${idx} missing independent verifier attestation`);
    }

    const qCert = rcpt.quorum_certificate;
    const prop = qCert.proposal;
    const expMemDg = domainDigest("vld.quorum-membership.v1", {
      lineage_id: prop.lineage_id,
      member_ids: membersSorted,
    });
    if (prop.membership_digest !== expMemDg) throw new Error("membership_digest mismatch");

    const propBody = {
      lineage_id: prop.lineage_id,
      membership_digest: prop.membership_digest,
      operation_id: prop.operation_id,
      predecessor_manifest_digest: prop.predecessor_manifest_digest,
      proposer_id: prop.proposer_id,
      schema: "vld.quorum-proposal.v1",
      slot: prop.slot,
      state_manifest_digest: prop.state_manifest_digest,
      term: prop.term,
    };
    const propDg = domainDigest("vld.quorum-proposal.v1", propBody);
    if (prop.proposal_digest !== propDg) throw new Error("proposal_digest mismatch");

    const seen = new Set();
    for (const v of qCert.votes) {
      if (!membersSorted.includes(v.voter_id) || seen.has(v.voter_id)) {
        throw new Error(`Invalid or duplicate voter ${v.voter_id}`);
      }
      seen.add(v.voter_id);
      if (quorum_member_secrets_utf8 && quorum_member_secrets_utf8[v.voter_id]) {
        const voteMsg = canonicalJson({
          domain: "vld.quorum-vote.v1",
          lineage_id: v.lineage_id,
          proposal_digest: v.proposal_digest,
          slot: v.slot,
          term: v.term,
          voter_id: v.voter_id,
        });
        const sig = crypto
          .createHmac("sha256", Buffer.from(quorum_member_secrets_utf8[v.voter_id], "utf8"))
          .update(Buffer.from(voteMsg, "utf8"))
          .digest("hex");
        if (sig !== v.signature_hmac) throw new Error(`HMAC mismatch for ${v.voter_id}`);
      }
    }
    if (2 * seen.size <= membersSorted.length) throw new Error("Quorum strict majority failed");

    const slotDg = domainDigest("vld.stage-slot.v1", {
      pipeline_id,
      stage_id: rcpt.stage_id,
      stage_index: idx,
      state_manifest_digest: rcpt.state_manifest.manifest_digest,
    });
    if (prop.slot !== idx + 1 || prop.state_manifest_digest !== slotDg || prop.predecessor_manifest_digest !== prevSlotDg) {
      throw new Error(`Stage ${idx} quorum slot/predecessor mismatch`);
    }

    const bodyJson =
      "{" +
      '"clock_bridge_digest":' +
      canonicalJson(rcpt.clock_bridge_digest) +
      ',"host_id":' +
      canonicalJson(rcpt.host_id) +
      ',"oracle_verdict":' +
      canonicalJson(rcpt.oracle_verdict) +
      ',"pipeline_id":' +
      canonicalJson(pipeline_id) +
      ',"prev_continuity_digest":' +
      canonicalJson(prevContDg) +
      ',"quorum_cert_digest":' +
      canonicalJson(qCert.certificate_digest) +
      ',"scheduler_id":' +
      canonicalJson(rcpt.scheduler_id) +
      ',"schema":"vld.cross-ground-continuity-receipt.v1"' +
      ',"source_ground_fingerprint":' +
      canonicalJson(rcpt.source_ground_fingerprint) +
      ',"source_representation":' +
      canonicalJson(rcpt.source_representation) +
      ',"stage_cost":' +
      formatStageCostCanonical(rcpt.stage_cost) +
      ',"stage_id":' +
      canonicalJson(rcpt.stage_id) +
      ',"stage_index":' +
      canonicalJson(idx) +
      ',"state_manifest":' +
      canonicalJson(rcpt.state_manifest) +
      ',"target_ground_fingerprint":' +
      canonicalJson(rcpt.target_ground_fingerprint) +
      ',"target_representation":' +
      canonicalJson(rcpt.target_representation) +
      ',"temporal":' +
      canonicalJson(rcpt.temporal) +
      "}";
    const contDg = domainDigestRaw("vld.cross-ground-continuity-receipt.v1", bodyJson);
    if (rcpt.continuity_digest !== contDg) {
      throw new Error(`Stage ${idx} continuity_digest mismatch: expected ${contDg}, got ${rcpt.continuity_digest}`);
    }

    prevContDg = contDg;
    prevSlotDg = slotDg;
    prevGroundFp = rcpt.target_ground_fingerprint;
  }

  return {
    final_continuity_digest: prevContDg,
    stages_verified: receipts.length,
    status: "VERIFIED_NODEJS",
  };
}

if (process.argv[2]) {
  const raw = fs.readFileSync(process.argv[2], "utf8");
  const out = verifyContinuityChain(JSON.parse(raw));
  console.log(JSON.stringify(out));
}
