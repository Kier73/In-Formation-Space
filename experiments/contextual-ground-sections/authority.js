"use strict";
const crypto = require("node:crypto");
const ZERO = "0".repeat(64);
const PREFIX = Buffer.from("IFS-CGS008-SIGNED\0", "utf8");
const fail = (reason) => { throw new Error("CGS-008 refused: " + reason); };
const check = (condition, reason) => { if (!condition) fail(reason); };
const canonical = (value) => {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") {
    const keys = Object.keys(value).sort();
    return "{" + keys.map(k => JSON.stringify(k) + ":" + canonical(value[k])).join(",") + "}";
  }
  check(value !== undefined && (value === null || typeof value === "boolean" ||
    typeof value === "string" || (Number.isSafeInteger(value))), "non-canonical value");
  return JSON.stringify(value);
};
const digest = (value) => crypto.createHash("sha256").update(canonical(value)).digest("hex");
const publicObject = (pem) => {
  check(typeof pem === "string" && pem.length < 1000, "invalid public key text");
  let key;
  try { key = crypto.createPublicKey(pem); } catch { fail("invalid public key"); }
  check(key.asymmetricKeyType === "ed25519", "only Ed25519 is supported");
  return key;
};
const keyId = (pem) => crypto.createHash("sha256")
  .update(publicObject(pem).export({type:"spki", format:"der"})).digest("hex");
const publicPEM = key => (key.type === "public" ? key : crypto.createPublicKey(key))
  .export({type:"spki", format:"pem"}).toString();
const generateIdentity = () => crypto.generateKeyPairSync("ed25519");
const payload = body => Buffer.concat([PREFIX, Buffer.from(canonical(body))]);
const signature = (body, privateKey) => crypto.sign(null, payload(body), privateKey).toString("base64");
function signed(body, keys) {
  return {body, signatures:keys.map(key=>({key_id:keyId(publicPEM(key.publicKey)),
    signature:signature(body,key.privateKey)})).sort((a,b)=>a.key_id.localeCompare(b.key_id))};
}
function verifySigned(envelope, publics, threshold) {
  check(envelope && typeof envelope === "object" &&
    Object.keys(envelope).sort().join() === "body,signatures" &&
    Array.isArray(envelope.signatures) &&
    Number.isSafeInteger(threshold) && threshold > 0, "signed envelope invalid");
  const allowed = new Map();
  for (const pem of publics) {
    const id = keyId(pem);
    check(!allowed.has(id), "duplicate trust key");
    allowed.set(id, publicObject(pem));
  }
  const seen = new Set();
  for (const s of envelope.signatures) {
    check(s && typeof s.key_id === "string" &&
      typeof s.signature === "string" && allowed.has(s.key_id) &&
      !seen.has(s.key_id), "unknown or duplicated signature");
    seen.add(s.key_id);
    let raw;
    try { raw = Buffer.from(s.signature,"base64"); } catch { fail("bad signature bytes"); }
    check(raw.toString("base64") === s.signature && raw.length === 64 &&
      crypto.verify(null,payload(envelope.body),allowed.get(s.key_id),raw),"signature invalid");
  }
  check(seen.size >= threshold, "insufficient independently keyed signatures");
  return digest(envelope.body);
}
function validateTrust(trust) {
  check(trust && trust.schema === "ifs.cgs008-trust/0.1" &&
    /^[0-9a-f]{64}$/.test(trust.ground) &&
    typeof trust.realm === "string" && trust.realm.length > 0 &&
    Array.isArray(trust.roots) && trust.roots.length >= 2 &&
    trust.threshold === 2 && typeof trust.receiver === "string", "untrusted bootstrap");
  check(new Set(trust.roots.map(keyId)).size === trust.roots.length,
    "trust roots are not distinct");
  check(!trust.roots.some(x=>keyId(x)===keyId(trust.receiver)),
    "receiver and root cannot share key");
  keyId(trust.receiver);
}
function validatePolicy(body,trust,index,previous,prevBody) {
  check(body && body.schema === "ifs.cgs008-policy/0.1" &&
    body.realm===trust.realm && body.ground===trust.ground &&
    body.version===index && body.previous===previous &&
    Number.isSafeInteger(body.valid_from) && Number.isSafeInteger(body.expires) &&
    body.valid_from>=0 && body.valid_from<body.expires &&
    (!prevBody || body.valid_from>=prevBody.valid_from) &&
    Array.isArray(body.grants) && body.grants.length>=2 &&
    Array.isArray(body.revoked) && new Set(body.revoked).size===body.revoked.length,
    "policy epoch, chain, or validity invalid");
  const names=new Set(), ids=new Set();
  for(const g of body.grants){
    check(g && typeof g.observer==="string" && /^[a-z0-9-]{1,48}$/.test(g.observer) &&
      !names.has(g.observer) && Array.isArray(g.features) &&
      g.features.length===1 && g.features[0]==="parity" &&
      typeof g.public_key==="string" && !ids.has(keyId(g.public_key)),
      "invalid observer grant");
    check(!trust.roots.some(x=>keyId(x)===keyId(g.public_key)) &&
      keyId(g.public_key)!==keyId(trust.receiver),
      "observation and authority keys must be separate");
    names.add(g.observer);ids.add(keyId(g.public_key));
  }
  for(const id of body.revoked) {
    check(typeof id==="string" && !names.has(id),"revoked observer cannot be active");
    if(prevBody)check(prevBody.grants.some(g=>g.observer===id),"revocation lacks prior grant");
  }
  if(prevBody){
    for(const g of prevBody.grants)if(!names.has(g.observer))
      check(body.revoked.includes(g.observer),"removed observer must be revoked explicitly");
    for(const g of body.grants){
      const p=prevBody.grants.find(x=>x.observer===g.observer);
      if(p)check(keyId(p.public_key)===keyId(g.public_key),
        "silent observer key rotation refused");
    }
  }
}
function verifyLedger(trust,entries,checkpoint=null) {
  validateTrust(trust);
  check(Array.isArray(entries)&&entries.length>0 && entries.length<=256,
    "empty or unbounded policy log");
  let previous=ZERO,prevBody=null,anchorFound=!checkpoint;
  for(let i=0;i<entries.length;i++){
    const entry=entries[i];
    validatePolicy(entry.body,trust,i+1,previous,prevBody);
    const actual=verifySigned(entry,trust.roots,trust.threshold);
    if(checkpoint && checkpoint.body.policy_version===i+1){
      check(checkpoint.body.policy_digest===actual,"anchored policy fork");
      anchorFound=true;
    }
    previous=actual;prevBody=entry.body;
  }
  check(anchorFound,"receiver's newer policy checkpoint is absent");
  return {entry:entries.at(-1),digest:previous,version:entries.length};
}
function checkpointBody(trust,counter,policyVersion,policyDigest,lastReceipt=ZERO,lastTime=0){
  return {schema:"ifs.cgs008-receiver-checkpoint/0.1",realm:trust.realm,
    ground:trust.ground,counter,policy_version:policyVersion,policy_digest:policyDigest,
    last_receipt:lastReceipt,last_time:lastTime};
}
function verifyCheckpoint(trust,checkpoint){
  check(checkpoint?.body?.schema==="ifs.cgs008-receiver-checkpoint/0.1" &&
    checkpoint.body.realm===trust.realm && checkpoint.body.ground===trust.ground &&
    Number.isSafeInteger(checkpoint.body.counter) && checkpoint.body.counter>=0 &&
    Number.isSafeInteger(checkpoint.body.policy_version) && checkpoint.body.policy_version>=0 &&
    Number.isSafeInteger(checkpoint.body.last_time) && checkpoint.body.last_time>=0 &&
    /^[0-9a-f]{64}$/.test(checkpoint.body.policy_digest) &&
    /^[0-9a-f]{64}$/.test(checkpoint.body.last_receipt),"invalid receiver checkpoint");
  verifySigned(checkpoint,[trust.receiver],1);
  return digest(checkpoint.body);
}
function bootstrap(trust,receiver){
  validateTrust(trust);
  check(keyId(publicPEM(receiver.publicKey))===keyId(trust.receiver),"wrong receiver bootstrap key");
  return signed(checkpointBody(trust,0,0,ZERO),[receiver]);
}
function advance(trust,log,checkpoint,receiver,now){
  verifyCheckpoint(trust,checkpoint);
  const latest=verifyLedger(trust,log,checkpoint.body.policy_version?checkpoint:null);
  check(Number.isSafeInteger(now) && now>=checkpoint.body.last_time &&
    latest.entry.body.valid_from<=now &&
    now<latest.entry.body.expires,"policy expired or not yet valid");
  check(latest.version>=checkpoint.body.policy_version,"rollback");
  if(latest.version===checkpoint.body.policy_version)
    check(latest.digest===checkpoint.body.policy_digest,"same-version fork");
  return signed(checkpointBody(trust,checkpoint.body.counter,latest.version,
    latest.digest,checkpoint.body.last_receipt,now),[receiver]);
}
function challenge(trust,log,checkpoint,receiver,now,nonce){
  const current=advance(trust,log,checkpoint,receiver,now);
  check(current.body.policy_version===checkpoint.body.policy_version &&
    current.body.policy_digest===checkpoint.body.policy_digest,
    "checkpoint must first persist latest policy");
  check(typeof nonce==="string"&&/^[0-9a-f]{32}$/.test(nonce),"nonce invalid");
  return signed({schema:"ifs.cgs008-receiver-challenge/0.1",realm:trust.realm,
    ground:trust.ground,policy_version:current.body.policy_version,
    policy_digest:current.body.policy_digest,
    checkpoint_digest:digest(checkpoint.body),counter:checkpoint.body.counter+1,
    issued_at:now,expires_at:now+10,nonce,feature:"parity"},[receiver]);
}
function observe(challengeSigned,observerId,value,source){
  check(typeof observerId==="string"&&Number.isInteger(value)&&[0,1].includes(value),
    "invalid observation");
  const c=challengeSigned.body;
  return signed({schema:"ifs.cgs008-observation/0.1",observer:observerId,
    ground:c.ground,realm:c.realm,policy_version:c.policy_version,
    policy_digest:c.policy_digest,challenge_digest:digest(c),nonce:c.nonce,
    counter:c.counter,feature:c.feature,value},[source]);
}
function consume(trust,log,checkpoint,request,observations,receiver,now){
  verifyCheckpoint(trust,checkpoint);
  const active=verifyLedger(trust,log,checkpoint.body.policy_version?checkpoint:null);
  check(active.version===checkpoint.body.policy_version &&
    active.digest===checkpoint.body.policy_digest,
    "policy not pinned to receiver's latest checkpoint");
  check(Number.isSafeInteger(now) && now>=checkpoint.body.last_time &&
    active.entry.body.valid_from<=now &&
    now<active.entry.body.expires,"policy expired for current receipt");
  verifySigned(request,[trust.receiver],1);
  const c=request.body;
  check(c.schema==="ifs.cgs008-receiver-challenge/0.1" &&
    c.realm===trust.realm && c.ground===trust.ground &&
    c.policy_version===active.version && c.policy_digest===active.digest &&
    c.checkpoint_digest===digest(checkpoint.body) &&
    c.counter===checkpoint.body.counter+1 &&
    c.feature==="parity" && /^[0-9a-f]{32}$/.test(c.nonce) &&
    Number.isSafeInteger(c.issued_at) && Number.isSafeInteger(c.expires_at) &&
    c.issued_at<=now && now<c.expires_at && c.expires_at-c.issued_at<=10,
    "stale, replayed, or wrong-context receiver challenge");
  const grants=new Map(active.entry.body.grants.map(g=>[g.observer,g]));
  check(Array.isArray(observations)&&observations.length===2,
    "exactly two separately authorized observers required");
  const values=[],seen=new Set();
  for(const obs of observations){
    const b=obs?.body, g=grants.get(b?.observer);
    check(g && !seen.has(b.observer) && g.features.includes(c.feature),
      "unknown, revoked, or repeated observer");
    seen.add(b.observer);
    verifySigned(obs,[g.public_key],1);
    check(b.schema==="ifs.cgs008-observation/0.1" &&
      b.ground===c.ground && b.realm===c.realm &&
      b.policy_version===c.policy_version && b.policy_digest===c.policy_digest &&
      b.challenge_digest===digest(c) && b.counter===c.counter &&
      b.nonce===c.nonce && b.feature===c.feature &&
      Number.isInteger(b.value)&&[0,1].includes(b.value),
      "signed observation context mismatch");
    values.push(b.value);
  }
  const status=values[0]===values[1]?"ADMITTED_AGREEMENT":"REFUSED_DISAGREEMENT";
  const receiptCommit=digest({request:request.body,
    signatures:observations.map(x=>({body:x.body,signatures:x.signatures}))});
  const next=signed(checkpointBody(trust,c.counter,active.version,active.digest,
    receiptCommit,now),[receiver]);
  return {status,returned_value:status==="ADMITTED_AGREEMENT"?values[0]:null,
    signers:[...seen].sort(),next_checkpoint:next,
    scope:"signed demonstration data, not verified sensor truth"};
}
function historical(trust,policyLog,epoch,request,observations){
  verifyLedger(trust,policyLog);
  check(Number.isSafeInteger(epoch) && epoch>=1 && epoch<=policyLog.length,
    "historical policy epoch absent");
  const oldPolicy=policyLog[epoch-1];
  verifySigned(request,[trust.receiver],1);
  check(request.body.policy_digest===digest(oldPolicy.body) &&
    request.body.policy_version===oldPolicy.body.version,"old policy binding mismatch");
  const grants=new Map(oldPolicy.body.grants.map(g=>[g.observer,g]));
  for(const obs of observations){
    const b=obs.body,g=grants.get(b.observer);
    check(g,"historical source unknown");
    verifySigned(obs,[g.public_key],1);
    check(b.challenge_digest===digest(request.body) &&
      b.policy_digest===digest(oldPolicy.body) && b.counter===request.body.counter &&
      b.nonce===request.body.nonce,"historical receipt wrong context");
  }
  return {historical_signature_valid:true,receipt_count:observations.length,
    current_authority:false,
    event_time_proven:false,
    warning:"Source-signature validity does not establish externally witnessed emission time"};
}
module.exports={ZERO,canonical,digest,keyId,publicPEM,generateIdentity,
  signed,verifySigned,validateTrust,verifyLedger,verifyCheckpoint,
  bootstrap,advance,challenge,observe,consume,historical};
