"use strict";
// CLT-009 — coupled observation and transport of executable actions.
function experiment(){
 const ok=(p,m)=>{if(!p)throw Error(m)}, N=256, bit=(x,i)=>(x>>>i)&1;
 const goal=x=>bit(x,0)^bit(x,4);
 const base=(a,x)=>a===0?((x<<1)&255)|(x>>>7):a===1?x^((bit(x,2)&bit(x,5))<<0):x^1;
 const stepWord=(f,x,word)=>word.reduce((v,a)=>f(a,v),x);
 const T=1000000000039n,word=[0,1,0,1,2];
 // A owns its admitted operator atlas. B has a different physical state and
 // two independently encoded sensor channels, with no shared state identity.
 function world(seed,corrupt=false){
  let rng=seed;const p=[0,1,2,3,4,5,6,7];
  for(const offset of [0,4])for(let i=3;i>0;i--){rng=(Math.imul(rng,1664525)+1013904223)>>>0;let j=rng%(i+1);[p[offset+i],p[offset+j]]=[p[offset+j],p[offset+i]]}
  const sign=(seed*73+19)&255;
  const encode=x=>p.reduce((v,j,i)=>v|(bit(x,i)<<j),0)^sign;
  const decode=y=>p.reduce((v,j,i)=>v|(bit(y^sign,j)<<i),0);
  // The target has two additional evolving hidden bits. A deliberate
  // degree-eight perturbation is invisible at all calibration anchors.
  const transition=(a,z)=>{const x=decode(z&255),h=z>>>8;
    let y=base(a,x);if(corrupt&&a===1&&x===255)y^=1;
    return encode(y)|(((h+1+bit(x,3))&3)<<8)};
  return {encode,decode,transition,observe:z=>[z&15,(z>>>4)&15]};
 }
 // Candidate discovery consumes paired sensor values at shared calibration
 // anchors, not physical states or the hidden signed permutation.
 function discover(pairs,channels){
  const active=Array.from({length:8},(_,i)=>i).filter(i=>channels.includes(i>>>2));
  const pack=o=>o[0]|(o[1]<<4);
  const maps=[];
  for(let i=0;i<8;i++){
   const candidates=[];
   for(const j of active)for(let c=0;c<2;c++){
    if(pairs.every(([s,t])=>bit(pack(s),i)===(bit(pack(t),j)^c)))candidates.push([j,c]);
   }
   if(candidates.length!==1)return null;
   maps.push(candidates[0]);
  }
  if(new Set(maps.map(m=>m[0])).size!==8)return null;
  return maps;
 }
 const translate=(m,y)=>m.reduce((v,[j,c],i)=>v|((bit(y,j)^c)<<i),0);
 const inverse=(m,x)=>m.reduce((v,[j,c],i)=>v|((bit(x,i)^c)<<j),0);
 const packed=o=>o[0]|(o[1]<<4);
 // Source qualification: independently inspect every state-action pair.
 // A bounded finite proof, not a claim that calibration establishes a law.
 function verify(w,m){
  let checks=0;
  for(let z=0;z<1024;z++)for(let a=0;a<3;a++){
   checks++;
   const x=translate(m,packed(w.observe(z))),y=translate(m,packed(w.observe(w.transition(a,z))));
   if(y!==base(a,x))return {status:"DISTINGUISHABLE",checks,witness:{z,a,x,expected:base(a,x),actual:y}};
  }
  return {status:"EQUIVALENT",checks};
 }
 const compose=(a,b)=>b.map(v=>a[v]);
 const sourceTable=Array.from({length:3},(_,a)=>Array.from({length:N},(_,x)=>base(a,x)));
 let block=Array.from({length:N},(_,i)=>i);for(const a of word)block=compose(sourceTable[a],block);
 let power=block,powered=Array.from({length:N},(_,i)=>i),t=T,compositions=0;
 while(t){if(t&1n){powered=compose(power,powered);compositions++}t>>=1n;if(t){power=compose(power,power);compositions++}}
 function direct(w,z,t){
  const seen=new Map(),hist=[];let calls=0;
  while(t&&!seen.has(z)){seen.set(z,hist.length);hist.push(z);for(const a of word){z=w.transition(a,z);calls++}t--}
  if(t){const s=seen.get(z);z=hist[s+Number(t%BigInt(hist.length-s))]}
  return {z,calls};
 }
 // Policy synthesis: determine whether a sensor representation suffices to
 // select HOLD or TOGGLE for either demanded goal bit, for all domain states.
 function actionGround(sensor){
  const by=new Map();let witness=null;
  for(let x=0;x<N;x++){
   const k=sensor(x),v=goal(x);
   if(by.has(k)&&by.get(k).value!==v){witness={left:by.get(k).x,right:x,observation:k};break}
   if(!by.has(k))by.set(k,{x,value:v});
  }
  if(witness)return {status:"DISTINGUISHABLE",witness};
  return {status:"SUFFICIENT",classes:by.size,choose:(x,wanted)=>by.get(sensor(x)).value^wanted};
 }
 const left=actionGround(x=>x&15),right=actionGround(x=>x>>>4),fused=actionGround(x=>x),derived=actionGround(goal);
 ok(left.status==="DISTINGUISHABLE"&&right.status==="DISTINGUISHABLE"&&fused.status==="SUFFICIENT"&&derived.status==="SUFFICIENT","sensor sufficiency");
 for(let x=0;x<N;x++)for(let wanted=0;wanted<2;wanted++){
  const a=derived.choose(x,wanted);ok(goal(a?base(2,x):x)===wanted,"derived policy");
 }
 const runs=[];
 for(const seed of [17,39,93,151]){
  const w=world(seed),anchors=[0,...Array.from({length:8},(_,i)=>1<<i)];
  const pairs=anchors.map(x=>[[x&15,x>>>4],w.observe(w.encode(x)|((x&3)<<8))]);
  const onlyLeft=discover(pairs,[0]),onlyRight=discover(pairs,[1]),m=discover(pairs,[0,1]);
  ok(!onlyLeft&&!onlyRight&&m,"coupled calibration");
  const evidence=verify(w,m);ok(evidence.status==="EQUIVALENT","transport proof");
  let verified=0,actionChecks=0,directCalls=0,targetNavigationCalls=0;
  // All observable anchors, not just favorable orbit intersections; 247
  // outside calibration. Both nuisance and action intentions vary.
  for(let x=0;x<N;x++){
   const z=w.encode(x)|((x%4)<<8),q=translate(m,packed(w.observe(z)));
   const predicted=powered[q],expected=inverse(m,predicted),actual=direct(w,z,T);
   directCalls+=actual.calls;
   ok(packed(w.observe(actual.z))===expected,"long transport");verified++;
   for(const wanted of [0,1]){
    const a=derived.choose(predicted,wanted),after=a?w.transition(2,actual.z):actual.z;
    ok(goal(translate(m,packed(w.observe(after))))===wanted,"transported action");actionChecks++;
   }
  }
  const bad=world(seed,true),badPairs=anchors.map(x=>[[x&15,x>>>4],bad.observe(bad.encode(x))]);
  const wrong=discover(badPairs,[0,1]);ok(wrong,"calibration must match");const badProof=verify(bad,wrong);ok(badProof.status==="DISTINGUISHABLE","hidden mutation accepted");
  runs.push({seed,pairedCalibration:anchors.length,individualSensors:"UNRESOLVED",coupledSensors:"CANDIDATE",evidence,verified,unseenAnchors:N-anchors.length,actionChecks,directCalls,targetNavigationCalls,hiddenMutation:badProof});
 }
 // Separate observer-refinement control: action policy cannot derive hidden
 // target state; two different nuisance states share the same observation.
 const w=world(17);ok(packed(w.observe(w.encode(25)))===packed(w.observe(w.encode(25)|256)),"hidden states visible");
 const strip=({choose,...rest})=>rest;
 return {horizon:T.toString(),word,sourceFormation:{transitionCells:3*N,wordCompositionCells:word.length*N,powerCompositions:compositions,powerCells:compositions*N},sensors:{left:strip(left),right:strip(right),fused:strip(fused),derived:strip(derived),policyChecks:512},runs,hiddenStateNotReconstructed:true};
}
if(require.main===module)console.log(JSON.stringify(experiment(),null,2));
module.exports={experiment};
