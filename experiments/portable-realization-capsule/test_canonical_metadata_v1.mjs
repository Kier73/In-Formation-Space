#!/usr/bin/env node
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import { canonical } from "./verify_capsule.mjs";

const corpusPath = new URL("../../formats/canonical-metadata-v1/test-vectors.json", import.meta.url);
const corpus = JSON.parse(readFileSync(corpusPath, "utf8"));

function sha256(text) {
  return createHash("sha256").update(Buffer.from(text, "utf8")).digest("hex");
}

test("shared canonical metadata v1 valid vectors produce exact UTF-8 bytes and digests", () => {
  assert.equal(corpus.profile, "in-formation-space.canonical-metadata.v1");
  for (const vector of corpus.valid) {
    const value = JSON.parse(vector.input_json);
    const actual = canonical(value);
    assert.equal(actual, vector.canonical_utf8, vector.name);
    assert.equal(sha256(actual), vector.sha256, vector.name);
  }
});

test("shared canonical metadata v1 invalid values are rejected", () => {
  for (const vector of corpus.invalid_values) {
    const value = JSON.parse(vector.input_json);
    assert.throws(
      () => canonical(value),
      undefined,
      vector.name,
    );
  }
});

test("shared canonical metadata v1 noncanonical source documents fail byte equality", () => {
  for (const vector of corpus.noncanonical_documents) {
    const value = JSON.parse(vector.input_json);
    const reencoded = canonical(value);
    assert.equal(reencoded, vector.canonical_utf8, vector.name);
    assert.notEqual(
      Buffer.from(vector.input_json, "utf8").compare(Buffer.from(reencoded, "utf8")),
      0,
      vector.name + " must not be accepted as canonical source bytes",
    );
  }
});

process.stdout.write(
  "canonical metadata v1: " + corpus.valid.length + " valid, " +
  corpus.invalid_values.length + " invalid, " +
  corpus.noncanonical_documents.length + " noncanonical vectors\n",
);
