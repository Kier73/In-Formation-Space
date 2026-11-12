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



class PythonFloat {
  constructor(value) {
    this.value = value;
  }
}

/** Match Python json.dumps(float) notation for finite binary64 values. */
function pythonFloatJson(value) {
  if (!Number.isFinite(value)) fail("sparse model contains a non-finite coefficient");
  if (Object.is(value, -0)) return "-0.0";
  const negative = value < 0;
  const sign = negative ? "-" : "";
  const absolute = Math.abs(value);
  let shortest = absolute.toString();

  function expandToFixed(text) {
    const pieces = text.toLowerCase().split("e");
    const mantissa = pieces[0];
    const exponent = pieces.length === 2 ? Number(pieces[1]) : 0;
    const point = mantissa.indexOf(".");
    const decimalPosition = (point < 0 ? mantissa.length : point) + exponent;
    const digits = mantissa.replace(".", "");
    if (decimalPosition <= 0) {
      return "0." + "0".repeat(-decimalPosition) + digits;
    }
    if (decimalPosition >= digits.length) {
      return digits + "0".repeat(decimalPosition - digits.length) + ".0";
    }
    return digits.slice(0, decimalPosition) + "." + digits.slice(decimalPosition);
  }

  if (absolute >= 1e-4 && absolute < 1e16) {
    if (/[eE]/.test(shortest)) shortest = expandToFixed(shortest);
    if (!shortest.includes(".")) shortest += ".0";
    return sign + shortest;
  }

  let mantissa;
  let exponent;
  if (/[eE]/.test(shortest)) {
    const pieces = shortest.toLowerCase().split("e");
    mantissa = pieces[0];
    exponent = Number(pieces[1]);
  } else {
    const point = shortest.indexOf(".");
    const decimalPosition = point < 0 ? shortest.length : point;
    const digits = shortest.replace(".", "");
    const first = digits.search(/[1-9]/);
    if (first < 0) return sign + "0.0";
    exponent = decimalPosition - first - 1;
    const significant = digits.slice(first).replace(/0+$/, "");
    mantissa = significant.length > 1
      ? significant[0] + "." + significant.slice(1)
      : significant[0];
  }
  const exponentText = (exponent >= 0 ? "+" : "-") +
    String(Math.abs(exponent)).padStart(2, "0");
  return sign + mantissa + "e" + exponentText;
}

function canonicalSparse(value) {
  if (value instanceof PythonFloat) return pythonFloatJson(value.value);
  if (Array.isArray(value)) {
    return "[" + value.map((member) => canonicalSparse(member)).join(",") + "]";
  }
  if (isObject(value)) {
    const keys = Object.keys(value);
    if (keys.some((key) => !/^[\x00-\x7f]*$/.test(key))) {
      fail("sparse-model digest has a non-ASCII object key");
    }
    keys.sort();
    return "{" + keys.map((key) =>
      JSON.stringify(key) + ":" + canonicalSparse(value[key])
    ).join(",") + "}";
  }
  return canonical(value);
}

function sparseBinaryEnvelope(payload) {
  if (payload.length < 4) fail("sparse binary payload lacks header length");
  const headerLength = payload.readUInt32LE(0);
  const bodyOffset = 4 + headerLength;
  if (headerLength <= 0 || bodyOffset > payload.length) {
    fail("sparse binary header is truncated");
  }
  const headerBytes = payload.subarray(4, bodyOffset);
  let header;
  try {
    header = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(headerBytes));
  } catch {
    fail("sparse binary header is not valid UTF-8 JSON");
  }
  requireObject(header, "sparse binary header");
  if (Buffer.compare(Buffer.from(canonical(header), "utf8"), headerBytes) !== 0) {
    fail("sparse binary header is not canonical");
  }

  const { header_sha256: headerHash, ...headerWithoutHash } = header;
  if (headerHash !== sha256(Buffer.from(canonical(headerWithoutHash), "utf8"))) {
    fail("sparse binary header digest mismatch");
  }
  const body = payload.subarray(bodyOffset);
  if (header.body_sha256 !== sha256(body)) {
    fail("sparse binary body digest mismatch");
  }
  return { header, body };
}

function readLittleEndianMask(body, offset, width) {
  const byteLength = Math.ceil(width / 8);
  const end = offset + byteLength;
  if (end > body.length) fail("row-mask binary bitmask is truncated");
  let mask = 0n;
  for (let index = byteLength - 1; index >= 0; index -= 1) {
    mask = (mask << 8n) | BigInt(body[offset + index]);
  }
  if ((mask >> BigInt(width)) !== 0n) {
    fail("row-mask binary bitmask has out-of-range bits");
  }
  const indices = [];
  for (let index = 0; index < width; index += 1) {
    if ((mask & (1n << BigInt(index))) !== 0n) indices.push(index);
  }
  return { mask, indices, offset: end };
}



function readUnsignedValues(body, offset, count, dtype) {
  if (!Number.isSafeInteger(count) || count < 0) {
    fail("CSR binary integer count is invalid");
  }
  const scalarSize = dtype === "u8" ? 1 : dtype === "u16" ? 2 : dtype === "u32" ? 4 : 0;
  if (scalarSize === 0) fail("CSR binary integer dtype is unsupported");
  const end = offset + count * scalarSize;
  if (!Number.isSafeInteger(end) || end > body.length) {
    fail("CSR binary integer values are truncated");
  }
  const values = [];
  for (let index = 0; index < count; index += 1) {
    const position = offset + index * scalarSize;
    values.push(
      scalarSize === 1 ? body.readUInt8(position) :
      scalarSize === 2 ? body.readUInt16LE(position) :
      body.readUInt32LE(position)
    );
  }
  return { values, offset: end };
}

function readScalarValues(body, offset, count, dtype, allowZero = false) {
  if (!Number.isSafeInteger(count) || count < 0) {
    fail("sparse binary scalar count is invalid");
  }
  const scalarSize = dtype === "i8" ? 1 : dtype === "f64" ? 8 : 0;
  if (scalarSize === 0) fail("row-mask binary scalar dtype is unsupported");
  const end = offset + count * scalarSize;
  if (!Number.isSafeInteger(end) || end > body.length) {
    fail("row-mask binary scalar values are truncated");
  }
  const values = [];
  for (let index = 0; index < count; index += 1) {
    const value = dtype === "i8"
      ? body.readInt8(offset + index)
      : body.readDoubleLE(offset + index * 8);
    if (!Number.isFinite(value) || (!allowZero && value === 0)) {
      fail("sparse binary stores a zero or non-finite coefficient");
    }
    values.push(value);
  }
  return { values, offset: end };
}

function decodeRowmaskBinary(payload, capsuleHeader) {
  const { header, body } = sparseBinaryEnvelope(payload);
  if (
    header.schema !== "sre002.rowmask-binary.v1" ||
    header.encoding !== "rowmask_binary"
  ) {
    fail("unsupported row-mask binary schema/encoding");
  }
  if (
    !Array.isArray(header.architecture) ||
    header.architecture.length < 3 ||
    header.architecture.some((width) => !Number.isSafeInteger(width) || width < 1) ||
    !Array.isArray(header.input_names) ||
    !Array.isArray(header.output_names) ||
    !Array.isArray(header.layers) ||
    header.layers.length !== header.architecture.length - 1
  ) {
    fail("row-mask binary model interface is malformed");
  }
  const inputNames = header.input_names;
  const outputNames = header.output_names;
  if (
    header.architecture[0] !== inputNames.length ||
    header.architecture[header.architecture.length - 1] !== outputNames.length ||
    new Set(inputNames).size !== inputNames.length ||
    new Set(outputNames).size !== outputNames.length ||
    inputNames.some((name) => typeof name !== "string" || name.length === 0) ||
    outputNames.some((name) => typeof name !== "string" || name.length === 0)
  ) {
    fail("row-mask binary register names do not match architecture");
  }

  let offset = 0;
  let storedParameterCount = 0;
  const layers = [];
  for (let layerIndex = 0; layerIndex < header.layers.length; layerIndex += 1) {
    const layer = header.layers[layerIndex];
    const inputWidth = header.architecture[layerIndex];
    const outputWidth = header.architecture[layerIndex + 1];
    if (
      requireInteger(layer.input_width, "rowmask.layer.input_width") !== inputWidth ||
      requireInteger(layer.output_width, "rowmask.layer.output_width") !== outputWidth
    ) {
      fail("row-mask binary layer widths do not match architecture");
    }
    const nnz = requireInteger(layer.nnz, "rowmask.layer.nnz");
    const biasNnz = requireInteger(layer.bias_nnz, "rowmask.layer.bias_nnz");
    if (nnz < 0 || biasNnz < 0 || nnz > inputWidth * outputWidth || biasNnz > outputWidth) {
      fail("row-mask binary layer scalar counts are out of range");
    }

    const rowMasks = [];
    for (let rowIndex = 0; rowIndex < outputWidth; rowIndex += 1) {
      const result = readLittleEndianMask(body, offset, inputWidth);
      offset = result.offset;
      rowMasks.push(result.indices);
    }
    const observedWeightCount = rowMasks.reduce((total, indices) => total + indices.length, 0);
    if (observedWeightCount !== nnz) fail("row-mask binary weight count differs from masks");
    const weightResult = readScalarValues(body, offset, nnz, layer.weight_dtype);
    offset = weightResult.offset;

    let valueCursor = 0;
    const weightRows = rowMasks.map((indices) => indices.map((sourceIndex) => [
      sourceIndex,
      new PythonFloat(weightResult.values[valueCursor++]),
    ]));

    const biasMask = readLittleEndianMask(body, offset, outputWidth);
    offset = biasMask.offset;
    if (biasMask.indices.length !== biasNnz) {
      fail("row-mask binary bias count differs from mask");
    }
    const biasResult = readScalarValues(body, offset, biasNnz, layer.bias_dtype);
    offset = biasResult.offset;
    const biasEntries = biasMask.indices.map((outputIndex, index) => [
      outputIndex,
      new PythonFloat(biasResult.values[index]),
    ]);

    storedParameterCount += nnz + biasNnz;
    layers.push({ weight_rows: weightRows, bias_entries: biasEntries });
  }
  if (offset !== body.length) fail("row-mask binary contains trailing body bytes");
  if (
    requireInteger(header.stored_parameter_count, "rowmask.stored_parameter_count") !==
    storedParameterCount
  ) {
    fail("row-mask binary stored parameter count mismatch");
  }

  const denseWeightSlots = header.architecture.slice(0, -1).reduce(
    (total, width, index) => total + width * header.architecture[index + 1],
    0
  );
  const denseEquivalentParameterCount = denseWeightSlots +
    header.architecture.slice(1).reduce((total, width) => total + width, 0);

  const sparsePayload = {
    schema: "mailcpu.sparse-transition-relu.v1",
    source_kind: header.source_kind,
    source_digest: header.source_digest,
    source_model_digest: header.source_model_digest,
    input_names: inputNames,
    output_names: outputNames,
    architecture: header.architecture,
    layers,
    dense_equivalent_parameter_count: denseEquivalentParameterCount,
    stored_parameter_count: storedParameterCount,
  };
  const sparseModelDigest = sha256(Buffer.from(canonicalSparse(sparsePayload), "utf8"));

  if (
    header.source_kind !== capsuleHeader.source.kind ||
    header.source_digest !== capsuleHeader.source.ground_digest ||
    header.source_model_digest !== capsuleHeader.realization.dense_model_digest ||
    sparseModelDigest !== capsuleHeader.realization.sparse_model_digest ||
    JSON.stringify(inputNames) !== JSON.stringify(capsuleHeader.interface.input_names) ||
    JSON.stringify(outputNames) !== JSON.stringify(capsuleHeader.interface.output_names) ||
    JSON.stringify(header.architecture) !== JSON.stringify(capsuleHeader.interface.architecture) ||
    capsuleHeader.codec.name !== "rowmask_binary" ||
    capsuleHeader.codec.schema !== header.schema ||
    capsuleHeader.realization.encoding !== "rowmask_binary"
  ) {
    fail("decoded row-mask model identity does not match capsule metadata");
  }

  return {
    header,
    sparseModelDigest,
    storedParameterCount,
    layers,
    inputWidth: header.architecture[0],
    outputWidth: header.architecture[header.architecture.length - 1],
  };
}



/**
 * Decode SRE-002 adaptive hybrid binary without invoking the Python codec.
 *
 * Each output row independently selects either:
 * - a dense scalar vector; or
 * - a little-endian input bitmask followed by exactly its nonzero values.
 * Biases make a separate dense/sparse choice for each layer.
 */


/**
 * Decode SRE-002 compressed sparse row (CSR) binary using the explicit
 * per-layer row pointers, index widths, coefficient dtypes, and bias arrays.
 */
function decodeCsrBinary(payload, capsuleHeader) {
  const { header, body } = sparseBinaryEnvelope(payload);
  if (
    header.schema !== "sre002.csr-binary.v1" ||
    header.encoding !== "csr_binary"
  ) {
    fail("unsupported CSR binary schema/encoding");
  }
  if (
    !Array.isArray(header.architecture) ||
    header.architecture.length < 3 ||
    header.architecture.some((width) => !Number.isSafeInteger(width) || width < 1) ||
    !Array.isArray(header.input_names) ||
    !Array.isArray(header.output_names) ||
    !Array.isArray(header.layers) ||
    header.layers.length !== header.architecture.length - 1
  ) {
    fail("CSR binary model interface is malformed");
  }

  const inputNames = header.input_names;
  const outputNames = header.output_names;
  if (
    header.architecture[0] !== inputNames.length ||
    header.architecture[header.architecture.length - 1] !== outputNames.length ||
    new Set(inputNames).size !== inputNames.length ||
    new Set(outputNames).size !== outputNames.length ||
    inputNames.some((name) => typeof name !== "string" || name.length === 0) ||
    outputNames.some((name) => typeof name !== "string" || name.length === 0)
  ) {
    fail("CSR binary register names do not match architecture");
  }

  let offset = 0;
  let storedParameterCount = 0;
  const layers = [];
  for (let layerIndex = 0; layerIndex < header.layers.length; layerIndex += 1) {
    const layer = header.layers[layerIndex];
    const inputWidth = header.architecture[layerIndex];
    const outputWidth = header.architecture[layerIndex + 1];
    if (
      requireInteger(layer.input_width, "csr.layer.input_width") !== inputWidth ||
      requireInteger(layer.output_width, "csr.layer.output_width") !== outputWidth
    ) {
      fail("CSR binary layer widths do not match architecture");
    }

    const nnz = requireInteger(layer.nnz, "csr.layer.nnz");
    const biasNnz = requireInteger(layer.bias_nnz, "csr.layer.bias_nnz");
    if (
      nnz < 0 || biasNnz < 0 ||
      nnz > inputWidth * outputWidth || biasNnz > outputWidth
    ) {
      fail("CSR binary coefficient counts are out of range");
    }

    const pointerResult = readUnsignedValues(
      body, offset, outputWidth + 1, layer.rowptr_dtype
    );
    offset = pointerResult.offset;
    const indexResult = readUnsignedValues(
      body, offset, nnz, layer.index_dtype
    );
    offset = indexResult.offset;
    const weightResult = readScalarValues(
      body, offset, nnz, layer.weight_dtype
    );
    offset = weightResult.offset;
    const biasIndexResult = readUnsignedValues(
      body, offset, biasNnz, layer.bias_index_dtype
    );
    offset = biasIndexResult.offset;
    const biasValueResult = readScalarValues(
      body, offset, biasNnz, layer.bias_dtype
    );
    offset = biasValueResult.offset;

    const pointers = pointerResult.values;
    const indices = indexResult.values;
    const values = weightResult.values;
    if (
      pointers.length !== outputWidth + 1 ||
      pointers[0] !== 0 ||
      pointers[pointers.length - 1] !== nnz
    ) {
      fail("CSR binary row pointers have invalid endpoints");
    }
    for (let index = 0; index < pointers.length - 1; index += 1) {
      if (
        pointers[index] > pointers[index + 1] ||
        pointers[index + 1] > nnz
      ) {
        fail("CSR binary row pointers are not monotonic or exceed nnz");
      }
    }

    const weightRows = [];
    for (let rowIndex = 0; rowIndex < outputWidth; rowIndex += 1) {
      const start = pointers[rowIndex];
      const end = pointers[rowIndex + 1];
      const row = [];
      let previousIndex = -1;
      for (let cursor = start; cursor < end; cursor += 1) {
        const inputIndex = indices[cursor];
        if (
          inputIndex >= inputWidth ||
          inputIndex <= previousIndex
        ) {
          fail("CSR binary row indices are out of range or not strictly ordered");
        }
        previousIndex = inputIndex;
        row.push([inputIndex, new PythonFloat(values[cursor])]);
      }
      weightRows.push(row);
    }

    const biasIndices = biasIndexResult.values;
    const biasValues = biasValueResult.values;
    const biasEntries = [];
    let previousBiasIndex = -1;
    for (let index = 0; index < biasIndices.length; index += 1) {
      const outputIndex = biasIndices[index];
      if (outputIndex >= outputWidth || outputIndex <= previousBiasIndex) {
        fail("CSR binary bias indices are out of range or not strictly ordered");
      }
      previousBiasIndex = outputIndex;
      biasEntries.push([outputIndex, new PythonFloat(biasValues[index])]);
    }

    storedParameterCount += nnz + biasNnz;
    layers.push({ weight_rows: weightRows, bias_entries: biasEntries });
  }

  if (offset !== body.length) fail("CSR binary contains trailing body bytes");
  if (
    requireInteger(header.stored_parameter_count, "csr.stored_parameter_count") !==
    storedParameterCount
  ) {
    fail("CSR binary stored parameter count mismatch");
  }

  const denseWeightSlots = header.architecture.slice(0, -1).reduce(
    (total, width, index) => total + width * header.architecture[index + 1],
    0
  );
  const denseEquivalentParameterCount = denseWeightSlots +
    header.architecture.slice(1).reduce((total, width) => total + width, 0);
  const sparsePayload = {
    schema: "mailcpu.sparse-transition-relu.v1",
    source_kind: header.source_kind,
    source_digest: header.source_digest,
    source_model_digest: header.source_model_digest,
    input_names: inputNames,
    output_names: outputNames,
    architecture: header.architecture,
    layers,
    dense_equivalent_parameter_count: denseEquivalentParameterCount,
    stored_parameter_count: storedParameterCount,
  };
  const sparseModelDigest = sha256(
    Buffer.from(canonicalSparse(sparsePayload), "utf8")
  );

  if (
    header.source_kind !== capsuleHeader.source.kind ||
    header.source_digest !== capsuleHeader.source.ground_digest ||
    header.source_model_digest !== capsuleHeader.realization.dense_model_digest ||
    sparseModelDigest !== capsuleHeader.realization.sparse_model_digest ||
    JSON.stringify(inputNames) !== JSON.stringify(capsuleHeader.interface.input_names) ||
    JSON.stringify(outputNames) !== JSON.stringify(capsuleHeader.interface.output_names) ||
    JSON.stringify(header.architecture) !== JSON.stringify(capsuleHeader.interface.architecture) ||
    capsuleHeader.codec.name !== "csr_binary" ||
    capsuleHeader.codec.schema !== header.schema ||
    capsuleHeader.realization.encoding !== "csr_binary"
  ) {
    fail("decoded CSR model identity does not match capsule metadata");
  }

  return {
    header,
    sparseModelDigest,
    storedParameterCount,
    layers,
    inputWidth: header.architecture[0],
    outputWidth: header.architecture[header.architecture.length - 1],
  };
}

function decodeHybridBinary(payload, capsuleHeader) {
  const { header, body } = sparseBinaryEnvelope(payload);
  if (
    header.schema !== "sre002.hybrid-binary.v1" ||
    header.encoding !== "hybrid_binary"
  ) {
    fail("unsupported hybrid binary schema/encoding");
  }
  if (
    !Array.isArray(header.architecture) ||
    header.architecture.length < 3 ||
    header.architecture.some((width) => !Number.isSafeInteger(width) || width < 1) ||
    !Array.isArray(header.input_names) ||
    !Array.isArray(header.output_names) ||
    !Array.isArray(header.layers) ||
    header.layers.length !== header.architecture.length - 1
  ) {
    fail("hybrid binary model interface is malformed");
  }

  const inputNames = header.input_names;
  const outputNames = header.output_names;
  if (
    header.architecture[0] !== inputNames.length ||
    header.architecture[header.architecture.length - 1] !== outputNames.length ||
    new Set(inputNames).size !== inputNames.length ||
    new Set(outputNames).size !== outputNames.length ||
    inputNames.some((name) => typeof name !== "string" || name.length === 0) ||
    outputNames.some((name) => typeof name !== "string" || name.length === 0)
  ) {
    fail("hybrid binary register names do not match architecture");
  }

  let offset = 0;
  let storedParameterCount = 0;
  let sparseRowCount = 0;
  let denseRowCount = 0;
  const layers = [];

  for (let layerIndex = 0; layerIndex < header.layers.length; layerIndex += 1) {
    const layer = header.layers[layerIndex];
    const inputWidth = header.architecture[layerIndex];
    const outputWidth = header.architecture[layerIndex + 1];

    if (
      requireInteger(layer.input_width, "hybrid.layer.input_width") !== inputWidth ||
      requireInteger(layer.output_width, "hybrid.layer.output_width") !== outputWidth ||
      typeof layer.sparse_bias !== "boolean"
    ) {
      fail("hybrid binary layer metadata does not match architecture");
    }
    const declaredSparseRows = requireInteger(
      layer.sparse_row_count,
      "hybrid.layer.sparse_row_count"
    );
    if (declaredSparseRows < 0 || declaredSparseRows > outputWidth) {
      fail("hybrid binary sparse row count is out of range");
    }

    const mode = readLittleEndianMask(body, offset, outputWidth);
    offset = mode.offset;
    if (mode.indices.length !== declaredSparseRows) {
      fail("hybrid binary sparse row count mismatch");
    }

    const sparseRows = new Set(mode.indices);
    const weightRows = [];
    for (let rowIndex = 0; rowIndex < outputWidth; rowIndex += 1) {
      if (sparseRows.has(rowIndex)) {
        const mask = readLittleEndianMask(body, offset, inputWidth);
        offset = mask.offset;
        const values = readScalarValues(
          body, offset, mask.indices.length, layer.weight_dtype
        );
        offset = values.offset;
        weightRows.push(mask.indices.map((inputIndex, valueIndex) => [
          inputIndex,
          new PythonFloat(values.values[valueIndex]),
        ]));
        sparseRowCount += 1;
      } else {
        const values = readScalarValues(
          body, offset, inputWidth, layer.weight_dtype, true
        );
        offset = values.offset;
        const entries = [];
        values.values.forEach((value, inputIndex) => {
          if (value !== 0) entries.push([inputIndex, new PythonFloat(value)]);
        });
        weightRows.push(entries);
        denseRowCount += 1;
      }
    }

    let biasEntries;
    if (layer.sparse_bias) {
      const mask = readLittleEndianMask(body, offset, outputWidth);
      offset = mask.offset;
      const values = readScalarValues(
        body, offset, mask.indices.length, layer.bias_dtype
      );
      offset = values.offset;
      biasEntries = mask.indices.map((outputIndex, valueIndex) => [
        outputIndex,
        new PythonFloat(values.values[valueIndex]),
      ]);
    } else {
      const values = readScalarValues(
        body, offset, outputWidth, layer.bias_dtype, true
      );
      offset = values.offset;
      biasEntries = [];
      values.values.forEach((value, outputIndex) => {
        if (value !== 0) biasEntries.push([outputIndex, new PythonFloat(value)]);
      });
    }

    storedParameterCount += weightRows.reduce((total, row) => total + row.length, 0);
    storedParameterCount += biasEntries.length;
    layers.push({ weight_rows: weightRows, bias_entries: biasEntries });
  }

  if (offset !== body.length) fail("hybrid binary contains trailing body bytes");
  if (
    requireInteger(header.stored_parameter_count, "hybrid.stored_parameter_count") !==
    storedParameterCount
  ) {
    fail("hybrid binary stored parameter count mismatch");
  }

  const denseWeightSlots = header.architecture.slice(0, -1).reduce(
    (total, width, index) => total + width * header.architecture[index + 1],
    0
  );
  const denseEquivalentParameterCount = denseWeightSlots +
    header.architecture.slice(1).reduce((total, width) => total + width, 0);
  const sparsePayload = {
    schema: "mailcpu.sparse-transition-relu.v1",
    source_kind: header.source_kind,
    source_digest: header.source_digest,
    source_model_digest: header.source_model_digest,
    input_names: inputNames,
    output_names: outputNames,
    architecture: header.architecture,
    layers,
    dense_equivalent_parameter_count: denseEquivalentParameterCount,
    stored_parameter_count: storedParameterCount,
  };
  const sparseModelDigest = sha256(
    Buffer.from(canonicalSparse(sparsePayload), "utf8")
  );

  if (
    header.source_kind !== capsuleHeader.source.kind ||
    header.source_digest !== capsuleHeader.source.ground_digest ||
    header.source_model_digest !== capsuleHeader.realization.dense_model_digest ||
    sparseModelDigest !== capsuleHeader.realization.sparse_model_digest ||
    JSON.stringify(inputNames) !== JSON.stringify(capsuleHeader.interface.input_names) ||
    JSON.stringify(outputNames) !== JSON.stringify(capsuleHeader.interface.output_names) ||
    JSON.stringify(header.architecture) !== JSON.stringify(capsuleHeader.interface.architecture) ||
    capsuleHeader.codec.name !== "hybrid_binary" ||
    capsuleHeader.codec.schema !== header.schema ||
    capsuleHeader.realization.encoding !== "hybrid_binary"
  ) {
    fail("decoded hybrid model identity does not match capsule metadata");
  }

  return {
    header,
    sparseModelDigest,
    storedParameterCount,
    sparseRowCount,
    denseRowCount,
    layers,
    inputWidth: header.architecture[0],
    outputWidth: header.architecture[header.architecture.length - 1],
  };
}

function predictSparse(model, inputs) {
  if (
    !Array.isArray(inputs) ||
    inputs.length !== model.inputWidth ||
    inputs.some((value) => value !== 0 && value !== 1)
  ) {
    fail("replay input is outside the declared Boolean input domain");
  }
  let values = inputs.slice();
  for (let layerIndex = 0; layerIndex < model.layers.length; layerIndex += 1) {
    const layer = model.layers[layerIndex];
    const biasMap = new Map(layer.bias_entries.map(([index, wrapped]) => [index, wrapped.value]));
    const nextValues = layer.weight_rows.map((row, outputIndex) => {
      let sum = 0;
      for (const [inputIndex, wrappedWeight] of row) {
        sum += wrappedWeight.value * values[inputIndex];
      }
      return (biasMap.get(outputIndex) ?? 0) + sum;
    });
    values = layerIndex < model.layers.length - 1
      ? nextValues.map((value) => Math.max(0, value))
      : nextValues;
  }
  return values.map((value) => {
    const nearest = Math.round(value);
    if (
      !Number.isFinite(value) ||
      (nearest !== 0 && nearest !== 1) ||
      Math.abs(value - nearest) > 1e-12
    ) {
      fail("decoded sparse realization left the exact Boolean output set");
    }
    return nearest;
  });
}

/**
 * Independently decode and replay an adaptive hybrid-binary capsule.
 *
 * The finite reference covers every Boolean input row. Optional trajectories
 * add a complete product of initial counter states and control sequences.
 */
export function replayBinaryCapsule(capsule, referenceRecords, trajectories = [], expectedCodec = null) {
  const verified = verifyCapsule(capsule);
  const capsuleHeaderSize = capsule.readUInt32LE(10);
  const capsuleHeader = JSON.parse(
    new TextDecoder("utf-8", { fatal: true }).decode(
      capsule.subarray(PREFIX_BYTES, PREFIX_BYTES + capsuleHeaderSize)
    )
  );
  const codec = capsuleHeader.codec.name;
  if (!["rowmask_binary", "csr_binary", "hybrid_binary"].includes(codec)) {
    fail("semantic replay supports rowmask_binary, csr_binary, and hybrid_binary only");
  }
  if (expectedCodec !== null && codec !== expectedCodec) {
    fail("capsule codec does not match the requested decoder");
  }
  const payload = capsule.subarray(PREFIX_BYTES + capsuleHeaderSize);
  const model = codec === "rowmask_binary"
    ? decodeRowmaskBinary(payload, capsuleHeader)
    : codec === "csr_binary"
      ? decodeCsrBinary(payload, capsuleHeader)
      : decodeHybridBinary(payload, capsuleHeader);
  const expectedRows = requireInteger(
    capsuleHeader.verification.input_row_count,
    "verification.input_row_count"
  );
  if (!Array.isArray(referenceRecords) || referenceRecords.length !== expectedRows) {
    fail("independent reference does not cover the declared complete input domain");
  }
  if (
    capsuleHeader.verification.reference_outputs_sha256 !==
    sha256(Buffer.from(canonical(referenceRecords), "utf8"))
  ) {
    fail("independent reference digest does not match capsule verification receipt");
  }

  const seenInputs = new Set();
  for (const record of referenceRecords) {
    requireObject(record, "reference row");
    const inputs = record.inputs;
    const outputs = record.outputs;
    if (
      !Array.isArray(inputs) || inputs.length !== model.inputWidth ||
      inputs.some((value) => value !== 0 && value !== 1) ||
      !Array.isArray(outputs) || outputs.length !== model.outputWidth ||
      outputs.some((value) => value !== 0 && value !== 1)
    ) {
      fail("independent reference row is outside the declared Boolean interface");
    }
    const key = inputs.join("");
    if (seenInputs.has(key)) fail("independent reference repeats an input assignment");
    seenInputs.add(key);
    const actual = predictSparse(model, inputs);
    if (JSON.stringify(actual) !== JSON.stringify(outputs)) {
      fail("decoded sparse realization disagrees with independent scalar reference");
    }
  }
  if (seenInputs.size !== 2 ** model.inputWidth) {
    fail("independent reference omits one or more Boolean input assignments");
  }

  if (!Array.isArray(trajectories)) {
    fail("trajectory reference must be an array");
  }
  let trajectoryCount = 0;
  let trajectoryStepCount = 0;
  if (trajectories.length > 0) {
    if (
      model.inputWidth !== 4 ||
      model.outputWidth !== 2 ||
      JSON.stringify(capsuleHeader.interface.input_names) !==
        JSON.stringify(["state_1", "state_0", "advance", "reset"]) ||
      JSON.stringify(capsuleHeader.interface.output_names) !==
        JSON.stringify(["next_state_1", "next_state_0"])
    ) {
      fail("recurrent replay requires the declared two-bit counter interface");
    }
    const horizon = Array.isArray(trajectories[0]?.controls)
      ? trajectories[0].controls.length
      : 0;
    if (horizon < 1 || !Number.isSafeInteger(horizon)) {
      fail("trajectory horizon must be a positive integer");
    }
    const expectedTrajectoryCount = 4 * (4 ** horizon);
    if (
      !Number.isSafeInteger(expectedTrajectoryCount) ||
      trajectories.length !== expectedTrajectoryCount
    ) {
      fail("trajectory reference does not cover every initial state/control sequence");
    }

    const seenTrajectories = new Set();
    for (const trajectory of trajectories) {
      requireObject(trajectory, "trajectory reference");
      const initial = trajectory.initial_state;
      const controls = trajectory.controls;
      const expectedStates = trajectory.expected_states;
      if (
        !Array.isArray(initial) || initial.length !== 2 ||
        initial.some((value) => value !== 0 && value !== 1) ||
        !Array.isArray(controls) || controls.length !== horizon ||
        !Array.isArray(expectedStates) || expectedStates.length !== horizon ||
        controls.some((pair) =>
          !Array.isArray(pair) || pair.length !== 2 ||
          pair.some((value) => value !== 0 && value !== 1)
        ) ||
        expectedStates.some((state) =>
          !Array.isArray(state) || state.length !== 2 ||
          state.some((value) => value !== 0 && value !== 1)
        )
      ) {
        fail("trajectory reference is outside the two-bit counter interface");
      }
      const key = initial.join("") + ":" + controls.map((pair) => pair.join("")).join(",");
      if (seenTrajectories.has(key)) fail("trajectory reference repeats a state/control sequence");
      seenTrajectories.add(key);

      let state = initial.slice();
      for (let step = 0; step < horizon; step += 1) {
        const inputs = [...state, ...controls[step]];
        const actual = predictSparse(model, inputs);
        const expected = expectedStates[step];
        if (JSON.stringify(actual) !== JSON.stringify(expected)) {
          fail("decoded sparse realization disagrees with recurrent trajectory reference");
        }
        state = actual;
        trajectoryStepCount += 1;
      }
      trajectoryCount += 1;
    }
    if (seenTrajectories.size !== expectedTrajectoryCount) {
      fail("trajectory reference omits one or more initial state/control sequences");
    }
  }

  return {
    valid: true,
    capsule_sha256: verified.capsule_sha256,
    payload_sha256: verified.payload_sha256,
    sparse_model_sha256: model.sparseModelDigest,
    codec,
    input_rows_replayed: seenInputs.size,
    semantic_comparisons: seenInputs.size,
    stored_parameter_count: model.storedParameterCount,
    sparse_row_count: model.sparseRowCount ?? null,
    dense_row_count: model.denseRowCount ?? null,
    trajectory_count: trajectoryCount,
    trajectory_steps: trajectoryStepCount,
  };
}


export function replayRowmaskCapsule(capsule, referenceRecords, trajectories = []) {
  return replayBinaryCapsule(capsule, referenceRecords, trajectories, "rowmask_binary");
}

export function replayCsrCapsule(capsule, referenceRecords, trajectories = []) {
  return replayBinaryCapsule(capsule, referenceRecords, trajectories, "csr_binary");
}

export function replayHybridCapsule(capsule, referenceRecords, trajectories = []) {
  return replayBinaryCapsule(capsule, referenceRecords, trajectories, "hybrid_binary");
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const file = process.argv[2];
    if (!file) fail("usage: node verify_capsule.mjs <capsule.bin> [--reference reference.json] [--trajectories trajectories.json]");
    const referenceFlag = process.argv.indexOf("--reference");
    let report;
    if (referenceFlag >= 0) {
      const referencePath = process.argv[referenceFlag + 1];
      if (!referencePath) fail("--reference requires a JSON file path");
      const capsuleBytes = readFileSync(file);
      const capsuleHeaderSize = capsuleBytes.readUInt32LE(10);
      const capsuleHeader = JSON.parse(
        new TextDecoder("utf-8", { fatal: true }).decode(
          capsuleBytes.subarray(PREFIX_BYTES, PREFIX_BYTES + capsuleHeaderSize)
        )
      );
      const references = JSON.parse(readFileSync(referencePath, "utf8"));
      const trajectoriesFlag = process.argv.indexOf("--trajectories");
      let trajectories = [];
      if (trajectoriesFlag >= 0) {
        const trajectoriesPath = process.argv[trajectoriesFlag + 1];
        if (!trajectoriesPath) fail("--trajectories requires a JSON file path");
        trajectories = JSON.parse(readFileSync(trajectoriesPath, "utf8"));
      }
      report = replayBinaryCapsule(
        capsuleBytes,
        references,
        trajectories,
        capsuleHeader.codec.name
      );
    } else {
      report = { valid: true, ...verifyCapsule(readFileSync(file)) };
    }
    process.stdout.write(`${JSON.stringify(report)}\n`);
  } catch (error) {
    process.stderr.write(`invalid capsule: ${error.message}\n`);
    process.exitCode = 1;
  }
}
