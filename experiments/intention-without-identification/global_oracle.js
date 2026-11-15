"use strict";
/* IWI-003 independent small-model global oracle.
 * Explicitly enumerates complete laws, then all reachable observation beliefs,
 * and solves the finite strong reachability game without a horizon cutoff.
 * Its enumeration is intentionally capped; this is NOT the large-scale lazy solver.
 */
const partial=require("./partial_ground.js");
function allLaws(input,cap=256) {
 const m=partial.validate(input);
 if(BigInt(m.possibleLaws)>BigInt(cap))throw Error("completion cap exceeded; global oracle unavailable");
 const cells=[];
 for(let a=0;a<m.next.length;a++)for(let s=0;s<m.n;s++)
  if(m.next[a][s].length>1)cells.push({kind:"t",a,s,values:m.next[a][s]});
 for(let s=0;s<m.n;s++)if(m.output[s].length>1)
  cells.push({kind:"o",s,values:m.output[s]});
 const t=m.next.map(row=>row.map(v=>v[0])),o=m.output.map(v=>v[0]),laws=[];
 function recur(i) {
  if(i===cells.length){laws.push({next:t.map(row=>row.slice()),output:o.slice()});return;}
  const c=cells[i];
  for(const v of c.values){if(c.kind==="o")o[c.s]=v;else t[c.a][c.s]=v;recur(i+1);}
 }
 recur(0);
 if(laws.length!==Number(m.possibleLaws))throw Error("completion count mismatch");
 return {m,laws};
}
function globalOracle(input,cap=256,capBeliefs=30000) {
 const {m,laws}=allLaws(input,cap),total=m.n*laws.length;
 if(total>22)throw Error("global oracle composite state cap exceeded");
 let initial=0,goal=0;
 for(let w=0;w<laws.length;w++){
  for(const s of m.start)initial|=1<<(w*m.n+s);
  for(const s of m.goal)goal|=1<<(w*m.n+s);
 }
 function split(b,action){
  const grouped=Array(16).fill(0);
  for(let state=0;state<total;state++)if((b>>>state)&1){
   const w=Math.floor(state/m.n),s=state%m.n,law=laws[w];
   const dest=law.next[action][s];
   grouped[law.output[dest]]|=1<<(w*m.n+dest);
  }
  return grouped.filter(Boolean);
 }
 function terminal(b){return (b&~goal)===0;}
 const reachable=[initial],seen=new Set(reachable);
 for(let i=0;i<reachable.length;i++){
  if(reachable.length>capBeliefs)throw Error("global belief cap exceeded");
  for(let a=0;a<m.next.length;a++)for(const next of split(reachable[i],a)){
   if(!seen.has(next)){seen.add(next);reachable.push(next);}
  }
 }
 const rank=new Map(),action=new Map();
 for(const b of reachable)if(terminal(b)){rank.set(b,0);action.set(b,null);}
 while(true){
  const pending=[];
  for(const b of reachable)if(!rank.has(b)){
   const candidates=[];
   for(let a=0;a<m.next.length;a++){
    const children=split(b,a);
    if(children.every(c=>rank.has(c)))candidates.push({a,r:1+Math.max(...children.map(c=>rank.get(c)))});
   }
   if(candidates.length){
    candidates.sort((x,y)=>x.r-y.r||x.a-y.a);
    pending.push({b,...candidates[0]});
   }
  }
  if(!pending.length)break;
  for(const v of pending){rank.set(v.b,v.r);action.set(v.b,v.a);}
 }
 // Verify every reachable winning descent, and every losing belief's closure.
 for(const b of reachable){
  if(rank.has(b)){
   if(rank.get(b)===0){if(!terminal(b))throw Error("false global goal");continue;}
   const childRanks=split(b,action.get(b)).map(c=>rank.get(c));
   if(childRanks.some(c=>c===undefined)||Math.max(...childRanks)>=rank.get(b))throw Error("false global descent");
  } else for(let a=0;a<m.next.length;a++)
   if(split(b,a).every(c=>rank.has(c)))throw Error("false global loss");
 }
 const losing=reachable.filter(b=>!rank.has(b)).sort((a,b)=>a-b);
 return {status:rank.has(initial)?"globally-winning":"globally-impossible",
  rootRank:rank.get(initial)??null,fullLawsEnumerated:laws.length,
  reachableBeliefs:reachable.length,winningReachableBeliefs:rank.size,
  losingTrapSize:losing.length,initialMask:initial,goalMask:goal,
  losingTrap:rank.has(initial)?null:losing};
}
module.exports={allLaws,globalOracle};
if(require.main===module){
 const out=Object.fromEntries(["remembered","unknowable"].map(name=>[name,globalOracle(partial.fixtures[name])]));
 process.stdout.write(JSON.stringify(out,null,2)+"\n");
}
