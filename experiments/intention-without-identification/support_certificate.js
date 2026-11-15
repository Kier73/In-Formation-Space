"use strict";
/* IWI-003 relevance support: a conservative set of uncertain cells visited by
 * some execution branch of a verified guaranteed policy. NOT a minimal set.
 */
const p=require("./partial_ground.js");
function certificate(input,report) {
 const model=p.validate(input);
 if(report.status!=="certain-within-horizon")
  return {status:"not-applicable-no-winning-policy",reason:"support is only certified for winning policies"};
 p.verify(input,report);
 const keys=new Set();
 let leafCount=0;
 function follow(b,tree) {
  if(tree.stop===true) {
   leafCount++;
   for(const world of b)for(const [key] of world.fixed)keys.add(key);
   return;
  }
  const outcomes=p.move(model,b,tree.action);
  if(outcomes.length!==tree.children.length)throw Error("policy branch mismatch");
  for(let i=0;i<outcomes.length;i++){
   if(outcomes[i].output!==tree.children[i].output)throw Error("output mismatch");
   follow(outcomes[i].belief,tree.children[i].plan);
  }
 }
 follow(p.seed(model),report.plan);
 const support=[...keys].sort();
 let assignments=1n;
 for(const key of support) {
  const [kind,first,second]=key.split(":");
  let choices;
  if(kind==="t"){
   const action=Number(first),state=Number(second);
   choices=model.next[action]?.[state];
  }else if(kind==="o")choices=model.output[Number(first)];
  else throw Error("unrecognized committed cell");
  if(!choices||choices.length<=1)throw Error("support includes non-uncertain cell");
  assignments*=BigInt(choices.length);
 }
 return {status:"verified-sufficient-support",keys:support,
  supportCellCount:support.length,possibleSupportAssignments:String(assignments),
  unresolvedUnusedCells:model.unknownCells-support.length,
  fullCompleteLaws:model.possibleLaws,terminalObservationLeaves:leafCount,
  minimumWorstCase:report.minimumWorstCase};
}
function audit(input,report,candidate) {
 const expected=certificate(input,report);
 if(JSON.stringify(candidate)!==JSON.stringify(expected))throw Error("invalid policy support certificate");
 return true;
}
function study() {
 const cases=[["remembered",p.fixtures.remembered,5],["erased_diagnostic",p.fixtures.unknowable,5],
  ["unvisited_24_unknown_cells",p.fixtures.unvisited,1]];
 return {experiment:"IWI-003-SUPPORT",claim:"conservative trace-local unknown-cell support of verified policies",
  cases:Object.fromEntries(cases.map(([name,m,h])=>[name,certificate(m,p.solve(m,h))]))};
}
module.exports={certificate,audit,study};
if(require.main===module)process.stdout.write(JSON.stringify(study(),null,2)+"\n");
