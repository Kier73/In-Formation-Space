"use strict";
function experiment(){
  "use strict";
  const P=65537, mod=x=>((x%P)+P)%P, assert=(v,m)=>{if(!v)throw Error(m)};
  const mat=(n,f)=>Array.from({length:n},(_,i)=>Array.from({length:n},(_,j)=>f(i,j)));
  const nnz=A=>A.reduce((s,row)=>s+row.filter(x=>x!==0).length,0);
  const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const rng=seed=>()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0};
  const states=[];for(let d=1;d<=3;d++)for(let r=d;r>=0;r--)states.push({r,c:d-r,d});
  const coeff=[[1],[1,-1],[1,-2,1],[1,-3,3,-1]];
  function diff(A,axis){const n=A.length;return mat(n,(i,j)=>axis==="r"?(i?mod(A[i][j]-A[i-1][j]):A[i][j]):(j?mod(A[i][j]-A[i][j-1]):A[i][j]))}
  function integ(A,axis){let B=A.map(r=>r.slice()),n=B.length;
    if(axis==="r")for(let i=1;i<n;i++)for(let j=0;j<n;j++)B[i][j]=mod(B[i][j]+B[i-1][j]);
    else for(let i=0;i<n;i++)for(let j=1;j<n;j++)B[i][j]=mod(B[i][j]+B[i][j-1]);return B}
  function make(A,r,c){let E=A;for(let i=0;i<r;i++)E=diff(E,"r");for(let j=0;j<c;j++)E=diff(E,"c");return E}
  function stencil(A,r,c,i,j,ledger){
    let v=0;for(let a=0;a<=r&&a<=i;a++)for(let b=0;b<=c&&b<=j;b++){
      v=mod(v+coeff[r][a]*coeff[c][b]*A[i-a][j-b]);ledger.units+=4; // read, two mul, add
    }return v
  }
  const app=(E,d)=>2*nnz(E)+d*(E.length-1);
  const acq=(n,d)=>2*(d*n*(n-1)+n*n); // full materialization+support scan, inverse+comparison
  function certify(A,E,r,c){let B=E;for(let k=0;k<r;k++)B=integ(B,"r");for(let k=0;k<c;k++)B=integ(B,"c");assert(eq(A,B),"inverse certificate")}
  function sparse(E){return E.map(row=>row.flatMap((x,j)=>x?[[j,x]]:[]))}
  function apply(S,r,c,b,expected){
    let n=b.length,x=b.slice(),ops=0;
    for(let k=0;k<c;k++)for(let j=n-2;j>=0;j--){x[j]=mod(x[j]+x[j+1]);ops++}
    let y=S.map(row=>row.reduce((s,[j,v])=>{ops+=2;return mod(s+v*x[j])},0));
    for(let k=0;k<r;k++)for(let i=1;i<n;i++){y[i]=mod(y[i]+y[i-1]);ops++}
    assert(ops===expected,"application ledger");return y
  }
  function probe(A,seed,m){
    const n=A.length,g=rng(seed),ledger={units:0},counts=states.map(()=>0);
    for(let t=0;t<m;t++){
      const pos=g()%(n*n),i=Math.floor(pos/n),j=pos%n;
      states.forEach((s,k)=>{if(stencil(A,s.r,s.c,i,j,ledger)!==0)counts[k]++})
    }
    return {units:ledger.units,counts,m}
  }
  const rows=[],families=["row2","col2","mixed11","row3","row4","random","identity","sparse","localized","permuted"],horizons=[1,8,32,128,512];
  let checks=0,certificateChecks=0,stencilChecks=0,probeCases=0;
  for(const n of [16,32,64,128])for(const seed of [17,83,119,401,929,1021])for(const family of families){
    const g=rng(seed*7919+n*127),v=()=>g()%P;
    let A;
    if(family==="random")A=mat(n,v);
    else if(family==="identity")A=mat(n,(i,j)=>+(i===j));
    else if(family==="sparse")A=mat(n,()=>g()%19===0?v():0);
    else {
      A=mat(n,(i,j)=>i===0?1+g()%5:g()%23===0?1+g()%5:0);
      let r=2,c=0;
      if(family==="col2"){r=0;c=2;A=mat(n,(i,j)=>j===0?1+g()%5:g()%23===0?1+g()%5:0)}
      if(family==="mixed11"){r=1;c=1;A=mat(n,(i,j)=>i===0||j===0?1+g()%5:g()%23===0?1:0)}
      if(family==="row3")r=3;
      if(family==="row4")r=4;
      for(let k=0;k<r;k++)A=integ(A,"r");for(let k=0;k<c;k++)A=integ(A,"c");
      if(family==="localized")for(let i=0;i<Math.ceil(n/3);i++)for(let j=0;j<Math.ceil(n/3);j++)A[i][j]=v();
      if(family==="permuted"){const idx=Array.from({length:n},(_,i)=>i);for(let i=n-1;i>0;i--){const j=g()%(i+1);[idx[i],idx[j]]=[idx[j],idx[i]]}A=idx.map(i=>A[i].slice())}
    }
    const root=app(A,0),base=2*n*n;
    // Exhaustive reference shares commuting intermediate states, exactly nine transitions.
    const table=new Map([["0,0",A]]),full=states.map(s=>{
      const parent=s.r?table.get(`${s.r-1},${s.c}`):table.get(`0,${s.c-1}`);
      const E=diff(parent,s.r?"r":"c");table.set(`${s.r},${s.c}`,E);
      return {...s,E,per:app(E,s.d)}
    });
    // Validation only, not charged to search: compare direct local stencil on held-out locations.
    for(const s of full)for(let k=0;k<8;k++){
      let i=g()%n,j=g()%n;assert(stencil(A,s.r,s.c,i,j,{units:0})===s.E[i][j],"stencil mismatch");stencilChecks++;
    }
    const m=64,probeResult=probe(A,(seed*104729+n*65537+families.indexOf(family)*8191)>>>0,m);
    const sample=probeResult.counts.map((k,i)=>({...states[i],rate:k/m}));
    const b=Array.from({length:n},v),truth=A.map(row=>row.reduce((s,x,j)=>mod(s+x*b[j]),0));
    for(const q of horizons){
      const direct=base+q*root,fullSearch=states.length*(n*(n-1)+n*n);
      const certCost=d=>d*n*(n-1)+n*n;
      const remaining=s=>q*s.per+certCost(s.d);
      let ref=full.reduce((best,s)=>remaining(s)<remaining(best)?s:best,full[0]);
      const refChosen=remaining(ref)<q*root?ref:null;
      const exCost=base+fullSearch+(refChosen?remaining(refChosen):q*root);
      const oracleGain=s=>q*(root-s.per)-acq(n,s.d);
      const oracle=full.reduce((best,s)=>oracleGain(s)>oracleGain(best)?s:best,full[0]);
      const oracleCost=direct-Math.max(0,oracleGain(oracle)); // free knowledge of support, charged selected acquisition
      const record={n,seed,family,q,direct,exhaustive:exCost,oracle:oracleCost,oraclePath:oracleGain(oracle)>0?[oracle.r,oracle.c]:null,methods:{}};
      for(const policy of ["point","confidence"]){
        // Root support is known exactly. An optimistic impossibility gate uses minimum acquisition.
        let units=0,chosen=null,attempt=null,estimate=null,actualGain=null;
        if(q*root>acq(n,1)){
          units=probeResult.units;probeCases++;
          const radius=policy==="confidence"?Math.sqrt(Math.log(states.length/0.05)/(2*m)):0;
          const ranked=sample.map(s=>({...s,pred:q*(root-(2*n*n*Math.min(1,s.rate+radius)+s.d*(n-1)))-acq(n,s.d)})).sort((a,b)=>b.pred-a.pred);
          const top=ranked[0];estimate=top.pred-units;
          if(estimate>0){
            attempt=[top.r,top.c];
            const E=make(A,top.r,top.c),per=app(E,top.d);
            units+=top.d*n*(n-1)+n*n; // exact evaluation, including losing candidate
            actualGain=q*(root-per)-certCost(top.d);
            if(actualGain>0){
              certify(A,E,top.r,top.c);certificateChecks++;units+=certCost(top.d);
              chosen={...top,E,per};
            }
          }
        }
        const per=chosen?chosen.per:root;
        assert(eq(apply(sparse(chosen?chosen.E:A),chosen?chosen.r:0,chosen?chosen.c:0,b,per),truth),"probe product");checks++;
        record.methods[policy]={total:base+units+q*per,units,attempt,selected:chosen?[chosen.r,chosen.c]:null,estimate,actualGain};
      }
      if(refChosen){certify(A,refChosen.E,refChosen.r,refChosen.c);certificateChecks++}
      assert(eq(apply(sparse(refChosen?refChosen.E:A),refChosen?refChosen.r:0,refChosen?refChosen.c:0,b,refChosen?refChosen.per:root),truth),"exhaustive product");checks++;
      rows.push(record)
    }
  }
  const summary=[];
  for(const n of [16,32,64,128])for(const family of families)for(const q of horizons){
    const s=rows.filter(x=>x.n===n&&x.family===family&&x.q===q);
    const mean=f=>Math.round(s.reduce((a,x)=>a+f(x),0)/s.length);
    const costs={direct:mean(x=>x.direct),exhaustive:mean(x=>x.exhaustive),oracle:mean(x=>x.oracle),point:mean(x=>x.methods.point.total),confidence:mean(x=>x.methods.confidence.total)};
    const stats={};for(const p of ["point","confidence"])stats[p]={attempts:s.filter(x=>x.methods[p].attempt).length,wins:s.filter(x=>x.methods[p].total<x.direct).length,losses:s.filter(x=>x.methods[p].total>x.direct).length,misses:s.filter(x=>x.oracle<x.direct&&x.methods[p].total>=x.direct).length};
    summary.push({n,family,q,costs,stats})
  }
  return {field:P,checks,certificateChecks,stencilChecks,probeCases,summary,rows};
}
console.log(JSON.stringify(experiment()));
