"use strict";
// IWI-001: exact finite guaranteed-state navigation; model-relative, not physical evidence.
function check(m) {
 const size=1<<m.n;
 if (!Number.isInteger(m.n)||m.n<1||m.n>12||!Number.isInteger(m.start)||m.start<1||m.start>=size||!Number.isInteger(m.goal)||m.goal<1||m.goal>=size) throw Error("invalid model masks");
 if (!Array.isArray(m.next)||!m.next.length||m.next.length>8||!Array.isArray(m.output)||m.output.length!==m.n) throw Error("invalid model shape");
 for(const row of m.next) {
   if(!Array.isArray(row)||row.length!==m.n)throw Error("invalid action");
   for(const d of row)if(!Number.isInteger(d)||d<0||d>=m.n)throw Error("invalid destination");
 }
 for(const o of m.output)if(!Number.isInteger(o)||o<0||o>15)throw Error("invalid observation");
 return size;
}
function goal(m,b){return !(b&~m.goal);}
function image(m,b,a){let v=0;for(let s=0;s<m.n;s++)if(b>>s&1)v|=1<<m.next[a][s];return v;}
function split(m,b,a){
 const out=Array(16).fill(0);
 for(let s=0;s<m.n;s++)if(b>>s&1){const d=m.next[a][s];out[m.output[d]]|=1<<d;}
 return out.flatMap((b,o)=>b?[{mask:b,output:o}]:[]);
}
function blind(m){
 check(m);const q=[[m.start,[]]],seen=new Set([m.start]);
 for(let i=0;i<q.length;i++){
   const [b,w]=q[i];if(goal(m,b))return {word:w,closure:null};
   for(let a=0;a<m.next.length;a++){let d=image(m,b,a);if(!seen.has(d)){seen.add(d);q.push([d,w.concat(a)]);}}
 }
 return {word:null,closure:[...seen].sort((a,b)=>a-b)};
}
function individual(m){
 check(m);const rows=[];
 for(let s=0;s<m.n;s++)if(m.start>>s&1){
   const q=[[s,0]],seen=new Set([s]);let distance=null;
   for(let i=0;i<q.length;i++){
     let [v,d]=q[i];if(m.goal>>v&1){distance=d;break;}
     for(const t of m.next){let u=t[v];if(!seen.has(u)){seen.add(u);q.push([u,d+1]);}}
   }
   rows.push({state:s,distance});
 }
 return rows;
}
function solve(m){
 const size=check(m),rank=Array(size).fill(-1),policy=Array(size).fill(-1);
 for(let b=1;b<size;b++)if(goal(m,b))rank[b]=0;
 for(let depth=1;depth<size;depth++){
   const next=[];
   for(let b=1;b<size;b++)if(rank[b]===-1)for(let a=0;a<m.next.length;a++){
     if(split(m,b,a).every(ch=>rank[ch.mask]>=0)){next.push([b,a]);break;}
   }
   if(!next.length)break;
   for(const [b,a] of next){rank[b]=depth;policy[b]=a;}
 }
 return {rank,policy,blind:blind(m),individual:individual(m)};
}
function audit(m,r){
 const size=check(m);
 if(!r||!Array.isArray(r.rank)||!Array.isArray(r.policy)||r.rank.length!==size||r.policy.length!==size||r.rank[0]!==-1||r.policy[0]!==-1)throw Error("invalid certificate shape");
 for(let b=1;b<size;b++){
  const d=r.rank[b],a=r.policy[b];
  if(!Number.isInteger(d)||d< -1||d>=size||!Number.isInteger(a))throw Error("invalid rank");
  if(d===0){if(!goal(m,b)||a!==-1)throw Error("invalid terminal");continue;}
  if(goal(m,b))throw Error("missing terminal");
  if(d===-1){
   if(a!==-1)throw Error("loser has strategy");
   for(let x=0;x<m.next.length;x++)if(split(m,b,x).every(y=>r.rank[y.mask]>=0))throw Error("false losing trap");
  }else{
   if(a<0||a>=m.next.length)throw Error("bad action");
   const chosen=split(m,b,a).map(x=>r.rank[x.mask]);
   if(chosen.some(x=>x<0)||Math.max(...chosen)+1!==d)throw Error("false descent");
   for(let x=0;x<m.next.length;x++){
     const ranks=split(m,b,x).map(y=>r.rank[y.mask]);
     if(ranks.every(y=>y>=0)&&1+Math.max(...ranks)<d)throw Error("nonminimal rank");
   }
  }
 }
 if(JSON.stringify(r.blind)!==JSON.stringify(blind(m))||JSON.stringify(r.individual)!==JSON.stringify(individual(m)))throw Error("bad baselines");
 return true;
}
function transcripts(m,r){
 if(r.rank[m.start]<0)return null;
 const rows=[],groups={};
 for(let origin=0;origin<m.n;origin++)if(m.start>>origin&1){
  let b=m.start,s=origin,steps=[];
  for(let d=0;d<=r.rank[m.start]&&!goal(m,b);d++){
   if(d===r.rank[m.start])throw Error("rank exceeded");
   const a=r.policy[b];s=m.next[a][s];const o=m.output[s];
   const child=split(m,b,a).find(x=>x.output===o);
   if(!child||!(child.mask>>s&1))throw Error("inconsistent trace");
   b=child.mask;steps.push([a,o]);
  }
  if(!(m.goal>>s&1))throw Error("goal never reached");
  const key=JSON.stringify(steps);(groups[key]??=[]).push(origin);
  rows.push({origin,final:s,transcript:steps});
 }
 return {rows,ambiguousOrigins:Object.values(groups).filter(x=>x.length>1)};
}
const fixtures={
 funnel:{n:3,start:7,goal:1,output:[0,0,0],next:[[0,1,2],[0,0,0]]},
 branch:{n:3,start:7,goal:1,output:[1,1,0],next:[[0,2,1],[1,0,0]]},
 erased:{n:3,start:7,goal:1,output:[0,0,0],next:[[0,2,1],[1,0,0]]}
};
function census(){
 const z={total:0,adaptiveWinning:0,blindWinning:0,adaptiveOnly:0,individuallyReachable:0,individualButNoAdaptive:0};
 for(let c=0;c<729;c++){
  let x=c;const next=[[],[]];
  for(let a=0;a<2;a++)for(let s=0;s<3;s++){next[a][s]=x%3;x=Math.floor(x/3);}
  for(let o=0;o<8;o++){
   const m={n:3,start:7,goal:1,next,output:[o&1,o>>1&1,o>>2&1]},r=solve(m);
   const win=r.rank[7]>=0,any=r.blind.word!==null,each=r.individual.every(x=>x.distance!==null);
   z.total++;if(win)z.adaptiveWinning++;if(any)z.blindWinning++;
   if(win&&!any)z.adaptiveOnly++;if(each)z.individuallyReachable++;
   if(each&&!win)z.individualButNoAdaptive++;
  }
 }
 return z;
}
function study(){
 return {experiment:"IWI-001",modelClass:"three states / two actions / binary post-action output",census:census(),
 examples:Object.fromEntries(Object.entries(fixtures).map(([name,m])=>{
   const r=solve(m);audit(m,r);return [name,{model:m,rootRank:r.rank[m.start],rank:r.rank,policy:r.policy,blind:r.blind,individual:r.individual,transcripts:transcripts(m,r)}];
 }))};
}
if(typeof module!=="undefined")module.exports={check,goal,image,split,blind,individual,solve,audit,transcripts,fixtures,census,study};
if(typeof require!=="undefined"&&require.main===module)process.stdout.write(JSON.stringify(study(),null,2)+"\n");
