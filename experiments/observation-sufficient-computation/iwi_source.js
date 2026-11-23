"use strict";
/** OFC-001: use the original IWI-001 guaranteed-belief policy and its verifier. */
const path = require("node:path");
const crypto = require("node:crypto");
const IWI = require(path.join(__dirname, "..", "intention-without-identification", "experiment.js"));
const uncertain = require(path.join(__dirname, "..", "intention-without-identification", "uncertain_ground.js"));

function exportedModel(name) {
  const original = Object.prototype.hasOwnProperty.call(IWI.fixtures, name);
  const multiLaw = Object.prototype.hasOwnProperty.call(uncertain.fixtures, name);
  if (!original && !multiLaw) throw Error("unknown bounded IWI experiment");
  // The ORIGINAL IWI-002 compiler forms the disjoint law-state product.
  // No candidate can switch its identity during actions or observations.
  const model = original ? IWI.fixtures[name] :
    uncertain.compile(uncertain.fixtures[name]).flat;
  const certificate = IWI.solve(model);
  if (!IWI.audit(model, certificate)) throw Error("IWI independent verification refused");
  const canonical = JSON.stringify({model, certificate});
  return {
    schema: "ifs.ofc001.original-iwi-policy.v1",
    fixture: name,
    model,
    certificate,
    source_digest: crypto.createHash("sha256").update(canonical).digest("hex"),
    producer: multiLaw
      ? "IWI-002 original uncertain-law product + IWI-001 solve+audit"
      : "IWI-001 solve+audit (the original research implementation)"
  };
}
if (require.main === module) {
  if (process.argv.length !== 3) throw Error("expected one declared experiment name");
  process.stdout.write(JSON.stringify(exportedModel(process.argv[2])) + "\n");
}
module.exports = {exportedModel};
