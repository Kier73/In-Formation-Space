#!/usr/bin/env node
/**
 * Independent Node.js verifier for In-Formation-Space portable realization
 * capsules, format v1. Uses only Node built-in modules.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const MAGIC = Buffer.from("IFSPRC01", "ascii");
const VERSION = 1;
const PREFIX_BYTES = 14;
const SCHEMA = "in-formation-space.portable-realization.v1";
const PYTHON_WHITESPACE = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u;

function fail(message) {
  throw new Error(message);
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireObject(value, field) {
  if (!isObject(value)) fail(`${field} must be an object`);
  return value;
}

function requireText(value, field) {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    PYTHON_WHITESPACE.test(value)
  ) {
    fail(`${field} must be a non-empty string`);
  }
  return value;
}

function requireDigest(value, field) {
  const digest = requireText(value, field);
  if (!/^[0-9a-f]{64}$/.test(digest)) {
    fail(`${field} must be a lowercase SHA-256 digest`);
  }
  return digest;
}

function requireInteger(value, field) {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) {
    fail(`${field} must be an interoperable safe integer`);
  }
  return value;
}

function requireUnicodeScalarString(value, field) {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        fail(`${field} contains invalid Unicode`);
      }
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      fail(`${field} contains invalid Unicode`);
    }
  }
}

/** Reproduce the v1 canonical bytes independently of the Python encoder. */
function canonical(value, field = "$") {
  if (value === null || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    requireUnicodeScalarString(value, field);
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      fail(`${field} floating-point or unsafe numeric value is not supported by canonical metadata v1`);
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item, index) => canonical(item, `${field}[${index}]`)).join(",")}]`;
  }
  if (isObject(value)) {
    const keys = Object.keys(value);
    if (keys.some((key) => !/^[\x00-\x7f]*$/.test(key))) {
      fail(`${field} object keys must be ASCII for canonical metadata v1`);
    }
    keys.sort();
    return `{${keys
      .map((key) => `${JSON.stringify(key)}:${canonical(value[key], `${field}.${key}`)}`)
      .join(",")}}`;
  }
  fail(`${field} contains a value unsupported by canonical metadata v1`);
}

function validateCore(core, payload) {
  requireObject(core, "capsule core");
  const expectedFields = [
    "schema", "version", "source", "realization", "interface",
    "codec", "verification", "toolchain", "payload",
  ].sort();
  if (JSON.stringify(Object.keys(core).sort()) !== JSON.stringify(expectedFields)) {
    fail("capsule core fields do not match schema");
  }
  if (core.schema !== SCHEMA || requireInteger(core.version, "version") !== VERSION) {
    fail("unsupported portable realization schema/version");
  }

  const source = requireObject(core.source, "source");
  requireText(source.repository, "source.repository");
  requireText(source.revision, "source.revision");
  requireText(source.kind, "source.kind");
  requireDigest(source.ground_digest, "source.ground_digest");

  const realization = requireObject(core.realization, "realization");
  requireText(realization.repository, "realization.repository");
  requireText(realization.revision, "realization.revision");
  requireText(realization.compiler_route, "realization.compiler_route");
  requireDigest(realization.dense_model_digest, "realization.dense_model_digest");
  requireDigest(realization.sparse_model_digest, "realization.sparse_model_digest");

  const interfaceData = requireObject(core.interface, "interface");
  const inputNames = interfaceData.input_names;
  const outputNames = interfaceData.output_names;
  const architecture = interfaceData.architecture;
  const domain = requireObject(interfaceData.domain, "interface.domain");

  if (
    !Array.isArray(inputNames) || inputNames.length === 0 ||
    inputNames.some((item) => typeof item !== "string" || item.length === 0) ||
    new Set(inputNames).size !== inputNames.length
  ) fail("interface.input_names must be unique non-empty strings");
  if (
    !Array.isArray(outputNames) || outputNames.length === 0 ||
    outputNames.some((item) => typeof item !== "string" || item.length === 0) ||
    new Set(outputNames).size !== outputNames.length
  ) fail("interface.output_names must be unique non-empty strings");
  if (
    !Array.isArray(architecture) || architecture.length < 3 ||
    architecture.some((width) => !Number.isSafeInteger(width) || width < 1) ||
    architecture[0] !== inputNames.length ||
    architecture[architecture.length - 1] !== outputNames.length
  ) fail("interface.architecture does not match its register names");
  if (domain.kind !== "finite_boolean") {
    fail("only finite_boolean interface domains are supported");
  }
  if (requireInteger(domain.input_width, "interface.domain.input_width") !== inputNames.length) {
    fail("interface domain width does not match input names");
  }

  const codec = requireObject(core.codec, "codec");
  const codecName = requireText(codec.name, "codec.name");
  requireText(codec.schema, "codec.schema");
  const codecPayloadDigest = requireDigest(codec.payload_sha256, "codec.payload_sha256");

  const receipt = requireObject(core.verification, "verification");
  if (receipt.status !== "verified-within-complete-finite-domain") {
    fail("capsule verification receipt is not complete");
  }
  if (requireInteger(receipt.input_row_count, "verification.input_row_count") !== 2 ** inputNames.length) {
    fail("verification receipt does not cover the complete Boolean domain");
  }
  if (receipt.output_domain !== "finite_boolean") {
    fail("verification receipt output domain is unsupported");
  }
  requireDigest(receipt.reference_outputs_sha256, "verification.reference_outputs_sha256");
  requireDigest(receipt.case_evidence_sha256, "verification.case_evidence_sha256");
  requireDigest(receipt.translation_contracts_sha256, "verification.translation_contracts_sha256");
  requireDigest(receipt.typed_program_digest, "verification.typed_program_digest");
  requireDigest(receipt.transition_table_digest, "verification.transition_table_digest");
  requireText(receipt.workload_id, "verification.workload_id");
  requireText(receipt.compiler_route, "verification.compiler_route");
  requireText(receipt.codec, "verification.codec");
  requireDigest(receipt.receipt_sha256, "verification.receipt_sha256");

  if (source.program_digest !== receipt.typed_program_digest) {
    fail("source program digest contradicts verification receipt");
  }
  if (realization.compiler_route !== receipt.compiler_route) {
    fail("compiler route contradicts verification receipt");
  }
  if (codecName !== receipt.codec || realization.encoding !== codecName) {
    fail("codec identity contradicts realization/verification receipt");
  }
  const { receipt_sha256: receiptHash, ...receiptUnsigned } = receipt;
  if (receiptHash !== sha256(Buffer.from(canonical(receiptUnsigned), "utf8"))) {
    fail("verification receipt digest mismatch");
  }

  const toolchain = requireObject(core.toolchain, "toolchain");
  for (const key of ["ecpu_revision", "vgi_revision", "ifs_revision"]) {
    requireText(toolchain[key], `toolchain.${key}`);
  }
  if (source.revision !== toolchain.ifs_revision) {
    fail("source revision contradicts IFS toolchain pin");
  }
  if (realization.revision !== toolchain.ecpu_revision) {
    fail("realization revision contradicts E-CPU toolchain pin");
  }

  const descriptor = requireObject(core.payload, "payload");
  if (requireInteger(descriptor.byte_length, "payload.byte_length") !== payload.length) {
    fail("payload byte length mismatch");
  }
  const payloadDigest = requireDigest(descriptor.sha256, "payload.sha256");
  if (payloadDigest !== sha256(payload)) {
    fail("payload SHA-256 mismatch");
  }
  if (codecPayloadDigest !== payloadDigest) {
    fail("codec payload digest contradicts payload descriptor");
  }
}

/** Verify framing, canonical bytes, all content digests, and identity links. */
export function verifyCapsule(capsule) {
  if (!Buffer.isBuffer(capsule) || capsule.length < PREFIX_BYTES) {
    fail("capsule is truncated");
  }
  if (!capsule.subarray(0, 8).equals(MAGIC)) {
    fail("capsule magic does not match");
  }
  if (capsule.readUInt16LE(8) !== VERSION) {
    fail("unsupported capsule framing version");
  }

  const headerLength = capsule.readUInt32LE(10);
  const payloadStart = PREFIX_BYTES + headerLength;
  if (headerLength <= 0 || payloadStart > capsule.length) {
    fail("capsule header is truncated");
  }
  const headerBytes = capsule.subarray(PREFIX_BYTES, payloadStart);
  let header;
  try {
    header = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(headerBytes));
  } catch {
    fail("capsule header is not valid UTF-8 JSON");
  }
  requireObject(header, "capsule header");
  if (Buffer.compare(Buffer.from(canonical(header), "utf8"), headerBytes) !== 0) {
    fail("capsule header is not canonical");
  }

  const { header_sha256: headerHash, ...withoutHeaderHash } = header;
  if (headerHash !== sha256(Buffer.from(canonical(withoutHeaderHash), "utf8"))) {
    fail("capsule header SHA-256 mismatch");
  }
  const { capsule_sha256: capsuleHash, ...core } = withoutHeaderHash;
  if (capsuleHash !== sha256(Buffer.from(canonical(core), "utf8"))) {
    fail("capsule identity SHA-256 mismatch");
  }

  const payload = capsule.subarray(payloadStart);
  validateCore(core, payload);
  return {
    capsule_sha256: capsuleHash,
    header_sha256: headerHash,
    payload_sha256: core.payload.sha256,
    payload_bytes: payload.length,
    source_repository: core.source.repository,
    codec: core.codec.name,
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const file = process.argv[2];
    if (!file) fail("usage: node verify_capsule.mjs <capsule.bin>");
    const report = verifyCapsule(readFileSync(file));
    process.stdout.write(`${JSON.stringify({ valid: true, ...report })}\n`);
  } catch (error) {
    process.stderr.write(`invalid capsule: ${error.message}\n`);
    process.exitCode = 1;
  }
}
