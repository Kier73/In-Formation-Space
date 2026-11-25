function depth(data){
const pop=x=>{let n=0;for(;x;x&=x-1)n++;return n};
const bits=x=>{let a=[];for(let i=0;x;x>>>=1,i++)if(x&1)a.push(i);return a};
function permutations(n){let out=[];function rec(a,left){if(!left.length){out.push(a);return}for(let x of left)rec(a.concat(x),left.filter(y=>y!==x))}rec([],Array.from({length:n},(_,i)=>i));return out}
function verify(ts,n,mask){let d=n*n,z=Array(d).fill(0n);for(let [a,b,c] of ts){if(!a||!b||!c||(c&~BigInt(mask)))return false;let v=0n;for(let i of bits(Number(a)))v^=b<<BigInt(i*d);for(let k of bits(Number(c)))z[k]^=v}for(let i=0;i<n;i++)for(let k=0;k<n;k++){let v=0n;if(mask>>>(i*n+k)&1)for(let j=0;j<n;j++)v^=1n<<BigInt((i*n+j)*d+j*n+k);if(z[i*n+k]!==v)return false}return true}
function naive(n,mask){let ts=[];for(let i=0;i<n;i++)for(let j=0;j<n;j++)for(let k=0;k<n;k++)if(mask>>>(i*n+k)&1)ts.push([1n<<BigInt(i*n+j),1n<<BigInt(j*n+k),1n<<BigInt(i*n+k)]);return ts}
function permute(x,n,p,q){let z=0;for(let i of bits(x))z|=1<<(p[Math.floor(i/n)]*n+q[i%n]);return z}
function run(n,seed){let d=n*n,N=1<<d,full=N-1,ps=permutations(n),identity=ps[0],ts=seed.map(t=>t.map(BigInt));if(!verify(ts,n,full))throw Error("seed");
 let base=new Uint16Array(N),counts=new Uint16Array(N);for(let [a,b,c] of ts)counts[Number(c)]++;for(let i=0;i<d;i++)for(let m=0;m<N;m++)if(m>>i&1)counts[m]+=counts[m^(1<<i)];for(let m=0;m<N;m++)base[m]=ts.length-counts[full^m];
 let hot=Uint16Array.from(base),choice=new Uint16Array(N),maps=[],comb=0;
 for(let p of ps)for(let q of ps){let idx=maps.length,trans=Array.from({length:d},(_,i)=>1<<(p[Math.floor(i/n)]*n+q[i%n])),masks=new Uint16Array(N);maps.push({p,q});for(let m=1;m<N;m++){let low=m&-m;masks[m]=masks[m^low]|trans[31-Math.clz32(low)];let t=masks[m];comb++;if(base[m]<hot[t]){hot[t]=base[m];choice[t]=idx}}}
 let lower=new Uint16Array(N),best=new Uint16Array(N),kind=new Uint8Array(N),split=new Uint16Array(N),splitQueries=0;
 for(let m=1;m<N;m++){let row=0,col=0;for(let i of bits(m)){row|=1<<Math.floor(i/n);col|=1<<(i%n)}
 // flattenings for active rows/columns, and individual output count.
 lower[m]=Math.max(n*pop(row),n*pop(col),pop(m));
 best[m]=Math.min(hot[m],n*pop(m));kind[m]=hot[m]<=n*pop(m)?1:2;
 let low=m&-m;for(let sub=(m-1)&m;sub;sub=(sub-1)&m){if(!(sub&low))continue;let oth=m^sub;if(!oth)continue;splitQueries++;let r=best[sub]+best[oth];if(r<best[m]){best[m]=r;kind[m]=3;split[m]=sub}}
 if(best[m]<lower[m])throw Error("below LB")
 }
 function realize(m){if(!m)return [];if(kind[m]===2)return naive(n,m);if(kind[m]===3)return realize(split[m]).concat(realize(m^split[m]));let {p,q}=maps[choice[m]];return ts.map(([a,b,c])=>[BigInt(permute(Number(a),n,p,identity)),BigInt(permute(Number(b),n,identity,q)),BigInt(permute(Number(c),n,p,q)&m)]).filter(t=>t[2])}
 let profile=[],improved=0,exact=0,checks=0,maxGain=0,witness=null;
 for(let k=1;k<=d;k++){let o={depth:k,subsets:0,minCost:65535,maxCost:0,meanCost:0,meanBase:0,meanHot:0,exactFloor:0,improved:0};for(let m=1;m<N;m++){if(pop(m)!==k)continue;o.subsets++;o.minCost=Math.min(o.minCost,best[m]);o.maxCost=Math.max(o.maxCost,best[m]);o.meanCost+=best[m];o.meanBase+=base[m];o.meanHot+=hot[m];if(best[m]===lower[m]){o.exactFloor++;exact++}if(best[m]<base[m]){o.improved++;improved++;if(base[m]-best[m]>maxGain){maxGain=base[m]-best[m];witness={mask:m,depth:k,base:base[m],best:best[m],lower:lower[m],terms:realize(m).map(t=>t.map(String))}}}}
 o.meanCost/=o.subsets;o.meanBase/=o.subsets;o.meanHot/=o.subsets;profile.push(o)}
 // shortest path through Boolean lattice; each edge reveals one additional output, cost is integrated rank.
 let score=new Uint32Array(N),parent=new Uint16Array(N);for(let m=1;m<N;m++){let s=2**31,pr=0;for(let i of bits(m)){let q=m^(1<<i);if(score[q]<s){s=score[q];pr=q}}score[m]=s+best[m];parent[m]=pr}
 let path=[];for(let m=full;m;m=parent[m])path.push(m);path.reverse();
 let pathReceipts=path.map((m,k)=>{let out=realize(m);if(out.length!==best[m]||!verify(out,n,m))throw Error("depth witness");checks++;return {depth:k+1,mask:m,revealed:31-Math.clz32(m^(k?path[k-1]:0)),rank:best[m],lower:lower[m],base:base[m],kind:kind[m],terms:out.map(t=>t.map(String))}});
 let rowMajor=Array.from({length:d},(_,k)=>{let m=(1<<(k+1))-1;return {depth:k+1,rank:best[m],base:base[m],lower:lower[m]}});
 // Check all n=3 masks; n=4 sampled plus full optimal path.
 for(let m=1;m<N;m+=n===3?1:127){let t=realize(m);if(t.length!==best[m]||!verify(t,n,m))throw Error("sample realization");checks++}
 return {n,seedRank:ts.length,fullRank:best[full],configurations:N-1,permutationComparisons:comb,splitQueries,improved,exact,maxGain,witness,profile,optimalIntegrated:score[full],rowMajorIntegrated:rowMajor.reduce((s,x)=>s+x.rank,0),fixedIncumbentRowMajor:rowMajor.reduce((s,x)=>s+x.base,0),path:pathReceipts,rowMajor,checks};
}
return [run(3,data.closed.results.find(x=>x.n===3).terms),run(4,data.hot.find(x=>x.n===4).terms)]
}
const fs=require('node:fs'),path=require('node:path');const read=x=>JSON.parse(fs.readFileSync(path.join(__dirname,x),'utf8'));console.log(JSON.stringify(depth({closed:read('mmg021_results.json'),hot:read('mmg012_results.json')}),null,2));
