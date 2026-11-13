#!/usr/bin/env node
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import {
  canonicalMetadataBytes,
  decodeCanonicalMetadataDocument,
} from "../../experiments/portable-realization-capsule/verify_capsule.mjs";

const corpus = JSON.parse(
  readFileSync(new URL("./vectors.json", import.meta.url), "utf8"),
);
assert.equal(corpus.schema, "in-formation.canonical-metadata-conformance-vectors/1");
assert.equal(corpus.profile, "canonical-metadata-v1");

function artifactBytes(vector) {
  let raw = Buffer.from(vector.input_json, "utf8");
  if (vector.prefix_bom) raw = Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), raw]);
  switch (vector.line_ending) {
    case "lf": return Buffer.concat([raw, Buffer.from("\n")]);
    case "double_lf": return Buffer.concat([raw, Buffer.from("\n\n")]);
    case "crlf": return Buffer.concat([raw, Buffer.from("\r\n")]);
    case "none": return raw;
    default: throw new Error(`unknown line ending: ${vector.line_ending}`);
  }
}

let passed = 0;
for (const vector of corpus.vectors) {
  let accepted = false;
  try {
    const document = decodeCanonicalMetadataDocument(artifactBytes(vector));
    const canonical = canonicalMetadataBytes(document);
    accepted = true;
    assert.equal(canonical.toString("utf8"), vector.input_json, vector.id);
    const digest = createHash("sha256").update(canonical).digest("hex");
    assert.equal(digest, vector.canonical_sha256, vector.id);
  } catch (error) {
    if (vector.accept) {
      throw new Error(`${vector.id} should have been accepted: ${error.message}`);
    }
  }
  assert.equal(accepted, vector.accept, vector.id);
  passed += 1;
}
process.stdout.write(`Node canonical-metadata-v1: ${passed} shared vectors passed\n`);
