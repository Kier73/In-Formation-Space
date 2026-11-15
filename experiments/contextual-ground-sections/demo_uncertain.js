"use strict";
const {solve,fixtures}=require("./sections.js");
const {makeGraph,FIELD}=require("./scale.js");
const {analyze}=require("./uncertain.js");
const edge=(id,state,domain)=>({
  id,from:"A",to:"C",evidence_state:state,
  source_revision:"synthetic-revision-17",domain
});
function demonstrate(){
  const f=fixtures()[0],r=solve(5,f.vertices,f.edges,"A");
  const exact={vertex:"A",kind:"exact"},parity={vertex:"A",kind:"parity"};
  const missing=edge("unknown-path","missing",{kind:"all-affine"});
  const contested=edge("contested-path","contested",
    {kind:"finite",maps:[[2,0],[2,3]]});
  const expired=edge("expired-path","expired",
    {kind:"finite",maps:[[2,0],[1,1]]});
  const cases=[
    ["one unconstrained edge",analyze(r,[missing],parity)],
    ["two unconstrained edges",analyze(r,[missing,
      {...missing,id:"second-unknown-path"}],parity)],
    ["two feasible, parity invariant",analyze(r,[contested],parity)],
    ["two feasible, exact state unknown",analyze(r,[contested],exact)],
    ["admissible candidate versus contradiction",analyze(r,[expired],parity)],
    ["one fixed candidate",analyze(r,[edge("fixed","unconfirmed",
      {kind:"finite",maps:[[2,0]]})],parity)]
  ];
  const g=makeGraph(1024,"flat");
  const base=solve(FIELD,g.vertices,g.edges,g.root);
  const pending=Array.from({length:128},(_,i)=>({
    id:"missing-"+i,from:g.root,to:g.vertices[10+i],
    evidence_state:"missing",source_revision:"synthetic-scaling",
    domain:{kind:"all-affine"}
  }));
  const giant=analyze(base,pending,{vertex:g.root,kind:"parity"});
  return {
    schema:"ifs.cgs005-demonstration/0.1",
    evidence:"deterministic synthetic model; no authenticated observer input",
    cases:cases.map(([name,x])=>({
      name,class:x.classification,completion_counts:x.counts,
      possible_root_count:x.possible_root_count,
      possible_output_examples:x.output_examples,
      authorized:x.can_admit
    })),
    scaling:{
      field:FIELD,vertices:g.vertices.length,original_edges:g.edges.length,
      uncertain_edges:pending.length,full_completion_count:giant.counts.possible_completions,
      consistent_completions:giant.counts.consistent_worlds,
      inconsistent_completions:giant.counts.inconsistent_worlds,
      roots:giant.possible_root_count,classification:giant.classification,
      assignment_enumeration:0,
      authenticated:false
    }
  };
}
module.exports={demonstrate};
if(require.main===module)process.stdout.write(JSON.stringify(demonstrate(),null,2)+"\n");
