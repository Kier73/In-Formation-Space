"use strict";
/* IWI-004: cryptographic claim binding and explicit trust policy.
 * A valid signature proves only which credential signed the claim.
 * "law" entitlement is a caller-supplied EXTERNAL premise; never inferred from a sample.
 * No live E-CPU/VGI authority or durable revocation is implemented here.
 */
const crypto=require("node:crypto");
const partial=require("./partial_ground.js");
const acquisition=require("./evidence_acquisition.js");
function sha(text){return crypto.createHash("sha256").update(text).digest("hex");}
function modelBinding(model,context,revision){
 if(typeof context!=="string"||!context||typeof revision!=="string"||!revision)throw Error("invalid context or revision");
 return sha(JSON.stringify({context,revision,model:partial.validate(model)}));
}
function sign(payload,privateKey){
 const bytes=Buffer.from(JSON.stringify(payload),"utf8");
 return {payload,signature:crypto.sign(null,bytes,privateKey).toString("base64")};
}
function validateTrust(anchors){
 if(!Array.isArray(anchors)||anchors.length>20)throw Error("invalid trust manifest");
 const found=new Set();
 for(const a of anchors){
  if(!a||typeof a.keyId!=="string"||!a.keyId||found.has(a.keyId)||
     typeof a.publicKeyPem!=="string"||!a.publicKeyPem||
     typeof a.context!=="string"||!a.context||!Array.isArray(a.authorizedLawCells)||
     new Set(a.authorizedLawCells).size!==a.authorizedLawCells.length)
    throw Error("invalid trust anchor");
  found.add(a.keyId);
 }
}
function review(model,context,revision,anchors,envelopes){
 const base=partial.validate(model);
 validateTrust(anchors);
 if(!Array.isArray(envelopes)||envelopes.length>30)throw Error("invalid envelope list");
 const binding=modelBinding(model,context,revision),seenNonces=new Set();
 const updates=new Map(),events=[];
 let violation=null;
 for(const envelope of envelopes){
  const q=envelope?.payload;
  if(!q||typeof q!=="object"||typeof envelope.signature!=="string"||
     typeof q.keyId!=="string"||typeof q.cell!=="string"||
     !Number.isInteger(q.value)||typeof q.nonce!=="string"||!q.nonce||
     typeof q.requestId!=="string"||!q.requestId||
     q.binding!==binding||q.context!==context||q.revision!==revision||
     !["sample","law-cell"].includes(q.kind)||
     Object.keys(q).sort().join(",")!=="binding,cell,context,keyId,kind,nonce,requestId,revision,value"){
    violation="INVALID_ENVELOPE_OR_SCOPE";events.push({status:"REFUSED",reason:violation});break;
  }
  const a=anchors.find(x=>x.keyId===q.keyId);
  if(!a||a.context!==context||seenNonces.has(q.keyId+":"+q.nonce)){
   violation="UNTRUSTED_IDENTITY_OR_REPLAY";events.push({status:"REFUSED",reason:violation});break;
  }
  let verified=false;
  try{
   const raw=Buffer.from(envelope.signature,"base64");
   verified=raw.length===64&&crypto.verify(null,Buffer.from(JSON.stringify(q),"utf8"),a.publicKeyPem,raw);
  }catch{verified=false;}
  if(!verified){violation="SIGNATURE_MISMATCH";events.push({status:"REFUSED",reason:violation});break;}
  seenNonces.add(q.keyId+":"+q.nonce);
  let cell;
  try{cell=acquisition.parseCell(model,q.cell);}catch{
    violation="INVALID_CELL";events.push({status:"REFUSED",reason:violation});break;
  }
  if(!cell.values.includes(q.value)){
   violation="OUTSIDE_DECLARED_MODEL";events.push({status:"REFUSED",reason:violation});break;
  }
  if(q.kind==="sample"){
   events.push({status:"SIGNED_SAMPLE_RETAINED",keyId:q.keyId,cell:q.cell,value:q.value,
    nonce:q.nonce,requestId:q.requestId,entailsLawValue:false});
   continue;
  }
  if(!a.authorizedLawCells.includes(q.cell)){
   violation="NO_LAW_COVERAGE_ENTITLEMENT";events.push({status:"REFUSED",reason:violation});break;
  }
  const already=updates.get(q.cell);
  if(already!==undefined&&already!==q.value){
   violation="CONTRADICTORY_AUTHORIZED_LAW_CLAIMS";
   events.push({status:"REFUSED",reason:violation,keyId:q.keyId,cell:q.cell,value:q.value});break;
  }
  updates.set(q.cell,q.value);
  events.push({status:"SIGNED_LAW_COVERAGE_CLAIM",keyId:q.keyId,cell:q.cell,value:q.value,
   nonce:q.nonce,requestId:q.requestId,coverageAssumption:"caller-trusted static complete-cell authority"});
 }
 let candidate=null;
 if(!violation&&updates.size){
   candidate={n:base.n,start:base.start,goal:base.goal,next:base.next,output:base.output};
   for(const [key,value] of [...updates.entries()].sort((a,b)=>a[0].localeCompare(b[0])))
      candidate=acquisition.restrict(candidate,key,value);
 }
 return {schema:"IWI-004/evidence-review-v1",context,revision,binding,
  status:violation?"REFUSED_"+violation:updates.size?"PROPOSE_REFINED_GROUND":"NO_LAW_REFINEMENT",
  events,proposedModel:candidate,
  admittedLawCellCount:violation?0:updates.size,
  executedExternalEffects:false,vgiGroundAdmitted:false,
  trustLimit:"signature plus caller-supplied coverage policy; not proof that the observer told the truth"};
}
module.exports={sha,modelBinding,sign,validateTrust,review};
