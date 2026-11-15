"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const crypto=require("node:crypto");
const p=require("./partial_ground.js");
const g=require("./global_oracle.js");
const q=require("./evidence_acquisition.js");
const ev=require("./evidence_claims.js");
const copy=x=>JSON.parse(JSON.stringify(x));
function keys(){
 const {publicKey,privateKey}=crypto.generateKeyPairSync("ed25519");
 return {publicKeyPem:publicKey.export({format:"pem",type:"spki"}),privateKey};
}
function claim(model,keyId,context,revision,cell,value,kind,nonce,privateKey){
 return ev.sign({binding:ev.modelBinding(model,context,revision),cell,context,
 keyId,kind,nonce,requestId:"request:"+cell,revision,value},privateKey);
}
test("minimal acquisition: one certified unknown law cell, symbolic cost 2",()=>{
 const f=q.fixtures.needed,r=q.plan(f.model,f.caps,f.horizon,f.queries);
 assert.equal(r.status,"REQUEST_LAW_EVIDENCE");
 assert.equal(r.minimumWorstEvidenceCost,2);
 assert.equal(r.maximumQueries,1);
 assert.equal(r.worstExecutionActions,2);
 assert.equal(r.tree.key,"t:0:1");
 assert.deepEqual(r.tree.children.map(c=>c.value),[2,3]);
 assert.equal(q.verify(f.model,f.caps,r).exactMinimumWorstCost,2);
});
test("global completion oracle validates joint impossibility and both acquired continuations",()=>{
 const f=q.fixtures.needed;
 assert.equal(g.globalOracle(f.model).status,"globally-impossible");
 for(const value of [2,3]){
  const narrowed=q.restrict(f.model,"t:0:1",value);
  const global=g.globalOracle(narrowed);
  assert.equal(global.status,"globally-winning");
  assert.equal(global.rootRank,2);
 }
});
test("refuse unlicensed acquisition without guessing a transition",()=>{
 const f=q.fixtures.prohibited,r=q.plan(f.model,f.caps,f.horizon,f.queries);
 assert.equal(r.status,"UNRESOLVED_WITHIN_DECLARED_BOUNDS");
 assert.equal(r.tree,null);
 assert.equal(q.verify(f.model,f.caps,r).verified,true);
});
test("when execution already succeeds, do not query law cells",()=>{
 for(const name of ["already_observable","irrelevant"]){
  const f=q.fixtures[name],r=q.plan(f.model,f.caps,f.horizon,f.queries);
  assert.equal(r.status,"READY");
  assert.equal(r.minimumWorstEvidenceCost,0);
  assert.equal(r.maximumQueries,0);
  assert.equal(q.verify(f.model,f.caps,r).verified,true);
 }
});
test("request binding and finite horizon/cost cannot be silently rewritten",()=>{
 const f=q.fixtures.needed,r=q.plan(f.model,f.caps,f.horizon,f.queries);
 for(const edit of [x=>x.minimumWorstEvidenceCost=1,x=>x.tree.children=[],
  x=>x.tree.children[1].value=2,x=>x.tree.key="t:1:1",
  x=>x.tree.children[0].plan={kind:"ready",actions:0,policy:{stop:true}},
  x=>x.executionHorizon=1,x=>x.baseModel.next[0][1]=[2]]) {
  const c=copy(r);edit(c);assert.throws(()=>q.verify(f.model,f.caps,c));
 }
 assert.throws(()=>q.plan(f.model,f.caps,3,1,{maxAcquisitionStates:1}));
});
test("query capabilities must explicitly authorize an exact static cell",()=>{
 const f=q.fixtures.needed;
 for(const caps of [
  [{key:"t:0:1",cost:0,scope:"offline-static-law-cell"}],
  [{key:"t:0:1",cost:1,scope:"live-sampled-observation"}],
  [{key:"t:0:1",cost:1,scope:"offline-static-law-cell"},{key:"t:0:1",cost:2,scope:"offline-static-law-cell"}],
  [{key:"t:9:1",cost:1,scope:"offline-static-law-cell"}]
 ])assert.throws(()=>q.plan(f.model,caps,3,1));
});
test("signed sample is retained but cannot narrow the universal Ground",()=>{
 const m=q.fixtures.needed.model,{publicKeyPem,privateKey}=keys(),ctx="test-session",rev="ground-r1";
 const anchors=[{keyId:"observer",publicKeyPem,context:ctx,authorizedLawCells:[]}];
 const e=claim(m,"observer",ctx,rev,"t:0:1",2,"sample","unique-1",privateKey);
 const out=ev.review(m,ctx,rev,anchors,[e]);
 assert.equal(out.status,"NO_LAW_REFINEMENT");
 assert.equal(out.events[0].entailsLawValue,false);
 assert.equal(out.proposedModel,null);
 assert.equal(q.plan(m,[],3,0).status,"UNRESOLVED_WITHIN_DECLARED_BOUNDS");
});
test("explicitly trusted law-cell entitlement permits a model revision proposal, not VGI admission",()=>{
 const m=q.fixtures.needed.model,{publicKeyPem,privateKey}=keys(),ctx="fixture-context",rev="r7";
 const anchors=[{keyId:"authority",publicKeyPem,context:ctx,authorizedLawCells:["t:0:1"]}];
 const e=claim(m,"authority",ctx,rev,"t:0:1",3,"law-cell","unique-2",privateKey);
 const out=ev.review(m,ctx,rev,anchors,[e]);
 assert.equal(out.status,"PROPOSE_REFINED_GROUND");
 assert.equal(out.admittedLawCellCount,1);
 assert.equal(out.vgiGroundAdmitted,false);
 assert.equal(out.executedExternalEffects,false);
 assert.deepEqual(out.proposedModel.next[0][1],[3]);
 const plan=q.plan(out.proposedModel,[],3,0);
 assert.equal(plan.status,"READY");assert.equal(plan.worstExecutionActions,2);
 assert.equal(q.verify(out.proposedModel,[],plan).verified,true);
});
test("a valid but unauthorized signer cannot promote a sample to law coverage",()=>{
 const m=q.fixtures.needed.model,{publicKeyPem,privateKey}=keys(),ctx="fixture-context",rev="r7";
 const anchors=[{keyId:"observer",publicKeyPem,context:ctx,authorizedLawCells:[]}];
 const e=claim(m,"observer",ctx,rev,"t:0:1",3,"law-cell","unique-3",privateKey);
 const out=ev.review(m,ctx,rev,anchors,[e]);
 assert.equal(out.status,"REFUSED_NO_LAW_COVERAGE_ENTITLEMENT");
 assert.equal(out.proposedModel,null);
});
test("tampered signature, wrong key and changed request binding fail closed",()=>{
 const m=q.fixtures.needed.model,k=keys(),other=keys(),ctx="ctx",rev="rev1";
 const anchors=[{keyId:"issuer",publicKeyPem:k.publicKeyPem,context:ctx,authorizedLawCells:["t:0:1"]}];
 const original=claim(m,"issuer",ctx,rev,"t:0:1",2,"law-cell","unique-4",k.privateKey);
 const attempts=[
  {...original,payload:{...original.payload,value:3}},
  {...original,payload:{...original.payload,requestId:"other"}},
  {...original,signature:ev.sign(original.payload,other.privateKey).signature},
  {...original,payload:{...original.payload,binding:"0".repeat(64)}}
 ];
 for(const bad of attempts)assert.match(ev.review(m,ctx,rev,anchors,[bad]).status,/^REFUSED_/);
 assert.equal(ev.review(m,ctx,"rev2",anchors,[original]).proposedModel,null);
});
test("conflicting genuine law claims refuse the entire proposed refinement",()=>{
 const m=q.fixtures.needed.model,k1=keys(),k2=keys(),ctx="ctx",rev="rev";
 const anchors=[{keyId:"a",publicKeyPem:k1.publicKeyPem,context:ctx,authorizedLawCells:["t:0:1"]},
  {keyId:"b",publicKeyPem:k2.publicKeyPem,context:ctx,authorizedLawCells:["t:0:1"]}];
 const one=claim(m,"a",ctx,rev,"t:0:1",2,"law-cell","n-a",k1.privateKey);
 const two=claim(m,"b",ctx,rev,"t:0:1",3,"law-cell","n-b",k2.privateKey);
 const out=ev.review(m,ctx,rev,anchors,[one,two]);
 assert.equal(out.status,"REFUSED_CONTRADICTORY_AUTHORIZED_LAW_CLAIMS");
 assert.equal(out.proposedModel,null);
 assert.equal(out.admittedLawCellCount,0);
});
test("replayed receipt nonce and out-of-domain report do not become Ground facts",()=>{
 const m=q.fixtures.needed.model,k=keys(),ctx="ctx",rev="rev";
 const anchors=[{keyId:"a",publicKeyPem:k.publicKeyPem,context:ctx,authorizedLawCells:["t:0:1"]}];
 const original=claim(m,"a",ctx,rev,"t:0:1",2,"law-cell","n-1",k.privateKey);
 assert.equal(ev.review(m,ctx,rev,anchors,[original,original]).status,"REFUSED_UNTRUSTED_IDENTITY_OR_REPLAY");
 const invalid=claim(m,"a",ctx,rev,"t:0:1",0,"law-cell","n-2",k.privateKey);
 assert.equal(ev.review(m,ctx,rev,anchors,[invalid]).status,"REFUSED_OUTSIDE_DECLARED_MODEL");
});
test("deterministic evidence-acquisition result reconstructs without source modification",()=>{
 const s=JSON.parse(fs.readFileSync(path.join(__dirname,"results","evidence_acquisition.json"),"utf8"));
 assert.deepEqual(q.study(),s);
});
