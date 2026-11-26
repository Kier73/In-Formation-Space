function flag(data){
const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
const pc=x=>bits(x).length;
function parity(x){let p=0;while(x){x&=x-1n;p^=1}return p}
function basis(){let m=new Map();return {m,reduce(x){while(x){let p=x.toString(2).length-1;if(!m.has(p))break;x^=m.get(p)}return x},add(x){x=this.reduce(x);if(!x)return false;m.set(x.toString(2).length-1,x);return true}}}
function rankFactors(q,n){let B=new Map(),U=[],V=[],mask=(1n<<BigInt(n))-1n;for(let i=0;i<n;i++){let x=q>>BigInt(i*n)&mask,tag=0n;while(x){let p=x.toString(2).length-1,z=B.get(p);if(!z){let j=V.length;V.push(x);U.push(0n);B.set(p,[x,1n<<BigInt(j)]);tag^=1n<<BigInt(j);break}x^=z[0];tag^=z[1]}for(let j of bits(tag))U[j]|=1n<<BigInt(i)}return U.map((u,i)=>[u,V[i]])}
function verify(t,n,queries){let d=n*n,z=queries.map(()=>0n);for(let [a,b,c] of t){if(!a||!b||!c||a>>BigInt(d)||b>>BigInt(d)||c>>BigInt(queries.length))return false;let p=0n;for(let i of bits(a))p^=b<<BigInt(i*d);for(let k of bits(c))z[k]^=p}
for(let j=0;j<queries.length;j++){let want=0n;for(let e of bits(queries[j])){let i=Math.floor(e/n),k=e%n;for(let h=0;h<n;h++)want^=1n<<BigInt((i*n+h)*d+h*n+k)}if(want!==z[j])return false}return true}
function direct(n,Q){let out=[];for(let i=0;i<Q.length;i++)for(let [u,v] of rankFactors(Q[i],n))for(let h=0;h<n;h++){let a=0n,b=0n;for(let j of bits(u))a|=1n<<BigInt(j*n+h);for(let j of bits(v))b|=1n<<BigInt(h*n+j);out.push([a,b,1n<<BigInt(i)])}return out}
function merge(t){let m=new Map();for(let [a,b,c] of t){let k=a+":"+b;if(m.has(k))m.get(k)[2]^=c;else m.set(k,[a,b,c])}return [...m.values()].filter(t=>t[2])}
function run(n,seed){let ts=seed.map(t=>t.map(BigInt)),d=n*n,N=2**d,r=ts.length;
let code=Array(N).fill(0n),unit=Array(d).fill(0n);for(let i=0;i<r;i++)for(let j of bits(ts[i][2]))unit[j]|=1n<<BigInt(i);
let hist=Array.from({length:n+1},()=>({count:0,min:r,max:0,tight:0}));let rank=new Uint8Array(N);
for(let q=1;q<N;q++){let bit=q&-q;code[q]=code[q^bit]^unit[31-Math.clz32(bit)];let k=rankFactors(BigInt(q),n).length,w=pc(code[q]);rank[q]=k;if(w<n*k)throw Error("rank bound");let h=hist[k];h.count++;h.min=Math.min(h.min,w);h.max=Math.max(h.max,w);if(w===n*k)h.tight++}
function closure(U){let B=basis(),qs=[];for(let q=1;q<N;q++)if((code[q]&~U)===0n&&B.add(BigInt(q)))qs.push(BigInt(q));return qs}
function queryLower(Q){let R=basis(),C=basis(),mask=(1n<<BigInt(n))-1n;for(let q of Q){for(let i=0;i<n;i++){R.add(q>>BigInt(i*n)&mask);let v=0n;for(let j=0;j<n;j++)if(q>>BigInt(j*n+i)&1n)v|=1n<<BigInt(j);C.add(v)}}return Math.max(n*R.m.size,n*C.m.size,Q.length)}
function project(Q){return ts.map(([a,b,c])=>[a,b,Q.reduce((v,q,j)=>v|(BigInt(parity(c&q))<<BigInt(j)),0n)]).filter(t=>t[2])}
function realize(Q){let a=merge(direct(n,Q)),b=project(Q);let out=a.length<b.length?a:b;if(!verify(out,n,Q))throw Error("witness");return {rank:out.length,lower:queryLower(Q),incumbent:b.length,direct:a.length,source:a.length<b.length?"factorized-query":"incumbent",terms:out.map(t=>t.map(String))}}
let Q=[],U=0n,flag=[],scans=0,latentSteps=0,root=0n;
while(Q.length<d){let bestQ=0,bestCost=Infinity,bestRank=Infinity;
 for(let q=1;q<N;q++){scans++;let extra=code[q]&~U;if(!extra)continue;let w=pc(extra);if(w<bestCost||w===bestCost&&rank[q]<bestRank){bestQ=q;bestCost=w;bestRank=rank[q]}}
 if(!bestQ)throw Error("incomplete");U|=code[bestQ];let closed=closure(U),B=basis();for(let q of Q)B.add(q);
 let add=[BigInt(bestQ),...closed].filter(q=>B.add(q));
 for(let j=0;j<add.length;j++){let q=add[j];Q.push(q);let z=realize(Q);if(j>0)latentSteps++;flag.push({depth:Q.length,query:String(q),queryRank:rank[Number(q)],newProducts:j?0:bestCost,latent:j>0,support:pc(U),...z})}
 if(Q.length!==closed.length)throw Error("closure mismatch")
}
let baseline=[],P=[];for(let j=0;j<d;j++){P.push(1n<<BigInt(j));let z=realize(P);baseline.push({depth:j+1,...z,terms:undefined})}
return {n,r,queries:N-1,hist,scans,latentSteps,flag,baseline,integrated:flag.reduce((s,x)=>s+x.rank,0),fixedQueryOrderIntegrated:baseline.reduce((s,x)=>s+x.rank,0),incumbentIntegrated:flag.reduce((s,x)=>s+x.incumbent,0),baselineIncumbentIntegrated:baseline.reduce((s,x)=>s+x.incumbent,0),verified:true}
}
return [run(3,data.closed.results.find(x=>x.n===3).terms),run(4,data.hot.find(x=>x.n===4).terms)]
}
const fs=require('node:fs'),path=require('node:path');const read=x=>JSON.parse(fs.readFileSync(path.join(__dirname,x),'utf8'));console.log(JSON.stringify(flag({closed:read('mmg021_results.json'),hot:read('mmg012_results.json')}),null,2));
