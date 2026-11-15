"use strict";
/*
 * CGS-006: separate reconstruction of conditional-world claims.
 * Does not import uncertain.js or its holonomy classification.
 *
 * For a candidate edge map y=a*x+b, directly substitute the producer's
 * (CGS-003-verified) root charts: a*(P_u(x))+b = P_v(x).
 * Solve this one-variable affine equation using extended Euclid.
 */
const {verify:verifyBase}=require("./verifier.js");
const m=(a,p)=>((a%p)+p)%p;
function fail(s){throw Error("invalid uncertain-world certificate: "+s);}
function inv(a,p) {
  let r=p,nr=a,t=0,nt=1;
  while(nr!==0){
    const q=Math.floor(r/nr);
    [r,nr]=[nr,r-q*nr];[t,nt]=[nt,t-q*nt];
  }
  if(r!==1)fail("not invertible");
  return m(t,p);
}
function expected(record,pending,target) {
  verifyBase(record);
  const p=record.field,vertexSet=new Set(record.vertices),
    ids=new Set(record.edges.map(e=>e.id));
  if(!Array.isArray(pending)||pending.length>4096||
     !target || !Object.hasOwn(record.tree_maps,target.vertex) ||
     !["exact","parity","threshold","constant"].includes(target.kind) ||
     (target.kind==="threshold" &&
        (!Number.isInteger(target.cutoff)||target.cutoff<1||target.cutoff>=p))||
     (target.kind==="constant" &&
        (!Number.isSafeInteger(target.value)||target.value<0||target.value>=p)))
    fail("invalid target or pending collection");
  let total=1n,all=1n,baseline=1n;
  const branches=[],special=new Set(),edgeSources=[];
  for(const e of pending) {
    if(!e||typeof e.id!=="string"||!e.id||ids.has(e.id)||
       !vertexSet.has(e.from)||!vertexSet.has(e.to)||
       !["missing","contested","expired","unconfirmed"].includes(e.evidence_state)||
       typeof e.source_revision!=="string"||!e.source_revision||
       !e.domain)fail("invalid evidence entry");
    ids.add(e.id);
    const pu=record.tree_maps[e.from],pv=record.tree_maps[e.to];
    let n,any=0n,none=0n,uniform=0n,pts=new Map(),domain=e.domain;
    if(domain.kind==="all-affine") {
      if(Object.keys(domain).length!==1)fail("unqualified all-affine");
      n=BigInt(p*(p-1));any=1n;none=BigInt(p-1);uniform=BigInt(p-2);
    }else if(domain.kind==="finite"&&Array.isArray(domain.maps)&&
      domain.maps.length>=1&&domain.maps.length<=5000){
      const seen=new Set();n=BigInt(domain.maps.length);
      for(const f of domain.maps) {
        if(!Array.isArray(f)||f.length!==2||f.some(x=>!Number.isInteger(x))||
           f[0]<1||f[0]>=p||f[1]<0||f[1]>=p||
           seen.has(f.join(",")))fail("invalid map alternatives");
        seen.add(f.join(","));
        // Independent direct equation: coefficient*x = right
        const coeff=m(f[0]*pu[0]-pv[0],p);
        const right=m(pv[1]-f[0]*pu[1]-f[1],p);
        if(coeff===0 && right===0)any++;
        else if(coeff===0)none++;
        else {
          const x=m(right*inv(coeff,p),p);
          pts.set(x,(pts.get(x)||0n)+1n);
        }
      }
    }else fail("invalid finite/entire map domain");
    const branch={any,uniform,pts};
    branches.push(branch);
    total*=n;all*=any;baseline*=any+uniform;
    for(const x of pts.keys())special.add(x);
    edgeSources.push({id:e.id,evidence_state:e.evidence_state,
      source_revision:e.source_revision,domain:domain.kind,
      candidate_maps:n.toString(),
      identity_holonomy:any.toString(),empty_fixpoint:none.toString()});
  }
  const numFix=x=>{
    let n=1n;
    for(const q of branches)n*=q.any+q.uniform+(q.pts.get(x)||0n);
    return n;
  };
  let flat=0n,single=0n,empty=0n,rootCount=0,kind="none",roots=[];
  if(record.status==="empty")empty=total;
  else if(record.status==="singleton"){
    single=numFix(record.root_value);empty=total-single;
    if(single>0n){rootCount=1;kind="listed";roots=[record.root_value];}
  }else {
    flat=all;
    let pairCount=BigInt(p-special.size)*baseline;
    for(const x of special)pairCount+=numFix(x);
    single=pairCount-BigInt(p)*flat;empty=total-flat-single;
    if(single<0n||empty<0n)fail("world-count contradiction");
    if(baseline>0n){rootCount=p;kind="all";}
    else{
      roots=[...special].filter(x=>numFix(x)>0n).sort((a,b)=>a-b);
      rootCount=roots.length;kind=rootCount?"listed":"none";
    }
  }
  const viable=flat+single;
  function output(x) {
    const chart=record.tree_maps[target.vertex];
    const y=m(chart[0]*x+chart[1],p);
    switch(target.kind){
      case "exact":return y;
      case "parity":return y%2;
      case "threshold":return Number(y>=target.cutoff);
      case "constant":return target.value;
    }
  }
  let invariant=false;
  if(viable>0n){
    if(rootCount===1||target.kind==="constant")invariant=true;
    else if(kind==="all")invariant=false; // bijective chart covers all field residues
    else invariant=roots.every(x=>output(x)===output(roots[0]));
  }
  const classification=viable===0n?"refuse-inconsistent":
    empty>0n?"conditional":
    invariant?"robust":"undetermined";
  return {counts:{
      possible_completions:total.toString(),
      all_sections_worlds:flat.toString(),
      singleton_section_worlds:single.toString(),
      inconsistent_worlds:empty.toString(),
      consistent_worlds:viable.toString()
    },classification,rootCount,kind,invariant,edgeSources,
    roots,output,numFix,viable};
}
function verify(record,pending,target,claim){
  const r=expected(record,pending,target);
  if(!claim || claim.schema!=="ifs.uncertain-ground-worlds/0.1"||
     claim.source_schema!==record.schema||claim.field!==record.field||
     JSON.stringify(claim.intention)!==JSON.stringify(target)||
     JSON.stringify(claim.counts)!==JSON.stringify(r.counts)||
     JSON.stringify(claim.edge_sources)!==JSON.stringify(r.edgeSources)||
     claim.possible_root_count!==r.rootCount||
     claim.possible_root_kind!==r.kind||
     claim.output_invariant_on_consistent_worlds!==r.invariant||
     claim.classification!==r.classification||
     claim.mathematically_invariant!==(r.classification==="robust")||
     claim.can_admit!==false)fail("forged scope, count, classification, or source");
  const examples=claim.output_examples;
  if(!Array.isArray(examples)||examples.length!==(r.viable===0n?0:r.invariant?1:2))
    fail("wrong intention witness size");
  const seen=new Set();
  for(const w of examples){
    if(!w||!Number.isInteger(w.root)||w.root<0||w.root>=record.field||
       (r.kind==="listed"&&!r.roots.includes(w.root))||
       r.numFix(w.root)===0n||w.value!==r.output(w.root)||
       seen.has(w.value))fail("invalid intention witness");
    seen.add(w.value);
  }
  if(!Array.isArray(claim.example_roots)||claim.example_roots.some(x=>
       !Number.isInteger(x)||x<0||x>=record.field||
       (r.kind==="listed"&&!r.roots.includes(x))||r.numFix(x)===0n))
    fail("invalid root example");
  return {verified:true,domain:"declared synthetic map alternatives",
    independent_equation_check:true,completions:r.counts.possible_completions,
    classification:r.classification,external_authority_verified:false};
}
module.exports={verify};
