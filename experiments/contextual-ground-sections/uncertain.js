"use strict";

/* CGS-005: conditional global sections under declared uncertain edge maps.
 *
 * Work is over an already mathematically verified, connected affine-field Ground.
 * Unknown, contested, or expired maps are explicit *possible completions*,
 * never trusted facts. No cryptographic or real-sensor authority is inferred.
 *
 * Core formula for base ALL and independent edge domains D_i:
 * F_i(x) = number of maps in D_i whose induced root holonomy fixes x
 * I_i    = number whose induced root holonomy is identity
 * ALL worlds       = product I_i
 * nonempty worlds  = sum_x product F_i(x) - (p-1)*product I_i
 * singleton worlds = nonempty - all
 *
 * Products count combinations, NOT probabilities. Uniform "all-affine" edge
 * domains are represented symbolically, not by constructing p(p-1) maps.
 */
const {multiply, inverse, apply, mod} = require("./sections.js");
const {verify} = require("./verifier.js");

function fail(s){throw new Error("invalid uncertain Ground: "+s);}
function mapClass(h,p) {
  if(h[0]===1 && h[1]===0) return {kind:"any"};
  if(h[0]===1) return {kind:"none"};
  const d = inverse([mod(h[0]-1,p),0],p)[0];
  return {kind:"point", value:mod(-h[1]*d,p)};
}
function summary(record, pending) {
  verify(record); // refuse forged or internally inconsistent base reports
  if(!Array.isArray(pending) || pending.length>4096) fail("pending edges invalid");
  const p=record.field, vertices=new Set(record.vertices);
  const ids=new Set(record.edges.map(e=>e.id));
  const labels=new Set(["missing","contested","expired","unconfirmed"]);
  const entries=[];
  for(const e of pending) {
    if(!e || typeof e.id!=="string" || !e.id || ids.has(e.id) ||
       !vertices.has(e.from) || !vertices.has(e.to) ||
       !labels.has(e.evidence_state) || typeof e.source_revision!=="string" ||
       !e.source_revision || !e.domain) fail("pending edge metadata");
    ids.add(e.id);
    const u=record.tree_maps[e.from],v=record.tree_maps[e.to];
    const hFor = pair => multiply(inverse(v,p),multiply(pair,u,p),p);
    let total,identity,none,uniform,points=new Map(),kind=e.domain.kind;
    if(kind==="all-affine") {
      if(Object.keys(e.domain).length!==1) fail("all-affine domain must be unqualified");
      total=BigInt(p*(p-1));identity=1n;none=BigInt(p-1);
      uniform=BigInt(p-2);
    } else if(kind==="finite") {
      const maps=e.domain.maps;
      if(!Array.isArray(maps) || maps.length<1 || maps.length>5000)
        fail("finite map domain length");
      const seen=new Set();
      total=BigInt(maps.length);identity=0n;none=0n;uniform=0n;
      for(const pair of maps) {
        if(!Array.isArray(pair) || pair.length!==2 ||
           !Number.isInteger(pair[0]) || !Number.isInteger(pair[1]) ||
           pair[0]<1 || pair[0]>=p || pair[1]<0 || pair[1]>=p ||
           seen.has(pair.join(","))) fail("invalid or repeated candidate map");
        seen.add(pair.join(","));
        const c=mapClass(hFor(pair),p);
        if(c.kind==="any") identity++;
        else if(c.kind==="none") none++;
        else points.set(c.value,(points.get(c.value)||0n)+1n);
      }
    } else fail("unsupported edge map domain");
    entries.push({id:e.id,from:e.from,to:e.to,evidence_state:e.evidence_state,
      source_revision:e.source_revision,kind,total,identity,none,uniform,points});
  }
  return entries;
}

function queryOutput(record,target,x) {
  const p=record.field;
  const v=apply(record.tree_maps[target.vertex],x,p);
  if(target.kind==="exact")return v;
  if(target.kind==="parity")return v%2;
  if(target.kind==="threshold")return Number(v>=target.cutoff);
  if(target.kind==="constant")return target.value;
  fail("unknown target kind");
}
function analyze(record, pending, target) {
  const es=summary(record,pending),p=record.field;
  if(!target || typeof target.vertex!=="string" ||
     !Object.hasOwn(record.tree_maps,target.vertex) ||
     !["exact","parity","threshold","constant"].includes(target.kind) ||
     (target.kind==="threshold" &&
       (!Number.isInteger(target.cutoff) || target.cutoff<1 || target.cutoff>=p)) ||
     (target.kind==="constant" &&
       (!Number.isSafeInteger(target.value) || target.value<0 || target.value>=p)))
    fail("invalid intention");
  let domainTotal=1n,allMaps=1n,background=1n;
  const exceptions=new Set();
  for(const e of es) {
    domainTotal*=e.total;
    allMaps*=e.identity;
    background*=e.identity+e.uniform;
    for(const x of e.points.keys())exceptions.add(x);
  }
  function fixingCount(x) {
    let n=1n;
    for(const e of es){
      n*=e.identity+e.uniform+(e.points.get(x)||0n);
      if(n===0n)break;
    }
    return n;
  }
  let worldsAll=0n,worldsSingleton=0n,worldsEmpty=0n;
  let rootCount=0;
  let rootKind="none";
  let roots=[];
  if(record.status==="empty") {
    worldsEmpty=domainTotal;
  } else if(record.status==="singleton") {
    const x=record.root_value;
    worldsSingleton=fixingCount(x);
    worldsEmpty=domainTotal-worldsSingleton;
    rootCount=worldsSingleton>0n?1:0;
    rootKind=rootCount?"listed":"none";
    roots=rootCount?[x]:[];
  } else {
    let sumFix=BigInt(p-exceptions.size)*background;
    for(const x of exceptions)sumFix+=fixingCount(x);
    worldsAll=allMaps;
    worldsSingleton=sumFix-BigInt(p)*worldsAll;
    worldsEmpty=domainTotal-worldsAll-worldsSingleton;
    if(worldsSingleton<0n||worldsEmpty<0n)fail("inconsistent count algebra");
    if(background>0n){
      rootCount=p;rootKind="all";
    }else{
      roots=[...exceptions].filter(x=>fixingCount(x)>0n).sort((a,b)=>a-b);
      rootCount=roots.length;
      rootKind=rootCount?"listed":"none";
    }
  }
  const feasible=worldsAll+worldsSingleton;
  if(feasible===0n && rootCount!==0) fail("feasible root mismatch");
  const results=[];
  const examples=[];
  const candidates=rootKind==="all"?
    Array.from({length:p},(_,i)=>i):roots;
  for(const x of candidates) {
    if(!results.some(y=>y.value===queryOutput(record,target,x))) {
      const value=queryOutput(record,target,x);
      results.push({value,root:x});
    }
    if(examples.length<3) examples.push(x);
    if(results.length===2)break;
  }
  const determined=results.length===1;
  const classification=feasible===0n?"refuse-inconsistent":
    worldsEmpty>0n?"conditional":
    determined?"robust":"undetermined";
  return {
    schema:"ifs.uncertain-ground-worlds/0.1",
    source_schema:record.schema,field:p,
    intention:target,
    edge_sources:es.map(e=>({id:e.id,evidence_state:e.evidence_state,
      source_revision:e.source_revision,domain:e.kind,
      candidate_maps:e.total.toString(),
      identity_holonomy:e.identity.toString(),
      empty_fixpoint:e.none.toString()})),
    counts:{possible_completions:domainTotal.toString(),
      all_sections_worlds:worldsAll.toString(),
      singleton_section_worlds:worldsSingleton.toString(),
      inconsistent_worlds:worldsEmpty.toString(),
      consistent_worlds:feasible.toString()},
    possible_root_count:rootCount,
    possible_root_kind:rootKind,
    example_roots:examples,
    output_examples:results,
    output_invariant_on_consistent_worlds:determined,
    classification,
    // Operational admissibility is stricter than mathematical feasibility.
    mathematically_invariant:classification==="robust",
    can_admit:false, // no external authenticity/authority proof in this experiment
    epistemic_scope:"declared alternatives; unsigned, unauthenticated, and unmeasured"
  };
}
module.exports={mapClass,summary,analyze};
