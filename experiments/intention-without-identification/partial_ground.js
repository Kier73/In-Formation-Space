"use strict";
/* IWI-003: exact lazy planning across static, incomplete finite transition and output laws.
 * Unknown entries are independent but fixed for each possible world.
 * Unused cells are not enumerated. All reported non-wins are depth-bounded.
 */
const IWI3 = "IWI-003";
function domain(value,top) {
 const vals=Array.isArray(value)?value:[value];
 if(!vals.length || vals.length>top)throw Error("empty/oversize domain");
 const seen=new Set();
 for(const v of vals){
   if(!Number.isInteger(v)||v<0||v>=top||seen.has(v))throw Error("invalid or duplicate domain entry");
   seen.add(v);
 }
 return [...vals].sort((a,b)=>a-b);
}
function validate(m) {
 if(!m||!Number.isInteger(m.n)||m.n<1||m.n>32||
    !Array.isArray(m.start)||!m.start.length||
    !Array.isArray(m.goal)||!m.goal.length||
    !Array.isArray(m.output)||m.output.length!==m.n||
    !Array.isArray(m.next)||m.next.length<1||m.next.length>8)throw Error("invalid model shape");
 const unique=(xs,top,label)=>{
  const seen=new Set();
  for(const x of xs){if(!Number.isInteger(x)||x<0||x>=top||seen.has(x))throw Error("invalid "+label);seen.add(x);}
  return [...xs].sort((a,b)=>a-b);
 };
 const start=unique(m.start,m.n,"start"),goal=unique(m.goal,m.n,"goal");
 const output=m.output.map(x=>domain(x,16));
 const next=m.next.map(row=>{
  if(!Array.isArray(row)||row.length!==m.n)throw Error("invalid transition row");
  return row.map(x=>domain(x,m.n));
 });
 let possibleLaws=1n,unknownCells=0;
 for(const d of [...output,...next.flat()]){possibleLaws*=BigInt(d.length);if(d.length>1)unknownCells++;}
 return {n:m.n,start,goal,output,next,possibleLaws:String(possibleLaws),unknownCells};
}
function insert(fixed,key,value) {
 const prior=fixed.find(pair=>pair[0]===key);
 if(prior)return prior[1]===value?fixed:null;
 return [...fixed,[key,value]].sort((a,b)=>a[0].localeCompare(b[0]));
}
function options(fixed,key,values){
 const prior=fixed.find(pair=>pair[0]===key);
 if(prior){
  if(!values.includes(prior[1]))throw Error("commitment outside permitted domain");
  return [{value:prior[1],fixed}];
 }
 if(values.length===1)return [{value:values[0],fixed}];
 return values.map(value=>({value,fixed:insert(fixed,key,value)}));
}
function canon(belief) {
 const map=new Map();
 for(const s of belief){
  if(!s||!Number.isInteger(s.s)||!Array.isArray(s.fixed))throw Error("invalid scenario");
  const key=JSON.stringify([s.s,s.fixed]);
  map.set(key,{s:s.s,fixed:s.fixed});
 }
 return [...map.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(x=>x[1]);
}
function seed(m){return canon(m.start.map(s=>({s,fixed:[]})));}
function move(m,belief,action,limits={}) {
 if(!Number.isInteger(action)||action<0||action>=m.next.length)throw Error("invalid action");
 const maxScenarios=limits.maxScenarios??20000;
 const groups=new Map();
 let generated=0;
 for(const world of belief) {
  for(const t of options(world.fixed,"t:"+action+":"+world.s,m.next[action][world.s])) {
   for(const o of options(t.fixed,"o:"+t.value,m.output[t.value])) {
    generated++;
    if(generated>maxScenarios)throw Error("scenario cap exceeded; result unresolved");
    const list=groups.get(o.value)??[];
    list.push({s:t.value,fixed:o.fixed});
    groups.set(o.value,list);
   }
  }
 }
 return [...groups.entries()].sort((a,b)=>a[0]-b[0])
  .map(([output,states])=>({output,belief:canon(states)}));
}
function terminal(m,belief) {return belief.length>0&&belief.every(x=>m.goal.includes(x.s));}
function makePlanner(m,maxDepth,opts={}) {
 if(!Number.isInteger(maxDepth)||maxDepth<0||maxDepth>16)throw Error("depth must be 0..16");
 const maxNodes=opts.maxNodes??60000,maxScenarios=opts.maxScenarios??20000;
 if(!Number.isInteger(maxNodes)||maxNodes<1||!Number.isInteger(maxScenarios)||maxScenarios<1)throw Error("invalid caps");
 const initial=seed(m),stats={uniqueDepthBeliefs:0,branchCalls:0,generatedBeliefWorlds:0,peakBeliefWorlds:initial.length};
 const cache=new Map();
 function visit(b,remaining) {
  const key=remaining+":"+JSON.stringify(b);
  if(cache.has(key))return cache.get(key);
  stats.uniqueDepthBeliefs++;
  if(stats.uniqueDepthBeliefs>maxNodes)throw Error("belief search cap exceeded; result unresolved");
  stats.peakBeliefWorlds=Math.max(stats.peakBeliefWorlds,b.length);
  if(terminal(m,b)){const ans={stop:true};cache.set(key,ans);return ans;}
  if(remaining===0){cache.set(key,null);return null;}
  for(let a=0;a<m.next.length;a++) {
   stats.branchCalls++;
   const kids=move(m,b,a,{maxScenarios});
   stats.generatedBeliefWorlds+=kids.reduce((x,c)=>x+c.belief.length,0);
   const children=[];
   let works=true;
   for(const k of kids){
    const result=visit(k.belief,remaining-1);
    if(!result){works=false;break;}
    children.push({output:k.output,plan:result});
   }
   if(works){const ans={action:a,children};cache.set(key,ans);return ans;}
  }
  cache.set(key,null);return null;
 }
 let winning=null,rank=null;
 for(let h=0;h<=maxDepth;h++){
  const answer=visit(initial,h);
  if(answer){winning=answer;rank=h;break;}
 }
 return {status:winning?"certain-within-horizon":"no-certain-policy-through-horizon",
    horizon:maxDepth,minimumWorstCase:rank,plan:winning,stats,
    initialPossibleStates:initial.length,possibleCompleteLaws:m.possibleLaws,
    unknownCells:m.unknownCells,fullCompletionsEnumerated:0};
}
function solve(input,maxDepth=5,opts={}) {return makePlanner(validate(input),maxDepth,opts);}
// Independent verifier: own transition expansion and commitment update, not move()/options().
function verify(input,report) {
 const m=validate(input),initial=seed(m);
 const maxScenarios=report?.limits?.maxScenarios??20000;
 function expand(b,a){
  const out=new Map(),all=[];
  for(const possible of b){
   const keyT="t:"+a+":"+possible.s,priorT=possible.fixed.find(x=>x[0]===keyT);
   const allowed=priorT?[priorT[1]]:m.next[a][possible.s];
   for(const d of allowed) {
    if(!m.next[a][possible.s].includes(d))throw Error("outside transition domain");
    const chosenT=priorT?possible.fixed:[...possible.fixed,[keyT,d]].sort((x,y)=>x[0].localeCompare(y[0]));
    const keyO="o:"+d,priorO=chosenT.find(x=>x[0]===keyO);
    const obs=priorO?[priorO[1]]:m.output[d];
    for(const o of obs){
     if(!m.output[d].includes(o))throw Error("outside observation domain");
     const chosenO=priorO?chosenT:[...chosenT,[keyO,o]].sort((x,y)=>x[0].localeCompare(y[0]));
     all.push({s:d,fixed:chosenO,output:o});
     if(all.length>maxScenarios)throw Error("verifier scenario cap exceeded");
    }
   }
  }
  for(const s of all){const group=out.get(s.output)??[];group.push({s:s.s,fixed:s.fixed});out.set(s.output,group);}
  return [...out.entries()].sort((a,b)=>a[0]-b[0]).map(([output,rows])=>({output,belief:canon(rows)}));
 }
 function walk(b,node,remaining){
  if(!node||typeof node!=="object")throw Error("missing policy node");
  if(node.stop===true){
    if(Object.keys(node).length!==1||!terminal(m,b))throw Error("false terminal claim");
    return;
  }
  if(remaining===0||terminal(m,b)||!Number.isInteger(node.action)||
     node.action<0||node.action>=m.next.length||
     !Array.isArray(node.children))throw Error("invalid policy action");
  const kids=expand(b,node.action);
  if(kids.length!==node.children.length)throw Error("missing or extra observation branch");
  for(let i=0;i<kids.length;i++) {
   if(node.children[i]?.output!==kids[i].output)throw Error("fabricated observation branch");
   walk(kids[i].belief,node.children[i].plan,remaining-1);
  }
 }
 // Separate exhaustive bounded-depth oracle, intentionally not using the planner's memo or transitions.
 const checked=new Map();
 function exists(b,depth){
  if(terminal(m,b))return true;
  if(depth===0)return false;
  const key=depth+"|"+JSON.stringify(b);
  if(checked.has(key))return checked.get(key);
  let result=false;
  for(let a=0;a<m.next.length;a++){
   if(expand(b,a).every(k=>exists(k.belief,depth-1))){result=true;break;}
  }
  checked.set(key,result);return result;
 }
 if(!report||!Number.isInteger(report.horizon)||report.horizon<0||report.horizon>16)throw Error("invalid report");
 if(report.status==="certain-within-horizon"){
  if(!Number.isInteger(report.minimumWorstCase)||report.minimumWorstCase<0||
     report.minimumWorstCase>report.horizon)throw Error("bad claimed rank");
  walk(initial,report.plan,report.minimumWorstCase);
  if(report.minimumWorstCase>0&&exists(initial,report.minimumWorstCase-1))throw Error("not minimal");
 }else if(report.status==="no-certain-policy-through-horizon"){
  if(report.plan!==null||report.minimumWorstCase!==null||exists(initial,report.horizon))
    throw Error("false bounded nonexistence");
 }else throw Error("unknown status");
 if(report.possibleCompleteLaws!==m.possibleLaws||report.unknownCells!==m.unknownCells||
    report.fullCompletionsEnumerated!==0||report.initialPossibleStates!==m.start.length)throw Error("misreported source scope");
 return {verified:true,scope:report.status,independentBeliefDepthChecks:checked.size};
}
// Fresh-effect comparison: Nature can pick an allowed successor afresh at *every use*.
// This is intentionally not equivalent to a static unknown deterministic law.
function freshEffects(input){
 const m=validate(input);
 if(m.n>12)throw Error("fresh-effects all-belief solver supports n<=12");
 const count=1<<m.n,rank=Array(count).fill(-1),policy=Array(count).fill(-1);
 const goalmask=m.goal.reduce((x,s)=>x|(1<<s),0);
 const startmask=m.start.reduce((x,s)=>x|(1<<s),0);
 function successor(b,a){
  const groups=Array(16).fill(0);
  for(let s=0;s<m.n;s++)if(b>>s&1)
    for(const d of m.next[a][s])
      for(const o of m.output[d])groups[o]|=1<<d;
  return groups.filter(Boolean);
 }
 for(let b=1;b<count;b++)if(!(b&~goalmask))rank[b]=0;
 for(let d=1;d<count;d++){
  const newOnes=[];
  for(let b=1;b<count;b++)if(rank[b]===-1)for(let a=0;a<m.next.length;a++){
    if(successor(b,a).every(c=>rank[c]>=0)){newOnes.push([b,a]);break;}
  }
  if(!newOnes.length)break;
  for(const [b,a] of newOnes){rank[b]=d;policy[b]=a;}
 }
 // Independently validate the full winning/losing partition, not only the root.
 for(let b=1;b<count;b++){
  if(rank[b]===0){if(b&~goalmask)throw Error("bad terminal");continue;}
  if(rank[b]<0){
   for(let a=0;a<m.next.length;a++)if(successor(b,a).every(c=>rank[c]>=0))throw Error("false fresh losing trap");
  }else{
   const kids=successor(b,policy[b]).map(c=>rank[c]);
   if(kids.some(k=>k<0)||1+Math.max(...kids)!==rank[b])throw Error("false fresh winner");
  }
 }
 return {rootRank:rank[startmask],winningBeliefCount:rank.filter(x=>x>=0).length};
}
function makeFixtures(){
 const n=7,trap=6,actions=5;
 const next=Array.from({length:actions},()=>Array(n).fill(trap));
 for(const row of next){row[0]=0;row[trap]=trap;}
 next[0][1]=[2,3]; // unknown but permanently fixed within each completion
 next[1][2]=4;next[1][3]=5; // diagnostics: O[4]!=O[5]
 next[2][4]=1;next[2][5]=1; // reset to source state
 next[3][2]=0;next[4][3]=0; // law-specific safe completion
 const remembered={n,start:[1],goal:[0],output:[3,0,0,0,1,2,0],next};
 const unknowable={...remembered,output:[3,0,0,0,0,0,0]};
 const large=26;
 const bigNext=[Array(large).fill(0),Array.from({length:large},(_,s)=>s)];
 for(let s=1;s<=24;s++)bigNext[1][s]=[s,s+1];
 const unvisited={n:large,start:Array.from({length:25},(_,i)=>i+1),goal:[0],
   output:Array(large).fill(0),next:bigNext};
 const micro={n:3,start:[1],goal:[0],output:[0,0,0],
   next:[[0,[1,2],1],[1,1,1]]};
 const unknownOutput={n:3,start:[1],goal:[0],output:[0,0,[0,1]],
   next:[[0,2,2],[1,1,1]]};
 return {remembered,unknowable,unvisited,micro,unknownOutput};
}
const fixtures=makeFixtures();
function study(){
 const cases=[
 ["remembered",fixtures.remembered,5],
 ["erased_diagnostic",fixtures.unknowable,5],
 ["unvisited_24_unknown_cells",fixtures.unvisited,1]
 ];
 return {experiment:IWI3,semantics:"static independent unknown transition/observation entries",
  results:Object.fromEntries(cases.map(([name,m,horizon])=>{
   const result=solve(m,horizon);const checked=verify(m,result);
   return [name,{model:m,report:result,verification:checked,
     freshEffects:m.n<=12?freshEffects(m):null}];
  }))};
}
module.exports={domain,validate,seed,move,terminal,solve,verify,freshEffects,fixtures,study};
if(require.main===module)process.stdout.write(JSON.stringify(study(),null,2)+"\n");
