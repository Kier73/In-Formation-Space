"use strict";
// CLT-002 executable finite version-space experiment; no external dependencies.
function experiment(nativePrior = null) {
  const N=8,A=3,L=N*A;
  function assert(ok,msg){if(!ok)throw Error(msg)}
  const eq=(a,b)=>a.length===b.length&&a.every((v,i)=>v===b[i]);
  function original(z,a) {
    if(a===0)return (z+1)%8;
    if(a===2)return (z*z+1)%8;
    const x=(z>>1)&1,y=(z>>2)&1;
    return (z&1)|((x&y)<<1)|((x^y)<<2);
  }
  let priorReads=0;
  const prior=Array.from({length:L},(_,i)=>{priorReads++;return original(Math.floor(i/A),i%A)});
  if(nativePrior!==null){assert(eq(prior,nativePrior),"native CLT prior disagrees");}
  const retained=nativePrior===null?prior:nativePrior;
  const charts=[];
  for(let s=1;s<N;s+=2)for(let b=0;b<N;b++)charts.push([s,b]);
  let writes=0;
  const cleanMap=new Map(), editMap=new Map();
  function put(m,t){m.set(t.join(","),t);}
  for(const [s,b] of charts){
    const row=Array(L);
    for(let z=0;z<N;z++)for(let a=0;a<A;a++){
      row[((s*z+b)%N)*A+a]=(s*retained[z*A+a]+b)%N; writes++;
    }
    put(cleanMap,row);
  }
  const cleanWrites=writes, clean=[...cleanMap.values()];
  for(const row of clean){
    put(editMap,row);
    for(let i=0;i<L;i++)for(let v=0;v<N;v++){
      if(v===row[i])continue;
      const t=row.slice();t[i]=v;writes+=L+1;put(editMap,t);
    }
  }
  const robust=[...editMap.values()];
  // Oracle independently calculates the target action; no candidate row passed to learner.
  function source(s,b,edits=[]){
    let count=0;
    return {
      ask(i){
        if(!Number.isInteger(i)||i<0||i>=L)throw Error("invalid observation address");
        count++;
        const e=edits.find(([j])=>j===i);if(e)return e[1];
        let z=0;while((s*z+b)%N!==Math.floor(i/A))z++;
        return (s*original(z,i%A)+b)%N;
      },
      reads:()=>count
    };
  }
  // Uniform-prior expected residual cardinality: sum of squared bucket counts / |V|.
  function discover(bank,oracle,policy,budget=L){
    let versions=bank.slice(), reads=0, queries=[], asked=new Set(), observations=new Map();
    while(versions.length>1&&queries.length<budget){
      let best=-1, score=Infinity;
      for(let i=0;i<L;i++){
        if(asked.has(i))continue;
        if(policy==="passive"){best=i;break;}
        const bins=Array(N).fill(0);
        for(const t of versions){bins[t[i]]++;reads++;}
        const value=bins.reduce((sum,x)=>sum+x*x,0);
        if(value<score){best=i;score=value;}
      }
      if(best<0)break;
      const answer=oracle.ask(best);
      asked.add(best);observations.set(best,answer);queries.push(best);
      versions=versions.filter(t=>{reads++;return t[best]===answer;});
    }
    const status=versions.length===0?"REFUSE":versions.length===1?"CONDITIONAL":"AMBIGUOUS";
    return {status,remaining:versions.length,candidate:versions.length===1?versions[0]:null,queries,observations,reads};
  }
  // Full-domain independent source audit. Reuse observed cells, not cached predictions.
  function audit(result,oracle){
    if(result.status!=="CONDITIONAL")return {accepted:false,additional:0};
    let additional=0,accepted=true;
    for(let i=0;i<L;i++){
      const v=result.observations.has(i)?result.observations.get(i):oracle.ask(i);
      if(!result.observations.has(i))additional++;
      if(v!==result.candidate[i])accepted=false;
    }
    return {accepted,additional};
  }
  function aggregate(bank,cases,policy){
    let sum=0,max=0,min=L,work=0,full=0,accepted=0,auditReads=0;
    for(const [s,b,edits] of cases){
      const o=source(s,b,edits),res=discover(bank,o,policy);
      assert(res.status==="CONDITIONAL","in-family source unresolved");
      const q=o.reads();sum+=q;max=Math.max(max,q);min=Math.min(min,q);work+=res.reads;
      const checked=audit(res,o);assert(checked.accepted,"audit failed");
      accepted++;auditReads+=checked.additional;full+=o.reads();
      assert(o.reads()===L,"unrestricted audit must cover all cells");
    }
    return {cases:cases.length,queries:sum,min,max,candidateReads:work,auditReads,fullyAuditedReads:full,accepted};
  }
  const cases=charts.map(([s,b])=>[s,b,[]]);
  const mutated=charts.filter((_,i)=>i%2===0).map(([s,b],k)=>{
    const i=(k*7+5)%L,v=(source(s,b).ask(i)+1+k%7)%N;
    return [s,b,[[i,v]]];
  });
  const cleanActive=aggregate(clean,cases,"active"),cleanPassive=aggregate(clean,cases,"passive");
  const robustActive=aggregate(robust,cases,"active"),robustMutated=aggregate(robust,mutated,"active");
  const robustPassive=aggregate(robust,mutated,"passive");
  const zero=discover(clean,source(1,0),"active",0);
  assert(zero.status==="AMBIGUOUS"&&zero.remaining===clean.length,"zero-budget ambiguity");
  // An out-of-family law can agree with all actively acquired clean probes.
  const baseline=discover(clean,source(1,0),"active");
  const omitted=Array.from({length:L},(_,i)=>i).find(i=>!baseline.observations.has(i));
  assert(omitted!==undefined,"need unseen cell");
  const bad=source(1,0,[[omitted,(source(1,0).ask(omitted)+1)%N]]);
  const misleading=discover(clean,bad,"active");
  assert(misleading.status==="CONDITIONAL"&&eq(misleading.candidate,baseline.candidate),"expected indistinguishable prefix");
  assert(!audit(misleading,bad).accepted,"independent audit must reject hidden mutation");
  // Value absent from all candidates at selected cell yields explicit refusal.
  let refused=false;
  for(let i=0;i<L&&!refused;i++){
    const values=new Set(clean.map(t=>t[i]));
    for(let v=0;v<N;v++)if(!values.has(v)){
      const res=discover(clean,source(1,0,[[i,v]]),"passive");
      // A premature singleton may instead require independent rejection.
      if(res.status==="REFUSE"){refused=true;break;}
      if(res.status==="CONDITIONAL")assert(!audit(res,source(1,0,[[i,v]])).accepted,"invalid law admitted");
    }
  }
  // Repeated identical intention: prediction cost only after exact audit.
  const coldReads=cases.length*L;
  return {nativePrior:nativePrior!==null,priorReads,cleanCandidates:clean.length,robustCandidates:robust.length,cleanBuildWrites:cleanWrites,robustBuildWrites:writes,cleanActive,cleanPassive,robustActive,robustMutated,robustPassive,coldReads,zeroBudget:zero.status,hiddenMutation:{cell:omitted,conditionalPrefixAccepted:true,fullAuditRejected:true},explicitRefusalObserved:refused};
}
if (require.main === module) {
  const prior = process.argv[2] ? JSON.parse(require("node:fs").readFileSync(process.argv[2],"utf8")) : null;
  console.log(JSON.stringify(experiment(prior),null,2));
}
module.exports = {experiment};
