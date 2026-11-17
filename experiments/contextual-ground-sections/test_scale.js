"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {FIELD,makeGraph,experiment}=require("./scale.js");
const {solve,assignment,apply}=require("./sections.js");
const {verify}=require("./verifier.js");

test("CGS-004: 1,024 virtual observers and 1,022 cycles, no assignment enumeration",()=>{
  const reports=experiment(1024);
  assert.deepEqual(reports.map(r=>r.mode),["flat","pinned","empty"]);
  assert.deepEqual(reports.map(r=>r.section_count),[FIELD,1,0]);
  for(const report of reports){
    assert.equal(report.vertices,1024);
    assert.equal(report.edges,2045);
    assert.equal(report.fundamental_cycles,1022);
    assert.equal(report.independent_arithmetic_verifier,true);
    assert.equal(report.enumerated_assignments,0);
    assert.ok(Number.isFinite(report.solver_and_verifier_ms));
  }
});
test("complete edge equations independently hold for admissible sample sections",()=>{
  for(const n of [4,32])for(const mode of ["flat","pinned"]){
    const g=makeGraph(n,mode),r=solve(g.p,g.vertices,g.edges,g.root);
    assert.equal(verify(r).section_count,mode==="flat"?FIELD:1);
    for(const x of mode==="flat"?[0,1,17,FIELD-1]:[FIELD-5]){
      const assignmentMap=assignment(r,x);
      for(const e of g.edges)
        assert.equal(assignmentMap[e.to],
          apply([e.a,e.b],assignmentMap[e.from],FIELD));
    }
  }
});
test("contradictory scaling fixture is rejected by its own mathematics",()=>{
  const g=makeGraph(64,"empty");
  const r=solve(g.p,g.vertices,g.edges,g.root);
  assert.equal(verify(r).section_count,0);
  assert.equal(r.flat,false);
  assert.throws(()=>assignment(r,0),/no global section/);
});
test("reject malformed scaling parameters",()=>{
  assert.throws(()=>makeGraph(3,"flat"),/invalid scale/);
  assert.throws(()=>makeGraph(8193,"flat"),/invalid scale/);
  assert.throws(()=>makeGraph(16,"unknown"),/invalid scale/);
});
