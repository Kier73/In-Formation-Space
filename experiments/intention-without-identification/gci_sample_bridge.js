"use strict";
/* Read-only GCI-004/GCI-005 receipt bridge for a *sample* feature observation.
 * Pinned interface: experiments/cross-ground-continuity/gci004/fabric_contract.py
 * This verifies ECDSA-SHA256 against a caller-pinned public key and exact request
 * but DOES NOT validate X.509 trust chain, peer transport or VGI authority.
 */
const crypto=require("node:crypto");
const receiptSchema="in-formation.gci004-observation-receipt/0.1";
function canonical(value,depth=0){
 if(depth>32)throw Error("nested record too deep");
 if(value===null)return "null";
 if(typeof value==="string"){
  if(!/^[\x20-\x7e]*$/.test(value))throw Error("non-ASCII source not in verified wire subset");
  return JSON.stringify(value);
 }
 if(typeof value==="number"){
  if(!Number.isSafeInteger(value))throw Error("unsafe or noninteger value");
  return String(value);
 }
 if(typeof value==="boolean")return value?"true":"false";
 if(Array.isArray(value))return "["+value.map(x=>canonical(x,depth+1)).join(",")+"]";
 if(value&&typeof value==="object"){
  const keys=Object.keys(value).sort();
  if(!keys.every(k=>/^[\x20-\x7e]+$/.test(k))||keys.length>200)throw Error("invalid canonical object keys");
  return "{"+keys.map(k=>JSON.stringify(k)+":"+canonical(value[k],depth+1)).join(",")+"}";
 }
 throw Error("unsupported JSON type");
}
function digest(doc){return crypto.createHash("sha256").update(canonical(doc),"utf8").digest("hex");}
function verifyGciSample({request,receipt,peerId,snapshotDigest,publicKeyPem}){
 const pay=receipt?.payload,signature=receipt?.signature_b64;
 if(!request||typeof request!=="object"||!pay||typeof pay!=="object"||
    typeof signature!=="string"||!signature||
    typeof peerId!=="string"||!peerId||typeof snapshotDigest!=="string"||!snapshotDigest||
    typeof publicKeyPem!=="string"||!publicKeyPem)throw Error("missing GCI receipt binding");
 const exact=["binding","challenge","feature","peer_id","phase_commitment","request_digest",
 "schema","snapshot_digest","task_id","value"].sort();
 if(JSON.stringify(Object.keys(pay).sort())!==JSON.stringify(exact)||
    pay.schema!==receiptSchema||pay.peer_id!==peerId||
    pay.snapshot_digest!==snapshotDigest||
    pay.request_digest!==digest(request)||pay.task_id!==request.task_id||
    pay.feature!==request.feature||pay.phase_commitment!==request.phase_commitment||
    pay.challenge!==request.challenge||
    canonical(pay.binding)!==canonical(request.binding))throw Error("wrong signed request or source binding");
 if(!["parity","low2"].includes(pay.feature)||
    !Number.isInteger(pay.value)||pay.value<0||
    pay.value>(pay.feature==="parity"?1:3))throw Error("invalid signed feature value");
 if(!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(signature))
    throw Error("noncanonical base64 signature");
 let verified=false;
 try{
  const key=crypto.createPublicKey(publicKeyPem);
  if(key.asymmetricKeyType!=="ec")throw Error("not EC public key");
  verified=crypto.verify("sha256",Buffer.from(canonical(pay),"utf8"),
    key,Buffer.from(signature,"base64"));
 }catch{verified=false;}
 if(!verified)throw Error("GCI receipt signature invalid");
 return {schema:"IWI-004/GCI-sample-projection-v1",receiptDigest:digest(receipt),
  requestDigest:digest(request),peerId,snapshotDigest,feature:pay.feature,
  value:pay.value,status:"SIGNED_FEATURE_SAMPLE_ONLY",
  entailsUniversalTransition:false,proposedLawDomainReduction:null,
  trustLimit:"requires separate verified leaf/CA/SAN, mTLS transcript, and receiver honesty; no law coverage"};
}
module.exports={canonical,digest,verifyGciSample,receiptSchema};
