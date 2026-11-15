"use strict";
const {multiply, inverse, solve} = require("./sections.js");
const {verify} = require("./verifier.js");

const FIELD = 65521; // prime; largest supported in this finite experiment.
const ID = i => "v" + String(i).padStart(5,"0");
const edge = (id,from,to,ab) =>
  ({id,from,to,a:ab[0],b:ab[1]});

/*
 * Construct an exact family of "virtual" Ground graphs with n vertices.
 * The chart of vertex i is P_i(x) = (i+1)*x + 37*i (mod FIELD).
 * All initial links are derived from P_to o P_from^-1.
 *
 * A single altered chord imposes the root holonomy 2x+5, which has
 * exactly one fixed point. A second altered chord imposes x+1,
 * leaving no root point. No assignment space is enumerated.
 */
function makeGraph(n, mode="flat") {
  if (!Number.isInteger(n) || n < 4 || n > 8192 ||
      !["flat","pinned","empty"].includes(mode))
    throw new Error("invalid scale fixture");
  const p=FIELD;
  const vertices=Array.from({length:n},(_,i)=>ID(i));
  const maps=Array.from({length:n},(_,i)=>[i+1,(37*i)%p]);
  const edges=[];
  for(let i=1;i<n;i++){
    const t=multiply(maps[i],inverse(maps[i-1],p),p);
    edges.push(edge("tree"+String(i).padStart(5,"0"),vertices[i-1],vertices[i],t));
  }
  for(let i=2;i<n;i++){
    let holonomy=[1,0];
    if(mode!=="flat" && i===n-2) holonomy=[2,5];
    if(mode==="empty" && i===n-1) holonomy=[1,1];
    const t=multiply(maps[i],
      multiply(holonomy,inverse(maps[0],p),p),p);
    edges.push(edge("chord"+String(i).padStart(5,"0"),vertices[0],vertices[i],t));
  }
  return {p,vertices,edges,root:vertices[0],mode};
}
function experiment(n=1024) {
  return ["flat","pinned","empty"].map(mode=>{
    const graph=makeGraph(n,mode);
    const start=process.hrtime.bigint();
    const record=solve(graph.p,graph.vertices,graph.edges,graph.root);
    const verdict=verify(record);
    const elapsed=Number(process.hrtime.bigint()-start)/1e6;
    const expected=mode==="flat"?FIELD:mode==="pinned"?1:0;
    if(verdict.section_count!==expected)
      throw new Error("scale fixture violated exact expected classification");
    if(mode==="pinned" && record.root_value!==FIELD-5)
      throw new Error("unexpected pinned root point");
    return {mode,field:FIELD,vertices:n,edges:graph.edges.length,
      fundamental_cycles:record.cycles.length,
      section_count:verdict.section_count,flat:verdict.flat,
      solver_and_verifier_ms:Math.round(elapsed*1000)/1000,
      independent_arithmetic_verifier:verdict.verified,
      enumerated_assignments:0};
  });
}
module.exports={FIELD,makeGraph,experiment};
if(require.main===module) {
  const n=process.argv[2]===undefined?1024:Number(process.argv[2]);
  process.stdout.write(JSON.stringify(experiment(n),null,2)+"\n");
}
