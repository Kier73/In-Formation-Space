"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const p=require("./partial_ground.js");
const s=require("./support_certificate.js");
const clone=x=>JSON.parse(JSON.stringify(x));
test("a repeated unknown transition contributes one necessary inspected cell",()=>{
 const m=p.fixtures.remembered,r=p.solve(m,5),cert=s.certificate(m,r);
 assert.equal(s.audit(m,r,cert),true);
 assert.deepEqual(cert.keys,["t:0:1"]);
 assert.equal(cert.possibleSupportAssignments,"2");
 assert.equal(cert.terminalObservationLeaves,2);
});
test("24 unrelated unknown cells do not enter the one-action realization support",()=>{
 const m=p.fixtures.unvisited,r=p.solve(m,1),cert=s.certificate(m,r);
 assert.deepEqual(cert.keys,[]);
 assert.equal(cert.supportCellCount,0);
 assert.equal(cert.unresolvedUnusedCells,24);
 assert.equal(cert.fullCompleteLaws,"16777216");
 assert.equal(cert.possibleSupportAssignments,"1");
 assert.equal(s.audit(m,r,cert),true);
});
test("an unknown observation law contributes its output cell when action reads it",()=>{
 const m={...p.fixtures.unknownOutput,goal:[2]};
 const r=p.solve(m,1),cert=s.certificate(m,r);
 assert.equal(r.minimumWorstCase,1);
 assert.deepEqual(cert.keys,["o:2"]);
 assert.equal(cert.possibleSupportAssignments,"2");
});
test("false reports cannot be used to claim a certificate, including a fake non-win",()=>{
 const m=p.fixtures.remembered,r=p.solve(m,5),cert=s.certificate(m,r);
 let bad=clone(cert);bad.keys=[];bad.supportCellCount=0;
 assert.throws(()=>s.audit(m,r,bad));
 bad=clone(r);bad.status="no-certain-policy-through-horizon";bad.plan=null;bad.minimumWorstCase=null;
 assert.throws(()=>s.certificate(m,bad));
 bad=clone(r);bad.plan={stop:true};
 assert.throws(()=>s.certificate(m,bad));
});
test("non-winning policies carry no alleged witness relevance support",()=>{
 const m=p.fixtures.unknowable,r=p.solve(m,5);
 const cert=s.certificate(m,r);
 assert.equal(cert.status,"not-applicable-no-winning-policy");
 assert.equal(s.audit(m,r,cert),true);
});
test("stored support certificates reconstruct exactly",()=>{
 const saved=JSON.parse(fs.readFileSync(path.join(__dirname,"results","support_certificate.json"),"utf8"));
 assert.deepEqual(s.study(),saved);
});
