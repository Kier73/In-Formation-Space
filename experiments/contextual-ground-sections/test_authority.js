"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const a=require("./authority.js");
const cp=x=>JSON.parse(JSON.stringify(x));
function context(){
  const root1=a.generateIdentity(),root2=a.generateIdentity();
  const receiver=a.generateIdentity();
  const alice=a.generateIdentity(),bob=a.generateIdentity(),charlie=a.generateIdentity();
  const trust={schema:"ifs.cgs008-trust/0.1",realm:"research-cgs008",
    ground:"f".repeat(64),threshold:2,
    roots:[a.publicPEM(root1.publicKey),a.publicPEM(root2.publicKey)],
    receiver:a.publicPEM(receiver.publicKey)};
  const grant=(id,key)=>({observer:id,public_key:a.publicPEM(key.publicKey),features:["parity"]});
  const p1=a.signed({schema:"ifs.cgs008-policy/0.1",realm:trust.realm,ground:trust.ground,
    version:1,previous:a.ZERO,valid_from:100,expires:250,
    grants:[grant("alice",alice),grant("bob",bob)],revoked:[]},[root1,root2]);
  const p2=a.signed({schema:"ifs.cgs008-policy/0.1",realm:trust.realm,ground:trust.ground,
    version:2,previous:a.digest(p1.body),valid_from:230,expires:600,
    grants:[grant("alice",alice),grant("charlie",charlie)],revoked:["bob"]},[root1,root2]);
  const cp0=a.bootstrap(trust,receiver);
  const cp1=a.advance(trust,[p1],cp0,receiver,150);
  const req1=a.challenge(trust,[p1],cp1,receiver,160,"aa".repeat(16));
  const obs1=[a.observe(req1,"alice",1,alice),a.observe(req1,"bob",1,bob)];
  const round1=a.consume(trust,[p1],cp1,req1,obs1,receiver,161);
  const post1=round1.next_checkpoint;
  const cp2=a.advance(trust,[p1,p2],post1,receiver,260);
  const req2=a.challenge(trust,[p1,p2],cp2,receiver,261,"bb".repeat(16));
  const obs2=[a.observe(req2,"alice",1,alice),a.observe(req2,"charlie",0,charlie)];
  return {root1,root2,receiver,alice,bob,charlie,trust,p1,p2,cp0,cp1,
    req1,obs1,round1,post1,cp2,req2,obs2};
}
const refuses=(fn)=>assert.throws(fn,/CGS-008 refused/);

test("two independently generated Ed25519 root signatures and real active observer quorum",()=>{
  const x=context();
  assert.notEqual(a.keyId(x.trust.roots[0]),a.keyId(x.trust.roots[1]));
  assert.equal(x.round1.status,"ADMITTED_AGREEMENT");
  assert.equal(x.round1.returned_value,1);
  assert.equal(x.post1.body.counter,1);
  assert.equal(a.verifyCheckpoint(x.trust,x.post1),a.digest(x.post1.body));
  assert.equal(x.cp2.body.policy_version,2);
  assert.equal(x.cp2.body.last_time,260);
  const round2=a.consume(x.trust,[x.p1,x.p2],x.cp2,x.req2,x.obs2,x.receiver,263);
  assert.equal(round2.status,"REFUSED_DISAGREEMENT");
  assert.equal(round2.returned_value,null);
  assert.equal(round2.next_checkpoint.body.counter,2);
  refuses(()=>a.consume(x.trust,[x.p1,x.p2],round2.next_checkpoint,
    x.req2,x.obs2,x.receiver,264));
});

test("historically signed observation remains inspectable but has no present authority",()=>{
  const x=context();
  const evidence=a.historical(x.trust,[x.p1,x.p2],1,x.req1,x.obs1);
  assert.equal(evidence.historical_signature_valid,true);
  assert.equal(evidence.current_authority,false);
  assert.equal(evidence.event_time_proven,false);
  refuses(()=>a.consume(x.trust,[x.p1,x.p2],x.cp2,x.req1,x.obs1,x.receiver,263));
  refuses(()=>a.consume(x.trust,[x.p1,x.p2],x.cp2,x.req2,
    [a.observe(x.req2,"alice",1,x.alice),a.observe(x.req2,"bob",1,x.bob)],
    x.receiver,263));
});

test("signed policy revisions enforce rollback and fork refusal after receiver checkpoint",()=>{
  const x=context();
  refuses(()=>a.verifyLedger(x.trust,[x.p1],x.cp2));
  refuses(()=>a.advance(x.trust,[x.p1],x.cp2,x.receiver,265));
  const fork=cp(x.p2);fork.body.expires=620;
  fork.signatures=x.p2.signatures;
  refuses(()=>a.advance(x.trust,[x.p1,fork],x.cp2,x.receiver,265));
  const validFork=a.signed({...x.p2.body,expires:620},[x.root1,x.root2]);
  refuses(()=>a.advance(x.trust,[x.p1,validFork],x.cp2,x.receiver,265));
});

test("single root, duplicated root, mismatched signature and bogus identity fail",()=>{
  const x=context();
  const one=a.signed(x.p2.body,[x.root1]);
  const dupe=a.signed(x.p2.body,[x.root1,x.root1]);
  refuses(()=>a.verifyLedger(x.trust,[x.p1,one]));
  refuses(()=>a.verifyLedger(x.trust,[x.p1,dupe]));
  const altered=cp(x.p1);altered.signatures[0].signature=Buffer.alloc(64).toString("base64");
  refuses(()=>a.verifyLedger(x.trust,[altered]));
  const unknown=a.signed(x.p2.body,[x.root1,x.alice]);
  refuses(()=>a.verifyLedger(x.trust,[x.p1,unknown]));
  const trust=cp(x.trust);trust.roots[1]=trust.roots[0];
  refuses(()=>a.validateTrust(trust));
});

test("unsigned policy grants cannot replace one of two trusted signatures",()=>{
  const x=context();
  const policy=cp(x.p2);policy.body.grants[1].observer="bob";
  refuses(()=>a.verifyLedger(x.trust,[x.p1,policy]));
  const policy2=a.signed({...x.p2.body,revoked:[]},[x.root1,x.root2]);
  refuses(()=>a.verifyLedger(x.trust,[x.p1,policy2]));
  const policy3=a.signed({...x.p2.body,grants:[x.p2.body.grants[0],
    {...x.p2.body.grants[1],public_key:x.trust.roots[0]}]},[x.root1,x.root2]);
  refuses(()=>a.verifyLedger(x.trust,[x.p1,policy3]));
});

test("replay, cross-ground, cross-nonce and phase substitution are rejected",()=>{
  const x=context();
  const wrong=cp(x.obs2);wrong[0].body.value=0;
  refuses(()=>a.consume(x.trust,[x.p1,x.p2],x.cp2,x.req2,wrong,x.receiver,263));
  const badContext=cp(x.req2);badContext.body.ground="0".repeat(64);
  refuses(()=>a.consume(x.trust,[x.p1,x.p2],x.cp2,badContext,x.obs2,x.receiver,263));
  const other=a.challenge(x.trust,[x.p1,x.p2],x.cp2,x.receiver,261,"cc".repeat(16));
  refuses(()=>a.consume(x.trust,[x.p1,x.p2],x.cp2,other,x.obs2,x.receiver,263));
  refuses(()=>a.consume(x.trust,[x.p1,x.p2],x.cp2,x.req2,
    [x.obs2[0],x.obs2[0]],x.receiver,263));
  refuses(()=>a.consume(x.trust,[x.p1,x.p2],x.cp2,x.req2,x.obs2,x.receiver,280));
  refuses(()=>a.consume(x.trust,[x.p1,x.p2],x.cp2,x.req2,x.obs2,x.receiver,220));
  refuses(()=>a.advance(x.trust,[x.p1,x.p2],x.cp2,x.receiver,250));
});

test("a signed checkpoint survives serialization but outside anchor is necessary",()=>{
  const x=context();
  const durable=cp(x.cp2);
  const digest=a.verifyCheckpoint(x.trust,durable);
  assert.equal(digest,a.digest(x.cp2.body));
  refuses(()=>a.verifyLedger(x.trust,[x.p1],durable));
  const tampered=cp(durable);tampered.body.counter=0;
  refuses(()=>a.verifyCheckpoint(x.trust,tampered));
  // Real rollback protection requires loading the *latest* durable checkpoint.
  // An older valid checkpoint still verifies absent a receiver/external anchor.
  assert.doesNotThrow(()=>a.verifyCheckpoint(x.trust,x.post1));
});

test("valid Ed25519 observation agreement is not independently verified sensor truth",()=>{
  const x=context();
  const forgedTruth=[a.observe(x.req2,"alice",0,x.alice),
    a.observe(x.req2,"charlie",0,x.charlie)];
  const result=a.consume(x.trust,[x.p1,x.p2],x.cp2,x.req2,forgedTruth,x.receiver,263);
  assert.equal(result.status,"ADMITTED_AGREEMENT");
  assert.match(result.scope,/not verified sensor truth/);
  assert.equal(result.returned_value,0);
});
