"use strict";
const {prime} = require("./sections.js");

/*
 * Exact histogram under a declared synthetic ensemble:
 * each independent fundamental-cycle holonomy is chosen uniformly from
 * AGL(1, F_p), with independent choices between cycles.
 *
 * |AGL(1,F_p)| = p(p-1).  Exactly p-1 maps fix any specified x.
 * Identity is the only map fixing every x.  Any other affine map
 * fixes at most one x. Therefore, with k independent cycles:
 *   all       = 1
 *   singleton = p * ((p-1)^k - 1)
 *   empty     = (p(p-1))^k - all - singleton.
 *
 * These are combinatorial counts, not empirical failure probabilities.
 */
function ensembleCounts(p, k) {
  if (!prime(p) || !Number.isSafeInteger(k) || k < 0 || k > 128)
    throw new Error("invalid finite-field ensemble");
  const n = BigInt(k), q = BigInt(p), perPoint = q - 1n;
  const total = (q * perPoint) ** n;
  const all = 1n;
  const singleton = q * (perPoint ** n - 1n);
  const empty = total - all - singleton;
  return {
    field: p, independent_cycles: k, distribution: "uniform independent AGL(1,F_p)",
    total: total.toString(), all: all.toString(),
    singleton: singleton.toString(), empty: empty.toString()
  };
}
module.exports = {ensembleCounts};
if (require.main === module) {
  process.stdout.write(JSON.stringify(
    [1,2,3,4].map(k => ensembleCounts(5,k)), null, 2) + "\n");
}
