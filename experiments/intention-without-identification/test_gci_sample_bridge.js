"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const crypto=require("node:crypto");
const bridge=require("./gci_sample_bridge.js");
const gate=require("./evidence_claims.js");
const acquisition=require("./evidence_acquisition.js");
const clone=x=>JSON.parse(JSON.stringify(x));
function fixture(){
 const {publicKey,privateKey}=crypto.generateKeyPairSync("ec",{namedCurve:"prime256v1"});
 const publicKeyPem=publicKey.export({format:"pem",type:"spki"});
 const request={schema:"in-formation.gci004-observation-request/0.1",
  task_id:"test-task",feature:"parity",binding:{source:"ground-v1",intention:"IWI-004"},
  phase_commitment:"commitment-abc",challenge:"challenge-123"};
 const peerId="observer-a",snapshotDigest="snapshot-hash-test";
 const payload={schema:bridge.receiptSchema,peer_id:peerId,snapshot_digest:snapshotDigest,
  request_digest:bridge.digest(request),task_id:request.task_id,feature:request.feature,
  binding:request.binding,phase_commitment:request.phase_commitment,
  challenge:request.challenge,value:1};
 const signature_b64=crypto.sign("sha256",Buffer.from(bridge.canonical(payload),"utf8"),privateKey).toString("base64");
 return {request,receipt:{payload,signature_b64},peerId,snapshotDigest,publicKeyPem};
}
test("canonical GCI subset sorts recursively, never accepts floats or Unicode ambiguity",()=>{
 assert.equal(bridge.canonical({z:[{b:2,a:"a"}],a:1}),'{ "placeholder":0 }'.replace('{ "placeholder":0 }','{"a":1,"z":[{"a":"a","b":2}]}'));
 assert.throws(()=>bridge.canonical({x:NaN}));
 assert.throws(()=>bridge.canonical({x:1.25}));
 assert.throws(()=>bridge.canonical({x:"é"}));
});
test("a real ECDSA-SHA256 key signed GCI feature projection remains sample only",()=>{
 const f=fixture(),out=bridge.verifyGciSample(f);
 assert.equal(out.status,"SIGNED_FEATURE_SAMPLE_ONLY");
 assert.equal(out.value,1);assert.equal(out.entailsUniversalTransition,false);
 assert.equal(out.proposedLawDomainReduction,null);
 assert.equal(out.requestDigest,bridge.digest(f.request));
});
test("wrong key, edited feature value, wrong challenge or peer are rejected",()=>{
 const f=fixture(),strangers=fixture();
 const edited=clone(f);edited.receipt.payload.value=0;
 const wrongChallenge=clone(f);wrongChallenge.request.challenge="new";
 const wrongPeer=clone(f);wrongPeer.peerId="observer-b";
 const wrongSnapshot=clone(f);wrongSnapshot.snapshotDigest="different";
 for(const candidate of [edited,wrongChallenge,wrongPeer,wrongSnapshot,
  {...f,publicKeyPem:strangers.publicKeyPem}])
   assert.throws(()=>bridge.verifyGciSample(candidate));
});
test("signed GCI sample cannot be substituted for a universal law-cell envelope",()=>{
 const projection=bridge.verifyGciSample(fixture());
 const f=acquisition.fixtures.needed;
 const anchor=[];
 const out=gate.review(f.model,"test-session","r1",anchor,[projection]);
 assert.match(out.status,/^REFUSED_/);
 assert.equal(out.proposedModel,null);
});
test("invalid ECDSA signer or mutated request schema is refused",()=>{
 const f=fixture(),ed=crypto.generateKeyPairSync("ed25519");
 assert.throws(()=>bridge.verifyGciSample({...f,publicKeyPem:ed.publicKey.export({format:"pem",type:"spki"})}));
 const changed=clone(f);changed.request.feature="low2";
 assert.throws(()=>bridge.verifyGciSample(changed));
 const noncanonical=clone(f);noncanonical.receipt.signature_b64="***";
 assert.throws(()=>bridge.verifyGciSample(noncanonical));
});
