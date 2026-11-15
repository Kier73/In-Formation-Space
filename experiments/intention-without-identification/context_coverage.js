"use strict";
/* IWI-005: finite closed-world coverage conditional on explicit physical/source premises.
 * A full signed table is an authenticated CLAIM; this does not prove observer honesty,
 * faithful state injection, stationary dynamics, or actual E-CPU/VGI authorization.
 * Cryptographic receipts and context/epoch equality are checked independently.
 */
const crypto=require("node:crypto");
const partial=require("./partial_ground.js");
const schema="IWI-005/finite-coverage-receipt-v1";
const ascii=/^[\x20-\x7e]*$/;
function canonical(value,depth=0){
 if(depth>32)throw Error("max JSON depth");
 if(value===null)return "null";
 if(typeof value==="string"){
  if(!ascii.test(value))throw Error("non-ASCII text outside this exact canonical profile");
  return JSON.stringify(value);
 }
 if(typeof value==="number"){
  if(!Number.isSafeInteger(value))throw Error("not a safe integer");
  return String(value);
 }
 if(typeof value==="boolean")return value?"true":"false";
 if(Array.isArray(value))return "["+value.map(v=>canonical(v,depth+1)).join(",")+"]";
 if(value&&typeof value==="object"){
  const keys=Object.keys(value).sort();
  if(keys.length>128||keys.some(k=>!ascii.test(k)))throw Error("invalid object key");
  return "{"+keys.map(k=>JSON.stringify(k)+":"+canonical(value[k],depth+1)).join(",")+"}";
 }
 throw Error("unsupported JSON type");
}
function sha(x){return crypto.createHash("sha256").update(canonical(x),"utf8").digest("hex");}
function exact(model){
 const m=partial.validate(model);
 if(m.next.some(row=>row.some(d=>d.length!==1))||m.output.some(d=>d.length!==1))
  throw Error("not a complete deterministic law");
 return {n:m.n,start:m.start,goal:m.goal,
  next:m.next.map(row=>row.map(x=>x[0])),output:m.output.map(x=>x[0])};
}
function fingerprint(model){return sha(exact(model));}
function scopeCheck(scope){
 const expected=["context","epoch","hostId","revision","runId","tableFingerprint"];
 if(!scope||Object.keys(scope).sort().join(",")!==expected.join(",")||
    !Number.isSafeInteger(scope.epoch)||scope.epoch<0||
    !["context","hostId","revision","runId"].every(k=>typeof scope[k]==="string"&&scope[k].length>0&&ascii.test(scope[k]))||
    typeof scope.tableFingerprint!=="string"||!/^[a-f0-9]{64}$/.test(scope.tableFingerprint))
  throw Error("invalid coverage scope");
 return scope;
}
function fullKeys(m){
 const keys=[];
 for(let a=0;a<m.next.length;a++)for(let s=0;s<m.n;s++)keys.push("t:"+a+":"+s);
 for(let s=0;s<m.n;s++)keys.push("o:"+s);
 return keys;
}
function cellValue(m,key){
 const part=key.split(":");
 return part[0]==="t"?m.next[+part[1]][+part[2]]:m.output[+part[1]];
}
function collect(model,scope,privateKey){
 const m=exact(model);
 scopeCheck(scope);
 if(scope.tableFingerprint!==fingerprint(model))throw Error("the declared table fingerprint is wrong");
 const receipt=fullKeys(m).map((cell,index)=>{
  const payload={schema,scope,index,cell,value:cellValue(m,cell),
   nonce:scope.runId+":"+index,kind:"controlled-state-action-sample"};
  return {payload,signature:crypto.sign(null,Buffer.from(canonical(payload),"utf8"),privateKey).toString("base64")};
 });
 return {schema:"IWI-005/coverage-bundle-v1",scope,receipts:receipt};
}
function contractCheck(contract){
 const expected=["actionSetComplete","outputReadFaithful","sourceControlled","stateSetComplete","stationaryWithinEpoch"];
 if(!contract||Object.keys(contract).sort().join(",")!==expected.join(",")||
   !expected.every(k=>contract[k]===true))throw Error("coverage contract missing critical premise");
 return true;
}
function verifyBundle(baseModel,expectedScope,bundle,publicKeyPem,contract){
 const m=partial.validate(baseModel);scopeCheck(expectedScope);contractCheck(contract);
 if(!bundle||bundle.schema!=="IWI-005/coverage-bundle-v1"||
  canonical(bundle.scope)!==canonical(expectedScope)||!Array.isArray(bundle.receipts))
  throw Error("unbound or replayed bundle");
 const keys=fullKeys(m);
 if(bundle.receipts.length!==keys.length)throw Error("not a complete finite cell cover");
 let pub;
 try{pub=crypto.createPublicKey(publicKeyPem);if(pub.asymmetricKeyType!=="ed25519")throw Error("wrong key type");}
 catch{throw Error("invalid trusted key");}
 const next=m.next.map(row=>row.map(()=>null)),output=m.output.map(()=>null);
 for(let i=0;i<keys.length;i++){
  const rec=bundle.receipts[i],r=rec?.payload;
  if(!r||rec.signature===undefined||typeof rec.signature!=="string"||
    Object.keys(r).sort().join(",")!=="cell,index,kind,nonce,schema,scope,value"||
    r.schema!==schema||r.kind!=="controlled-state-action-sample"||
    r.cell!==keys[i]||r.index!==i||r.nonce!==expectedScope.runId+":"+i||
    canonical(r.scope)!==canonical(expectedScope)||!Number.isSafeInteger(r.value))
   throw Error("coverage receipt missing/wrong cell or context");
  let good=false;
  if(/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(rec.signature)){
   try{
    good=crypto.verify(null,Buffer.from(canonical(r),"utf8"),
      pub,Buffer.from(rec.signature,"base64"));
   }catch{good=false;}
  }
  if(!good)throw Error("invalid signed coverage receipt");
  const kind=keys[i].split(":");
  if(kind[0]==="t"){
   const a=+kind[1],s=+kind[2];
   if(!m.next[a][s].includes(r.value))throw Error("transition outside Ground domain");
   next[a][s]=r.value;
  }else{
   const s=+kind[1];
   if(!m.output[s].includes(r.value))throw Error("output outside Ground domain");
   output[s]=r.value;
  }
 }
 const proposedModel={n:m.n,start:m.start,goal:m.goal,next,output};
 if(fingerprint(proposedModel)!==expectedScope.tableFingerprint)
   throw Error("different source table fingerprint");
 return {schema:"IWI-005/conditional-coverage-v1",scope:expectedScope,
  status:"CONDITIONAL_COMPLETE_FINITE_COVERAGE",
  requiredReceipts:keys.length,verifiedReceipts:keys.length,
  proposedModel,modelFingerprint:fingerprint(proposedModel),
  coveragePremises:"closed states/actions + controlled source state + faithful output + stationary within pinned epoch; assumptions, not empirical proofs",
  nativeGroundAdmitted:false,externalEffectsAuthorized:false};
}
function compareEpochs(first,second){
 if(first?.status!=="CONDITIONAL_COMPLETE_FINITE_COVERAGE"||
    second?.status!=="CONDITIONAL_COMPLETE_FINITE_COVERAGE")
  return {status:"REFUSED_UNVERIFIED_EPOCH"};
 if(first.scope.context!==second.scope.context||
    first.scope.hostId!==second.scope.hostId||
    first.scope.revision!==second.scope.revision||
    first.scope.epoch>=second.scope.epoch||
    first.scope.runId===second.scope.runId)
  return {status:"REFUSED_EPOCH_SCOPE"};
 if(first.scope.tableFingerprint!==second.scope.tableFingerprint||
   canonical(first.proposedModel)!==canonical(second.proposedModel))
  return {status:"REFUSED_TRANSITION_DISAGREEMENT"};
 return {status:"CONDITIONALLY_CONSISTENT_ACROSS_EPOCHS",
  earlier: first.scope.epoch,later:second.scope.epoch,
  matchedCompleteTable:first.modelFingerprint,
  unknownBetweenEpochs:true,unknownFutureEpochs:true,
  independentPhysicalAttestation:false};
}
function indistinguishableCountermodels(base,observedCells,sequence){
 const m=partial.validate(base);
 if(!Array.isArray(observedCells)||!Array.isArray(sequence))throw Error("invalid countermodel input");
 const observed=new Set(observedCells);
 const key="t:0:1";
 if(!m.next[0]?.[1]||m.next[0][1].length<2||observed.has(key))throw Error("no unobserved divergent cell");
 const a=m.next[0][1][0],b=m.next[0][1][1];
 function complete(v){
  const next=m.next.map(row=>row.map(d=>d[0])),output=m.output.map(d=>d[0]);
  next[0][1]=v;return{n:m.n,start:m.start,goal:m.goal,next,output};
 }
 const models=[complete(a),complete(b)];
 for(const cell of observed){
  if(!fullKeys(models[0]).includes(cell))throw Error("bad retained cell");
  if(cellValue(models[0],cell)!==cellValue(models[1],cell))
   throw Error("retained observation distinguishes countermodels");
 }
 function replay(model){
  let state=1,trace=[];
  for(const act of sequence){
   if(!Number.isInteger(act)||act<0||act>=model.next.length)throw Error("bad action");
   state=model.next[act][state];trace.push(state);
  }
  return {trace,terminalState:state,goal:model.goal.includes(state)};
 }
 return {unobservedCell:key,allowedValues:[a,b],
  retainedObservationsEquivalent:true,
  candidateA:models[0],candidateB:models[1],
  outcomeA:replay(models[0]),outcomeB:replay(models[1])};
}
function finitePrefixCounterexample(length){
 if(!Number.isInteger(length)||length<0||length>1000000)throw Error("bad horizon");
 // Define two infinite time-varying systems via piecewise transition law:
 // L0(t) = 0 for all t; L1(t) = 0 for t < length, 1 otherwise.
 return {observedPrefixLength:length,agreeOnEveryObservedIndex:true,
  firstPossibleDivergence:length,stableSystemAtNext:0,
  changedSystemAtNext:1,
  claim:"no finite prefix alone certifies stability at unobserved future indices"};
}
module.exports={schema,canonical,sha,exact,fingerprint,scopeCheck,fullKeys,
 collect,contractCheck,verifyBundle,compareEpochs,indistinguishableCountermodels,
 finitePrefixCounterexample};
