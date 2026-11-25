function makeOTG(){
"use strict";
const bit=i=>1n<<BigInt(i);
const ok=(v,msg)=>{if(!v)throw Error(msg)};
function meter(cap=30000000){return {work:0,tick(n=1){this.work+=n;if(this.work>cap)throw Error("work cap")}}}
function indices(x,m){let a=[],i=0;while(x){m.tick();if(x&1n)a.push(i);x>>=1n;i++}return a}
function dot(a,b,m){let x=a&b,s=0;while(x){m.tick();x&=x-1n;s^=1}m.tick();return s}
function validate(s,old,m){ok(Number.isInteger(s.n)&&s.n>=1&&s.n<=128&&[0,1].includes(s.c)&&Array.isArray(s.l)&&Array.isArray(s.p),"source");let seen=new Set;for(const i of s.l){m.tick();ok(Number.isInteger(i)&&i>=0&&i<s.n&&!seen.has(i),"linear");seen.add(i)}seen=new Set;for(const p of s.p){m.tick();ok(Array.isArray(p)&&p.length===2&&Number.isInteger(p[0])&&Number.isInteger(p[1])&&p[0]>=0&&p[0]<p[1]&&p[1]<s.n&&!seen.has(p.join(",")),"pair");seen.add(p.join(","))}ok(Array.isArray(old)&&old.length<=s.n&&old.every(r=>typeof r==="bigint"&&r>0n&&r<bit(s.n)),"old rows")}
function evalF(s,x,m){let y=s.c;for(const i of s.l){m.tick();y^=Number((x>>BigInt(i))&1n)}for(const [i,j] of s.p){m.tick();y^=Number(((x>>BigInt(i))&(x>>BigInt(j)))&1n)}return y}
function polar(s,m){let p=Array(s.n).fill(0n);for(const [i,j] of s.p){m.tick(2);p[i]^=bit(j);p[j]^=bit(i)}return p}
function echelon(rows,n,m){let piv=Array(n).fill(null);for(let i=0;i<rows.length;i++){let r=rows[i],t=bit(i);for(let j=0;j<n&&r;j++){m.tick();if(!(r&bit(j)))continue;if(piv[j]){m.tick(2);r^=piv[j].r;t^=piv[j].t}else{piv[j]={r,t};break}}ok(r!==0n,"dependent rows")}return piv}
function residual(r,piv,m){for(let j=0;j<piv.length&&r;j++){m.tick();if(piv[j]&&(r&bit(j))){m.tick();r^=piv[j].r}}return r}
function solve(piv,rhs,free,m){let x=free;for(let i=piv.length-1;i>=0;i--){m.tick();let p=piv[i];if(p&&dot(p.t,rhs,m)!==dot(p.r,x,m))x^=bit(i)}return x}
function observe(rows,x,m){let z=0n;for(let i=0;i<rows.length;i++){m.tick();if(dot(rows[i],x,m))z|=bit(i)}return z}
function compile(s,old=[],cap=30000000){
const m=meter(cap);validate(s,old,m);let rows=old.slice(),piv=echelon(rows,s.n,m),events=[],B=polar(s,m);
for(let i=0;i<s.n;i++){const r=B[i];if(!residual(r,piv,m))continue;const next=echelon([...rows,r],s.n,m);const d=solve(next,bit(rows.length),0n,m);const x=(evalF(s,d,m)^s.c)?0n:bit(i);ok(evalF(s,x,m)!==evalF(s,x^d,m),"polar witness");events.push({kind:"polar",index:i,row:r,d,x});rows.push(r);piv=next}
let extra=0n,witness=0n;
for(let i=0;i<s.n;i++){m.tick();if(piv[i])continue;const d=solve(piv,0n,bit(i),m);if(evalF(s,d,m)!==s.c){extra|=bit(i);if(!witness)witness=d}}
if(extra){events.push({kind:"radical",row:extra,d:witness,x:0n});rows.push(extra);piv=echelon(rows,s.n,m)}
let k=rows.length,section=rows.map((_,i)=>solve(piv,bit(i),0n,m)),l=[],p=[],v=section.map(x=>evalF(s,x,m)^s.c);
for(let i=0;i<k;i++){m.tick();if(v[i])l.push(i);for(let j=i+1;j<k;j++){m.tick();if(evalF(s,section[i]^section[j],m)^s.c^v[i]^v[j])p.push([i,j])}}
return {rows,events,decoder:{n:k,c:s.c,l,p},formationWork:m.work}
}
// Independent checker: high-pivot rank plus direct symbolic substitution, not producer section or discovery.
function rank(rows,n,m){let a=rows.slice(),r=0;for(let j=n-1;j>=0;j--){let i=r;while(i<a.length&&!(a[i]&bit(j))){m.tick();i++}m.tick();if(i===a.length)continue;[a[r],a[i]]=[a[i],a[r]];for(i=r+1;i<a.length;i++){m.tick();if(a[i]&bit(j)){m.tick();a[i]^=a[r]}}r++}return r}
function verify(s,old,g,cap=30000000){const m=meter(cap);try{
validate(s,old,m);ok(g&&Array.isArray(g.rows)&&Array.isArray(g.events)&&g.rows.length<=s.n&&g.events.length===g.rows.length-old.length,"shape");
ok(old.every((v,i)=>g.rows[i]===v)&&g.rows.every(r=>typeof r==="bigint"&&r>0n&&r<bit(s.n)),"rows");
ok(rank(g.rows,s.n,m)===g.rows.length,"row rank");
let B=Array(s.n).fill(0n);for(const [i,j] of s.p){m.tick(2);B[i]|=bit(j);B[j]|=bit(i)}
let baseRank=rank([...old,...B],s.n,m),extra=0;
for(let j=0;j<g.events.length;j++){const e=g.events[j],i=old.length+j;ok(e.row===g.rows[i]&&typeof e.d==="bigint"&&e.d>0n&&e.d<bit(s.n)&&typeof e.x==="bigint"&&e.x>=0n&&e.x<bit(s.n),"event");
ok(g.rows.slice(0,i).every(r=>dot(r,e.d,m)===0)&&dot(e.row,e.d,m)===1&&evalF(s,e.x,m)!==evalF(s,e.x^e.d,m),"counterexample");
if(e.kind==="polar"){ok(!extra&&Number.isInteger(e.index)&&B[e.index]===e.row,"polar")}
else{ok(e.kind==="radical"&&!extra&&i===g.rows.length-1&&[...old,...B].every(r=>dot(r,e.d,m)===0),"radical lower bound");extra=1}}
ok(g.rows.length===baseRank+extra,"minimal rank");
const d=g.decoder;ok(d&&d.n===g.rows.length&&[0,1].includes(d.c)&&Array.isArray(d.l)&&Array.isArray(d.p),"decoder");
let masks=g.rows.map(r=>indices(r,m)),terms=new Set;
const toggle=(i,j=i)=>{m.tick();let k=i<=j?i+","+j:j+","+i;if(terms.has(k))terms.delete(k);else terms.add(k)};
const valid=i=>Number.isInteger(i)&&i>=0&&i<d.n;
let seen=new Set;for(const i of d.l){ok(valid(i)&&!seen.has(i),"decoder linear");seen.add(i);for(const a of masks[i])toggle(a)}
seen=new Set;for(const [i,j] of d.p){ok(valid(i)&&valid(j)&&i<j&&!seen.has(i+","+j),"decoder pair");seen.add(i+","+j);for(const a of masks[i])for(const b of masks[j])toggle(a,b)}
ok(d.c===s.c&&terms.size===s.l.length+s.p.length,"identity size");
for(const i of s.l){m.tick();ok(terms.has(i+","+i),"linear identity")}for(const [i,j] of s.p){m.tick();ok(terms.has(i+","+j),"pair identity")}
return {ok:true,work:m.work}
}catch(e){return {ok:false,work:m.work,reason:String(e.message)}}}
function campaign(){
let seed=90210;const rand=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed};const sample=(n)=>{let x=0n;for(let i=0;i<n;i++)if((rand()>>>23)&1)x|=bit(i);return x};
const randomSource=n=>{let l=[],p=[];for(let i=0;i<n;i++){if((rand()>>>27)<13)l.push(i);for(let j=i+1;j<n;j++)if((rand()>>>27)<12)p.push([i,j])}return {n,c:rand()>>>31,l,p}};
let sources=0,states=0,tamper=0;
for(let n=2;n<=8;n++)for(let trial=0;trial<24;trial++){
const s=randomSource(n),old=trial%3===0?[1n]:[],g=compile(s,old),v=verify(s,old,g);ok(v.ok,v.reason);sources++;
let mm=meter(),kernel=0;for(let x=0n;x<bit(n);x++){ok(evalF(s,x,mm)===evalF(g.decoder,observe(g.rows,x,mm),mm),"exhaustive query");states++;if(old.every(r=>!dot(r,x,mm))){let invariant=true;for(let y=0n;y<bit(n);y++){if(evalF(s,y,mm)!==evalF(s,y^x,mm)){invariant=false;break}}if(invariant)kernel++}}
ok(kernel===2**(n-g.rows.length),"independent exhaustive rank minimum");
const bad={...g,decoder:{...g.decoder,c:g.decoder.c^1}};ok(!verify(s,old,bad).ok,"tamper decoder");tamper++;
if(g.events.length){let events=g.events.slice();events[0]={...events[0],d:0n};ok(!verify(s,old,{...g,events}).ok,"tamper witness");tamper++}
}
function structured(n){let p=[],l=[];for(let i=0;i<n;i++){if(i%5===4)l.push(i);for(let j=i+1;j<n;j++){let a=i%5,b=j%5;if((a===0&&b===1)||(a===1&&b===0)||(a===2&&b===3)||(a===3&&b===2))p.push([i,j])}}return {n,c:1,l,p}}
let rows=[];
for(const [kind,n] of [["structured",32],["structured",64],["structured",128],["random",16],["random",32]]){
const s=kind==="structured"?structured(n):randomSource(n),g=compile(s),v=verify(s,[],g);ok(v.ok,v.reason);
let direct=meter(),acquire=meter(),warm=meter();for(let i=0;i<128;i++){let x=sample(n);ok(evalF(s,x,direct)===evalF(g.decoder,observe(g.rows,x,acquire),warm),"heldout")}
rows.push({kind,n,sourceTerms:s.l.length+s.p.length,rank:g.rows.length,decoderTerms:g.decoder.l.length+g.decoder.p.length,formation:g.formationWork,verification:v.work,queries:128,direct:direct.work,acquisition:acquire.work,warm:warm.work,total:g.formationWork+v.work+acquire.work+warm.work})}
let refusal=false;try{compile(structured(32),[],1)}catch(e){refusal=e.message==="work cap"}ok(refusal,"cap refusal");
return {sources,states,tamper,refusal,rows}
}
return {compile,verify,observe,evalF,meter,campaign};
}

if(typeof module!=="undefined") { module.exports=makeOTG(); if(require.main===module) console.log(JSON.stringify(module.exports.campaign(),null,2)); }
