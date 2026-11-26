function rgf004(){
"use strict";
const P=2305843009213693951n,MAXDEG=3,MAXTERMS=20000,MAXEXP=3000000;
const mod=x=>(x%P+P)%P,assert=(b,m)=>{if(!b)throw Error(m)};
const ctr=()=>({field:0,div:0,visits:0}),work=c=>c.field+c.div+c.visits;
const A=(a,b,c)=>(c.field++,mod(a+b)),M=(a,b,c)=>(c.field++,mod(a*b));
const zeros=n=>Array(n).fill(0n),same=(a,b)=>a.length===b.length&&a.every((x,i)=>x===b[i]);
function inv(a,c){let r=P,s=mod(a),u=0n,v=1n;while(s){c.div++;let q=r/s;[r,s]=[s,r-q*s];c.field+=2;[u,v]=[v,u-q*v]}assert(r===1n,"inverse");return mod(u)}
function dot(a,b,c){assert(a.length===b.length,"width");let y=0n;for(let i=0;i<a.length;i++)y=A(y,M(a[i],b[i],c),c);return y}
const project=(B,x,c)=>B.map(b=>dot(b,x,c));
const advance=(x,v,t,c)=>x.map((a,i)=>A(a,M(v[i],mod(t),c),c));
const key=ids=>ids.slice().sort((a,b)=>a-b).join(",");
const ids=k=>k===""?[]:k.split(",").map(Number);
function insert(map,k,a,c){c.visits++;let v=A(map.get(k)||0n,a,c);if(v)map.set(k,v);else map.delete(k);assert(map.size<=MAXTERMS,"term budget")}
function canonical(raw,c){let out=new Map();for(const t of raw)insert(out,key(t.i),t.a,c);return out}
function validate(raw,k,c){assert(Number.isInteger(k)&&k>=1&&k<=16&&raw.length<=MAXTERMS,"source bounds");for(const t of raw){c.visits+=1+t.i.length;assert(typeof t.a==="bigint"&&t.a>=0n&&t.a<P&&t.i.length<=MAXDEG&&t.i.every(i=>Number.isInteger(i)&&i>=0&&i<k),"source term")}}
function evalPoly(poly,x,c){let v=0n;for(const [k,a] of poly){c.visits++;let t=a;for(const i of ids(k))t=M(t,x[i],c);v=A(v,t,c)}return v}
function evalRaw(raw,x,c){let y=0n;for(const t of raw){c.visits++;let a=t.a;for(const j of t.i)a=M(a,x[j],c);y=A(y,a,c)}return y}
function gradRows(poly,k,c){let rows=new Map();for(const [s,a] of poly){let i=ids(s);for(let j=0;j<i.length;j++){let m=key(i.filter((_,l)=>l!==j));if(!rows.has(m))rows.set(m,zeros(k));let v=rows.get(m);v[i[j]]=A(v[i[j]],a,c);c.visits++}}return [...rows.values()]}
function basis(rows,k,c){
 const b=[],p=[];
 for(const row of rows){let v=row.slice();for(let j=0;j<b.length;j++){c.visits++;const f=v[p[j]];if(f)for(let l=0;l<k;l++)v[l]=A(v[l],-M(f,b[j][l],c),c)}
 let j=v.findIndex(x=>x!==0n);if(j<0)continue;let q=inv(v[j],c);v=v.map(a=>M(a,q,c));b.push(v);p.push(j)}
 // Gauss-Jordan on pivot columns: section has unit entries at pivots.
 for(let j=b.length-1;j>=0;j--)for(let i=0;i<j;i++){const f=b[i][p[j]];if(f)for(let l=0;l<k;l++)b[i][l]=A(b[i][l],-M(f,b[j][l],c),c)}
 return {B:b,pivots:p}
}
// independent rank, rightmost columns, no constructor calls
function rank(rows,k,c){const a=rows.map(r=>r.slice());let r=0;for(let j=k-1;j>=0&&r<a.length;j--){let i=r;while(i<a.length&&!a[i][j]){i++;c.visits++}if(i===a.length)continue;[a[r],a[i]]=[a[i],a[r]];let q=inv(a[r][j],c);for(let l=r+1;l<a.length;l++){let f=M(a[l][j],q,c);if(f)for(let t=0;t<=j;t++)a[l][t]=A(a[l][t],-M(f,a[r][t],c),c)}r++}return r}
// section has x[pivot_j]=z_j and remaining x=0
function restrict(poly,pivots,c){const m=new Map(pivots.map((p,i)=>[p,i])),q=new Map();for(const [s,a] of poly){let i=ids(s);c.visits+=1+i.length;if(i.every(j=>m.has(j)))insert(q,key(i.map(j=>m.get(j))),a,c)}return q}
function form(raw,k,c){validate(raw,k,c);const poly=canonical(raw,c),{B,pivots}=basis(gradRows(poly,k,c),k,c);return {B,pivots,q:restrict(poly,pivots,c)}}
// independently derive gradients by grouping exponent counts in raw terms
function checkGrad(raw,k,c){const rows=new Map();for(const t of raw){let e=new Map();for(const i of t.i){c.visits++;e.set(i,(e.get(i)||0)+1)}for(const [j,m] of e){const a=[];for(const [i,v] of e)for(let l=0;l<v-(i===j?1:0);l++)a.push(i);const s=key(a);if(!rows.has(s))rows.set(s,zeros(k));const v=rows.get(s);v[j]=A(v[j],M(t.a,BigInt(m),c),c)}}return [...rows.values()]}
function verify(raw,k,g,c){try{
validate(raw,k,c);const r=g.B.length;assert(r<=k&&g.B.every(b=>b.length===k&&b.every(a=>typeof a==="bigint"&&a>=0n&&a<P)),"chart");
assert(g.q instanceof Map&&g.q.size<=MAXTERMS,"q size");
assert(rank(checkGrad(raw,k,c),k,c)===r&&rank(g.B,k,c)===r,"rank certificate");
let expansion=new Map(),steps=0;
for(const [s,a] of g.q){const i=ids(s);assert(key(i)===s&&i.length<=MAXDEG&&i.every(j=>Number.isInteger(j)&&j>=0&&j<r)&&typeof a==="bigint"&&a>0n&&a<P,"q term");
function rec(j,ks,v){if(j===i.length){insert(expansion,key(ks),v,c);return}
for(let l=0;l<k;l++){c.visits++;assert(++steps<=MAXEXP,"expansion budget");const w=g.B[i[j]][l];if(w)rec(j+1,[...ks,l],M(v,w,c))}}
rec(0,[],a)
}
// independent equality: sorted source monomials, sum within groups
let sorted=raw.map(t=>({s:key(t.i),a:t.a})).sort((a,b)=>a.s.localeCompare(b.s)),ref=new Map();
for(let i=0;i<sorted.length;){let j=i,a=0n;while(j<sorted.length&&sorted[j].s===sorted[i].s){a=A(a,sorted[j].a,c);c.visits++;j++}if(a)ref.set(sorted[i].s,a);i=j}
return ref.size===expansion.size&&[...ref].every(([s,a])=>expansion.get(s)===a)
}catch{return false}}
function sumNewton(f,d,len,c){let a=Array.from({length:d+1},(_,i)=>f(BigInt(i))),b=1n,y=0n;for(let j=0;j<=d;j++){b=M(M(b,A(mod(len),-BigInt(j),c),c),inv(BigInt(j+1),c),c);y=A(y,M(b,a[0],c),c);a=a.slice(1).map((v,i)=>A(v,-a[i],c))}return y}
function sumOracle(f,d,len,c){let v=[0n];for(let j=0;j<=d;j++)v.push(A(v[j],f(BigInt(j)),c));let y=0n;for(let i=0;i<v.length;i++){let a=1n,b=1n;for(let j=0;j<v.length;j++)if(i!==j){a=M(a,A(mod(len),-BigInt(j),c),c);b=M(b,BigInt(i-j),c)}y=A(y,M(v[i],M(a,inv(b,c),c),c),c)}return y}
function compose(B,C,c){return B.map(b=>C[0].map((_,j)=>dot(b,C.map(r=>r[j]),c)))}
function run(B,poly,task,c,mode){
 let x=project(B,task.x,c),v=project(B,task.v,c),y=task.y,t=0n;
 const evalf=mode==="oracle"||mode==="eager"?(x=>evalRaw(poly,x,c)):(x=>evalPoly(poly,x,c));
 const d=mode==="oracle"||mode==="eager"?Math.max(0,...poly.map(t=>t.i.length)):Math.max(0,...[...poly.keys()].map(k=>ids(k).length));
 function seg(n){if(!n)return;if(mode==="eager"){for(let j=0n;j<n;j++){y=A(y,evalf(x),c);x=advance(x,v,1n,c)}return}
 y=A(y,(mode==="oracle"?sumOracle:sumNewton)(j=>evalf(advance(x,v,j,c)),d,n,c),c);x=advance(x,v,n,c)}
 for(const e of task.events){seg(e.t-t);v=advance(v,project(B,e.dv,c),1n,c);y=A(y,e.a,c);t=e.t}seg(task.n-t);return {x,v,y}
}
let seed=281981;function rnd(n){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return (seed>>>8)%n}
const rand=()=>BigInt(1+rnd(997));
function source(n,k,r,degree){
 // C is surjective onto factor coordinates, certified by identity block.
 const C=Array.from({length:k},(_,i)=>Array.from({length:n},(_,j)=>j<k?(i===j?1n:0n):rand()));
 const latent=Array.from({length:r},(_,i)=>Array.from({length:k},(_,j)=>j<r?(i===j?1n:0n):rand()));
 let raw=[];
 // sum of separate powers of hidden independent linear forms. No latent directions given to learner.
 for(const b of latent){let a=rand();function rec(j,is,v){if(j===degree){raw.push({i:is,a:v});return}for(let l=0;l<k;l++)if(b[l])rec(j+1,[...is,l],mod(v*b[l]))}rec(0,[],a)}
 // add cancelling syntactic factors across the entire factor chart.
 for(let i=0;i<k;i++){let a=rand(),j=(i+1)%k;raw.push({i:[i,j],a},{i:[j,i],a:P-a})}
 return {C,raw,expectedRank:r}
}
function task(n,t,m){return {x:Array.from({length:n},rand),v:Array.from({length:n},rand),y:rand(),n:t,events:Array.from({length:m},(_,i)=>({t:t*BigInt(i+1)/BigInt(m+1),dv:Array.from({length:n},rand),a:rand()}))}}
function campaign(name,n,k,r,d,N,events){
 const {C,raw,expectedRank}=source(n,k,r,d),base=ctr(),formation=ctr(),verification=ctr(),semantic=ctr(),factor=ctr(),oracle=ctr(),eager=ctr();
 validate(raw,k,base);const canon=canonical(raw,base);
 const g=form(raw,k,formation);assert(g.B.length===expectedRank,"unexpected semantic rank");assert(verify(raw,k,g,verification),"certificate refused");
 const B=compose(g.B,C,formation);let checks=0,eagerChecks=0,crossover=null;
 for(let i=0;i<N;i++){let t=task(n,i%8===0?32n:10n**24n+BigInt(i),events);
 let ref=run(C,raw,t,oracle,"oracle"),a=run(C,canon,t,factor,"factor"),b=run(B,g.q,t,semantic,"semantic");
 assert(a.y===ref.y&&same(a.x,ref.x)&&same(a.v,ref.v),"factor");assert(b.y===ref.y&&same(b.x,project(g.B,ref.x,oracle))&&same(b.v,project(g.B,ref.v,oracle)),"semantic");checks+=2;
 if(t.n===32n){let e=run(C,raw,t,eager,"eager");assert(e.y===ref.y&&same(e.x,ref.x)&&same(e.v,ref.v),"eager");eagerChecks++}
 if(crossover===null&&work(formation)+work(verification)+work(semantic)<work(base)+work(factor))crossover=i+1
 }
 return {name,n,factorRank:k,semanticRank:g.B.length,rawTerms:raw.length,canonicalTerms:canon.size,reducedTerms:g.q.size,tasks:N,events,checks,eagerChecks,crossover,work:{factor:work(base)+work(factor),semantic:work(formation)+work(verification)+work(semantic),factorSetup:work(base),semanticFormation:work(formation),semanticVerification:work(verification),factorRun:work(factor),semanticRun:work(semantic),oracle:work(oracle),eager:work(eager)},ledger:{base,formation,verification,semantic,factor,oracle,eager}}
}
const campaigns=[campaign("hidden-rank-two",48,10,2,3,64,8),campaign("hidden-rank-four",48,10,4,3,32,4),campaign("full-rank-control",16,8,8,2,24,2),campaign("short-use-control",48,10,2,3,1,0)];
const c=ctr(),s=source(12,6,2,3),g=form(s.raw,6,c);assert(verify(s.raw,6,g,c),"control valid");
let bad={...g,q:new Map(g.q)},first=[...bad.q.keys()][0];bad.q.set(first,mod(bad.q.get(first)+1n));assert(!verify(s.raw,6,bad,c),"bad polynomial accepted");
let altered={...g,B:g.B.map(b=>b.slice())};altered.B[0][5]=mod(altered.B[0][5]+1n);assert(!verify(s.raw,6,altered,c),"bad direction accepted");
let oversized={...g,B:[...g.B,zeros(6)]};assert(!verify(s.raw,6,oversized,c),"nonminimal accepted");
const cancelled=[{i:[0,1],a:1n},{i:[1,0],a:P-1n}],z=form(cancelled,2,c);assert(z.B.length===0&&verify(cancelled,2,z,c),"rank zero");
const constant=[{i:[],a:42n}],q=form(constant,2,c);assert(q.B.length===0&&verify(constant,2,q,c),"constant");
let refused=false;try{form([{i:[0,0,0,0],a:1n}],2,c)}catch{refused=true}assert(refused,"degree");
return {version:"RGF-004",prime:P.toString(),seed:281981,campaigns,controls:{tamperedPolynomial:"refused",tamperedDirection:"refused",nonminimalChart:"refused",cancellationRank:z.B.length,constantRank:q.B.length,degreeOverflow:"refused"}}
}

console.log(JSON.stringify(rgf004(),null,2));
