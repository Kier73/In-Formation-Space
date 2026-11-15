"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const os=require("node:os");
const path=require("node:path");
const crypto=require("node:crypto");
const {spawnSync}=require("node:child_process");
const p=require("./partial_ground.js");
const q=require("./evidence_acquisition.js");
const c=require("./context_coverage.js");
const clone=x=>JSON.parse(JSON.stringify(x));
const contract={actionSetComplete:true,outputReadFaithful:true,sourceControlled:true,
  stateSetComplete:true,stationaryWithinEpoch:true};
function fixtures(){
 const base=p.fixtures.remembered;
 const alpha=c.exact(q.restrict(base,"t:0:1",2));
 const beta=c.exact(q.restrict(base,"t:0:1",3));
 const pair=crypto.generateKeyPairSync("ed25519");
 const publicKey=pair.publicKey.export({type:"spki",format:"pem"});
 const privateKey=pair.privateKey;
 const scope=(model,epoch,runId,context="lab/context-A")=>({
  context,epoch,hostId:"controlled-host-a",revision:"ground-r1",
  runId,tableFingerprint:c.fingerprint(model)});
 return {base,alpha,beta,publicKey,privateKey,scope};
}
function certify(f,model,epoch,runId,context="lab/context-A"){
 const scope=f.scope(model,epoch,runId,context);
 const bundle=c.collect(model,scope,f.privateKey);
 return c.verifyBundle(f.base,scope,bundle,f.publicKey,contract);
}
test("complete finite coverage signs and checks every state-action and output cell",()=>{
 const f=fixtures(),scope=f.scope(f.alpha,1,"test-run-1");
 const signed=c.collect(f.alpha,scope,f.privateKey);
 const expected=f.alpha.next.length*f.alpha.n+f.alpha.n;
 assert.equal(signed.receipts.length,expected);
 const verified=c.verifyBundle(f.base,scope,signed,f.publicKey,contract);
 assert.equal(verified.requiredReceipts,expected);
 assert.equal(verified.verifiedReceipts,expected);
 assert.equal(verified.status,"CONDITIONAL_COMPLETE_FINITE_COVERAGE");
 assert.equal(verified.nativeGroundAdmitted,false);
 assert.equal(verified.externalEffectsAuthorized,false);
 assert.deepEqual(verified.proposedModel,f.alpha);
 const result=p.solve(verified.proposedModel,2);
 assert.equal(result.minimumWorstCase,2);
 assert.equal(p.verify(verified.proposedModel,result).verified,true);
});
test("the exact closed state/action/output enumeration rejects any missing, duplicate or reordered cell",()=>{
 const f=fixtures(),scope=f.scope(f.alpha,1,"test-run-2");
 const signed=c.collect(f.alpha,scope,f.privateKey);
 const lost=clone(signed);lost.receipts.pop();
 assert.throws(()=>c.verifyBundle(f.base,scope,lost,f.publicKey,contract));
 const duplicate=clone(signed);duplicate.receipts[3]=duplicate.receipts[2];
 assert.throws(()=>c.verifyBundle(f.base,scope,duplicate,f.publicKey,contract));
 const swapped=clone(signed);[swapped.receipts[0],swapped.receipts[1]]=[swapped.receipts[1],swapped.receipts[0]];
 assert.throws(()=>c.verifyBundle(f.base,scope,swapped,f.publicKey,contract));
});
test("correctly signed reports cannot be moved to a different context or epoch",()=>{
 const f=fixtures(),scope=f.scope(f.alpha,3,"test-run-3");
 const signed=c.collect(f.alpha,scope,f.privateKey);
 for(const newScope of [
  {...scope,context:"lab/context-B"},
  {...scope,epoch:4},
  {...scope,runId:"new-run"},
  {...scope,revision:"ground-r2"}
 ])assert.throws(()=>c.verifyBundle(f.base,newScope,signed,f.publicKey,contract));
});
test("tampered signed values, wrong identity or wrong complete-law fingerprint fail closed",()=>{
 const f=fixtures(),scope=f.scope(f.alpha,1,"test-run-4");
 const signed=c.collect(f.alpha,scope,f.privateKey);
 const changed=clone(signed);changed.receipts[8].payload.value=0;
 assert.throws(()=>c.verifyBundle(f.base,scope,changed,f.publicKey,contract));
 const outsider=crypto.generateKeyPairSync("ed25519");
 assert.throws(()=>c.verifyBundle(f.base,scope,signed,
  outsider.publicKey.export({type:"spki",format:"pem"}),contract));
 const incorrect=c.collect(f.beta,f.scope(f.beta,1,"test-run-4"),f.privateKey);
 assert.throws(()=>c.verifyBundle(f.base,scope,incorrect,f.publicKey,contract));
});
test("absence of any independent coverage premise refuses complete-law status",()=>{
 const f=fixtures(),scope=f.scope(f.alpha,1,"test-run-5");
 const signed=c.collect(f.alpha,scope,f.privateKey);
 for(const key of Object.keys(contract)){
  assert.throws(()=>c.verifyBundle(f.base,scope,signed,f.publicKey,{...contract,[key]:false}));
 }
 assert.throws(()=>c.verifyBundle(f.base,scope,signed,f.publicKey,{}));
});
test("two fresh signed processes with equal scoped tables yield only conditional continuity",()=>{
 const f=fixtures();
 const before=certify(f,f.alpha,1,"pre-restart");
 const after=certify(f,f.alpha,2,"post-restart");
 const result=c.compareEpochs(before,after);
 assert.equal(result.status,"CONDITIONALLY_CONSISTENT_ACROSS_EPOCHS");
 assert.equal(result.unknownBetweenEpochs,true);
 assert.equal(result.unknownFutureEpochs,true);
 assert.equal(result.independentPhysicalAttestation,false);
});
test("same signing identity with contradictory law after restart is refused",()=>{
 const f=fixtures();
 const before=certify(f,f.alpha,1,"before");
 const changed=certify(f,f.beta,2,"after");
 const result=c.compareEpochs(before,changed);
 assert.equal(result.status,"REFUSED_TRANSITION_DISAGREEMENT");
 // A previously valid epoch-one certificate cannot be used as epoch-two evidence.
 const oldScope=f.scope(f.alpha,1,"before");
 assert.throws(()=>c.verifyBundle(f.base,{...oldScope,epoch:2},
  c.collect(f.alpha,oldScope,f.privateKey),f.publicKey,contract));
});
test("context change always requires separate coverage and prevents automatic carry",()=>{
 const f=fixtures(),before=certify(f,f.alpha,1,"context-A","lab/context-A");
 const after=certify(f,f.alpha,2,"context-B","lab/context-B");
 assert.equal(c.compareEpochs(before,after).status,"REFUSED_EPOCH_SCOPE");
});
test("two complete models match all retained evidence but differ on requested realization",()=>{
 const f=fixtures();
 const witness=c.indistinguishableCountermodels(f.base,["o:0","o:2","t:1:2"],[0,3]);
 assert.equal(witness.retainedObservationsEquivalent,true);
 assert.deepEqual(witness.allowedValues,[2,3]);
 assert.equal(witness.outcomeA.goal,true);
 assert.equal(witness.outcomeB.goal,false);
 assert.equal(witness.outcomeA.terminalState,0);
 assert.equal(witness.outcomeB.terminalState,6);
 assert.throws(()=>c.indistinguishableCountermodels(f.base,["t:0:1"],[0,3]));
});
test("any finite observed time prefix admits a later divergent process",()=>{
 for(const horizon of [0,1,2,10,100,1000000]){
  const w=c.finitePrefixCounterexample(horizon);
  assert.equal(w.agreeOnEveryObservedIndex,true);
  assert.equal(w.firstPossibleDivergence,horizon);
  assert.notEqual(w.stableSystemAtNext,w.changedSystemAtNext);
 }
});
test("two actual OS child processes produce separately checkable signed tables",()=>{
 const f=fixtures(),dir=fs.mkdtempSync(path.join(os.tmpdir(),"iwi005-"));
 const keyFile=path.join(dir,"signer.pem");
 const sourceFile=path.join(dir,"manifest.json");
 try{
  fs.writeFileSync(keyFile,f.privateKey.export({type:"pkcs8",format:"pem"}));
  function run(model,epoch,label){
   const scope=f.scope(model,epoch,label);
   fs.writeFileSync(sourceFile,JSON.stringify({model,scope}));
   const proc=spawnSync(process.execPath,[path.join(__dirname,"coverage_worker.js"),sourceFile,keyFile],
    {encoding:"utf8",timeout:15000});
   if(proc.status!==0)throw Error("worker failed: "+proc.stderr);
   const output=JSON.parse(proc.stdout);
   assert.equal(output.schema,"IWI-005/test-worker-output");
   const verified=c.verifyBundle(f.base,scope,output.bundle,f.publicKey,contract);
   return {pid:output.producerPid,verified};
  }
  const first=run(f.alpha,1,"process-one");
  const second=run(f.alpha,2,"process-two");
  assert.notEqual(first.pid,second.pid);
  assert.equal(c.compareEpochs(first.verified,second.verified).status,
   "CONDITIONALLY_CONSISTENT_ACROSS_EPOCHS");
  const divergent=run(f.beta,3,"process-three");
  assert.equal(c.compareEpochs(second.verified,divergent.verified).status,
   "REFUSED_TRANSITION_DISAGREEMENT");
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
