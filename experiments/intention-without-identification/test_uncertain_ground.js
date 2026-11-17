"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const e=require("./experiment.js");
const u=require("./uncertain_ground.js");
const clone=x=>JSON.parse(JSON.stringify(x));
test("joint Ground product preserves immutable candidate identity",()=>{
 const z=u.compile(u.fixtures.safe_diagnosis);
 assert.equal(z.flat.n,6);
 assert.equal(z.worlds.length,2);
 assert.equal(z.flat.start,2|(2<<3));
 assert.equal(z.flat.goal,1|(1<<3));
 assert.deepEqual(z.flat.output,[0,0,0,1,1,1]);
});
test("safe diagnosis creates a common robust strategy of rank 2",()=>{
 const r=u.analyze(u.fixtures.safe_diagnosis);
 assert.equal(r.rootRank,2);assert.equal(r.blind.word,null);
 assert.deepEqual(r.candidateSolutions.map(x=>x.rootRank),[1,1]);
 const rootAction=r.policy[r.compiled.flat.start];assert.equal(rootAction,2);
 assert.deepEqual(r.witness.rows.map(x=>[x.possibleWorld,x.transcript.map(z=>z[0])]),
 [["alpha",[2,0]],["beta",[2,1]]]);
});
test("erasing law-specific observations defeats robust control",()=>{
 const r=u.analyze(u.fixtures.silent_conflict);
 assert.equal(r.rootRank,-1);assert.equal(r.blind.word,null);
 assert.deepEqual(r.candidateSolutions.map(x=>x.rootRank),[1,1]);
 const flat=r.compiled.flat;
 for(const b of r.blind.closure)assert((b&~flat.goal)!==0);
});
test("some worlds share target realization without revealing their governing law",()=>{
 const r=u.analyze(u.fixtures.silent_common_funnel);
 assert.equal(r.rootRank,1);assert.deepEqual(r.blind.word,[0]);
 assert.deepEqual(r.witness.ambiguousOrigins,[[1,3]]);
});
test("each candidate separately is not evidence of joint realizability",()=>{
 assert.equal(u.analyze(u.fixtures.single_alpha).rootRank,1);
 assert.equal(u.analyze(u.fixtures.silent_conflict).rootRank,-1);
});
test("independent bounded-depth recursion confirms robust versus impossible",()=>{
 for(const fixture of [u.fixtures.safe_diagnosis,u.fixtures.silent_conflict]){
  const m=u.compile(fixture).flat,r=e.solve(m),cache=new Map();
  function oracle(b,k){
   if(e.goal(m,b))return true;if(k===0)return false;
   const key=b+":"+k;if(cache.has(key))return cache.get(key);
   const found=m.next.some((v,a)=>e.split(m,b,a).every(c=>oracle(c.mask,k-1)));
   cache.set(key,found);return found;
  }
  for(let k=0;k<=3;k++)assert.equal(oracle(m.start,k),r.rank[m.start]>=0&&r.rank[m.start]<=k);
 }
});
test("tampering with reconstructed Ground/report is rejected",()=>{
 const c=u.fixtures.safe_diagnosis,r=u.analyze(c);
 assert.equal(u.auditAnalysis(c,r),true);
 const broken=clone(r);broken.policy[broken.compiled.flat.start]=0;
 assert.throws(()=>u.auditAnalysis(c,broken));
 const changed=clone(c);changed[1].model.output=[0,0,0];
 assert.throws(()=>u.auditAnalysis(changed,r));
});
test("malformed candidate spaces fail closed",()=>{
 assert.throws(()=>u.compile([]));
 const c=clone(u.fixtures.safe_diagnosis);
 c[1].id=c[0].id;assert.throws(()=>u.compile(c));
 c[1].id="beta";c[1].model.next=[c[1].model.next[0]];
 assert.throws(()=>u.compile(c));
});
test("reconstruct all committed cross-Ground evidence",()=>{
 const stored=JSON.parse(fs.readFileSync(path.join(__dirname,"results","uncertain_ground.json"),"utf8"));
 assert.deepEqual(u.study(),stored);
});
