"use strict";
/* IWI-004: exact symbolic-cost acquisition planning over static incomplete laws.
 * Queries are perfect OFFLINE law-cell oracles assumed by the model.
 * They are NOT live observations, physical receiver attestations, or authority.
 */
const p=require("./partial_ground.js");
const canon=x=>JSON.stringify(x);
const entitlement="perfect offline nonintervening exact static-cell oracle (not sample observation)";
function parseCell(model,key){
 const m=p.validate(model),bits=String(key).split(":");
 if(bits[0]==="t"&&bits.length===3&&/^(0|[1-9][0-9]*)$/.test(bits[1])&&/^(0|[1-9][0-9]*)$/.test(bits[2])){
  const a=Number(bits[1]),s=Number(bits[2]);
  if(!Number.isSafeInteger(a)||!Number.isSafeInteger(s)||a>=m.next.length||s>=m.n)throw Error("bad transition key");
  return {key,kind:"t",a,s,values:m.next[a][s]};
 }
 if(bits[0]==="o"&&bits.length===2&&/^(0|[1-9][0-9]*)$/.test(bits[1])){
  const s=Number(bits[1]);if(!Number.isSafeInteger(s)||s>=m.n)throw Error("bad output key");
  return {key,kind:"o",s,values:m.output[s]};
 }
 throw Error("malformed law-cell key");
}
function restrict(model,key,value){
 const m=p.validate(model),c=parseCell(model,key);
 if(!Number.isInteger(value)||!c.values.includes(value))throw Error("unsupported cell value");
 const next=m.next.map(row=>row.map(v=>v.slice())),output=m.output.map(v=>v.slice());
 if(c.kind==="t")next[c.a][c.s]=[value];else output[c.s]=[value];
 return {n:m.n,start:m.start,goal:m.goal,next,output};
}
function validateCaps(model,caps){
 if(!Array.isArray(caps)||caps.length>12)throw Error("bad acquisition catalogue");
 const seen=new Set();
 return caps.map(x=>{
  if(!x||typeof x.key!=="string"||x.scope!=="offline-static-law-cell"||
   !Number.isSafeInteger(x.cost)||x.cost<1||x.cost>10000||seen.has(x.key))
    throw Error("invalid or duplicate query capability");
  seen.add(x.key);parseCell(model,x.key);
  return {key:x.key,cost:x.cost,scope:x.scope};
 }).sort((x,y)=>x.key.localeCompare(y.key));
}
function measures(tree){
 if(tree.kind==="ready")return {cost:0,queries:0,actions:tree.actions,leaves:1};
 if(tree.kind!=="query"||!tree.children.length)throw Error("malformed strategy");
 const child=tree.children.map(c=>measures(c.plan));
 return {cost:tree.cost+Math.max(...child.map(c=>c.cost)),
  queries:1+Math.max(...child.map(c=>c.queries)),
  actions:Math.max(...child.map(c=>c.actions)),
  leaves:child.reduce((x,c)=>x+c.leaves,0)};
}
function plan(model,caps,horizon=5,maxQueries=2,limits={}){
 const m=p.validate(model),catalogue=validateCaps(model,caps);
 if(!Number.isInteger(horizon)||horizon<0||horizon>16||
  !Number.isInteger(maxQueries)||maxQueries<0||maxQueries>10)throw Error("bad horizons");
 const cap=limits.maxAcquisitionStates??3000;
 if(!Number.isInteger(cap)||cap<1)throw Error("bad search cap");
 const cache=new Map();let states=0,executionChecks=0;
 function search(current,available,remaining){
  const key=canon([current.next,current.output,remaining,available.map(x=>x.key)]);
  if(cache.has(key))return cache.get(key);
  if(++states>cap)throw Error("acquisition search cap exceeded; unresolved");
  const execution=p.solve(current,horizon);executionChecks++;
  if(execution.status==="certain-within-horizon"){
    const node={kind:"ready",actions:execution.minimumWorstCase,policy:execution.plan};
    cache.set(key,node);return node;
  }
  if(remaining===0){cache.set(key,null);return null;}
  let best=null,score=null;
  for(const c of available){
   const vals=parseCell(current,c.key).values;
   if(vals.length<2)continue;
   const rest=available.filter(x=>x.key!==c.key);
   const children=[];let feasible=true;
   for(const value of vals){
    const sub=search(restrict(current,c.key,value),rest,remaining-1);
    if(!sub){feasible=false;break;}
    children.push({value,plan:sub});
   }
   if(!feasible)continue;
   const candidate={kind:"query",key:c.key,cost:c.cost,children};
   const cost=measures(candidate);
   if(!score || cost.cost<score.cost ||
     (cost.cost===score.cost && (cost.queries<score.queries||
      (cost.queries===score.queries && c.key<best.key)))){
     best=candidate;score=cost;
   }
  }
  cache.set(key,best);return best;
 }
 const root=search(model,catalogue,maxQueries),value=root?measures(root):null;
 return {schema:"IWI-004/acquisition-v1",baseModel:p.validate(model),
  catalogue,entitlement,executionHorizon:horizon,maxQueries,
  status:root?(root.kind==="ready"?"READY":"REQUEST_LAW_EVIDENCE"):"UNRESOLVED_WITHIN_DECLARED_BOUNDS",
  tree:root,minimumWorstEvidenceCost:value?.cost??null,
  maximumQueries:value?.queries??null,worstExecutionActions:value?.actions??null,
  possibleCompleteLaws:m.possibleLaws,
  stats:{acquisitionStates:states,executionChecks}};
}
function verify(model,caps,r,expected={}){
 const m=p.validate(model),catalogue=validateCaps(model,caps);
 if(expected.executionHorizon!==undefined && r?.executionHorizon!==expected.executionHorizon)
   throw Error("execution intention horizon mismatch");
 if(expected.maxQueries!==undefined && r?.maxQueries!==expected.maxQueries)
   throw Error("authorized acquisition budget mismatch");
 if(!r||r.schema!=="IWI-004/acquisition-v1"||r.entitlement!==entitlement||
  canon(r.baseModel)!==canon(m)||canon(r.catalogue)!==canon(catalogue)||
  r.possibleCompleteLaws!==m.possibleLaws||
  !Number.isInteger(r.executionHorizon)||r.executionHorizon<0||r.executionHorizon>16||
  !Number.isInteger(r.maxQueries)||r.maxQueries<0||r.maxQueries>10)throw Error("unbound or malformed report");
 let readyLeaves=0;
 function inspect(current,available,remaining,tree){
  if(!tree||typeof tree!=="object")throw Error("missing strategy");
  if(tree.kind==="ready"){
   if(Object.keys(tree).sort().join(",")!=="actions,kind,policy")throw Error("unexpected terminal");
   const report=p.solve(current,r.executionHorizon);
   p.verify(current,report);
   if(report.status!=="certain-within-horizon"||tree.actions!==report.minimumWorstCase||
    canon(report.plan)!==canon(tree.policy))throw Error("false execution guarantee");
   readyLeaves++;return {cost:0,queries:0,actions:tree.actions};
  }
  const c=available.find(x=>x.key===tree.key);
  if(tree.kind!=="query"||remaining===0||!c||c.cost!==tree.cost||
   !Array.isArray(tree.children))throw Error("unauthorized query");
  const domain=parseCell(current,c.key).values,rest=available.filter(x=>x.key!==c.key);
  if(domain.length<2||tree.children.length!==domain.length)throw Error("missing query outcomes");
  const kids=[];
  for(let i=0;i<domain.length;i++){
   if(tree.children[i]?.value!==domain[i])throw Error("falsified query branch");
   kids.push(inspect(restrict(current,c.key,domain[i]),rest,remaining-1,tree.children[i].plan));
  }
  return {cost:c.cost+Math.max(...kids.map(x=>x.cost)),
   queries:1+Math.max(...kids.map(x=>x.queries)),
   actions:Math.max(...kids.map(x=>x.actions))};
 }
 if(r.status==="READY"||r.status==="REQUEST_LAW_EVIDENCE"){
  const metrics=inspect(model,catalogue,r.maxQueries,r.tree);
  if(r.minimumWorstEvidenceCost!==metrics.cost||r.maximumQueries!==metrics.queries||
   r.worstExecutionActions!==metrics.actions||
   (r.status==="READY")!==(r.tree.kind==="ready"))throw Error("false metrics/status");
 }else if(r.status==="UNRESOLVED_WITHIN_DECLARED_BOUNDS"){
  if(r.tree!==null||r.minimumWorstEvidenceCost!==null||r.maximumQueries!==null||
   r.worstExecutionActions!==null)throw Error("false nonexistence shape");
 }else throw Error("unrecognized status");
 // Independent alternate-choice enumeration to prove minimum cost or bounded impossibility.
 // Does not call the planner's search()/cache or trust its reported branch costs.
 const visited=new Map();
 function optimum(current,available,remaining){
  const k=canon([current.next,current.output,remaining,available.map(c=>c.key)]);
  if(visited.has(k))return visited.get(k);
  if(p.solve(current,r.executionHorizon).status==="certain-within-horizon"){visited.set(k,0);return 0;}
  if(remaining===0){visited.set(k,null);return null;}
  let best=null;
  for(const c of available){
   const values=parseCell(current,c.key).values;
   if(values.length<2)continue;
   const rest=available.filter(x=>x.key!==c.key);
   const costs=values.map(v=>optimum(restrict(current,c.key,v),rest,remaining-1));
   if(costs.some(v=>v===null))continue;
   const cost=c.cost+Math.max(...costs);
   if(best===null||cost<best)best=cost;
  }
  visited.set(k,best);return best;
 }
 const opt=optimum(model,catalogue,r.maxQueries);
 if(opt!==r.minimumWorstEvidenceCost)throw Error("failed independent cost/no-plan oracle");
 return {verified:true,exactMinimumWorstCost:opt,independentQueryStates:visited.size,
  verifiedExecutionLeaves:readyLeaves};
}
const fixtures={
 needed:{model:p.fixtures.unknowable,caps:[{key:"t:0:1",cost:2,scope:"offline-static-law-cell"}],horizon:3,queries:1},
 prohibited:{model:p.fixtures.unknowable,caps:[],horizon:3,queries:1},
 already_observable:{model:p.fixtures.remembered,caps:[{key:"t:0:1",cost:2,scope:"offline-static-law-cell"}],horizon:5,queries:1},
 irrelevant:{model:p.fixtures.unvisited,caps:[{key:"t:1:1",cost:1,scope:"offline-static-law-cell"}],horizon:1,queries:1}
};
function study(){
 return {experiment:"IWI-004",note:"offline perfect law-cell queries are hypothetical authorization-specific capabilities",
  cases:Object.fromEntries(Object.entries(fixtures).map(([name,f])=>{
   const report=plan(f.model,f.caps,f.horizon,f.queries);
   return [name,{report,verification:verify(f.model,f.caps,report)}];
  }))};
}
module.exports={parseCell,restrict,validateCaps,measures,plan,verify,fixtures,study};
if(require.main===module)process.stdout.write(JSON.stringify(study(),null,2)+"\n");
