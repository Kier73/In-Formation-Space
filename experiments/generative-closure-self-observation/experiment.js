"use strict";
function experiment(){
  const P=257, mod=x=>((x%P)+P)%P, assert=(v,m)=>{if(!v)throw Error(m)};
  const rng=s=>()=>{s^=s<<13;s^=s>>>17;s^=s<<5;return s>>>0};
  const mat=(n,f)=>Array.from({length:n},(_,i)=>Array.from({length:n},(_,j)=>f(i,j)));
  const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const arms=["r1","r2","r3","c1","c2","c3"];
  const n=48,q=128,N=n*n,base=2*N;
  const nnz=A=>A.reduce((s,r)=>s+r.filter(x=>x!==0).length,0);
  function at(A,axis,i,j,t){return axis==="r"?(i>=t?A[i-t][j]:0):(j>=t?A[i][j-t]:0)}
  function field(L,x){L.u++;return mod(x)}
  function inverse(a,L){let b=P-2,r=1;while(b){if(b&1)r=field(L,r*a);a=field(L,a*a);b>>=1}return r}
  function solve(M,k,L){
    M=M.map(r=>r.slice());
    for(let j=0;j<k;j++){
      let p=j;while(p<k&&!M[p][j]){L.u++;p++}if(p===k)return null;
      [M[j],M[p]]=[M[p],M[j]];
      let inv=inverse(M[j][j],L);for(let t=j;t<=k;t++)M[j][t]=field(L,M[j][t]*inv);
      for(let i=0;i<k;i++)if(i!==j){let a=M[i][j];for(let t=j;t<=k;t++){let z=field(L,a*M[j][t]);M[i][t]=field(L,M[i][t]-z)}}
    }return M.map(r=>r[k])
  }
  function transform(A,axis,theta,L){
    return mat(n,(i,j)=>{let x=A[i][j];L.u++;for(let t=1;t<=theta.length;t++){L.u++;let z=field(L,theta[t-1]*at(A,axis,i,j,t));x=field(L,x-z)}return x})
  }
  function reconstruct(E,axis,theta,L){
    const A=mat(n,()=>0);
    for(let i=0;i<n;i++)for(let j=0;j<n;j++){let x=E[i][j];L.u++;for(let t=1;t<=theta.length;t++){L.u++;let z=field(L,theta[t-1]*at(A,axis,i,j,t));x=field(L,x+z)}A[i][j]=x}
    return A
  }
  function appCost(E,k){return 2*nnz(E)+2*Array.from({length:k},(_,i)=>n-i-1).reduce((a,b)=>a+b,0)}
  function apply(E,axis,theta,b){
    const k=theta.length,x=b.slice();let ops=0;
    if(axis==="c")for(let j=n-1;j>=0;j--)for(let t=1;t<=k&&j+t<n;t++){x[j]=mod(x[j]+theta[t-1]*x[j+t]);ops+=2}
    const y=E.map(row=>row.reduce((s,v,j)=>{if(v){ops+=2;return mod(s+v*x[j])}return s},0));
    if(axis==="r")for(let i=0;i<n;i++)for(let t=1;t<=k&&i>=t;t++){y[i]=mod(y[i]+theta[t-1]*y[i-t]);ops+=2}
    assert(ops===appCost(E,k),"application ledger");return y
  }
  function propose(A,arm,seed){
    const axis=arm[0],k=+arm[1],g=rng(seed),L={u:0};
    const coord=()=>{let i=g()%n,j=g()%n;if(axis==="r")i=k+g()%(n-k);else j=k+g()%(n-k);return [i,j]};
    const sample=Array.from({length:48},coord);
    let best=null,score=0;
    for(let trial=0;trial<8;trial++){
      const M=Array.from({length:k},()=>{const [i,j]=coord();L.u+=k+1;return [...Array.from({length:k},(_,t)=>at(A,axis,i,j,t+1)),A[i][j]]});
      const theta=solve(M,k,L);if(!theta)continue;
      if(theta[k-1]===0)continue; // canonical order
      let hits=0;
      for(const [i,j] of sample){let x=A[i][j];L.u++;for(let t=1;t<=k;t++){L.u++;let z=field(L,theta[t-1]*at(A,axis,i,j,t));x=field(L,x-z)}if(x===0)hits++;L.u++}
      if(hits>score){score=hits;best=theta}
    }
    // separate validation sample; no reuse of the fitting/ranking sample
    let valid=0;
    if(best)for(let z=0;z<48;z++){let [i,j]=coord(),x=A[i][j];L.u++;for(let t=1;t<=k;t++){L.u++;let v=field(L,best[t-1]*at(A,axis,i,j,t));x=field(L,x-v)}if(!x)valid++;L.u++}
    return {arm,axis,k,theta:best,score,valid,cost:L.u}
  }
  function make(f,seed){
    const g=rng(seed),v=()=>1+g()%(P-1);
    if(f==="random")return {A:mat(n,()=>g()%P)};
    if(f==="sparse")return {A:mat(n,()=>g()%19===0?v():0)};
    const axis=f[0],k=+f[1],theta=Array.from({length:k},v);
    // Unknown, varying coefficients; no unit-difference prior.
    const E=mat(n,(i,j)=>(axis==="r"?i:j)<k||g()%23===0?v():0);
    return {A:reconstruct(E,axis,theta,{u:0}),theta,axis}
  }
  const profiles={},trace=[],totals={},policies=["fixed","rotate","self","all"],stats={};let checks=0,certs=0,proposals=0;
  for(const p of policies){totals[p]=0;stats[p]={wins:0,losses:0,admitted:0,probes:0,overhead:0,coefficientMatches:0};profiles[p]=Object.fromEntries(arms.map(a=>[a,{tries:0,reward:0,success:0}]))}
  // Streaming regime shifts; same tasks and per-arm seeds for every policy.
  // Self uses only its own prior selected-arm observations, decayed after every task.
  for(let t=0;t<240;t++){
    const regime=Math.floor(t/60),g=rng(0x123456+t*8191),families=[["r2","r2","r3","random","sparse"],["c2","c2","c3","random","sparse"],["r1","c1","r3","c3","random"],["random","random","sparse","r2","c2"]][regime];
    const f=families[g()%families.length],{A,theta,axis}=make(f,12345+t*65537),root=2*nnz(A),direct=base+q*root;
    const b=Array.from({length:n},()=>g()%P),truth=apply(A,"r",[],b),records={};
    for(const p of policies){
      const prof=profiles[p];let order;
      if(p==="fixed")order=["r2","c2"];
      if(p==="rotate")order=[arms[t%6],arms[(t+1)%6]];
      if(p==="all")order=arms.slice();
      if(p==="self"){
        // Upper-confidence exploration over measured net value, with recency.
        // Every sixth task probes the least-observed arm first.
        const sorted=arms.slice().sort((a,b)=>((prof[b].reward/(prof[b].tries+1))+0.12/Math.sqrt(prof[b].tries+1))-((prof[a].reward/(prof[a].tries+1))+0.12/Math.sqrt(prof[a].tries+1)));
        if(t%6===0){let least=arms.slice().sort((a,b)=>prof[a].tries-prof[b].tries)[0];order=[least,...sorted.filter(a=>a!==least)].slice(0,2)}else order=sorted.slice(0,2);
        for(const a of arms){prof[a].tries*=0.94;prof[a].reward*=0.94;prof[a].success*=0.94}
      }
      let overhead=0,best=null,observed=[];
      // Exact upper bound: even zero application cost cannot repay a full scan
      if(q*root>N)for(const arm of order){
        const z=propose(A,arm,(t+1)*104729+arms.indexOf(arm)*8191);proposals++;overhead+=z.cost;stats[p].probes++;
        let reward=-z.cost,success=false;
        // Held-out prediction only screens; full residual and certificate decide.
        if(z.theta&&z.valid>=36){
          const L={u:0},E=transform(A,z.axis,z.theta,L);L.u+=N;
          overhead+=L.u;reward-=L.u;
          const per=appCost(E,z.k),C={u:0},recon=reconstruct(E,z.axis,z.theta,C);C.u+=N;
          assert(eq(recon,A),"coefficient reconstruction");certs++;overhead+=C.u;reward-=C.u;
          const benefit=q*(root-per);reward+=benefit;
          if(benefit>0&&(!best||per<best.per)){best={...z,E,per};success=true}
        }
        if(p==="self"){prof[arm].tries++;prof[arm].reward+=reward/(q*2*N);prof[arm].success+=+success}
        observed.push({arm,fit:z.score,heldout:z.valid,theta:z.theta,cost:z.cost,reward});
      }
      let selected=best&&q*(root-best.per)>0?best:null;
      const total=base+overhead+q*(selected?selected.per:root);
      assert(eq(selected?apply(selected.E,selected.axis,selected.theta,b):apply(A,"r",[],b),truth),"product mismatch");checks++;
      totals[p]+=total;stats[p].overhead+=overhead;stats[p].wins+=+(total<direct);stats[p].losses+=+(total>direct);stats[p].admitted+=+!!selected;
      stats[p].coefficientMatches+=+(!!selected&&selected.axis===axis&&eq(selected.theta,theta));
      records[p]={order,observed,selected:selected?{arm:selected.arm,theta:selected.theta,per:selected.per}:null,total};
    }
    trace.push({t,regime,f,theta,direct,records,selfProfile:JSON.parse(JSON.stringify(profiles.self))})
  }
  const direct=trace.reduce((s,x)=>s+x.direct,0);
  const regimes=Array.from({length:4},(_,regime)=>{let a=trace.filter(x=>x.regime===regime);return {regime,direct:a.reduce((s,x)=>s+x.direct,0),costs:Object.fromEntries(policies.map(p=>[p,a.reduce((s,x)=>s+x.records[p].total,0)])),selfOrders:Object.fromEntries(arms.map(arm=>[arm,a.filter(x=>x.records.self.order.includes(arm)).length]))}});
  return {field:P,n,q,checks,certs,proposals,direct,totals,stats,regimes,trace}
}
console.log(JSON.stringify(experiment()));
