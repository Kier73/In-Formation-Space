"use strict";

/*
 * CGS-001: exact global sections for locally invertible affine transports.
 * Educational finite-field model, not a claim of authenticated physical sensing.
 * Maps are f(x) = a*x+b (mod p), with nonzero a and prime p <= 65521.
 */
const I = [1, 0];
const mod = (x, p) => ((x % p) + p) % p;

function prime(p) {
  if (!Number.isSafeInteger(p) || p < 2 || p > 65521) return false;
  for (let i = 2; i * i <= p; i++) if (p % i === 0) return false;
  return true;
}
function multiply(f, g, p) { // f after g
  return [mod(f[0] * g[0], p), mod(f[0] * g[1] + f[1], p)];
}
function inverse(f, p) {
  if (mod(f[0], p) === 0) throw new Error("noninvertible transport");
  let a = f[0], n = p - 2, out = 1;
  while (n > 0) {
    if (n % 2) out = mod(out * a, p);
    a = mod(a * a, p);
    n = Math.floor(n / 2);
  }
  return [out, mod(-out * f[1], p)];
}
const apply = (f, x, p) => mod(f[0] * x + f[1], p);
const isIdentity = f => f[0] === 1 && f[1] === 0;

function normalize(p, vertices, edges, root) {
  if (!prime(p)) throw new Error("p must be a prime <= 65521");
  if (!Array.isArray(vertices) || vertices.length < 1 ||
      vertices.some(v => typeof v !== "string" || !v.length) ||
      new Set(vertices).size !== vertices.length) throw new Error("invalid vertices");
  if (!vertices.includes(root)) throw new Error("root absent");
  if (!Array.isArray(edges)) throw new Error("invalid edges");
  const ids = new Set(), nodes = new Set(vertices);
  return edges.map(e => {
    if (!e || typeof e.id !== "string" || !e.id ||
        ids.has(e.id) || !nodes.has(e.from) || !nodes.has(e.to) ||
        !Number.isInteger(e.a) || !Number.isInteger(e.b) ||
        e.a < 1 || e.a >= p || e.b < 0 || e.b >= p) {
      throw new Error("invalid edge");
    }
    ids.add(e.id);
    return {id: e.id, from: e.from, to: e.to, a: e.a, b: e.b};
  }).sort((x, y) => x.id < y.id ? -1 : x.id > y.id ? 1 : 0);
}

/*
 * The tree gives a unique transport P_v : root -> v.
 * Every non-tree edge u->v imposes the root constraint
 * P_v^-1 o E_uv o P_u (x) = x.
 *
 * An affine constraint (a-1)x = -b over F_p is either:
 * any root point, exactly one root point, or no root point.
 * Thus a connected graph has 0, 1, or p exact global sections.
 */
function solve(p, vertices, edges, root) {
  const es = normalize(p, vertices, edges, root);
  const adjacency = new Map(vertices.map(v => [v, []]));
  for (const e of es) {
    adjacency.get(e.from).push([e.to, e, true]);
    adjacency.get(e.to).push([e.from, e, false]);
  }
  const transport = new Map([[root, I]]);
  const treeEdges = new Set();
  const queue = [root];
  for (let i = 0; i < queue.length; i++) {
    const v = queue[i];
    for (const [w, e, forward] of adjacency.get(v)) {
      if (transport.has(w)) continue;
      const t = forward ? [e.a, e.b] : inverse([e.a, e.b], p);
      transport.set(w, multiply(t, transport.get(v), p));
      treeEdges.add(e.id);
      queue.push(w);
    }
  }
  if (queue.length !== vertices.length) throw new Error("disconnected graph");
  let fixed = null, origin = null, conflict = null;
  const cycles = [];
  for (const e of es) {
    if (treeEdges.has(e.id)) continue;
    const h = multiply(inverse(transport.get(e.to), p),
                 multiply([e.a, e.b], transport.get(e.from), p), p);
    let constraint;
    if (isIdentity(h)) {
      constraint = {kind: "any"};
    } else if (h[0] === 1) {
      constraint = {kind: "none"};
      if (!conflict) conflict = [e.id];
    } else {
      const inv = inverse([mod(h[0] - 1, p), 0], p)[0];
      const value = mod(-h[1] * inv, p);
      constraint = {kind: "point", value};
      if (fixed === null) { fixed = value; origin = e.id; }
      else if (fixed !== value && !conflict) conflict = [origin, e.id];
    }
    cycles.push({edge: e.id, holonomy: h, constraint});
  }
  const status = conflict ? "empty" : fixed === null ? "all" : "singleton";
  const maps = Object.fromEntries(
    [...transport.entries()].sort(([a], [b]) => a.localeCompare(b))
  );
  return {
    schema: "ifs.contextual-ground-sections/0.1",
    field: p, root, vertices: [...vertices].sort(),
    edges: es, tree_edges: [...treeEdges].sort(),
    tree_maps: maps, cycles,
    flat: cycles.every(c => isIdentity(c.holonomy)),
    status, root_value: status === "singleton" ? fixed : null,
    section_count: status === "empty" ? 0 : status === "all" ? p : 1,
    obstruction_edges: conflict || []
  };
}

function assignment(record, x) {
  if (!Number.isInteger(x) || x < 0 || x >= record.field)
    throw new Error("invalid root value");
  if (record.status === "empty" ||
      (record.status === "singleton" && x !== record.root_value))
    throw new Error("root value has no global section");
  return Object.fromEntries(
    Object.entries(record.tree_maps).map(([v, f]) =>
      [v, apply(f, x, record.field)])
  );
}

/* Answer a query only if its value is identical on every admitted section.
 * For all-field fibers, this enumerates p root points explicitly.
 */
function decide(record, output) {
  if (record.status === "empty") return {status: "refuse", reason: "no global section"};
  const values = record.status === "singleton"
    ? [record.root_value] : Array.from({length: record.field}, (_, i) => i);
  let expected, first = true;
  for (const x of values) {
    const y = output(assignment(record, x));
    if (first) { expected = y; first = false; }
    else if (!Object.is(y, expected))
      return {status: "undetermined", example_root: x};
  }
  return {status: "determined", value: expected, admissible_sections: record.section_count};
}

/* Change every observer's coordinate chart independently.
 * G_v o E_uv o G_u^-1 must preserve section count.
 */
function changeCharts(p, edges, gauges) {
  return edges.map(e => {
    const left = gauges[e.to], right = gauges[e.from];
    if (!Array.isArray(left) || !Array.isArray(right) ||
        left.length !== 2 || right.length !== 2 ||
        !left.every(Number.isInteger) || !right.every(Number.isInteger) ||
        mod(left[0], p) === 0 || mod(right[0], p) === 0)
      throw new Error("invalid gauge");
    const f = multiply(left, multiply([e.a, e.b], inverse(right, p), p), p);
    return {...e, a: f[0], b: f[1]};
  });
}

/* Deliberately independent oracle: enumerate all vertex assignments.
 * Small fixtures only; do NOT use as a production solver.
 */
function bruteForce(p, vertices, edges) {
  if (Math.pow(p, vertices.length) > 250000) throw new Error("oracle too large");
  const all = [], values = new Array(vertices.length).fill(0);
  const indexes = new Map(vertices.map((v, i) => [v, i]));
  function visit(i) {
    if (i === vertices.length) {
      if (edges.every(e =>
        values[indexes.get(e.to)] === apply([e.a, e.b], values[indexes.get(e.from)], p))) {
        all.push(Object.fromEntries(vertices.map((v, j) => [v, values[j]])));
      }
      return;
    }
    for (let x = 0; x < p; x++) { values[i] = x; visit(i + 1); }
  }
  visit(0);
  return all;
}

function fixtures() {
  const vertices = ["A", "B", "C"];
  return [
    {id: "flat", vertices, edges: [
      {id:"ab",from:"A",to:"B",a:1,b:0},
      {id:"bc",from:"B",to:"C",a:1,b:0},
      {id:"ac",from:"A",to:"C",a:1,b:0}]},
    {id: "translation-obstruction", vertices, edges: [
      {id:"ab",from:"A",to:"B",a:1,b:0},
      {id:"bc",from:"B",to:"C",a:1,b:0},
      {id:"ac",from:"A",to:"C",a:1,b:1}]},
    {id: "nonflat-but-realizable", vertices, edges: [
      {id:"ab",from:"A",to:"B",a:1,b:0},
      {id:"bc",from:"B",to:"C",a:1,b:0},
      {id:"ac",from:"A",to:"C",a:2,b:0}]},
    {id: "incompatible-fixed-points", vertices:["A","B","C","D"], edges: [
      {id:"ab",from:"A",to:"B",a:1,b:0},
      {id:"bc",from:"B",to:"C",a:1,b:0},
      {id:"bd",from:"B",to:"D",a:1,b:0},
      {id:"ac",from:"A",to:"C",a:2,b:0},
      {id:"ad",from:"A",to:"D",a:2,b:4}]}
  ];
}
function demonstration() {
  return fixtures().map(f => {
    const r = solve(5, f.vertices, f.edges, "A");
    const brute = bruteForce(5, f.vertices, f.edges);
    if (r.section_count !== brute.length) throw new Error("oracle mismatch");
    return {case: f.id, flat: r.flat, status: r.status,
      section_count: r.section_count, root_value: r.root_value,
      cycles: r.cycles, obstruction_edges: r.obstruction_edges};
  });
}
module.exports = {mod, prime, multiply, inverse, apply, solve, assignment,
  decide, changeCharts, bruteForce, fixtures, demonstration};
if (require.main === module) process.stdout.write(JSON.stringify(demonstration(), null, 2) + "\n");
