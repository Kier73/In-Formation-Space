"use strict";
/* Mutation tests over downloaded, historical, workflow-attested GCI-005 data.
 * This file is intentionally not runnable without the REAL prior artifacts.
 */
const fs=require("node:fs");
const assert=require("node:assert/strict");
const {verifyHistorical,digest}=require("./verify_historical_projection.js");
const copy=x=>JSON.parse(JSON.stringify(x));
const reseal=x=>{const body={...x};delete body.report_digest;x.report_digest=digest(body);};
const propagateSignedSource=d=>{
  reseal(d[2]);
  d[0].source_signed_report_digest=d[2].report_digest;
  d[3].gci005_report_digest=d[2].report_digest;
  reseal(d[3]);
  d[0].source_blind_audit_digest=d[3].report_digest;
};
if(require.main===module){
  if(process.argv.length!==6)throw Error(
    "usage: node test_historical_artifact.js BRIDGE PUBLIC QUORUM BLIND");
  const originals=process.argv.slice(2).map(x=>JSON.parse(fs.readFileSync(x,"utf8")));
  assert.equal(verifyHistorical(...originals).verified,true);
  const experiments=[
    ["promoted historical authority",d=>{d[0].current_authority=true;}],
    ["rewritten old source commit",d=>{d[0].source_commit="0".repeat(40);}],
    ["wrong private-phase scope",d=>{d[0].private_phase_consumed=true;}],
    ["altered realization value",d=>{d[0].rounds[0].allowed_intention_values=[1-d[0].rounds[0].allowed_intention_values[0]];}],
    ["falsified remaining phase count",d=>{d[0].rounds[0].prior_phase_count=0;}],
    ["resealed forged peer signature",d=>{
      d[2].rounds[0].receipts[0].signature_b64="AA==";propagateSignedSource(d);
    }],
    ["resealed false signed parity",d=>{
      const p=d[2].rounds[0].receipts[0].payload;p.value=1-p.value;
      propagateSignedSource(d);
    }],
    ["wrong ground source",d=>{d[0].source_ground_fingerprint="a".repeat(64);}],
    ["tampered independently recorded audit",d=>{d[3].rounds[0].peer_readings=[1,1];}],
    ["changed expired credential timestamp",d=>{d[0].evidence_validation_time="2027-01-01T00:00:00+00:00";}],
  ];
  const results=[];
  for(const [name,mutation]of experiments){
    const d=originals.map(copy);
    mutation(d);
    assert.throws(()=>verifyHistorical(...d),undefined,
                  "invalid historical evidence was accepted: "+name);
    results.push(name);
  }
  process.stdout.write(JSON.stringify({real_source_verified:true,
    deliberate_mutations_rejected:results.length,mutations:results},null,2)+"\n");
}
