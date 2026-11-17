"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {fixtures,solve,bruteForce,apply}=require("./sections.js");
const {makeGraph,FIELD}=require("./scale.js");
const {analyze}=require("./uncertain.js");

function record(i,p=5){
  const f=fixtures()[i];return solve(p,f.vertices,f.edges,"A");
}
const P=(id,kind="all-affine",maps=[],state="missing")=>({
  id,from:"A",to:"C",evidence_state:state,source_revision:"declared-revision-17",
  domain:kind==="all-affine"?{kind:"all-affine"}:{kind:"finite",maps}
});
function oracle(rec,pending,target) {
  const p=rec.field;
  const possibilities=pending.map(e=>{
    if(e.domain.kind==="finite")return e.domain.maps;
    const out=[];
    for(let a=1;a<p;a++)for(let b=0;b<p;b++)out.push([a,b]);
    return out;
  });
  const counts={all:0,singleton:0,empty:0};
  const roots=new Set(),outcomes=new Set();
  let worlds=0;
  function visit(i,chosen){
    if(i!==pending.length) {
      for(const pair of possibilities[i])visit(i+1,[...chosen,pair]);
      return;
    }
    worlds++;
    const edges=rec.edges.concat(chosen.map(([a,b],j)=>({
      id:pending[j].id,from:pending[j].from,to:pending[j].to,a,b
    })));
    const sections=bruteForce(p,rec.vertices,edges);
    if(sections.length===0)counts.empty++;
    else if(sections.length===p)counts.all++;
    else if(sections.length===1)counts.singleton++;
    else throw Error("unexpected oracle count");
    for(const section of sections) {
      roots.add(section[rec.root]);
      const v=section[target.vertex];
      outcomes.add(target.kind==="exact"?v:
        target.kind==="parity"?v%2:
        target.kind==="threshold"?Number(v>=target.cutoff):target.value);
    }
  }
  visit(0,[]);
  return {counts,roots:roots.size,outcomes:outcomes.size,worlds};
}
function compare(rec,pending,target) {
  const exact=analyze(rec,pending,target);
  const brute=oracle(rec,pending,target);
  assert.equal(Number(exact.counts.possible_completions),brute.worlds);
  assert.equal(Number(exact.counts.all_sections_worlds),brute.counts.all);
  assert.equal(Number(exact.counts.singleton_section_worlds),brute.counts.singleton);
  assert.equal(Number(exact.counts.inconsistent_worlds),brute.counts.empty);
  assert.equal(exact.possible_root_count,brute.roots);
  assert.equal(exact.output_invariant_on_consistent_worlds,
    brute.outcomes===1);
  assert.equal(exact.can_admit,false);
  return exact;
}

test("one and two missing affine cycle links: exact 0/1/p worlds match brute force",()=>{
  const r=record(0);
  const one=compare(r,[P("one")],{vertex:"A",kind:"exact"});
  assert.deepEqual(one.counts,{
    possible_completions:"20",all_sections_worlds:"1",
    singleton_section_worlds:"15",inconsistent_worlds:"4",
    consistent_worlds:"16"
  });
  assert.equal(one.classification,"conditional");
  const two=compare(r,[P("one"),P("two")],{vertex:"A",kind:"parity"});
  assert.deepEqual(two.counts,{
    possible_completions:"400",all_sections_worlds:"1",
    singleton_section_worlds:"75",inconsistent_worlds:"324",
    consistent_worlds:"76"
  });
  assert.equal(two.classification,"conditional");
});

test("all existing sections or none constrain future uncertain links",()=>{
  const pinned=compare(record(2),[P("pending")],{vertex:"A",kind:"exact"});
  assert.equal(pinned.counts.singleton_section_worlds,"4");
  assert.equal(pinned.counts.inconsistent_worlds,"16");
  assert.equal(pinned.possible_root_count,1);
  assert.equal(pinned.output_invariant_on_consistent_worlds,true);
  assert.equal(pinned.classification,"conditional");
  const impossible=compare(record(1),[P("pending")],{vertex:"A",kind:"constant",value:1});
  assert.equal(impossible.classification,"refuse-inconsistent");
  assert.equal(impossible.counts.inconsistent_worlds,"20");
});

test("multiple compatible worlds: parity intended result survives unknown phase",()=>{
  const r=record(0);
  const e=P("contested","finite",[[2,0],[2,3]],"contested");
  const parity=compare(r,[e],{vertex:"A",kind:"parity"});
  assert.equal(parity.classification,"robust");
  assert.equal(parity.output_examples[0].value,0);
  assert.equal(parity.possible_root_count,2);
  assert.equal(parity.counts.consistent_worlds,"2");
  assert.equal(parity.counts.inconsistent_worlds,"0");
  assert.equal(parity.can_admit,false);
  const full=compare(r,[e],{vertex:"A",kind:"exact"});
  assert.equal(full.classification,"undetermined");
  assert.equal(full.output_examples.length,2);
});

test("finite candidate worlds can be inconsistent, even if each link is invertible",()=>{
  const r=record(0);
  const first=P("first","finite",[[2,0],[2,3]],"contested");
  const second=P("second","finite",[[2,0],[2,4]],"expired");
  const result=compare(r,[first,second],{vertex:"C",kind:"parity"});
  assert.equal(result.classification,"conditional");
  assert.equal(result.counts.consistent_worlds,"1");
  assert.equal(result.counts.inconsistent_worlds,"3");
  const impossible=compare(r,[P("shift","finite",[[1,1]],"expired")],
    {vertex:"C",kind:"exact"});
  assert.equal(impossible.classification,"refuse-inconsistent");
});

test("exhaustive small p=3 world/domain combinations agree with direct assignments",()=>{
  const r=solve(3,["A","B","C"],[
    {id:"ab",from:"A",to:"B",a:1,b:0},
    {id:"bc",from:"B",to:"C",a:1,b:0}
  ],"A");
  const all=[];
  for(let a=1;a<3;a++)for(let b=0;b<3;b++)all.push([a,b]);
  for(let i=0;i<all.length;i++)for(let j=0;j<all.length;j++){
    compare(r,[P("one","finite",[all[i]]),P("two","finite",[all[j]])],
      {vertex:"A",kind:"parity"});
  }
  compare(r,[P("all")],{vertex:"A",kind:"threshold",cutoff:2});
});

test("verified 1024-host Ground supports pending completion counting without world enumeration",()=>{
  const graph=makeGraph(1024,"flat");
  const r=solve(graph.p,graph.vertices,graph.edges,graph.root);
  const edges=Array.from({length:128},(_,i)=>({
    id:"uncertain-"+i,from:graph.vertices[0],to:graph.vertices[100+i],
    evidence_state:"missing",source_revision:"hypothetical-snapshot",
    domain:{kind:"all-affine"}
  }));
  const report=analyze(r,edges,{vertex:graph.root,kind:"parity"});
  assert.equal(report.possible_root_count,FIELD);
  assert.equal(report.classification,"conditional");
  assert.equal(report.counts.all_sections_worlds,"1");
  assert.equal(report.counts.possible_completions,
    (BigInt(FIELD*(FIELD-1))**128n).toString());
  assert.equal(report.counts.consistent_worlds,
    (1n+BigInt(FIELD)*((BigInt(FIELD-1)**128n)-1n)).toString());
  assert.equal(report.can_admit,false);
});

test("all source-status tags remain declared, never silently certified",()=>{
  const r=record(0);
  for(const state of ["missing","contested","expired","unconfirmed"]){
    const q=analyze(r,[P(state,"finite",[[2,0]],state)],
      {vertex:"A",kind:"parity"});
    assert.equal(q.edge_sources[0].evidence_state,state);
    assert.equal(q.can_admit,false);
  }
});

test("invalid evidence metadata, repeated maps and forged base certificates refused",()=>{
  const r=record(0),target={vertex:"A",kind:"exact"};
  const err=e=>assert.throws(()=>analyze(r,[e],target),/invalid uncertain Ground/);
  err(P("x","finite",[]));
  err(P("x","finite",[[1,0],[1,0]]));
  err(P("x","finite",[[0,1]]));
  err({...P("x"),source_revision:""});
  err({...P("x"),evidence_state:"authenticated"});
  err({...P("x"),domain:{kind:"all-affine",maps:[[1,0]]}});
  assert.throws(()=>analyze({...r,section_count:999},[],target),
    /invalid section certificate/);
  assert.throws(()=>analyze(r,[P("x"),P("x")],target),
    /invalid uncertain Ground/);
});
