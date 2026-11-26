function joint(){
 const bits=x=>{let a=[];for(let i=0;x;x>>>=1,i++)if(x&1)a.push(i);return a};
 function outer(a,b){let z=0;for(let i of bits(a))z^=b<<(4*i);return z}
 function target(q){let z=0;for(let i of bits(q))for(let j=0;j<2;j++)z^=1<<(((i>>1)*2+j)*4+j*2+(i&1));return z}
 function rank(x){let b=[0,0,0,0],r=0;for(let i=0;i<4;i++){let v=x>>>(4*i)&15;while(v){let p=31-Math.clz32(v);if(!b[p]){b[p]=v;r++;break}v^=b[p]}}return r}
 function factor(v){let i=31-Math.clz32(v),b=v>>>(4*(i>>2))&15,a=0;for(let k=0;k<4;k++)if(v>>>(4*k)&15)a|=1<<k;if(!a||outer(a,b)!==v)throw Error("factor");return [a,b]}
 function f2(q){let ans=[];for(let a=1;a<16;a++)for(let b=1;b<16;b++){let v=target(q)^outer(a,b);if(rank(v)!==1)continue;let p=factor(v);if(16*a+b<16*p[0]+p[1])ans.push([[a,b],p])}if(ans.length!==3)throw Error("factor count");return ans}
 function verify(ts){let got=[0,0,0,0];for(let [a,b,c] of ts)for(let j of bits(c))got[j]^=outer(a,b);return got.every((x,i)=>x===target(1<<i))}
 function solve(prefix,queries){
  let K=new Map();for(let i=0;i<prefix.length;i++){let v=outer(...prefix[i]),t=1<<i;while(v){let p=31-Math.clz32(v),z=K.get(p);if(!z){K.set(p,[v,t]);break}v^=z[0];t^=z[1]}}
  let piv=[...K.keys()].sort((a,b)=>b-a),free=Array.from({length:16},(_,i)=>i).filter(i=>!K.has(i));
  function reduce(v){let t=0;for(let p of piv)if(v>>>p&1){let z=K.get(p);v^=z[0];t^=z[1]}return [v,t]}
  function project(v){let [w]=reduce(v),z=0;for(let i=0;i<free.length;i++)if(w>>>free[i]&1)z|=1<<i;return z}
  let dic=new Map();for(let a=1;a<16;a++)for(let b=1;b<16;b++){let q=project(outer(a,b));if(q&&!dic.has(q))dic.set(q,[a,b])}
  let N=1<<free.length,dist=new Int8Array(N).fill(-1),prev=new Int32Array(N),queue=new Uint16Array(N);queue[0]=0;dist[0]=0;let tail=1,checks=0;
  for(let h=0;h<tail;h++){let v=queue[h];for(let q of dic.keys()){let w=v^q;checks++;if(dist[w]<0){dist[w]=dist[v]+1;prev[w]=q;queue[tail++]=w}}}
  if(tail!==N)throw Error("disconnected");
  let s=project(target(queries[2])),t=project(target(queries[3]));let best=99,center=0,centers=0;
  for(let x=0;x<N;x++){let c=dist[x]+dist[x^s]+dist[x^t];if(c<best){best=c;center=x;centers=1}else if(c===best)centers++}
  let terms=prefix.map(([a,b],i)=>[a,b,1<<Math.floor(i/2)]);
  function path(q,mask){while(q){let e=prev[q],p=dic.get(e);terms.push([p[0],p[1],mask]);q^=e}}
  path(center,12);path(center^s,4);path(center^t,8);
  for(let j=2;j<4;j++){let r=target(queries[j]);for(let [a,b,c] of terms)if(c>>j&1)r^=outer(a,b);let [z,u]=reduce(r);if(z)throw Error("residual");for(let i of bits(u))terms[i][2]^=1<<j}
  // convert output query basis back into standard entries.
  let decoder=[];for(let j=0;j<4;j++){for(let k=1;k<16;k++){let q=0;for(let i of bits(k))q^=queries[i];if(q===1<<j){decoder.push(k);break}}}
  let raw=terms.map(([a,b,c])=>[a,b,decoder.reduce((z,m,j)=>z|((bits(m&c).length%2)<<j),0)]);
  if(!verify(raw)||raw.length!==prefix.length+best)throw Error("verify");
  return {queries,prefix,dimension:free.length,atoms:dic.size,states:tail,edgeChecks:checks,individual:[dist[s],dist[t],dist[s^t]],collective:best,center,optimalCenters:centers,rank:raw.length,terms:raw}
 }
 let results=[];for(let [label,queries] of [["same-row",[1,2,4,8]],["same-column",[1,4,2,8]],["diagonal",[1,8,2,4]]])for(let A of f2(queries[0]))for(let B of f2(queries[1])){let r=solve(A.concat(B),queries);results.push({label,...r})}
 let summary=[];for(let label of ["same-row","same-column","diagonal"]){let a=results.filter(x=>x.label===label);summary.push({label,topologies:a.length,collectiveCosts:a.map(x=>x.collective),individualCosts:[...new Set(a.map(x=>x.individual.join(",")))],states:a.reduce((s,x)=>s+x.states,0),checks:a.reduce((s,x)=>s+x.edgeChecks,0),shortcut:a.filter(x=>x.collective<x.individual[0]+x.individual[1]).length})}
 return {summary,results};
}
console.log(JSON.stringify(joint(),null,2));
