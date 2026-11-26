"use strict";
// CLT-011 — active descriptor perception for native VLM proposal routing.
function experiment(){
 const assert=(v,m)=>{if(!v)throw Error(m)},u=x=>x>>>0;
 function generator(seed,count,hostile=false){
  let r=seed;const next=()=>r=(Math.imul(r,1664525)+1013904223)>>>0;
  const C=k=>[1,0,0,0,u(k)],X=[0,0,0,0,0];
  const chart=(k,d,inv)=>[X,C(65535),[5,0,1,0,0],[3,2,2,0,0],[3,3,2,0,0],C(k),[3,4,5,0,0],[2,0,6,0,0],C(d),[2,7,8,0,0],[5,9,1,0,0],[3,10,10,0,0],[3,11,10,0,0],C(inv),[3,12,13,0,0],[2,9,14,0,0]];
  const cases=[];
  for(let i=0;i<count;i++){
   const type=i%6,k=(next()&65535)*65536,d=next();let nodes,label;
   if(type===0||type===1){nodes=[X,C(next()),C(next())];let pos=0;for(let j=0;j<1+(next()%12);j++){nodes.push([3,pos,1,0,0],[2,nodes.length,2,0,0]);pos=nodes.length-1}label=1}
   else if(type===2){nodes=chart(k,d,-k);label=2}
   else if(type===3){nodes=chart(k,d,-k+65536*(1+(next()%65535)));label=0}
   else if(type===4){nodes=[X,[3,0,0,0,0]];label=0}
   else{nodes=[X,C(next()),[4,0,1,0,0]];label=0}
   if(hostile&&type===2){nodes[14]=[2,12,13,0,0];label=0}
   cases.push({nodes,out:nodes.length-1,label});
  }
  return cases;
 }
 function coarse(c){
  const live=new Set([c.out]);for(let i=c.out;i>=0;i--)if(live.has(i)){const [op,a,b,d]=c.nodes[i];if(op>=2){live.add(a);live.add(b);if(op===7)live.add(d)}}
  const f=[0,0,0,Number(c.nodes.length===16&&c.out===15)*16,0,16];
  for(const i of live){const [op,a,b]=c.nodes[i];if(op===4||op===5)f[0]=16;if(op===6||op===7)f[1]=16;if(op===3){f[5]=0;if(c.nodes[a][0]!==1&&c.nodes[b][0]!==1)f[2]=16}if(op===5)f[4]=16}return f;
 }
 const fields=Array.from({length:16},(_,i)=>i);
 function probes(){
  const a=[];
  for(const i of fields){for(const op of ["zero","aligned"])a.push({op,i,cost:1,key:`${op}(${i})`})}
  for(const i of fields)for(let j=i+1;j<16;j++)for(const op of ["equal","inverse"])a.push({op,i,j,cost:2,key:`${op}(${i},${j})`});
  return a;
 }
 function value(p,c,seen){
  const read=i=>{if(seen)seen.add(i);return c.nodes[i]?.[0]===1?c.nodes[i][4]:null};
  const a=read(p.i);if(p.op==="zero")return a===0;if(p.op==="aligned")return a!==null&&(a&65535)===0;
  const b=read(p.j);return a!==null&&b!==null&&(p.op==="equal"?a===b:u(a+b)===0);
 }
 function counts(cs){let a=[0,0,0];for(const c of cs)a[c.label]++;return a}
 function majority(cs){const a=counts(cs);return a.indexOf(Math.max(...a))}
 function impurity(cs){let [a,b,c]=counts(cs);return a*b+a*c+b*c}
 const all=probes(),train=generator(20261124,600),held=generator(20261125,600),hostile=generator(1234567,120,true);
 let trainingProbeTests=0;
 function tree(cs,depth,used){
  const q=impurity(cs);if(q===0||depth===0)return {proposal:majority(cs),training:cs.length};
  let best=null;
  for(const p of all){if(used.has(p.key))continue;const yes=[],no=[];for(const c of cs){trainingProbeTests++;(value(p,c)?yes:no).push(c)}
   if(!yes.length||!no.length)continue;
   const gain=q-impurity(yes)-impurity(no);
   if(gain>0&&(!best||gain*best.p.cost>best.gain*p.cost)){best={p,gain,yes,no}}
  }
  if(!best)return {proposal:majority(cs),training:cs.length};
  const next=new Set([...used,best.p.key]);return {probe:best.p,yes:tree(best.yes,depth-1,next),no:tree(best.no,depth-1,next)};
 }
 const groups=new Map();for(const c of train){const k=coarse(c).join(",");if(!groups.has(k))groups.set(k,[]);groups.get(k).push(c)}
 const model=Object.fromEntries([...groups].map(([k,cs])=>[k,{baseline:majority(cs),tree:tree(cs,3,new Set())}]));
 function infer(c,adaptive){
  let route=model[coarse(c).join(",")],seen=new Set(),probes=0;
  if(!route)return {proposal:0,reads:0,probes};
  if(!adaptive)return {proposal:route.baseline,reads:0,probes};
  let node=route.tree;while(node.probe){probes++;node=value(node.probe,c,seen)?node.yes:node.no}
  return {proposal:node.proposal,reads:seen.size,probes};
 }
 function score(cs,adaptive){
  const s={cases:cs.length,correct:0,available:0,admitted:0,falseProposals:0,fallbacks:0,additionalReads:0,derivedTests:0};
  for(const c of cs){const p=infer(c,adaptive);s.correct+=Number(p.proposal===c.label);s.available+=Number(c.label!==0);s.admitted+=Number(p.proposal!==0&&p.proposal===c.label);s.falseProposals+=Number(p.proposal!==0&&p.proposal!==c.label);s.fallbacks+=Number(!(p.proposal!==0&&p.proposal===c.label));s.additionalReads+=p.reads;s.derivedTests+=p.probes}
  return s;
 }
 const baseline=score(held,false),adaptive=score(held,true),challenge=score(hostile,true);
 assert(adaptive.correct===held.length,"structured heldout");assert(challenge.falseProposals>0,"unseen chart mutation must challenge sensor");
 // Native check consumes fresh generated descriptors, native coarse features,
 // proposed action, and construction label; not a source of local authority.
 const cases=[...held,...hostile].map(c=>({...c,features:coarse(c),proposal:infer(c,true).proposal}));
 return {results:{training:train.length,coarseClasses:groups.size,conflictedClasses:[...groups.values()].filter(cs=>impurity(cs)>0).length,grammar:all.length,trainingProbeTests,model,baseline,adaptive,challenge},cases};
}
if(require.main===module){const e=experiment();console.log(JSON.stringify(process.argv.includes("--native-cases")?e.cases:e.results,null,2))}
module.exports={experiment};
