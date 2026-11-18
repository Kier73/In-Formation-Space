// Standalone Zero-Dependency Node.js Cross-Language Verifier for VLD Continuity Receipts (VIV-001).
// Uses ONLY Node.js built-in `node:crypto` and `node:fs` modules.

import crypto from "node:crypto";
import fs from "node:fs";

const GENESIS_DIGEST = "0".repeat(64);

export function canonicalJson(val) {
  if (val === null || typeof val === "boolean") return JSON.stringify(val);
  if (typeof val === "number") {
    if (!Number.isFinite(val)) throw new Error("Non-finite number rejected");
    if (Object.is(val, -0)) return "0";
    return JSON.stringify(val);
  }
  if (typeof val === "string") {
    if (/[\uD800-\uDFFF]/.test(val)) throw new Error("Lone UTF-16 surrogate rejected");
    return JSON.stringify(val);
  }
  if (Array.isArray(val)) return "[" + val.map(canonicalJson).join(",") + "]";
  if (typeof val === "object") {
    const keys = Object.keys(val).sort();
    return (
      "{" +
      keys
        .map((k) => {
          if (/[\uD800-\uDFFF]/.test(k)) throw new Error("Lone UTF-16 surrogate in key rejected");
          return JSON.stringify(k) + ":" + canonicalJson(val[k]);
        })
        .join(",") +
      "}"
    );
  }
  throw new Error("Unsupported value type");
}

// Python json.dumps formats float 1.0 as "1.0" whereas JS JSON.stringify(1.0) formats as "1".
// For explicit float fields (`stage_cost`), preserve Python-compatible canonical float representation.
function formatStageCostCanonical(sc) {
  const fmtFloat = (x) => {
    if (typeof x !== "number" || !Number.isFinite(x)) throw new Error("Non-finite cost");
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
  if (!domain || domain.includes("\u0000")) throw new Error("Invalid domain tag");
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
  const {
    pipeline_id,
    initial_input,
    receipts,
    expected_stages = null,
    quorum_member_ids,
    quorum_member_secrets_utf8 = null,
    require_verified_tag = true,
  } = bundle;

  if (!Array.isArray(receipts) || receipts.length === 0) {
    throw new Error("Empty receipts");
  }
  if (expected_stages !== null && receipts.length > expected_stages.length) {
    throw new Error("Receipt count exceeds expected_stages length");
  }
  if (!Array.isArray(quorum_member_ids) || quorum_member_ids.length === 0) {
    throw new Error("Invalid quorum_member_ids");
  }
  const membersSorted = [...new Set(quorum_member_ids.map(String))].sort();
  if (membersSorted.length !== quorum_member_ids.length) {
    throw new Error("Duplicate quorum_member_ids rejected");
  }
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
    const verdict = String(rcpt.oracle_verdict ?? "");
    if (!verdict.startsWith("PASS") || (require_verified_tag && !verdict.includes("|VERIFIED:"))) {
      throw new Error(`Stage ${idx} missing independent verifier attestation`);
    }

    if (expected_stages !== null) {
      const exp = expected_stages[idx];
      if (
        String(rcpt.stage_id) !== String(exp.stage_id) ||
        String(rcpt.target_ground_fingerprint) !== String(exp.ground_fingerprint) ||
        String(rcpt.source_representation) !== String(exp.input_representation) ||
        String(rcpt.target_representation) !== String(exp.output_representation)
      ) {
        throw new Error(`Stage ${idx} expected_stages specification mismatch`);
      }
    }

    const qCert = rcpt.quorum_certificate;
    const prop = qCert.proposal;
    const expMemDg = domainDigest("vld.quorum-membership.v1", {
      lineage_id: String(prop.lineage_id),
      member_ids: membersSorted,
    });
    if (prop.membership_digest !== expMemDg) throw new Error("membership_digest mismatch");

    const memDoc = qCert.membership ?? {};
    if (
      !Array.isArray(memDoc.member_ids) ||
      memDoc.member_ids.length !== membersSorted.length ||
      memDoc.member_ids.some((m, i) => String(m) !== membersSorted[i]) ||
      memDoc.membership_digest !== expMemDg ||
      Number(memDoc.quorum_size) !== qMin
    ) {
      throw new Error("Quorum certificate membership object mismatch");
    }

    const propBody = {
      lineage_id: String(prop.lineage_id),
      membership_digest: String(prop.membership_digest),
      operation_id: String(prop.operation_id),
      predecessor_manifest_digest: String(prop.predecessor_manifest_digest),
      proposer_id: String(prop.proposer_id),
      schema: "vld.quorum-proposal.v1",
      slot: Number(prop.slot),
      state_manifest_digest: String(prop.state_manifest_digest),
      term: Number(prop.term),
    };
    const propDg = domainDigest("vld.quorum-proposal.v1", propBody);
    if (prop.proposal_digest !== propDg) throw new Error("proposal_digest mismatch");

    const seen = new Set();
    const normalizedVotes = [];
    for (const v of qCert.votes) {
      const voterId = String(v.voter_id);
      if (!membersSorted.includes(voterId) || seen.has(voterId)) {
        throw new Error(`Invalid or duplicate voter ${voterId}`);
      }
      if (
        v.proposal_digest !== propDg ||
        String(v.lineage_id) !== propBody.lineage_id ||
        Number(v.slot) !== propBody.slot ||
        Number(v.term) !== propBody.term
      ) {
        throw new Error(`Stage ${idx} vote proposal/lineage/slot/term mismatch for ${voterId}`);
      }
      seen.add(voterId);
      if (quorum_member_secrets_utf8 !== null) {
        if (!Object.prototype.hasOwnProperty.call(quorum_member_secrets_utf8, voterId)) {
          throw new Error(`Missing verification secret for voter ${voterId}`);
        }
        const voteMsg = canonicalJson({
          domain: "vld.quorum-vote.v1",
          lineage_id: propBody.lineage_id,
          proposal_digest: propDg,
          slot: propBody.slot,
          term: propBody.term,
          voter_id: voterId,
        });
        const expectedHex = crypto
          .createHmac("sha256", Buffer.from(String(quorum_member_secrets_utf8[voterId]), "utf8"))
          .update(Buffer.from(voteMsg, "utf8"))
          .digest("hex");
        const suppliedBuf = Buffer.from(String(v.signature_hmac ?? ""), "utf8");
        const expectedBuf = Buffer.from(expectedHex, "utf8");
        if (suppliedBuf.length !== expectedBuf.length || !crypto.timingSafeEqual(suppliedBuf, expectedBuf)) {
          throw new Error(`HMAC mismatch for ${voterId}`);
        }
      }
      normalizedVotes.push({
        lineage_id: propBody.lineage_id,
        proposal_digest: propDg,
        signature_hmac: String(v.signature_hmac),
        slot: propBody.slot,
        term: propBody.term,
        voter_id: voterId,
      });
    }
    if (2 * seen.size <= membersSorted.length) throw new Error("Quorum strict majority failed");

    normalizedVotes.sort((a, b) => (a.voter_id < b.voter_id ? -1 : a.voter_id > b.voter_id ? 1 : 0));
    const certBody = {
      membership: {
        lineage_id: propBody.lineage_id,
        member_ids: membersSorted,
        membership_digest: expMemDg,
        quorum_size: qMin,
      },
      proposal: { ...propBody, proposal_digest: propDg },
      schema: "vld.quorum-certificate.v1",
      votes: normalizedVotes,
    };
    const computedCertDg = domainDigest("vld.quorum-certificate.v1", certBody);
    if (qCert.certificate_digest !== computedCertDg) {
      throw new Error(`Stage ${idx} certificate_digest mismatch: expected ${computedCertDg}, got ${qCert.certificate_digest}`);
    }

    const slotDg = domainDigest("vld.stage-slot.v1", {
      pipeline_id,
      stage_id: rcpt.stage_id,
      stage_index: idx,
      state_manifest_digest: rcpt.state_manifest.manifest_digest,
    });
    if (propBody.slot !== idx + 1 || propBody.state_manifest_digest !== slotDg || propBody.predecessor_manifest_digest !== prevSlotDg) {
      throw new Error(`Stage ${idx} quorum slot/predecessor mismatch`);
    }

    const bodyJson =
      "{" +
      '"clock_bridge_digest":' +
      canonicalJson(rcpt.clock_bridge_digest) +
      ',"host_id":' +
      canonicalJson(rcpt.host_id) +
      ',"oracle_verdict":' +
      canonicalJson(verdict) +
      ',"pipeline_id":' +
      canonicalJson(pipeline_id) +
      ',"prev_continuity_digest":' +
      canonicalJson(prevContDg) +
      ',"quorum_cert_digest":' +
      canonicalJson(computedCertDg) +
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

if (process.argv[1] && process.argv[2] && import.meta.url.endsWith("vld_standalone_verifier.mjs")) {
  const raw = fs.readFileSync(process.argv[2], "utf8");
  const out = verifyContinuityChain(JSON.parse(raw));
  console.log(JSON.stringify(out));
}
