#!/usr/bin/env node
/**
 * Independent prepared-result validator.
 *
 * This process validates the portable envelope, its assigned E-CPU claim
 * identity, both PSC checkpoints, and the exact typed one-step transition.
 * The live quorum proof remains the responsibility of the E-CPU claim store.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";
import { verifyPortableStatefulCheckpoint } from "./verify_capsule.mjs";

const PREPARED_SCHEMA = "ifs.psc.stateful-recovery-worker-prepared.v2";
const ENVELOPE_SCHEMA = "in-formation-space.stateful-runtime-recovery-handoff.v1";
const MAX_INPUT_BYTES = 96 * 1024 * 1024;

function fail(message) {
  throw new Error(message);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value, expected, field) {
  if (!isObject(value)) fail(`${field} must be an object`);
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) {
    fail(`${field} fields do not match the exact schema`);
  }
}

function canonical(value, field = "$") {
  if (value === null || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) fail(`${field} must contain only interoperable safe integers`);
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item, index) => canonical(item, `${field}[${index}]`)).join(",")}]`;
  }
  if (isObject(value)) {
    const keys = Object.keys(value);
    if (keys.some((key) => !/^[\x00-\x7f]*$/.test(key))) {
      fail(`${field} object keys must be ASCII`);
    }
    keys.sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonical(value[key], `${field}.${key}`)}`).join(",")}}`;
  }
  fail(`${field} contains a value outside canonical metadata v1`);
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function objectDigest(value) {
  return sha256(Buffer.from(canonical(value), "utf8"));
}

function requireText(value, field) {
  if (typeof value !== "string" || value.length === 0 || value.trim() !== value) {
    fail(`${field} must be non-empty trimmed text`);
  }
  return value;
}

function requireDigest(value, field) {
  const selected = requireText(value, field);
  if (!/^[0-9a-f]{64}$/.test(selected)) fail(`${field} must be a lowercase SHA-256 digest`);
  return selected;
}

function requireInteger(value, field, minimum = 0) {
  if (!Number.isSafeInteger(value) || value < minimum) fail(`${field} must be an integer >= ${minimum}`);
  return value;
}

function same(left, right) {
  return canonical(left) === canonical(right);
}

function readJsonFile(path, field) {
  const bytes = readFileSync(path);
  if (bytes.length === 0 || bytes.length > MAX_INPUT_BYTES) {
    fail(`${field} is empty or exceeds its finite byte bound`);
  }
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    fail(`${field} is not valid UTF-8 JSON`);
  }
}

function decodeCanonicalBase64(value, field, maxBytes = MAX_INPUT_BYTES) {
  if (typeof value !== "string" || value.length > Math.ceil(maxBytes / 3) * 4) {
    fail(`${field} is missing or exceeds its finite Base64 bound`);
  }
  const decoded = Buffer.from(value, "base64");
  if (decoded.length === 0 || decoded.length > maxBytes || decoded.toString("base64") !== value) {
    fail(`${field} is not canonical Base64 or exceeds its finite byte bound`);
  }
  return decoded;
}

function validateEnvelope(envelope) {
  exactKeys(
    envelope,
    ["schema", "session_id", "checkpoint_sha256", "checkpoint_base64", "ticket", "envelope_sha256"],
    "handoff envelope"
  );
  if (envelope.schema !== ENVELOPE_SCHEMA) fail("unsupported handoff envelope schema");
  requireText(envelope.session_id, "envelope.session_id");
  const envelopeDigest = requireDigest(envelope.envelope_sha256, "envelope.envelope_sha256");
  const { envelope_sha256: _discarded, ...envelopeCore } = envelope;
  if (objectDigest(envelopeCore) !== envelopeDigest) fail("handoff envelope digest mismatch");

  const checkpoint = decodeCanonicalBase64(envelope.checkpoint_base64, "envelope.checkpoint_base64");
  const checkpointDigest = requireDigest(envelope.checkpoint_sha256, "envelope.checkpoint_sha256");
  if (sha256(checkpoint) !== checkpointDigest) fail("handoff input checkpoint digest mismatch");

  const ticket = envelope.ticket;
  exactKeys(
    ticket,
    ["schema", "claim", "manifest", "proof", "state_commitment", "claim_index", "merkle_proof", "digest"],
    "portable execution claim ticket"
  );
  if (ticket.schema !== "mailcpu.portable-execution-claim-bundle.v2") {
    fail("unsupported portable execution claim bundle schema");
  }
  const { digest: ticketDigest, ...ticketCore } = ticket;
  if (objectDigest(ticketCore) !== requireDigest(ticketDigest, "ticket.digest")) {
    fail("portable claim ticket digest mismatch");
  }

  const claim = ticket.claim;
  exactKeys(
    claim,
    [
      "schema", "parent_request_digest", "child_request_digest", "address_digest",
      "operator_id", "operator_contract_digest", "operator_spec",
      "computational_ground_fingerprint", "replay_policy", "assignments",
      "status", "result_digest", "child_receipt_digest", "completion_generation",
      "claim_id", "digest",
    ],
    "execution claim"
  );
  if (claim.schema !== "mailcpu.transferable-execution-claim.v1") {
    fail("unsupported execution claim schema");
  }
  const { claim_id: claimId, digest: claimDigest, ...claimPayload } = claim;
  if (objectDigest(claimPayload) !== requireDigest(claimDigest, "claim.digest")) {
    fail("execution claim digest mismatch");
  }
  const identity = {
    schema: "mailcpu.transferable-execution-claim-identity.v1",
    parent_request_digest: claim.parent_request_digest,
    child_request_digest: claim.child_request_digest,
    address_digest: claim.address_digest,
    operator_id: claim.operator_id,
    operator_contract_digest: claim.operator_contract_digest,
    operator_spec: claim.operator_spec,
    computational_ground_fingerprint: claim.computational_ground_fingerprint,
    replay_policy: claim.replay_policy,
  };
  if (objectDigest(identity) !== requireDigest(claimId, "claim.claim_id")) {
    fail("execution claim stable identity mismatch");
  }
  if (claim.status !== "assigned" || !Array.isArray(claim.assignments) || claim.assignments.length === 0) {
    fail("handoff ticket must carry an assigned execution claim");
  }
  if (claim.child_request_digest !== checkpointDigest) {
    fail("execution claim does not bind the input checkpoint digest");
  }
  const assignment = claim.assignments[claim.assignments.length - 1];
  exactKeys(
    assignment,
    ["epoch", "owner_peer_id", "owner_host_id", "implementation_fingerprint", "state_generation", "failure_evidence_digest"],
    "current assignment"
  );
  requireInteger(assignment.epoch, "assignment.epoch", 1);
  requireInteger(assignment.state_generation, "assignment.state_generation", 1);
  requireText(assignment.owner_peer_id, "assignment.owner_peer_id");
  requireText(assignment.owner_host_id, "assignment.owner_host_id");
  requireDigest(assignment.implementation_fingerprint, "assignment.implementation_fingerprint");

  return {
    checkpoint,
    checkpointDigest,
    envelopeDigest,
    claimId,
    assignment,
  };
}

function verifyPrepared(envelope, record) {
  const expectedFields = [
    "schema", "request_sequence", "input_claim_id", "input_checkpoint_sha256",
    "input_envelope_sha256", "assignment_epoch", "owner_peer_id", "owner_host_id",
    "implementation_fingerprint", "output_checkpoint_base64", "output_checkpoint_sha256",
    "receipt_core", "receipt_sha256", "independent_verification", "prepared_sha256",
  ];
  exactKeys(record, expectedFields, "prepared result");
  if (record.schema !== PREPARED_SCHEMA) fail("unsupported prepared-result schema");

  const { prepared_sha256: suppliedPreparedDigest, ...preparedCore } = record;
  if (objectDigest(preparedCore) !== requireDigest(suppliedPreparedDigest, "prepared_sha256")) {
    fail("prepared-result canonical digest mismatch");
  }

  const validatedEnvelope = validateEnvelope(envelope);
  const assignment = validatedEnvelope.assignment;
  requireInteger(record.request_sequence, "prepared.request_sequence", 1);
  if (
    record.input_claim_id !== validatedEnvelope.claimId ||
    record.input_checkpoint_sha256 !== validatedEnvelope.checkpointDigest ||
    record.input_envelope_sha256 !== validatedEnvelope.envelopeDigest ||
    record.assignment_epoch !== assignment.epoch ||
    record.owner_peer_id !== assignment.owner_peer_id ||
    record.owner_host_id !== assignment.owner_host_id ||
    record.implementation_fingerprint !== assignment.implementation_fingerprint
  ) {
    fail("prepared result does not bind the exact input, claim, assignment epoch, and target");
  }

  const outputCheckpoint = decodeCanonicalBase64(
    record.output_checkpoint_base64,
    "prepared.output_checkpoint_base64"
  );
  const outputCheckpointDigest = requireDigest(
    record.output_checkpoint_sha256,
    "prepared.output_checkpoint_sha256"
  );
  if (sha256(outputCheckpoint) !== outputCheckpointDigest) {
    fail("prepared output checkpoint byte digest mismatch");
  }

  const receipt = record.receipt_core;
  exactKeys(
    receipt,
    [
      "schema", "session_id", "input_checkpoint_sha256", "input_claim_id",
      "assignment_epoch", "owner_peer_id", "owner_host_id", "implementation_fingerprint",
      "tick_before", "tick_after", "state_before", "state_after", "revision",
      "program_digest", "model_digest", "transition_event_digest",
      "output_checkpoint_sha256", "output_checkpoint_bytes",
    ],
    "continuation receipt"
  );
  if (receipt.schema !== "ifs.stateful-runtime-rehome-receipt.v1") {
    fail("unsupported continuation receipt schema");
  }
  if (objectDigest(receipt) !== requireDigest(record.receipt_sha256, "prepared.receipt_sha256")) {
    fail("continuation receipt digest mismatch");
  }

  const inputReport = verifyPortableStatefulCheckpoint(validatedEnvelope.checkpoint);
  const outputReport = verifyPortableStatefulCheckpoint(outputCheckpoint);
  if (
    inputReport.restored_tick + 1 !== outputReport.restored_tick ||
    inputReport.event_count + 1 !== outputReport.event_count ||
    inputReport.restored_revision !== outputReport.restored_revision ||
    !same(inputReport.resumed_state, outputReport.restored_state) ||
    inputReport.resumed_tick !== outputReport.restored_tick ||
    inputReport.resumed_revision !== outputReport.restored_revision ||
    inputReport.resumed_event_digest !== outputReport.chain_head_digest ||
    inputReport.restored_program_digest !== outputReport.restored_program_digest ||
    inputReport.restored_model_digest !== outputReport.restored_model_digest ||
    inputReport.realization_count !== outputReport.realization_count
  ) {
    fail("prepared output is not the exact next transition predicted from its input checkpoint");
  }

  const expectedReceipt = {
    schema: "ifs.stateful-runtime-rehome-receipt.v1",
    session_id: envelope.session_id,
    input_checkpoint_sha256: validatedEnvelope.checkpointDigest,
    input_claim_id: validatedEnvelope.claimId,
    assignment_epoch: assignment.epoch,
    owner_peer_id: assignment.owner_peer_id,
    owner_host_id: assignment.owner_host_id,
    implementation_fingerprint: assignment.implementation_fingerprint,
    tick_before: inputReport.restored_tick,
    tick_after: outputReport.restored_tick,
    state_before: inputReport.restored_state,
    state_after: outputReport.restored_state,
    revision: inputReport.restored_revision,
    program_digest: inputReport.restored_program_digest,
    model_digest: inputReport.restored_model_digest,
    transition_event_digest: outputReport.chain_head_digest,
    output_checkpoint_sha256: outputCheckpointDigest,
    output_checkpoint_bytes: outputCheckpoint.length,
  };
  if (!same(receipt, expectedReceipt)) {
    fail("continuation receipt does not match the independently replayed checkpoint transition");
  }

  const verification = {
    schema: "ifs.psc.independent-prepared-result-verification.v1",
    verifier: "verify_prepared_result.mjs+verify_capsule.mjs",
    input_checkpoint_sha256: validatedEnvelope.checkpointDigest,
    output_checkpoint_sha256: outputCheckpointDigest,
    input_envelope_sha256: validatedEnvelope.envelopeDigest,
    input_claim_id: validatedEnvelope.claimId,
    assignment_epoch: assignment.epoch,
    receipt_sha256: record.receipt_sha256,
    input_event_digest: inputReport.chain_head_digest,
    output_event_digest: outputReport.chain_head_digest,
    tick_before: inputReport.restored_tick,
    tick_after: outputReport.restored_tick,
    state_before: inputReport.restored_state,
    state_after: outputReport.restored_state,
    revision: inputReport.restored_revision,
    program_digest: inputReport.restored_program_digest,
    model_digest: inputReport.restored_model_digest,
    realization_count: outputReport.realization_count,
    exhaustive_model_rows: inputReport.exhaustive_model_rows + outputReport.exhaustive_model_rows,
  };
  const verificationDigest = objectDigest(verification);
  const fullVerification = { ...verification, verification_digest: verificationDigest };
  if (
    record.independent_verification !== null &&
    !same(record.independent_verification, fullVerification)
  ) {
    fail("stored independent-verification receipt differs from this independent replay");
  }

  return {
    valid: true,
    verification: fullVerification,
    verification_digest: verificationDigest,
  };
}

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) fail(`missing required ${name} argument`);
  return process.argv[index + 1];
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const envelope = readJsonFile(argument("--envelope"), "handoff envelope");
    const prepared = readJsonFile(argument("--prepared"), "prepared result");
    process.stdout.write(`${JSON.stringify(verifyPrepared(envelope, prepared))}\n`);
  } catch (error) {
    process.stderr.write(`invalid prepared result: ${error.message}\n`);
    process.exitCode = 1;
  }
}
