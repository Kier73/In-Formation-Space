"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {solve, fixtures, bruteForce, changeCharts} = require("./sections.js");
const {verify} = require("./verifier.js");
const copy = x => JSON.parse(JSON.stringify(x));
const fails = record => assert.throws(() => verify(record), /invalid section certificate/);

test("independent verifier accepts all four complete certificates", () => {
  for(const f of fixtures()) {
    const record=solve(5,f.vertices,f.edges,"A");
    const verdict=verify(JSON.parse(JSON.stringify(record)));
    assert.equal(verdict.verified,true);
    assert.equal(verdict.status,record.status);
    assert.equal(verdict.section_count,bruteForce(5,f.vertices,f.edges).length);
  }
});
test("verifier independently checks every affine-labelled F_3 triangle", () => {
  const v=["A","B","C"];
  const maps=[];
  for(let a=1;a<3;a++)for(let b=0;b<3;b++)maps.push([a,b]);
  let checked=0;
  for(const ab of maps)for(const bc of maps)for(const ac of maps){
    const edges=[
      {id:"ab",from:"A",to:"B",a:ab[0],b:ab[1]},
      {id:"bc",from:"B",to:"C",a:bc[0],b:bc[1]},
      {id:"ac",from:"A",to:"C",a:ac[0],b:ac[1]}
    ];
    const r=solve(3,v,edges,"A");
    assert.equal(verify(r).section_count,bruteForce(3,v,edges).length);
    checked++;
  }
  assert.equal(checked,216);
});
test("forged conclusions and individual intermediate proofs fail closed", () => {
  const r=solve(5,fixtures()[2].vertices,fixtures()[2].edges,"A");
  const mutations=[
    x=>{x.status="all";},
    x=>{x.flat=true;},
    x=>{x.root_value=1;},
    x=>{x.section_count=5;},
    x=>{x.cycles[0].holonomy[0]=1;},
    x=>{x.cycles[0].constraint.value=1;},
    x=>{x.tree_maps.C[0]=4;},
    x=>{x.tree_edges=[];},
    x=>{x.cycles=[];},
    x=>{x.edges[0].b=4;},
    x=>{x.vertices.push("Z");},
    x=>{x.field=4;},
    x=>{x.schema="unknown";},
    x=>{x.obstruction_edges=["forged"];}
  ];
  for(const mutate of mutations) {
    const x=copy(r);mutate(x);fails(x);
  }
});
test("empty-certificate witness mutation is rejected", () => {
  const f=fixtures()[3], r=solve(5,f.vertices,f.edges,"A");
  const changed=copy(r);
  changed.obstruction_edges.pop();
  fails(changed);
});
test("independently verified coordinate changes preserve section cardinality", () => {
  const f=fixtures()[2];
  const base=solve(5,f.vertices,f.edges,"A");
  const changed=solve(5,f.vertices,changeCharts(5,f.edges,
    {A:[2,1],B:[4,3],C:[3,2]}),"A");
  assert.equal(verify(base).section_count,verify(changed).section_count);
  assert.equal(verify(base).flat,verify(changed).flat);
});
