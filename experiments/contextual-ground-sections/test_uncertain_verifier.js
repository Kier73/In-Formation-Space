"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {fixtures,solve}=require("./sections.js");
const {makeGraph}=require("./scale.js");
const {analyze}=require("./uncertain.js");
const {verify}=require("./uncertain_verifier.js");
const copy=x=>JSON.parse(JSON.stringify(x));
const base=()=>{
  const f=fixtures()[0];return solve(5,f.vertices,f.edges,"A");
};
const finite=(id,maps,state="contested")=>({
  id,from:"A",to:"C",evidence_state:state,
  source_revision:"v17",domain:{kind:"finite",maps}
});
const any=(id)=>({
  id,from:"A",to:"C",evidence_state:"missing",
  source_revision:"v17",domain:{kind:"all-affine"}
});

test("direct-equation certificate auditor reconstructs six synthetic scenarios",()=>{
  const r=base(),parity={vertex:"A",kind:"parity"};
  const cases=[
    [any("one")],
    [any("one"),any("two")],
    [finite("two-even",[[2,0],[2,3]])],
    [finite("uncertain",[[2,0],[1,1]],"expired")],
    [finite("pin",[[2,0]],"unconfirmed")],
    [finite("a",[[2,0],[2,3]]),finite("b",[[2,0],[2,4]])]
  ];
  for(const edges of cases) {
    const claim=analyze(r,edges,parity);
    const evidence=verify(r,edges,parity,copy(claim));
    assert.equal(evidence.verified,true);
    assert.equal(evidence.external_authority_verified,false);
  }
});

test("an exact, undetermined intention and empty base reconstruct independently",()=>{
  for(const [i,edges] of [
    [0,[finite("even",[[2,0],[2,3]])]],
    [1,[any("future")]],
    [2,[any("future")]]
  ]) {
    const f=fixtures()[i],r=solve(5,f.vertices,f.edges,"A");
    const intent={vertex:"A",kind:"exact"};
    const c=analyze(r,edges,intent);
    assert.equal(verify(r,edges,intent,c).classification,c.classification);
  }
});

test("independent auditor rejects forged counts, examples and authority",()=>{
  const r=base(),e=[finite("two-even",[[2,0],[2,3]])],
    intent={vertex:"A",kind:"parity"};
  const claim=analyze(r,e,intent);
  const mutations=[
    c=>c.counts.consistent_worlds="3",
    c=>c.counts.inconsistent_worlds="1",
    c=>c.possible_root_count=1,
    c=>c.classification="conditional",
    c=>c.output_invariant_on_consistent_worlds=false,
    c=>c.can_admit=true,
    c=>c.edge_sources[0].source_revision="different",
    c=>c.edge_sources[0].identity_holonomy="99",
    c=>c.output_examples[0].value=1,
    c=>c.output_examples[0].root=1,
    c=>c.output_examples=[],
    c=>c.example_roots=[9],
    c=>c.source_schema="invented"
  ];
  for(const mutate of mutations){
    const c=copy(claim);mutate(c);
    assert.throws(()=>verify(r,e,intent,c),/invalid uncertain-world certificate/);
  }
});

test("independent direct equations agree with arithmetic verifier for all 36 two-edge F_3 map combinations",()=>{
  const r=solve(3,["A","B","C"],[
    {id:"ab",from:"A",to:"B",a:1,b:0},
    {id:"bc",from:"B",to:"C",a:1,b:0}
  ],"A");
  const maps=[];for(let a=1;a<3;a++)for(let b=0;b<3;b++)maps.push([a,b]);
  const target={vertex:"C",kind:"threshold",cutoff:2};
  let checked=0;
  for(const a of maps)for(const b of maps) {
    const edges=[finite("one",[a]),finite("two",[b])];
    const claim=analyze(r,edges,target);
    assert.equal(verify(r,edges,target,claim).verified,true);
    checked++;
  }
  assert.equal(checked,36);
});

test("large 1024-vertex/128-unknown-link count is independently reconstructed",()=>{
  const g=makeGraph(1024,"flat");
  const r=solve(g.p,g.vertices,g.edges,g.root);
  const pending=Array.from({length:128},(_,i)=>({
    id:"u"+i,from:g.root,to:g.vertices[100+i],evidence_state:"missing",
    source_revision:"synthetic",domain:{kind:"all-affine"}
  }));
  const intent={vertex:g.root,kind:"parity"};
  const report=analyze(r,pending,intent);
  const audit=verify(r,pending,intent,report);
  assert.equal(audit.verified,true);
  assert.equal(audit.external_authority_verified,false);
  assert.equal(audit.completions,
    (BigInt(g.p*(g.p-1))**128n).toString());
});
