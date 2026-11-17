"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const partial=require("./partial_ground.js");
const global=require("./global_oracle.js");
const base=require("./experiment.js");
const copy=v=>JSON.parse(JSON.stringify(v));
test("IWI-003 keeps a fixed law when the same unknown transition is revisited",()=>{
 const m=partial.validate(partial.fixtures.micro);
 const first=partial.move(m,partial.seed(m),0);
 assert.equal(first.length,1);assert.equal(first[0].belief.length,2);
 const again=partial.move(m,partial.move(m,first[0].belief,1)[0].belief,0);
 assert.equal(again.length,1);assert.equal(again[0].belief.length,2);
 for(const scenario of again[0].belief){
  const fixed=scenario.fixed.find(x=>x[0]==="t:0:1");
  assert.equal(fixed[1],scenario.s);
 }
});
test("unknown observation law stays fixed across repeated readings",()=>{
 const m=partial.validate(partial.fixtures.unknownOutput);
 const branches=partial.move(m,partial.seed(m),0);
 assert.deepEqual(branches.map(b=>b.output),[0,1]);
 for(const b of branches){
  const reset=partial.move(m,b.belief,1);
  const repeated=partial.move(m,reset[0].belief,0);
  assert.deepEqual(repeated.map(x=>x.output),[b.output]);
 }
});
test("static uncertain transition can be safely navigated in exactly five steps",()=>{
 const m=partial.fixtures.remembered,r=partial.solve(m,5);
 assert.equal(r.status,"certain-within-horizon");assert.equal(r.minimumWorstCase,5);
 assert.equal(partial.verify(m,r).verified,true);
 assert.equal(r.possibleCompleteLaws,"2");
});
test("a fresh adversarial choice is not the same as a static unknown law",()=>{
 assert.equal(partial.solve(partial.fixtures.remembered,5).minimumWorstCase,5);
 const r=partial.freshEffects(partial.fixtures.remembered);
 assert.equal(r.rootRank,-1);
});
test("erased diagnostics are globally impossible, not just outside five steps",()=>{
 const m=partial.fixtures.unknowable,r=partial.solve(m,5),g=global.globalOracle(m);
 assert.equal(r.status,"no-certain-policy-through-horizon");
 assert.equal(partial.verify(m,r).verified,true);
 assert.equal(g.status,"globally-impossible");
 assert(g.losingTrap.includes(g.initialMask));
 assert.equal(g.fullLawsEnumerated,2);
});
test("global oracle independently checks static five-step optimality",()=>{
 const r=global.globalOracle(partial.fixtures.remembered);
 assert.equal(r.status,"globally-winning");assert.equal(r.rootRank,5);
 assert.equal(r.fullLawsEnumerated,2);
 assert.equal(r.reachableBeliefs,13);
});
test("each completely specified law has a shorter individual winning strategy",()=>{
 const models=global.allLaws(partial.fixtures.remembered).laws;
 assert.equal(models.length,2);
 for(const law of models){
  const m={n:7,start:2,goal:1,next:law.next,output:law.output};
  const r=base.solve(m);
  assert.equal(base.audit(m,r),true);
  assert.equal(r.rank[m.start],2);
 }
});
test("lazy convergence covers 2^24 complete laws without materializing any",()=>{
 const m=partial.fixtures.unvisited,r=partial.solve(m,1);
 assert.equal(r.possibleCompleteLaws,"16777216");
 assert.equal(r.unknownCells,24);
 assert.equal(r.status,"certain-within-horizon");
 assert.equal(r.minimumWorstCase,1);
 assert.equal(r.fullCompletionsEnumerated,0);
 assert.equal(r.stats.uniqueDepthBeliefs,3);
 assert.equal(partial.verify(m,r).verified,true);
 assert.throws(()=>global.globalOracle(m));
});
test("root stop requires every possible current state to be a goal",()=>{
 const m={n:2,start:[0,1],goal:[0],output:[0,0],next:[[0,0]]};
 const r=partial.solve(m,1);assert.equal(r.minimumWorstCase,1);
 assert.throws(()=>partial.verify(m,{...r,minimumWorstCase:0,plan:{stop:true}}));
});
test("independent verifier rejects false terminal, missing branch and changed law",()=>{
 const m=partial.fixtures.remembered,r=partial.solve(m,5);
 const falseTerminal=copy(r);falseTerminal.plan={stop:true};
 assert.throws(()=>partial.verify(m,falseTerminal));
 const missing=copy(r);missing.plan.children=[];
 assert.throws(()=>partial.verify(m,missing));
 const changed=copy(m);changed.output[4]=0;changed.output[5]=0;
 assert.throws(()=>partial.verify(changed,r));
});
test("independent verifier rejects forged nonexistence and wrong minimum depth",()=>{
 const m=partial.fixtures.remembered,r=partial.solve(m,5);
 const forged={...r,status:"no-certain-policy-through-horizon",minimumWorstCase:null,plan:null};
 assert.throws(()=>partial.verify(m,forged));
 const nonminimal={...r,minimumWorstCase:6,horizon:6};
 assert.throws(()=>partial.verify(m,nonminimal));
});
test("invalid incomplete models and resource exhaustion fail closed",()=>{
 const m=partial.fixtures.micro;
 for(const bad of [
  {...m,start:[1,1]}, {...m,next:[[0,[2,2],1],[1,1,1]]},
  {...m,next:[[0,[1,5],1],[1,1,1]]}, {...m,output:[0,0,[]]},
  {...m,goal:[]}, {...m,n:33}
 ])assert.throws(()=>partial.solve(bad,3));
 assert.throws(()=>partial.solve(m,17));
 assert.throws(()=>partial.solve(m,3,{maxNodes:0}));
 assert.throws(()=>partial.solve(m,3,{maxScenarios:1}));
});
test("model claims about possible completions are audited",()=>{
 const m=partial.fixtures.unvisited,r=partial.solve(m,1);
 assert.throws(()=>partial.verify(m,{...r,possibleCompleteLaws:"1"}));
 assert.throws(()=>partial.verify(m,{...r,fullCompletionsEnumerated:16777216}));
});
test("recorded IWI-003 evidence exactly reconstructs",()=>{
 const p=path.join(__dirname,"results","partial_ground.json");
 assert.deepEqual(JSON.parse(fs.readFileSync(p,"utf8")),partial.study());
});
