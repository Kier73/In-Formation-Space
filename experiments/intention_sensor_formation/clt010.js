"use strict";
// CLT-010: intention-driven formation of reusable Boolean sensors.
function experiment(){
 const N=256,n=8,ALL=15;
 const assert=(p,m)=>{if(!p)throw Error(m)},bit=(x,i)=>(x>>>i)&1;
 function world(seed){
  let p=Array.from({length:n},(_,i)=>i),r=seed;
  for(let i=n-1;i>0;i--){r=(Math.imul(r,1664525)+1013904223)>>>0;let j=r%(i+1);[p[i],p[j]]=[p[j],p[i]]}
  function success(task,x,a){
   const u=bit(x,p[0])^bit(x,p[4]),v=bit(x,p[1])^bit(x,p[5]);
   if(task==="A")return bit(a,0)===u;
   if(task==="B")return bit(a,1)===v;
   if(task==="C")return bit(a,0)===(u&v);
   if(task==="hidden")return bit(a,0)===(u^Number(x===255));
   if(task==="triple")return ((u===0&&v===0?3:u===1&&v===0?6:u===0&&v===1?5:7)&(1<<a))!==0;
   throw Error("task");
  }
  return success;
 }
 const raw=Array.from({length:n},(_,i)=>({key:`x${i}`,op:"bit",i,size:1}));
 function binary(op,a,b){
  if(a.key===b.key)return null;
  if(a.key>b.key)[a,b]=[b,a];
  return {key:`${op}(${a.key},${b.key})`,op,a,b,size:1+a.size+b.size};
 }
 function grammar(bank){
  const list=new Map(raw.map(x=>[x.key,x]));
  for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)for(const op of ["xor","and"]){const f=binary(op,raw[i],raw[j]);list.set(f.key,f)}
  for(const f of bank)list.set(f.key,f);
  for(let i=0;i<bank.length;i++)for(let j=i+1;j<bank.length;j++)for(const op of ["xor","and"]){const f=binary(op,bank[i],bank[j]);if(f)list.set(f.key,f)}
  return [...list.values()].sort((a,b)=>a.size-b.size||a.key.localeCompare(b.key,"en"));
 }
 function form(success,task,bank,maxWidth=2){
  const counters={trainingActionTests:0,auditActionTests:0,featureOps:0,partitionVisits:0,candidateTests:0,conflicts:0},known=new Map(),memo=new Map(),candidates=grammar(bank);
  const feature=(f,x)=>{
   const key=f.key+":"+x;if(memo.has(key))return memo.get(key);
   counters.featureOps++;let z;
   if(f.op==="bit")z=bit(x,f.i);
   else {const a=feature(f.a,x),b=feature(f.b,x);z=f.op==="and"?a&b:a^b}
   memo.set(key,z);return z;
  };
  const code=(fs,x)=>fs.reduce((v,f,i)=>v|(feature(f,x)<<i),0);
  function mask(x,audit){let m=0;for(let a=0;a<4;a++){counters[audit?"auditActionTests":"trainingActionTests"]++;if(success(task,x,a))m|=1<<a}return m}
  function add(x,m){known.set(x,m===undefined?mask(x,false):m)}
  add(0);for(let i=0;i<n;i++)add(1<<i);for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)add((1<<i)|(1<<j));
  const initial=known.size;
  function test(fs){
   counters.candidateTests++;
   const cells=new Map();
   for(const [x,m] of known){
    counters.partitionVisits++;const k=code(fs,x);
    const old=cells.get(k)??ALL,v=old&m;
    if(!v)return null;
    cells.set(k,v);
   }
   return new Map([...cells].map(([k,m])=>[k,31-Math.clz32(m&-m)]));
  }
  function select(){
   let policy=test([]);if(policy)return {fs:[],policy};
   for(const f of candidates){policy=test([f]);if(policy)return {fs:[f],policy}}
   if(maxWidth>=2)for(let i=0;i<candidates.length;i++)for(let j=i+1;j<candidates.length;j++){
    policy=test([candidates[i],candidates[j]]);if(policy)return {fs:[candidates[i],candidates[j]],policy};
   }
   return null;
  }
  function conflictCore(){
   let m=ALL,core=[];for(const [x,v] of known){if((m&v)!==m){core.push([x,v]);m&=v}if(!m)break}
   if(m)return null;
   for(let i=core.length-1;i>=0;i--){let rest=core.filter((_,j)=>j!==i);if(rest.reduce((s,[,v])=>s&v,ALL)===0)core=rest}
   return {states:core.map(([x,v])=>({x,mask:v})),pairwiseCompatible:core.every(([x,v],i)=>core.every(([y,w],j)=>i===j||(v&w)!==0))};
  }
  const core=conflictCore();
  let audits=0,firstCounterexample=null;
  while(true){
   const found=select();
   if(!found)return {status:"UNRESOLVED",reason:"bounded-sensor-grammar",initial,known:known.size,grammar:candidates.length,core,counters,audits,firstCounterexample};
   audits++;
   let failure=null;
   for(let x=0;x<N;x++){
    const k=code(found.fs,x),a=found.policy.get(k);
    if(a!==undefined)counters.auditActionTests++;
    if(a===undefined||!success(task,x,a)){failure=x;break}
   }
   if(failure===null){
    const evalRaw=(f,x)=>f.op==="bit"?bit(x,f.i):f.op==="xor"?evalRaw(f.a,x)^evalRaw(f.b,x):evalRaw(f.a,x)&evalRaw(f.b,x);
    let independentChecks=0;
    for(let x=0;x<N;x++){const key=found.fs.reduce((z,f,i)=>z|(evalRaw(f,x)<<i),0);assert(success(task,x,found.policy.get(key)),"policy mismatch");independentChecks++}
    return {status:"EXACT",width:found.fs.length,sensors:found.fs.map(f=>f.key),expressions:found.fs,initial,known:known.size,grammar:candidates.length,core,counters,audits,firstCounterexample,independentChecks};
   }
   assert(!known.has(failure),"counterexample already known");counters.conflicts++;
   const m=mask(failure,true);
   if(firstCounterexample===null)firstCounterexample={state:failure,mask:m};
   add(failure,m);
  }
 }
 function clean(r){const {expressions,...rest}=r;return rest}
 const runs=[];
 for(const seed of [17,39,93,151]){
  const source=world(seed),bank=[];
  const a=form(source,"A",bank);assert(a.status==="EXACT"&&a.width===1,"A");bank.push(...a.expressions);
  const b=form(source,"B",bank);assert(b.status==="EXACT"&&b.width===1,"B");bank.push(...b.expressions);
  const cold=form(source,"C",[]),warm=form(source,"C",bank);
  assert(cold.status==="EXACT"&&cold.width===2&&warm.status==="EXACT"&&warm.width===1,"cascade");
  const triple=form(source,"triple",bank);
  assert(triple.status==="EXACT"&&triple.core.states.length===3&&triple.core.pairwiseCompatible,"triple obstruction");
  const hidden=form(source,"hidden",bank,1);
  assert(hidden.status==="UNRESOLVED"&&hidden.firstCounterexample?.state===255,"hidden refusal");
  runs.push({seed,A:clean(a),B:clean(b),C_cold:clean(cold),C_warm:clean(warm),triple:clean(triple),hidden:clean(hidden)});
 }
 return {domain:N,actions:4,runs};
}
if(require.main===module)console.log(JSON.stringify(experiment(),null,2));
module.exports={experiment};
