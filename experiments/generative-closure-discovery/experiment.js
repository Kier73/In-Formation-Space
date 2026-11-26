"use strict";
function experiment() {
  'use strict';
  const P=257, mod=x=>((x%P)+P)%P;
  const assert=(x,msg)=>{if(!x)throw Error(msg)};
  const pow=(a,k)=>{let r=1;while(k){if(k%2)r=mod(r*a);a=mod(a*a);k=Math.floor(k/2)}return r};
  const inv=x=>{assert(x!==0,"zero inverse");return pow(x,P-2)};
  const rng=seed=>()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%P};
  const mat=(n,f)=>Array.from({length:n},(_,i)=>Array.from({length:n},(_,j)=>f(i,j)));
  const nz=x=>x!==0;
  const nnz=A=>A.reduce((s,r)=>s+r.filter(nz).length,0);
  const eq=(A,B)=>JSON.stringify(A)===JSON.stringify(B);
  function ntt(a,inverse=false) {
    const n=a.length,b=a.slice();
    for(let i=1,j=0;i<n;i++){let bit=n>>1;for(;j&bit;bit>>=1)j^=bit;j^=bit;if(i<j)[b[i],b[j]]=[b[j],b[i]]}
    for(let len=2;len<=n;len*=2){
      const root=pow(3,(P-1)/len),w0=inverse?inv(root):root;
      for(let i=0;i<n;i+=len){let w=1;for(let j=0;j<len/2;j++){
        const u=b[i+j],v=mod(w*b[i+j+len/2]);b[i+j]=mod(u+v);b[i+j+len/2]=mod(u-v);w=mod(w*w0)
      }}
    }
    if(inverse){const scale=inv(n);for(let i=0;i<n;i++)b[i]=mod(b[i]*scale)}
    return b;
  }
  // Unit ledger: field arithmetic and cell inspections; NTT counts
  // four field operations per butterfly, plus a conservative 64 per stage
  // for root/inverse preparation and inverse scale. Not a wall-clock model.
  const fftCost=(n,inverse=false)=>2*n*Math.log2(n)+64*Math.log2(n)+(inverse?n+64:0);
  const termCost=(t,n)=>t.kind==="cyclic"?fftCost(n)+fftCost(n,true)+2*n:2*(t.u.filter(nz).length+t.v.filter(nz).length);
  function candidate(E,kind) {
    const n=E.length, old=nnz(E); let term,rem,setup=0;
    if(kind==="cyclic"){
      // E[i,j] = c[(i-j) mod n]; infer each c from the modal diagonal.
      const c=Array(n).fill(0);
      for(let k=0;k<n;k++){const counts=new Map();for(let j=0;j<n;j++){const x=E[(j+k)%n][j];counts.set(x,(counts.get(x)||0)+1)}
        let best=0,count=counts.get(0)||0;for(const [x,v] of counts)if(v>count){best=x;count=v}c[k]=best}
      setup+=2*n*n;
      if(!c.some(nz))return {setup};
      rem=mat(n,(i,j)=>mod(E[i][j]-c[(i-j+n)%n]));
      term={kind,c,spectrum:ntt(c)};setup+=2*n*n+fftCost(n);
    }else{
      let i=-1,j=-1;const rows=E.map(r=>r.filter(nz).length),cols=Array(n).fill(0);
      for(const r of E)for(let k=0;k<n;k++)if(r[k])cols[k]++;
      let score=0;for(let a=0;a<n;a++)for(let b=0;b<n;b++)if(E[a][b]&&rows[a]*cols[b]>score){i=a;j=b;score=rows[a]*cols[b]}
      setup+=3*n*n;
      if(i<0)return {setup};
      const scale=inv(E[i][j]),u=E.map(r=>r[j]),v=E[i].map(x=>mod(x*scale));
      rem=mat(n,(a,b)=>mod(E[a][b]-u[a]*v[b]));term={kind,u,v};setup+=3*n*n+2*n+64;
    }
    const left=nnz(rem);setup+=2*n*n+2*n; // count original/residual scans and term support
    return {term,rem,setup,gain:2*(old-left)-termCost(term,n)};
  }
  function discover(A,allowed) {
    const n=A.length;let E=A.map(r=>r.slice()),terms=[],setup=n*n,history=[];
    for(let step=0;step<4 && nnz(E)>0;step++){
      setup+=n*n;let best=null;
      for(const kind of allowed){const c=candidate(E,kind);setup+=c.setup;if(c.gain>0&&(!best||c.gain>best.gain))best=c}
      if(!best)break;
      terms.push(best.term);E=best.rem;history.push({kind:best.term.kind,gain:best.gain,residual:nnz(E)});setup+=n*n;
    }
    // Verify reconstruction coefficient by coefficient, including the explicit residual.
    for(let i=0;i<n;i++)for(let j=0;j<n;j++){
      let x=E[i][j];for(const t of terms){x=mod(x+(t.kind==="cyclic"?t.c[(i-j+n)%n]:t.u[i]*t.v[j]));setup+=t.kind==="cyclic"?2:3}
      assert(x===A[i][j],"reconstruction mismatch");setup++;
    }
    const sparse=E.map(r=>r.flatMap((v,j)=>v?[[j,v]]:[]));setup+=2*n*n; // residual encoding and nnz count
    return {terms,sparse,setup,perColumn:2*nnz(E)+terms.reduce((s,t)=>s+termCost(t,n),0),history};
  }
  function apply(D,b) {
    const n=b.length,y=D.sparse.map(r=>r.reduce((s,[j,v])=>mod(s+v*b[j]),0));
    for(const t of D.terms)if(t.kind==="cyclic"){
      const f=ntt(b),z=ntt(f.map((x,j)=>mod(x*t.spectrum[j])),true);for(let i=0;i<n;i++)y[i]=mod(y[i]+z[i])
    }else{
      let z=0;for(let j=0;j<n;j++)if(t.v[j])z=mod(z+t.v[j]*b[j]);for(let i=0;i<n;i++)if(t.u[i])y[i]=mod(y[i]+t.u[i]*z)
    }
    return y;
  }
  const rows=[],families=["cyclic","rank","mixed","random","identity"];
  let checks=0;
  for(const n of [32,64,128])for(const family of families)for(const seed of [17,83,119]){
    const rand=rng(seed),c=Array.from({length:n},rand),u=Array.from({length:n},(_,i)=>i<n/2?rand():0),v=Array.from({length:n},(_,j)=>j<n/2?rand():0);
    const A=mat(n,(i,j)=>family==="random"?rand():family==="identity"?+(i===j):mod((family!=="rank"?c[(i-j+n)%n]:0)+(family!=="cyclic"?u[i]*v[j]:0)));
    const methods={sparse:{terms:[],sparse:A.map(r=>r.flatMap((v,j)=>v?[[j,v]]:[])),setup:n*n,perColumn:2*nnz(A),history:[]},cyclic:discover(A,["cyclic"]),rank:discover(A,["rank"]),adaptive:discover(A,["cyclic","rank"])};
    for(let q=0;q<5;q++){const b=Array.from({length:n},rand),truth=A.map(r=>r.reduce((s,x,j)=>mod(s+x*b[j]),0));
      for(const D of Object.values(methods)){assert(eq(apply(D,b),truth),`product mismatch ${n} ${family}`);checks++}}
    rows.push({n,family,seed,methods:Object.fromEntries(Object.entries(methods).map(([k,d])=>[k,{setup:d.setup,perColumn:d.perColumn,history:d.history}]))});
  }
  const summary=[];
  for(const n of [32,64,128])for(const family of families){
    const subset=rows.filter(r=>r.n===n&&r.family===family);
    const mean=(method,key)=>Math.round(subset.reduce((s,r)=>s+r.methods[method][key],0)/subset.length);
    const costs=Object.fromEntries(["sparse","cyclic","rank","adaptive"].map(m=>[m,{setup:mean(m,"setup"),perColumn:mean(m,"perColumn")}]));
    const b=costs.sparse,a=costs.adaptive,delta=b.perColumn-a.perColumn;
    summary.push({n,family,costs,breakEven:delta>0?Math.max(0,Math.floor((a.setup-b.setup)/delta)+1):null,adaptiveTerms:subset[0].methods.adaptive.history.map(x=>x.kind)});
  }
  // An independent direct convolution test also detects transform normalization/orientation errors.
  for(const n of [2,4,8,16,32,64,128,256]){const rand=rng(n),a=Array.from({length:n},rand),b=Array.from({length:n},rand);assert(eq(ntt(ntt(a),true),a),"NTT inverse");assert(eq(ntt(ntt(a).map((x,j)=>mod(x*ntt(b)[j])),true),a.map((_,i)=>a.reduce((s,x,j)=>mod(s+x*b[(i-j+n)%n]),0))),"convolution");checks+=2}
  return {field:P,checks,rows,summary};
}
console.log(JSON.stringify(experiment(),null,2));
