"use strict";
function experiment(){
  const P=65537, mod=x=>((x%P)+P)%P, assert=(x,m)=>{if(!x)throw Error(m)};
  const mat=(n,f)=>Array.from({length:n},(_,i)=>Array.from({length:n},(_,j)=>f(i,j)));
  const count=A=>A.reduce((s,r)=>s+r.filter(x=>x!==0).length,0);
  const rng=seed=>()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed};
  const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  function diff(A,axis){
    const n=A.length;
    return mat(n,(i,j)=>axis==="r"?(i?mod(A[i][j]-A[i-1][j]):A[i][j]):(j?mod(A[i][j]-A[i][j-1]):A[i][j]));
  }
  function integrate(A,axis){
    const n=A.length,B=A.map(r=>r.slice());
    if(axis==="r")for(let i=1;i<n;i++)for(let j=0;j<n;j++)B[i][j]=mod(B[i][j]+B[i-1][j]);
    else for(let i=0;i<n;i++)for(let j=1;j<n;j++)B[i][j]=mod(B[i][j]+B[i][j-1]);
    return B;
  }
  function cost(A,r,c){return 2*count(A)+(r+c)*(A.length-1)}
  function certify(A,node){
    let B=node.E;
    for(let i=0;i<node.r;i++)B=integrate(B,"r");
    for(let j=0;j<node.c;j++)B=integrate(B,"c");
    assert(equal(A,B),"coefficient reconstruction");
    return (node.r+node.c)*A.length*(A.length-1)+A.length*A.length;
  }
  function direct(A,b){return A.map(row=>row.reduce((s,x,j)=>mod(s+x*b[j]),0))}
  function apply(node,b){
    let x=b.slice(),n=b.length,ops=0;
    for(let k=0;k<node.c;k++)for(let i=n-2;i>=0;i--){x[i]=mod(x[i]+x[i+1]);ops++}
    let y=node.sparse.map(row=>row.reduce((s,[j,v])=>{ops+=2;return mod(s+v*x[j])},0));
    for(let k=0;k<node.r;k++)for(let i=1;i<n;i++){y[i]=mod(y[i]+y[i-1]);ops++}
    assert(ops===node.perColumn,"application ledger");
    return y;
  }
  function search(A,policy,q){
    const n=A.length,step=n*(n-1)+n*n;
    let setup=n*n, seen=new Map(), explored=[], root={r:0,c:0,E:A,perColumn:cost(A,0,0),path:[]};
    seen.set("0,0",root);
    const key=(r,c)=>`${r},${c}`;
    function child(node,axis){
      const r=node.r+(axis==="r"),c=node.c+(axis==="c"),k=key(r,c);
      if(seen.has(k))return seen.get(k);
      // No additional candidate if cumulative search alone already exceeds
      // the maximum possible savings against direct application at this horizon.
      if(policy==="budgeted"&&setup-n*n+step>=q*root.perColumn)return null;
      const E=diff(node.E,axis),z={r,c,E,perColumn:cost(E,r,c),path:[...node.path,axis]};
      setup+=step;seen.set(k,z);explored.push({r,c,perColumn:z.perColumn});return z;
    }
    if(policy==="greedy"){
      let x=root;
      for(let depth=0;depth<3;depth++){
        const options=["r","c"].map(a=>child(x,a)).filter(Boolean).sort((a,b)=>a.perColumn-b.perColumn);
        if(!options.length||options[0].perColumn>=x.perColumn)break;
        x=options[0];
      }
    }else if(policy==="lookahead"||policy==="budgeted"){
      let level=[root];
      for(let depth=0;depth<3;depth++){
        const next=new Map();
        for(const node of level)for(const axis of ["r","c"]){const z=child(node,axis);if(z)next.set(key(z.r,z.c),z)}
        level=[...next.values()];
      }
    }else if(policy==="row"||policy==="column"){
      let x=root;for(let depth=0;depth<3;depth++)x=child(x,policy==="row"?"r":"c");
    }
    // Search costs are sunk. Selection includes the remaining cost of
    // certifying the chosen node. Baseline requires no transform certificate.
    const cert=z=>z.path.length?z.path.length*n*(n-1)+n*n:0;
    const ranked=[...seen.values()].sort((a,b)=>(cert(a)+q*a.perColumn)-(cert(b)+q*b.perColumn));
    const chosen=ranked[0]; if(chosen.path.length)setup+=certify(A,chosen);
    chosen.sparse=chosen.E.map(row=>row.flatMap((v,j)=>v?[[j,v]]:[]));
    // Initial/candidate scans count support discovery. Final encoding scans
    // all entries again, including for direct; charge every method equally.
    setup+=n*n;
    return {node:chosen,setup,perColumn:chosen.perColumn,total:setup+q*chosen.perColumn,explored,path:chosen.path,
      residual:count(chosen.E),initialNeighbors:explored.filter(z=>z.r+z.c===1)};
  }
  const rows=[],families=["row2","column2","mixed11","row3","random","identity"],horizons=[1,8,32,128,512];
  let checks=0,certChecks=0;
  for(const n of [16,32,64,128])for(const seed of [17,83,119])for(const family of families){
    const rand=rng(seed),rint=k=>rand()%k;
    // Independently varying positive increments with sparse innovations.
    // Values for row2/column2/mixed11 at these sizes cannot wrap.
    let A;
    if(family==="random")A=mat(n,()=>rint(P));
    else if(family==="identity")A=mat(n,(i,j)=>+(i===j));
    else if(family==="mixed11"){
      const E=mat(n,(i,j)=>i===0&&j===0?1:i===0||j===0?1+rint(2):rint(13)===0?1:0);
      A=integrate(integrate(E,"r"),"c");
    }else{
      let E=mat(n,(i,j)=>i===0?1+rint(2):rint(17)===0?1:0);
      for(let k=0;k<(family==="row3"?3:2);k++)E=integrate(E,"r");
      A=family==="column2"?mat(n,(i,j)=>E[j][i]):E;
    }
    const vectors=Array.from({length:3},()=>Array.from({length:n},()=>rint(P)));
    const truths=vectors.map(b=>direct(A,b));
    for(const q of horizons){
      const methods={};
      for(const p of ["direct","greedy","row","column","lookahead","budgeted"]){
        const d=search(A,p,q);
        if(d.path.length)certChecks++;
        for(let k=0;k<vectors.length;k++){assert(equal(apply(d.node,vectors[k]),truths[k]),`product ${n} ${family} ${p}`);checks++}
        const {node,...record}=d;methods[p]=record;
      }
      rows.push({n,seed,family,q,methods});
    }
  }
  // Independent transform-order and inverse test on arbitrary coefficients.
  for(const n of [2,4,8,16,32,64,128]){
    const rand=rng(n),A=mat(n,()=>rand()%P);
    for(const axis of ["r","c"]){assert(equal(integrate(diff(A,axis),axis),A),"inverse");checks++}
    assert(equal(diff(diff(A,"r"),"c"),diff(diff(A,"c"),"r")),"commutation");checks++;
  }
  const summary=[];
  for(const n of [16,32,64,128])for(const family of families)for(const q of horizons){
    const subset=rows.filter(r=>r.n===n&&r.family===family&&r.q===q);
    const mean=p=>Math.round(subset.reduce((s,r)=>s+r.methods[p].total,0)/subset.length);
    const costs=Object.fromEntries(["direct","greedy","row","column","lookahead","budgeted"].map(p=>[p,mean(p)]));
    summary.push({n,family,q,costs,paths:subset.map(r=>r.methods.lookahead.path.join("")),barrier:subset.filter(r=>r.methods.lookahead.path.length>1&&r.methods.lookahead.initialNeighbors.every(z=>z.perColumn>=r.methods.direct.perColumn)).length});
  }
  return {field:P,checks,certChecks,rows,summary};
}
console.log(JSON.stringify(experiment(),null,2));
