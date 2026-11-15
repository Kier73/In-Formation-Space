"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  solve, assignment, decide, changeCharts, inverse, apply, multiply,
  bruteForce, fixtures, demonstration
} = require("./sections.js");
const {ensembleCounts} = require("./ensemble.js");

const AB = (id, from, to, a, b) => ({id, from, to, a, b});
const affine = p => Array.from({length: p - 1}, (_, k) =>
  Array.from({length: p}, (_, b) => [k + 1, b])).flat();

test("four fundamentally different globalization regimes and independent oracle", () => {
  const expected = [
    ["flat", true, "all", 5, null],
    ["translation-obstruction", false, "empty", 0, null],
    ["nonflat-but-realizable", false, "singleton", 1, 0],
    ["incompatible-fixed-points", false, "empty", 0, null]
  ];
  for (const [i, f] of fixtures().entries()) {
    const r = solve(5, f.vertices, f.edges, "A");
    assert.deepEqual([f.id, r.flat, r.status, r.section_count, r.root_value], expected[i]);
    const brute = bruteForce(5, f.vertices, f.edges);
    assert.equal(brute.length, r.section_count);
    for (const a of brute) assert.deepEqual(assignment(r, a.A), a);
  }
  assert.equal(demonstration().length, 4);
});

test("all 216 affine-labeled triangles over F_3: full independent enumeration", () => {
  const vertices = ["A", "B", "C"], maps = affine(3);
  const histogram = {all: 0, singleton: 0, empty: 0};
  for (const ab of maps) for (const bc of maps) for (const ac of maps) {
    const edges = [
      AB("ab", "A", "B", ...ab), AB("bc", "B", "C", ...bc),
      AB("ac", "A", "C", ...ac)
    ];
    const r = solve(3, vertices, edges, "A");
    const brute = bruteForce(3, vertices, edges);
    assert.equal(r.section_count, brute.length);
    histogram[r.status]++;
    for (const a of brute) assert.deepEqual(assignment(r, a.A), a);
  }
  assert.deepEqual(histogram, {all:36, singleton:108, empty:72});
});

test("two and three independent cycles: exact ensemble law matches full enumeration", () => {
  const vertices = ["A", "B"];
  for (const [p, k] of [[5, 2], [3, 3]]) {
    const maps = affine(p), histogram = {all:0, singleton:0, empty:0};
    const choices = Array(k).fill(0);
    function visit(i) {
      if (i < k) {
        for (let j = 0; j < maps.length; j++) {choices[i] = j; visit(i + 1);}
        return;
      }
      const edges = [AB("tree", "A", "B", 1, 0)];
      for (let j = 0; j < k; j++) edges.push(AB("loop"+j, "A", "B", ...maps[choices[j]]));
      const r = solve(p, vertices, edges, "A");
      const brute = bruteForce(p, vertices, edges);
      assert.equal(r.section_count, brute.length);
      histogram[r.status]++;
    }
    visit(0);
    const law = ensembleCounts(p,k);
    assert.equal(String(histogram.all), law.all);
    assert.equal(String(histogram.singleton), law.singleton);
    assert.equal(String(histogram.empty), law.empty);
  }
});

test("independent observer chart changes preserve all sections, not just counts", () => {
  let seed = 0xC05E2026;
  const next = n => {seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed % n;};
  const vertices = ["A","B","C","D"], names = ["ab","ac","ad","bc","bd","cd"];
  const endpoints = [["A","B"],["A","C"],["A","D"],["B","C"],["B","D"],["C","D"]];
  for (let trial = 0; trial < 120; trial++) {
    const edges = names.map((id,i) =>
      AB(id,...endpoints[i],1+next(4),next(5)));
    const gauges = Object.fromEntries(vertices.map(v => [v,[1+next(4),next(5)]]));
    const changed = changeCharts(5, edges, gauges);
    const original = solve(5, vertices, edges, "A");
    const transformed = solve(5, vertices, changed, "A");
    assert.equal(original.section_count, transformed.section_count);
    assert.equal(original.flat, transformed.flat);
    const originalOracle = bruteForce(5, vertices, edges);
    const changedOracle = bruteForce(5, vertices, changed);
    assert.equal(originalOracle.length, changedOracle.length);
    const image = originalOracle.map(a => Object.fromEntries(
      vertices.map(v => [v,apply(gauges[v], a[v],5)])));
    assert.deepEqual(image, changedOracle);
  }
});

test("inverting arbitrary edge direction does not change realizability", () => {
  for (const f of fixtures()) {
    const reversed = f.edges.map(e => {
      const [a,b] = inverse([e.a,e.b], 5);
      return AB(e.id, e.to, e.from, a, b);
    });
    const a = solve(5,f.vertices,f.edges,"A");
    const b = solve(5,f.vertices,reversed,"A");
    assert.equal(a.section_count,b.section_count);
    assert.equal(a.flat,b.flat);
    assert.equal(a.root_value,b.root_value);
  }
});

test("witness cycles are sufficient to make a formerly valid Ground empty", () => {
  const translation = fixtures()[1];
  const r = solve(5,translation.vertices,translation.edges,"A");
  assert.equal(r.obstruction_edges.length,1);
  const removed = translation.edges.filter(e => e.id !== r.obstruction_edges[0]);
  assert.equal(solve(5,translation.vertices,removed,"A").section_count,5);

  const incompatible = fixtures()[3];
  const s = solve(5,incompatible.vertices,incompatible.edges,"A");
  assert.equal(s.obstruction_edges.length,2);
  for (const edgeId of s.obstruction_edges) {
    assert.equal(solve(5,incompatible.vertices,
      incompatible.edges.filter(e => e.id !== edgeId),"A").section_count,1);
  }
});

test("intention-relative claims: determined, undetermined, refusal", () => {
  const cases = fixtures().map(f => solve(5,f.vertices,f.edges,"A"));
  assert.deepEqual(decide(cases[0], () => "unchanged"),
    {status:"determined",value:"unchanged",admissible_sections:5});
  assert.equal(decide(cases[0], a => a.A).status,"undetermined");
  assert.deepEqual(decide(cases[2], a => a.C),
    {status:"determined",value:0,admissible_sections:1});
  assert.deepEqual(decide(cases[1], a => a.A),
    {status:"refuse",reason:"no global section"});
  assert.throws(() => assignment(cases[2],1),/no global section/);
});

test("refuses invalid moduli, coordinates, edges and disconnected charts", () => {
  assert.throws(() => solve(4,["A"],[],"A"),/prime/);
  assert.throws(() => solve(2,["A","A"],[],"A"),/vertices/);
  assert.throws(() => solve(5,["A","B"],[],"A"),/disconnected/);
  assert.throws(() => solve(5,["A"],[], "B"),/root absent/);
  assert.throws(() => solve(5,["A"],[AB("x","A","A",0,1)],"A"),/invalid edge/);
  assert.throws(() => solve(5,["A"],[
    AB("x","A","A",1,0),AB("x","A","A",1,1)],"A"),/invalid edge/);
  assert.throws(() => changeCharts(5,[AB("x","A","A",1,0)],{A:[0,1]}),/gauge/);
});

test("affine composition and inversion are correct over all F_5 maps", () => {
  for (const f of affine(5)) {
    const inv = inverse(f,5);
    assert.deepEqual(multiply(f,inv,5),[1,0]);
    assert.deepEqual(multiply(inv,f,5),[1,0]);
    for (let x=0; x<5; x++) assert.equal(apply(inv,apply(f,x,5),5),x);
  }
});
