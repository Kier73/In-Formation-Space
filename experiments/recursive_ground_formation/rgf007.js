function rgf007(){
"use strict";
const P=2305843009213693951n,L=P-1n,ok=(x,s)=>{if(!x)throw Error(s)};
const mod=(a,p=P)=>(a%p+p)%p, C=()=>({field:0,integer:0,visits:0,exponent:0}),work=c=>Object.values(c).reduce((a,b)=>a+b,0);
const abs=a=>a<0n?-a:a;
function gcd(a,b,c){a=abs(a);b=abs(b);while(b){c.integer++;[a,b]=[b,a%b]}return a}
function primitive(v,c){let g=0n;for(const a of v)g=gcd(g,a,c);if(!g)return v;return v.map(a=>(c.integer++,a/g))}
const zero=n=>Array(n).fill(0n),same=(a,b)=>a.length===b.length&&a.every((v,i)=>v===b[i]);
function dot(a,b,c){let z=0n;for(let i=0;i<a.length;i++){c.visits++;z+=a[i]*b[i];c.integer+=2}return z}
function pow(a,n,p,c){ok(n>=0n,"negative exponent");let z=1n;a=mod(a,p);while(n){c.exponent++;if(n&1n){z=z*a%p;c.field++}n>>=1n;if(n){a=a*a%p;c.field++}}return z}
function evalQ(q,x,c){let y=0n;for(const t of q){c.visits++;let z=t.a;for(let i=0;i<x.length;i++){c.visits++;if(t.e[i]){z=z*pow(x[i],t.e[i],P,c)%P;c.field++}}y=(y+z)%P;c.field++}return y}
function canonical(raw,n,c){ok(raw.length<=128,"term cap");let m=new Map();for(const t of raw){ok(typeof t.a==="bigint"&&t.a>=0n&&t.a<P&&t.e.length===n&&t.e.every(a=>typeof a==="bigint"&&a>=0n&&a<=12n),"source term");let k=t.e.join(",");m.set(k,mod((m.get(k)||0n)+t.a));c.field++;c.visits+=n+1}return [...m].filter(([,a])=>a).map(([k,a])=>({a,e:k.split(",").map(BigInt)}))}
function constraints(qs,n,c){let rows=[];for(const q of qs)for(let i=1;i<q.length;i++){rows.push(q[i].e.map((a,j)=>(c.integer++,a-q[0].e[j])));c.visits+=n}return rows}
// Integer fraction-free row elimination. Primitive rows limit growth.
function nullspace(rows,n,c){
 let a=rows.map(r=>r.slice()),p=[],r=0;
 for(let j=0;j<n&&r<a.length;j++){
 let k=r;while(k<a.length&&!a[k][j]){k++;c.visits++}if(k===a.length)continue;
 [a[r],a[k]]=[a[k],a[r]];a[r]=primitive(a[r],c);
 for(let i=0;i<a.length;i++)if(i!==r&&a[i][j]){
 let x=a[r][j],y=a[i][j];a[i]=primitive(a[i].map((v,l)=>(c.integer+=3,x*v-y*a[r][l])),c)}
 p.push(j);r++;
 }
 let free=Array.from({length:n},(_,i)=>i).filter(i=>!p.includes(i)),out=[];
 for(const j of free){let v=zero(n),den=1n;for(let i=0;i<r;i++){den*=abs(a[i][p[i]]);c.integer++}
 v[j]=den;for(let i=0;i<r;i++){v[p[i]]=-a[i][j]*(den/a[i][p[i]]);c.integer+=2}out.push(primitive(v,c))}
 return out
}
function form(raw,n,c){
 ok(n>=1&&n<=12&&raw.length>=1&&raw.length<=4,"source bound");let qs=raw.map(q=>canonical(q,n,c)),rows=constraints(qs,n,c),kernel=nullspace(rows,n,c),weights=[];
 // Bounded candidate grammar: basis, sign reversal, pairwise +/- combinations.
 let cand=kernel.flatMap(v=>[v,v.map(a=>-a)]);
 for(let i=0;i<kernel.length;i++)for(let j=i+1;j<kernel.length;j++)for(const a of [1n,-1n])for(const b of [1n,-1n])cand.push(kernel[i].map((v,k)=>(c.integer+=3,a*v+b*kernel[j][k])));
 let seen=new Set();
 for(let w of cand){w=primitive(w,c);if(!w.some(a=>a>0n)||w.some(a=>a<0n||a>128n))continue;
 let d=qs.map(q=>q.length?dot(q[0].e,w,c):0n);if(!d.some(a=>a>0n))continue;
 let k=w.join(",");if(seen.has(k))continue;seen.add(k);weights.push({w,d})}
 let ops=weights.flatMap((v,i)=>qs.map((q,j)=>({weight:i,source:j,w:v.w,d:v.d})).filter(a=>qs[a.source].length));
 return {qs,kernel,weights,ops}
}
// Independently group raw terms, then check all monomial weights. No construction/rank routine used.
function verify(raw,n,g,c){try{
 let q=raw.map(ts=>{let s=ts.map(t=>({k:t.e.join(","),a:t.a})).sort((a,b)=>a.k.localeCompare(b.k)),out=[];
 for(let i=0;i<s.length;){let j=i,a=0n;while(j<s.length&&s[j].k===s[i].k){a=mod(a+s[j++].a);c.field++;c.visits++}if(a)out.push({e:s[i].k.split(",").map(BigInt),a});i=j}return out});
 ok(g.qs.length===q.length&&q.every((ts,i)=>ts.length===g.qs[i].length&&ts.every(t=>g.qs[i].some(u=>u.a===t.a&&same(u.e,t.e)))),"source binding");
 for(const a of g.ops){ok(a.source>=0&&a.source<q.length&&q[a.source].length&&a.w.length===n&&a.w.every(w=>typeof w==="bigint"&&w>=0n&&w<=128n)&&a.w.some(w=>w>0n)&&a.d.length===q.length,"op shape");
 for(let j=0;j<q.length;j++){if(!q[j].length)ok(a.d[j]===0n,"zero degree");for(const t of q[j]){let d=0n;for(let k=0;k<n;k++){d+=t.e[k]*a.w[k];c.integer+=2;c.visits++}ok(d===a.d[j],"grading identity")}}}
 return true}catch{return false}}
function geom(a,t,c){ // sum 1+a+...+a^(t-1) mod L, binary composition
 let s=0n,p=1n,b=mod(a,L),r=1n;
 while(t){c.exponent++;if(t&1n){s=(s+p*r)%L;p=p*b%L;c.integer+=3}t>>=1n;if(t){r=(r+b*r)%L;b=b*b%L;c.integer+=3}}return s
}
function factor(z,e,s,t,c){if(!e||!t)return 1n;if(!z)return 0n;c.integer++;return pow(z,e*s%L,P,c)}
function advance(a,z,t,s,c){let q=z[a.source];return z.map((v,j)=>{c.visits++;if(!a.d[j]||!t)return v;let k=factor(q,a.d[j],s,t,c);c.field++;return v*k%P})}
function rawAdvance(a,x,z,t,s,c){return x.map((v,j)=>{c.visits++;if(!a.w[j]||!t)return v;let k=factor(z,a.w[j],s,t,c);c.field++;return v*k%P})}
function evaluator(g,mode,c){let cache=new Map();function sum(a,t){let k=a.d[a.source]+":"+t;c.visits++;if(!cache.has(k))cache.set(k,geom(1n+a.d[a.source],t,c));return cache.get(k)}
 return {cache,run(x,word){let z=g.qs.map(q=>evalQ(q,x,c)),obs=[];for(const [i,t] of word){const a=g.ops[i],s=sum(a,t);
 if(mode==="raw"){x=rawAdvance(a,x,z[a.source],t,s,c);z=g.qs.map(q=>evalQ(q,x,c))}
 else{if(mode==="both")x=rawAdvance(a,x,z[a.source],t,s,c);z=advance(a,z,t,s,c)}
 obs.push({z:z.slice(),x:mode==="scalar"?null:x.slice()})}return obs}}
}
// Independent exact huge-time oracle: exponent matrix for full coordinates plus morphologies.
// Residue and positivity tracked independently to handle zero bases and 0^0.
function matrixOracle(g,x,word,c){
 let z=g.qs.map(q=>evalQ(q,x,c)),n=x.length,k=n+z.length,v=[...x,...z],out=[];
 function mulmat(a,b){return a.map(r=>Array.from({length:k},(_,j)=>{let s=0n;for(let i=0;i<k;i++){s=(s+r[i]*b[i][j])%L;c.integer+=2}return s}))}
 function boolmat(a,b){return a.map(r=>Array.from({length:k},(_,j)=>{for(let i=0;i<k;i++){c.visits++;if(r[i]&&b[i][j])return true}return false}))}
 for(const [id,count] of word){let op=g.ops[id],E=Array.from({length:k},(_,i)=>Array.from({length:k},(_,j)=>(i===j?1n:0n)+(j===n+op.source?(i<n?op.w[i]:op.d[i-n]):0n)));
 let B=E.map(r=>r.map(x=>x>0n)),t=count;
 while(t){c.exponent++;if(t&1n)v=E.map((r,i)=>{let a=1n;for(let j=0;j<k;j++){c.visits++;if(!B[i][j])continue;if(v[j]===0n){a=0n;break}a=a*pow(v[j],r[j],P,c)%P;c.field++}return a});
 t>>=1n;if(t){E=mulmat(E,E);B=boolmat(B,B)}}
 ok(same(v.slice(n),g.qs.map(q=>evalQ(q,v.slice(0,n),c))),"oracle consistency");out.push({x:v.slice(0,n),z:v.slice(n)})
 }return out
}
function eager(g,x,word,c){let out=[];for(const [id,t] of word){let a=g.ops[id];for(let j=0n;j<t;j++){let z=evalQ(g.qs[a.source],x,c);x=x.map((v,i)=>{c.field++;return v*pow(z,a.w[i],P,c)%P})}out.push({x:x.slice(),z:g.qs.map(q=>evalQ(q,x,c))})}return out}
let seed=720173;function rnd(n){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return (seed>>>8)%n}
const rndF=()=>BigInt(1+rnd(1000));
function fixture(n,groups){
 let qs=Array.from({length:groups},()=>[]),w=Array.from({length:n},(_,i)=>[1n,2n,3n][i%3]);
 for(let i=0;i<n;i++){let j=i%groups,e=zero(n);e[i]=6n/w[i];qs[j].push({a:rndF(),e})}
 // Extra cross monomials (when sum of weighted exponents is six).
 for(let j=0;j<groups;j++){let is=Array.from({length:n},(_,i)=>i).filter(i=>i%groups===j);for(let i=0;i<is.length-1;i++){let a=is[i],b=is[i+1],e=zero(n);
 for(let u=1n;u<6n;u++)if(6n>u*w[a]&&(6n-u*w[a])%w[b]===0n){e[a]=u;e[b]=(6n-u*w[a])/w[b];qs[j].push({a:rndF(),e});break}}
 let e=zero(n);e[(j+1)%n]=1n;let a=rndF();qs[j].push({a,e},{a:P-a,e:e.slice()})}
 return qs
}
function campaign(name,n,groups,N,blocks){
 let raw=fixture(n,groups),fc=C(),vc=C(),g=form(raw,n,fc);ok(verify(raw,n,g,vc)&&g.ops.length>0,"formed operations");
 let cs=C(),cr=C(),cb=C(),audit=C(),ec=C(),scalar=evaluator(g,"scalar",cs),full=evaluator(g,"raw",cr),both=evaluator(g,"both",cb),checks=0,eagerChecks=0,crossover=null;
 for(let i=0;i<N;i++){let x=Array.from({length:n},rndF);if(i%7===0)for(let j=0;j<n;j++)if(j%groups===0)x[j]=0n;
 let word=Array.from({length:blocks},(_,j)=>[rnd(g.ops.length),i%6===0?BigInt(rnd(5)):10n**24n+BigInt(rnd(1000))]);
 let a=scalar.run(x,word),b=full.run(x,word),d=both.run(x,word),ref=matrixOracle(g,x,word,audit);
 for(let j=0;j<blocks;j++){ok(same(a[j].z,ref[j].z)&&same(b[j].z,ref[j].z)&&same(b[j].x,ref[j].x)&&same(d[j].z,ref[j].z)&&same(d[j].x,ref[j].x),"oracle mismatch");checks+=3}
 if(i%6===0){let r=eager(g,x,word,ec);for(let j=0;j<blocks;j++){ok(same(r[j].x,ref[j].x)&&same(r[j].z,ref[j].z),"eager");eagerChecks++}}
 if(crossover===null&&work(fc)+work(vc)+work(cs)<work(cr)+work(fc)+work(vc))crossover=i+1;
 }
 let setup=work(fc)+work(vc);
 return {name,n,groups,tasks:N,blocks,checks,eagerChecks,kernelRank:g.kernel.length,weightCount:g.weights.length,operations:g.ops.length,weights:g.weights.map(a=>({w:a.w.map(String),d:a.d.map(String)})),work:{formation:work(fc),qualification:work(vc),scalar:work(cs)+setup,full:work(cr)+setup,both:work(cb)+setup,audit:work(audit),eager:work(ec)},runtime:{scalar:work(cs),full:work(cr),both:work(cb)},crossoverAfterSharedSetup:crossover,cache:{scalar:scalar.cache.size,full:full.cache.size,both:both.cache.size}}
}
const campaigns=[campaign("heterogeneous-two",6,2,24,8),campaign("heterogeneous-three",9,3,18,6),campaign("single-coordinate-control",1,1,12,6),campaign("single-use",6,2,1,1)];
const c=C(),raw=fixture(6,2),g=form(raw,6,c);ok(verify(raw,6,g,c),"valid");
let bad={...g,ops:g.ops.map(a=>({...a,d:a.d.slice()}))};bad.ops[0].d[0]+=1n;ok(!verify(raw,6,bad,c),"tampered degree");
let no=form([[{a:1n,e:[1n,0n]},{a:1n,e:[0n,1n]},{a:1n,e:[1n,1n]}]],2,c);ok(no.kernel.length===0&&no.ops.length===0,"full constraint refusal");
let signed=form([[{a:1n,e:[0n,0n]},{a:1n,e:[1n,1n]}]],2,c);ok(signed.kernel.length===1&&signed.ops.length===0,"signed refusal");
let zcase=form([[{a:1n,e:[1n,0n]}],[{a:1n,e:[0n,1n]}]],2,c);
let id=zcase.ops.findIndex(a=>a.source===0&&a.w[1]>0n),word=[[id,10n**24n]],x=[0n,3n];ok(id>=0,"zero op");
let a=evaluator(zcase,"scalar",c).run(x,word)[0],b=matrixOracle(zcase,x,word,c)[0];ok(same(a.z,b.z)&&same(b.x,[0n,0n]),"zero positive exponent");
let id2=zcase.ops.findIndex(a=>a.source===0&&a.w[0]>0n&&a.w[1]===0n);ok(id2>=0,"zero exponent op");
let b2=matrixOracle(zcase,x,[[id2,10n**24n]],c)[0];ok(same(b2.x,[0n,3n]),"zero exponent preservation");
return {version:"RGF-007",prime:P.toString(),seed:720173,campaigns,controls:{tamperedDegree:"refused",fullConstraintRank:"no generated operation",signedOnlyKernel:"no nonnegative candidate",zeroPositiveExponent:"checked",zeroExponentPreservation:"checked"}}
}

console.log(JSON.stringify(rgf007(),null,2));
