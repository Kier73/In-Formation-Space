"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const x=require("./experiment.js");
const clone=v=>JSON.parse(JSON.stringify(v));

test("all 5,832 labelled machines match exact census",()=>{
 assert.deepEqual(x.census(),{total:5832,adaptiveWinning:3656,blindWinning:3128,
 adaptiveOnly:528,individuallyReachable:3960,individualButNoAdaptive:304});
});
test("all 5,832 models carry internally complete rank/loss certificates",()=>{
 for(let code=0;code<729;code++){
  let t=code;const next=[[],[]];
  for(let a=0;a<2;a++)for(let s=0;s<3;s++){next[a][s]=t%3;t=Math.floor(t/3);}
  for(let o=0;o<8;o++){
   const m={n:3,start:7,goal:1,next,output:[o&1,o>>1&1,o>>2&1]};
   assert.equal(x.audit(m,x.solve(m)),true);
  }
 }
});
test("blind intervention realizes target without identifying the origin",()=>{
 const m=x.fixtures.funnel,r=x.solve(m);
 assert.equal(r.rank[7],1);assert.deepEqual(r.blind.word,[1]);
 assert.deepEqual(x.transcripts(m,r).ambiguousOrigins,[[0,1,2]]);
});
test("conditional actions, not merely conditional stop, beat every blind word",()=>{
 const m=x.fixtures.branch,r=x.solve(m);
 assert.equal(r.rank[7],3);assert.equal(r.blind.word,null);
 const children=x.split(m,7,r.policy[7]);
 assert.equal(children.length,2);
 assert(children.every(c=>r.rank[c.mask]>0));
 assert.notEqual(r.policy[children[0].mask],r.policy[children[1].mask]);
 assert.equal(x.transcripts(m,r).rows.length,3);
});
test("erasing outputs leaves individual paths but forbids universal control",()=>{
 const m=x.fixtures.erased,r=x.solve(m);
 assert.equal(r.rank[7],-1);assert.equal(r.blind.word,null);
 assert(r.individual.every(d=>d.distance!==null));
 for(const b of r.blind.closure)assert((b&~m.goal)!==0);
});
test("independent recursive bounded-depth oracle verifies all three fixtures",()=>{
 for(const m of Object.values(x.fixtures)){
  const r=x.solve(m),cache=new Map();
  function oracle(b,k){
   if(x.goal(m,b))return true;
   if(k===0)return false;
   const key=b+":"+k;if(cache.has(key))return cache.get(key);
   const success=m.next.some((row,a)=>x.split(m,b,a).every(c=>oracle(c.mask,k-1)));
   cache.set(key,success);return success;
  }
  for(let b=1;b<(1<<m.n);b++)for(let k=0;k<(1<<m.n);k++)
   assert.equal(oracle(b,k),r.rank[b]>=0&&r.rank[b]<=k,"belief="+b+" depth="+k);
 }
});
test("forged rank, strategy, and baseline are refused",()=>{
 const m=x.fixtures.branch,r=x.solve(m);
 let z=clone(r);z.rank[7]=1;assert.throws(()=>x.audit(m,z));
 z=clone(r);z.policy[7]=99;assert.throws(()=>x.audit(m,z));
 z=clone(r);z.rank[7]=-1;z.policy[7]=-1;assert.throws(()=>x.audit(m,z));
 z=clone(r);z.blind.word=[];assert.throws(()=>x.audit(m,z));
});
test("invalid models fail closed",()=>{
 for(const bad of [
  {...x.fixtures.funnel,n:13},
  {...x.fixtures.funnel,start:0},
  {...x.fixtures.funnel,goal:8},
  {...x.fixtures.funnel,output:[0,1]},
  {...x.fixtures.funnel,next:[[0,1,5]]}
 ])assert.throws(()=>x.solve(bad));
});
test("hidden-state relabelling preserves reachability and worst-case rank",()=>{
 const old=x.fixtures.branch,p=[2,0,1];
 const remap=b=>p.reduce((v,t,s)=>v|((b>>s&1)<<t),0);
 const m={n:3,start:remap(old.start),goal:remap(old.goal),
  next:old.next.map(row=>{const z=Array(3);for(let s=0;s<3;s++)z[p[s]]=p[row[s]];return z;}),
  output:(()=>{const z=Array(3);for(let s=0;s<3;s++)z[p[s]]=old.output[s];return z;})()};
 const r=x.solve(m);assert.equal(x.audit(m,r),true);
 assert.equal(x.solve(old).rank[old.start],r.rank[m.start]);
 assert.equal(r.blind.word,null);
});
test("committed evidence is deterministic and reconstructed exactly",()=>{
 const evidence=JSON.parse(fs.readFileSync(path.join(__dirname,"results","census.json"),"utf8"));
 assert.deepEqual(x.study(),evidence);
});
