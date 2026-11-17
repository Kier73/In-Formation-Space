"use strict";
// IWI-002: static uncertainty over multiple possible transition/observation Grounds.
// Each candidate is a possible immutable world, not a vote or an independent reality.
const e=require("./experiment.js");
function compile(candidates){
 if(!Array.isArray(candidates)||!candidates.length||candidates.length>12)throw Error("invalid candidate set");
 let n=0,actions=null;
 const flat={n:0,start:0,goal:0,output:[],next:[]},worlds=[],ids=new Set();
 for(const c of candidates){
  if(!c||typeof c.id!=="string"||!c.id.length||ids.has(c.id)||!c.model)throw Error("invalid candidate identity");
  ids.add(c.id);const m=c.model;e.check(m);
  if(actions===null){actions=m.next.length;flat.next=Array.from({length:actions},()=>[]);}
  if(actions!==m.next.length||n+m.n>12)throw Error("incompatible actions or oversize product");
  for(let s=0;s<m.n;s++){
   flat.output[n+s]=m.output[s];
   for(let a=0;a<actions;a++)flat.next[a][n+s]=n+m.next[a][s];
  }
  flat.start|=m.start<<n;
  flat.goal|=m.goal<<n;
  worlds.push({id:c.id,offset:n,states:m.n,initial:m.start,goal:m.goal});
  n+=m.n;
 }
 flat.n=n;e.check(flat);
 return {flat,worlds};
}
function analyze(candidates){
 const compiled=compile(candidates),r=e.solve(compiled.flat);
 e.audit(compiled.flat,r);
 const rows=candidates.map(c=>{
  const s=e.solve(c.model);e.audit(c.model,s);
  return {id:c.id,rootRank:s.rank[c.model.start],blindWord:s.blind.word};
 });
 const t=e.transcripts(compiled.flat,r);
 return {candidates,compiled,rootRank:r.rank[compiled.flat.start],
  policy:r.policy,rank:r.rank,blind:r.blind,candidateSolutions:rows,
  witness:t&&{...t,rows:t.rows.map(x=>({...x,
   possibleWorld:compiled.worlds.find(w=>x.origin>=w.offset&&x.origin<w.offset+w.states).id,
   localOrigin:x.origin-compiled.worlds.find(w=>x.origin>=w.offset&&x.origin<w.offset+w.states).offset}))}};
}
function auditAnalysis(candidates,result){
 const expected=analyze(candidates);
 if(JSON.stringify(result)!==JSON.stringify(expected))throw Error("model-uncertainty witness does not reconstruct");
 return true;
}
const A={n:3,start:2,goal:1,output:[0,0,0],
 next:[[0,0,2],[0,2,2],[0,1,2]]};
const B={n:3,start:2,goal:1,output:[1,1,1],
 next:[[0,2,2],[0,0,2],[0,1,2]]};
const fixtures={
 safe_diagnosis:[{id:"alpha",model:A},{id:"beta",model:B}],
 silent_conflict:[{id:"alpha",model:A},{id:"beta",model:{...B,output:[0,0,0]}}],
 single_alpha:[{id:"alpha",model:A}],
 silent_common_funnel:[
 {id:"alpha",model:{n:2,start:2,goal:1,output:[0,0],next:[[0,0],[0,1]]}},
 {id:"beta",model:{n:2,start:2,goal:1,output:[0,0],next:[[0,0],[1,1]]}}
 ]
};
function study(){
 return {experiment:"IWI-002",interpretation:"static uncertainty over candidate transition laws; synthetic only",
 cases:Object.fromEntries(Object.entries(fixtures).map(([id,c])=>[id,analyze(c)]))};
}
module.exports={compile,analyze,auditAnalysis,fixtures,study};
if(typeof require!=="undefined"&&require.main===module)process.stdout.write(JSON.stringify(study(),null,2)+"\n");
