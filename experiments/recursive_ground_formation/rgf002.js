function rgf002(){
"use strict";
const P=2305843009213693951n,D=8,MAX_EAGER=4096n;
const mod=x=>((x%P)+P)%P;
const ctr=()=>({field:0,division:0,structure:0,sourceCalls:0});
const work=c=>c.field+c.division+c.structure;
const A=(x,y,c)=>(c.field++,mod(x+y)),M=(x,y,c)=>(c.field++,mod(x*y));
const assert=(b,m)=>{if(!b)throw Error(m)};
function inv(a,c){let r=P,s=mod(a),u=0n,v=1n;while(s){c.division++;let q=r/s;[r,s]=[s,r-q*s];c.field+=2;[u,v]=[v,u-q*v]}assert(r===1n,"noninvertible");return mod(u)}
function peval(a,t,c){let y=0n;for(let j=a.length-1;j>=0;j--)y=A(M(y,t,c),a[j],c);return y}
function linmul(a,x,v,c){let b=Array(a.length+1).fill(0n);for(let j=0;j<a.length;j++){b[j]=A(b[j],M(a[j],x,c),c);b[j+1]=A(b[j+1],M(a[j],v,c),c)}return b}
function valid(src,dim,c){
assert(src&&Object.keys(src).sort().join(",")==="kind,terms"&&src.kind==="sparse-monomials-v1"&&Array.isArray(src.terms)&&src.terms.length>0&&src.terms.length<=16,"unsupported source");
assert(Number.isInteger(dim)&&dim>=1&&dim<=64,"dimension");
let d=0;for(const term of src.terms){c.structure++;assert(Object.keys(term).sort().join(",")==="a,factors"&&typeof term.a==="bigint"&&term.a>=0n&&term.a<P&&Array.isArray(term.factors)&&term.factors.length<=D,"term/degree");d=Math.max(d,term.factors.length);for(const j of term.factors){c.structure++;assert(Number.isInteger(j)&&j>=0&&j<dim,"factor")}}return d
}
function source(src,x,c){c.sourceCalls++;let y=0n;for(const term of src.terms){c.structure++;let q=term.a;for(const j of term.factors){c.structure++;q=M(q,x[j],c)}y=A(y,q,c)}return y}
function at(x,v,t,c){return x.map((a,i)=>A(a,M(v[i],mod(t),c),c))}
function sourceLine(src,x,v,t,c){return source(src,at(x,v,t,c),c)}
// Independent source-line interpreter: grouped repeated factors and binary powers.
function sourceCheck(src,x,v,t,c){c.sourceCalls++;let y=0n;for(const term of src.terms){c.structure++;let q=term.a;const ex=new Map();for(const j of term.factors){c.structure++;ex.set(j,(ex.get(j)||0)+1)}for(const [j,e] of ex){let b=A(x[j],M(v[j],t,c),c),k=e,z=1n;while(k){if(k%2)z=M(z,b,c);k=Math.floor(k/2);if(k)b=M(b,b,c)}q=M(q,z,c)}y=A(y,q,c)}return y}
function choose(n,k){let a=1n;for(let j=1;j<=k;j++)a=a*BigInt(n-j+1)/BigInt(j);return a}
function basis(d,c){
let rows=[],b=[1n];
for(let j=1;j<=d+1;j++){
b=linmul(b,BigInt(1-j),1n,c).map(a=>M(a,invSmall(j,c),c)); // inverse deliberately computed once below in optimized form
rows.push(b);
}
// Independent degree-bound identity: delta B_j = B_{j-1} at j points; B_j(0)=0.
for(let j=1;j<=d+1;j++){assert(rows[j-1].length===j+1&&rows[j-1][0]===0n,"basis geometry");for(let k=0;k<j;k++){const t=BigInt(37+k),delta=A(peval(rows[j-1],t+1n,c),-peval(rows[j-1],t,c),c);assert(delta===(j===1?1n:peval(rows[j-2],t,c)),"basis certificate")}}
return rows
}
function invSmall(j,c){return inv(BigInt(j),c)}
function newton(src,x,v,d,rows,c){
let vals=Array.from({length:d+1},(_,j)=>sourceLine(src,x,v,BigInt(j),c)),a=[];
while(vals.length){a.push(vals[0]);vals=vals.slice(1).map((q,j)=>A(q,-vals[j],c))}
let h=Array(d+2).fill(0n);
for(let j=0;j<a.length;j++)for(let k=0;k<rows[j].length;k++)h[k]=A(h[k],M(a[j],rows[j][k],c),c);
return h
}
function directPlan(d,c){const pascal=Array.from({length:d+2},()=>[]),inverse=[];for(let j=0;j<=d+1;j++){pascal[j]=Array(j+1).fill(1n);for(let k=1;k<j;k++)pascal[j][k]=A(pascal[j-1][k-1],pascal[j-1][k],c);if(j)inverse[j]=inv(BigInt(j),c)}return {pascal,inverse}}
function direct(src,x,v,d,plan,c){
let f=Array(d+1).fill(0n);
for(const term of src.terms){c.structure++;let a=[term.a];for(const j of term.factors){c.structure++;a=linmul(a,x[j],v[j],c)}for(let k=0;k<a.length;k++)f[k]=A(f[k],a[k],c)}
let h=Array(d+2).fill(0n);
for(let j=d;j>=0;j--){const q=M(f[j],plan.inverse[j+1],c);h[j+1]=q;for(let k=0;k<=j;k++)f[k]=A(f[k],-M(q,plan.pascal[j+1][k],c),c)}
assert(f.every(a=>a===0n),"triangular residual");return h
}
function verify(src,x,v,h,c){
const d=valid(src,x.length,c);
if(!Array.isArray(h)||h.length!==d+2||h.some(a=>typeof a!=="bigint"||a<0n||a>=P)||h[0]!==0n)return false;
// Both sides degree <=d, check d+1 distinct field points. SourceCheck does not use constructor samples.
for(let j=0;j<=d;j++){const t=BigInt(101+j),delta=A(peval(h,t+1n,c),-peval(h,t,c),c);if(delta!==sourceCheck(src,x,v,t,c))return false}return true
}
// Independent oracle: cumulative values at 0..d+1, Lagrange interpolation, no Newton or triangular solve.
function oracleSum(src,x,v,n,d,c){
let vals=[0n];for(let k=0;k<=d;k++)vals.push(A(vals[k],sourceCheck(src,x,v,BigInt(k),c),c));
let z=0n,t=mod(n);for(let j=0;j<vals.length;j++){let top=1n,bottom=1n;for(let k=0;k<vals.length;k++)if(j!==k){top=M(top,A(t,-BigInt(k),c),c);bottom=M(bottom,BigInt(j-k),c)}z=A(z,M(vals[j],M(top,inv(bottom,c),c),c),c)}return z
}
function eagerSeg(src,x,v,y,n,c){for(let t=0n;t<n;t++){y=A(y,source(src,x,c),c);x=x.map((a,i)=>A(a,v[i],c))}return {x,y}}
function validateTask(task,c){const {src,x,v,n,events}=task;let d=valid(src,x.length,c);assert(v.length===x.length&&[...x,...v].every(a=>typeof a==="bigint"&&a>=0n&&a<P)&&typeof n==="bigint"&&n>=0n,"state");let prev=-1n;for(const e of events){c.structure+=3;assert(typeof e.t==="bigint"&&e.t>prev&&e.t>=0n&&e.t<n&&typeof e.impulse==="bigint"&&e.impulse>=0n&&e.impulse<P&&Array.isArray(e.dv)&&e.dv.length===x.length&&e.dv.every(a=>typeof a==="bigint"&&a>=0n&&a<P),"event");prev=e.t}return d}
function run(task,mode,c,cache,stats){
let d=validateTask(task,c),{src,n,events}=task,x=task.x.slice(),v=task.v.slice(),y=task.y,start=0n;
if(mode==="eager"&&n>MAX_EAGER)return null;
function seg(len){
if(!len)return;
const route=mode==="hybrid"?(len<=16n?"eager":"direct"):mode;
if(route==="eager"){({x,y}=eagerSeg(src,x,v,y,len,c));return}
let sum;
if(route==="oracle")sum=oracleSum(src,x,v,len,d,c);
else{
const key=(route==="direct"?"D":"N")+d;
let plan=cache.get(key);
if(!plan){plan=route==="direct"?directPlan(d,c):basis(d,c);cache.set(key,plan);stats.compiles++}
const h=route==="direct"?direct(src,x,v,d,plan,c):newton(src,x,v,d,plan,c);
assert(verify(src,x,v,h,c),"source certificate refused");stats.certificates++;
sum=peval(h,mod(len),c);
}
y=A(y,sum,c);x=at(x,v,len,c)
}
for(const e of events){seg(e.t-start);c.structure+=3;y=A(y,e.impulse,c);v=v.map((a,i)=>A(a,e.dv[i],c));start=e.t}seg(n-start);return {x,y,v}
}
const equal=(a,b)=>a&&b&&a.y===b.y&&a.x.every((v,i)=>v===b.x[i])&&a.v.every((v,i)=>v===b.v[i]);
let seed=746193;function rnd(n){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%n}
const b=()=>BigInt(rnd(1000000));
function task(dim,d,n,eventCount){
const terms=Array.from({length:6},(_,j)=>({a:b()+1n,factors:Array.from({length:j===0?d:rnd(d+1)},()=>rnd(dim))}));
let x=Array.from({length:dim},b),v=Array.from({length:dim},b);
let events=Array.from({length:eventCount},(_,j)=>({t:n*BigInt(j+1)/BigInt(eventCount+1),impulse:b(),dv:Array.from({length:dim},(_,i)=>i%5===j?b():0n)}));
return {src:{kind:"sparse-monomials-v1",terms},x,v,y:b(),n,events}
}
const modes=["eager","cold","warm","direct","hybrid"],campaigns=[];
function campaign(name,count,dim,ns,degrees,events){
let result=Object.fromEntries(modes.map(m=>[m,{cost:ctr(),compiles:0,certificates:0,completed:0,refused:0}])),audit=ctr(),warm=new Map(),directCache=new Map(),hybridCache=new Map();
for(let i=0;i<count;i++){
const t=task(dim,degrees[i%degrees.length],ns[i%ns.length],events),ref=run(t,"oracle",audit,new Map(),{compiles:0,certificates:0});
for(const mode of modes){const s=result[mode],cache=mode==="warm"?warm:mode==="direct"?directCache:mode==="hybrid"?hybridCache:new Map();
const got=run(t,mode,s.cost,cache,s);
if(got===null){s.refused++;continue}assert(equal(got,ref),name+" "+mode+" mismatch");s.completed++}
}
for(const r of Object.values(result)){r.work=work(r.cost)}
let payload=m=>[...m.values()].reduce((n,a)=>n+(Array.isArray(a)?a.reduce((s,row)=>s+row.length,0):a.pascal.reduce((s,row)=>s+row.length,0)+a.inverse.length-1)*8,0);
return {name,count,dim,geometryBits:Math.floor(dim*Math.log2(Number(P))),eventCount:events,result,auditWork:work(audit),retainedPayloadBytes:{warm:payload(warm),direct:payload(directCache),hybrid:payload(hybridCache)}}
}
campaigns.push(campaign("short",24,8,[8n,16n,32n],[1,2,4,8],0));
campaigns.push(campaign("medium",24,16,[256n,1024n,4096n],[1,2,4,8],2));
campaigns.push(campaign("huge",32,32,[10n**12n,10n**24n,P+19n],[0,1,2,4,8],3));
// Adversarial certificates: wrong coefficient, excessive degree, unsupported source fields.
const c=ctr(),t=task(8,4,10n**24n,2),d=valid(t.src,8,c),rows=basis(d,c),h=newton(t.src,t.x,t.v,d,rows,c);
assert(verify(t.src,t.x,t.v,h,c),"valid cert");
let bad=h.slice();bad[1]=A(bad[1],1n,c);assert(!verify(t.src,t.x,t.v,bad,c),"bad cert accepted");
let over=[0n,1n];for(let j=0;j<=d+1;j++)over=linmul(over,-BigInt(101+j),1n,c);
assert(!verify(t.src,t.x,t.v,over,c),"overdegree accepted");
let opaque=false;try{valid({...t.src,override:1},8,c)}catch{opaque=true}assert(opaque,"unknown source accepted");
let degree=false;try{valid({kind:"sparse-monomials-v1",terms:[{a:1n,factors:Array(D+1).fill(0)}]},8,c)}catch{degree=true}assert(degree,"source degree bound accepted");
const no={...t,events:t.events.slice(0,-1)},a=run(t,"warm",c,new Map(),{compiles:0,certificates:0}),z=run(no,"warm",c,new Map(),{compiles:0,certificates:0});assert(!equal(a,z),"missing event invisible");
let duplicate=false;try{validateTask({...t,events:[t.events[0],t.events[0]]},c)}catch{duplicate=true}assert(duplicate,"duplicate event accepted");
return {version:"RGF-002",prime:P.toString(),maxDegree:D,seed:746193,campaigns,controls:{badCertificate:"refused",overdegreeCertificate:"refused",opaqueSource:"refused",sourceDegreeOverflow:"refused",duplicateEvent:"refused",missingEventChangesState:true,work:work(c)}}
}

console.log(JSON.stringify(rgf002(),null,2));
