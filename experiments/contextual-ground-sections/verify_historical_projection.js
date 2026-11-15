"use strict";
/* CGS-007 secondary implementation: independent Node mathematical and
 * receipt-signature reconstruction. Does not execute Python producer code.
 * It is NOT independent issuer trust or GitHub provenance verification.
 */
const fs=require("node:fs");
const crypto=require("node:crypto");

function refuse(reason){throw Error("CGS-007 secondary verifier refused: "+reason);}
function check(x,msg){if(!x)refuse(msg);}
function sortedJSON(x){
  if(Array.isArray(x))return "["+x.map(sortedJSON).join(",")+"]";
  if(x!==null&&typeof x==="object"){
    const keys=Object.keys(x).sort();
    return "{"+keys.map(k=>JSON.stringify(k)+":"+sortedJSON(x[k])).join(",")+"}";
  }
  return JSON.stringify(x);
}
const digest=x=>crypto.createHash("sha256").update(sortedJSON(x)).digest("hex");
function sealed(x){
  check(x&&typeof x==="object"&&typeof x.report_digest==="string","missing seal");
  const clone={...x};delete clone.report_digest;
  check(digest(clone)===x.report_digest,"altered seal");
}
function future(s,k){
  let m=[5,1],out=[1,0];
  // affine pair composition f(g(x)) modulo 8
  function then(f,g){return [(f[0]*g[0])%8,(f[0]*g[1]+f[1])%8];}
  while(k>0){if(k%2===1)out=then(m,out);m=then(m,m);k=Math.floor(k/2);}
  return (out[0]*s+out[1])%8;
}
function yParity(s){
  return (3*future(s,1000000000000137)+11)%2;
}
function verifyHistorical(bridge,publicSource,quorum,blind){
  check(bridge.schema==="ifs.cgs007-historical-observer-constraint/0.1",
        "unexpected bridge schema");
  sealed(publicSource);sealed(quorum);sealed(blind);
  const original=(quorum.rounds||[]);
  check(original.length===2 && bridge.rounds?.length===2,"missing paired rounds");
  check(bridge.source_signed_report_digest===quorum.report_digest &&
        bridge.source_public_digest===publicSource.report_digest &&
        bridge.source_ground_fingerprint===quorum.binding?.ground_fingerprint &&
        bridge.source_intention_digest===quorum.binding?.source_digest &&
        bridge.source_blind_audit_digest===blind.report_digest &&
        blind.gci005_report_digest===quorum.report_digest &&
        blind.source_digest===quorum.binding?.source_digest &&
        bridge.current_authority===false &&
        bridge.private_phase_consumed===false,
        "bridge source binding or admission status differs");
  check(bridge.historical_signature_check==="passed" &&
        bridge.source_run===43616685083 &&
        bridge.source_commit==="90e719ae6efab12107ee8de2b77afe5e73dd35b2",
        "unrecognized historical source");
  const eventTime=new Date(bridge.evidence_validation_time);
  check(!Number.isNaN(eventTime.getTime()) &&
        eventTime.toISOString()==="2026-11-14T16:54:29.000Z",
        "invalid or unpinned historical validation time");
  const threshold=publicSource.observer?.value;
  check(Number.isInteger(threshold) && [0,1].includes(threshold) &&
        bridge.initial_threshold_bit===threshold,
        "threshold mismatch");
  const initial=Array.from({length:8},(_,i)=>i).filter(i=>Number(i>=4)===threshold);
  const claimed=[];
  for(let i=0;i<2;i++){
    const round=original[i],given=bridge.rounds[i];
    check(Array.isArray(round.receipts)&&round.receipts.length===2 &&
          Array.isArray(round.discovery)&&round.discovery.length===2,
          "missing signed peer records");
    sealed(quorum); // cross-check before any use of included records
    const ca=new crypto.X509Certificate(round.ca_certificate_pem);
    check(ca.verify(ca.publicKey),"unverified synthetic CA self signature");
    const start=Date.parse(ca.validFrom),end=Date.parse(ca.validTo);
    check(start<=eventTime.getTime()&&eventTime.getTime()<=end,
          "CA outside historical validation window");
    const results=[],keys=[];
    for(let j=0;j<2;j++){
      const receipt=round.receipts[j],discovery=round.discovery[j];
      check(receipt.peer_id===discovery.peer_id &&
            receipt.peer_id===["observer-a","observer-b"][j],
            "peer identity mismatch");
      const cert=new crypto.X509Certificate(discovery.certificate_pem);
      check(cert.issuer===ca.subject && cert.verify(ca.publicKey),
            "unverified leaf signature");
      const leafStart=Date.parse(cert.validFrom),leafEnd=Date.parse(cert.validTo);
      check(leafStart<=eventTime.getTime() && eventTime.getTime()<=leafEnd,
            "leaf outside historical validation window");
      check(typeof discovery.dns==="string" &&
            cert.subjectAltName?.includes("DNS:"+discovery.dns),
            "leaf SAN mismatch");
      const pem=cert.publicKey.export({type:"spki",format:"pem"}).toString();
      keys.push(pem);
      const p=receipt.payload,q=receipt.request;
      check(p.peer_id===discovery.peer_id &&
            p.feature==="parity" && p.task_id==="far-y-parity" &&
            p.binding?.ground_fingerprint===quorum.binding.ground_fingerprint &&
            p.phase_commitment===publicSource.phase_commitment &&
            p.challenge===q.challenge &&
            p.request_digest===digest(q) &&
            p.snapshot_digest===discovery.snapshot_digest &&
            p.value!==true && p.value!==false &&
            Number.isInteger(p.value) && [0,1].includes(p.value),
            "signed payload binding mismatch");
      const signature=Buffer.from(receipt.signature_b64,"base64");
      check(crypto.verify("sha256",Buffer.from(sortedJSON(p)),cert.publicKey,signature),
            "receipt signature invalid");
      results.push(p.value);
    }
    check(keys[0]!==keys[1],"not independently keyed receivers");
    check(round.receipts[0].request.challenge===round.receipts[1].request.challenge,
          "paired challenges differ");
    const status=i===0?"ADMITTED_AGREEMENT":"REFUSED_DISAGREEMENT";
    check(round.scenario===["honest-agreement","signed-false-reading"][i] &&
          blind.rounds?.[i]?.verdict===status &&
          JSON.stringify(blind.rounds[i].peer_readings)===JSON.stringify(results),
          "original phase-blind audit does not bind signed readings");
    check(given.receipt_status===status &&
          round.verdict.status===status &&
          ((results[0]===results[1])===(i===0)),
          "signed conflict was incorrectly admitted");
    const filtered=i===0?initial.filter(x=>x%2===results[0]):initial;
    const values=[...new Set(filtered.map(yParity))].sort((a,b)=>a-b);
    check(given.prior_phase_count===initial.length &&
          given.measurement_used===(i===0) &&
          given.current_execution_authorized===false &&
          JSON.stringify(given.admissible_phase_candidates)===JSON.stringify(filtered) &&
          JSON.stringify(given.allowed_intention_values)===JSON.stringify(values) &&
          given.mathematically_determined===(values.length===1),
          "phase-blind intention projection mismatch");
    claimed.push({scenario:round.scenario,status,remaining:filtered.length,
      allowed_y_parity:values});
  }
  return {verified:true,phase_witness_read:false,live_authority:false,
    source_run:bridge.source_run,rounds:claimed};
}
module.exports={verifyHistorical,sortedJSON,digest,future,yParity};
if(require.main===module){
  if(process.argv.length!==6)refuse("usage: node verify_historical_projection.js BRIDGE PUBLIC QUORUM BLIND");
  const files=process.argv.slice(2).map(x=>JSON.parse(fs.readFileSync(x,"utf8")));
  process.stdout.write(JSON.stringify(verifyHistorical(...files),null,2)+"\n");
}
