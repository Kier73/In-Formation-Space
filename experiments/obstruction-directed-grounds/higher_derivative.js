function build(){
"use strict";
const b=i=>1n<<BigInt(i), has=(x,i)=>!!(x&b(i)), check=(x,s)=>{if(!x)throw Error(s)};
function meter(cap=40000000){return {work:0,tick(n=1){this.work+=n;if(this.work>cap)throw Error("work cap")}}}
function pc(x,m){let z=0;while(x){m.tick();x&=x-1n;z++}return z}
const dot=(x,y,m)=>pc(x&y,m)%2;
function toggle(s,t,m){m.tick();if(s.has(t))s.delete(t);else s.add(t)}
function validate(n,fs,old,m){check(Number.isInteger(n)&&n>=1&&n<=128&&Array.isArray(fs)&&fs.length>0&&fs.length<=16&&Array.isArray(old)&&old.length<=n,"domain");for(const f of fs){check(Array.isArray(f)&&f.length<=100000&&new Set(f).size===f.length,"source");for(const t of f){m.tick();check(typeof t==="bigint"&&t>=0n&&t<b(n)&&pc(t,m)<=4,"term")}}for(const r of old){m.tick();check(typeof r==="bigint"&&r>0n&&r<b(n),"row")}}
function ev(f,x,m){let y=0;for(const t of f){m.tick();if((t&x)===t)y^=1}return y}
function echelon(rows,n,m){let p=Array(n).fill(null);for(let j=0;j<rows.length;j++){let r=rows[j],t=b(j);for(let i=0;i<n&&r;i++){m.tick();if(!has(r,i))continue;if(p[i]){m.tick(2);r^=p[i].r;t^=p[i].t}else{p[i]={r,t};break}}check(r,"dependent")}return p}
function reduce(r,p,m){for(let i=0;i<p.length&&r;i++){m.tick();if(p[i]&&has(r,i)){m.tick();r^=p[i].r}}return r}
function solve(p,rhs,free,m){let x=free;for(let i=p.length-1;i>=0;i--){m.tick();if(p[i]&&dot(p[i].t,rhs,m)!==dot(p[i].r,x,m))x^=b(i)}return x}
function kernel(p,m){let free=[],basis=[];for(let i=0;i<p.length;i++){m.tick();if(!p[i]){free.push(i);basis.push(solve(p,0n,b(i),m))}}return {free,basis}}
function derivative(f,d,m){let s=new Set;for(const t of f){m.tick();let u=t&d;for(let a=u;a;a=(a-1n)&u)toggle(s,t^a,m)}return s}
function degree(ds,m){let k=-1;for(const s of ds)for(const t of s)k=Math.max(k,pc(t,m));return k}
function mul(a,c,m){let s=new Set;for(const x of a)for(const y of c)toggle(s,x|y,m);return s}
function formRows(rows,n,m){return rows.map(r=>{let s=new Set;for(let i=0;i<n;i++){m.tick();if(has(r,i))s.add(b(i))}return s})}
function sub(f,forms,m){let out=new Set;for(const t of f){m.tick();let p=new Set([0n]),u=t,i=0;while(u){m.tick();if(u&1n)p=mul(p,forms[i],m);u>>=1n;i++}for(const a of p)toggle(out,a,m)}return [...out].sort((a,c)=>a<c?-1:a>c?1:0)}
function compile(n,fs,old=[],cap=40000000){let m=meter(cap);validate(n,fs,old,m);let rows=old.slice(),p=echelon(rows,n,m),rounds=[];
for(;;){const {free,basis}=kernel(p,m),ds=fs.map(f=>basis.map(d=>derivative(f,d,m))),k=degree(ds.flat(),m);if(k<0)break;let added=[];
for(let j=0;j<fs.length;j++){let cs=new Map;for(let i=0;i<basis.length;i++)for(const t of ds[j][i]){m.tick();if(pc(t,m)===k)cs.set(t,(cs.get(t)||0n)|b(free[i]))}
for(const [term,row] of cs){if(!reduce(row,p,m))continue;const next=echelon([...rows,row],n,m),d=solve(next,b(rows.length),0n,m),diff=derivative(fs[j],d,m);check(diff.has(term),"coefficient witness");let x=0n,min=Infinity;for(const t of diff){let c=pc(t,m);if(c<min){min=c;x=t}}check(ev(fs[j],x,m)!==ev(fs[j],x^d,m),"point witness");added.push({target:j,term,row,d,x});rows.push(row);p=next}}
check(added.length>0,"progress");rounds.push({degree:k,basis,added});check(rounds.length<=4,"degree descent")}
const section=rows.map((_,i)=>solve(p,b(i),0n,m)),sf=Array.from({length:n},(_,i)=>new Set(section.flatMap((x,j)=>{m.tick();return has(x,i)?[b(j)]:[]})));
return {rows,rounds,decoders:fs.map(f=>sub(f,sf,m)),formation:m.work}}
function auditDerivative(f,d,m){let s=new Set;for(const t of f){m.tick();let p=[t],u=t&d;while(u){m.tick();let l=u&(-u);u^=l;p=p.concat(p.map(x=>{m.tick();return x^l}))}for(const x of p)toggle(s,x,m);toggle(s,t,m)}return s}
function rank(rows,n,m){let a=rows.slice(),r=0;for(let i=n-1;i>=0;i--){let j=r;while(j<a.length&&!has(a[j],i)){m.tick();j++}m.tick();if(j===a.length)continue;[a[r],a[j]]=[a[j],a[r]];for(j=r+1;j<a.length;j++){m.tick();if(has(a[j],i)){m.tick();a[j]^=a[r]}}r++}return r}
function verify(n,fs,old,g,cap=40000000){let m=meter(cap);try{validate(n,fs,old,m);check(g&&Array.isArray(g.rows)&&Array.isArray(g.rounds)&&Array.isArray(g.decoders)&&g.rows.length<=n&&g.rounds.length<=4&&g.decoders.length===fs.length&&g.rows.every(r=>typeof r==="bigint"&&r>0n&&r<b(n))&&old.every((r,i)=>g.rows[i]===r),"shape");let cur=old.slice(),last=4;check(rank(cur,n,m)===cur.length,"old rank");
for(const round of g.rounds){check(Number.isInteger(round.degree)&&round.degree>=0&&round.degree<last&&Array.isArray(round.basis)&&Array.isArray(round.added)&&round.added.length>0,"round");last=round.degree;const basis=round.basis;check(basis.length===n-cur.length&&basis.every(d=>typeof d==="bigint"&&d>0n&&d<b(n)&&cur.every(r=>!dot(r,d,m)))&&rank(basis,n,m)===basis.length,"kernel");let ds=fs.map(f=>basis.map(d=>auditDerivative(f,d,m)));check(degree(ds.flat(),m)===last,"degree");
for(const e of round.added){check(Number.isInteger(e.target)&&e.target>=0&&e.target<fs.length&&typeof e.term==="bigint"&&e.term>=0n&&e.term<b(n)&&pc(e.term,m)===last&&e.row===g.rows[cur.length]&&typeof e.d==="bigint"&&e.d>0n&&e.d<b(n)&&typeof e.x==="bigint"&&e.x>=0n&&e.x<b(n),"event");check(basis.every((d,i)=>dot(e.row,d,m)===Number(ds[e.target][i].has(e.term))),"necessary row");check(cur.every(r=>!dot(r,e.d,m))&&dot(e.row,e.d,m)===1&&ev(fs[e.target],e.x,m)!==ev(fs[e.target],e.x^e.d,m),"counterexample");cur.push(e.row)}check(rank(cur,n,m)===cur.length,"rank")}
check(cur.length===g.rows.length,"rows");let k=cur.length,q=formRows(cur,n,m);
for(let i=0;i<fs.length;i++){let f=g.decoders[i];check(Array.isArray(f)&&f.length<=100000&&new Set(f).size===f.length&&f.every(t=>typeof t==="bigint"&&t>=0n&&t<b(k)&&pc(t,m)<=4),"decoder");let out=new Set;for(const t of f){let factors=[];for(let j=0;j<k;j++){m.tick();if(has(t,j))factors.push(q[j])}function walk(j,x){m.tick();if(j===factors.length){toggle(out,x,m);return}for(const r of factors[j])walk(j+1,x|r)}walk(0,0n)}check(out.size===fs[i].length&&fs[i].every(t=>out.has(t)),"identity")}
return {ok:true,work:m.work}
}catch(e){return {ok:false,work:m.work,reason:String(e.message)}}}
function observe(rows,x,m){let z=0n;for(let i=0;i<rows.length;i++){m.tick(2);if(dot(rows[i],x,m))z|=b(i)}return z}
function image(g,cap=40000000,maxRank=16){let m=meter(cap),k=g.rows.length;check(k<=maxRank&&k<=20,"image rank cap");let labels=new Map;for(let z=0n;z<b(k);z++){let y=0n;for(let i=0;i<g.decoders.length;i++){m.tick();if(ev(g.decoders[i],z,m))y|=b(i)}if(!labels.has(y))labels.set(y,z)}return {labels,work:m.work,bits:Math.ceil(Math.log2(labels.size))}}
function campaign(){
let seed=926034;const rand=()=>seed=(Math.imul(seed,1664525)+1013904223)>>>0;
let small=0,states=0,tamper=0,profiles={};
for(let n=2;n<=7;n++)for(let j=0;j<24;j++){let fs=Array.from({length:1+j%3},()=>{let f=[];for(let t=0n;t<b(n);t++)if(pc(t,meter())<=4&&(rand()>>>27)<8)f.push(t);return f}),old=j%4===0?[1n]:[],g=compile(n,fs,old),v=verify(n,fs,old,g);check(v.ok,v.reason);small++;let key=g.rounds.map(r=>r.degree).join(",");profiles[key]=(profiles[key]||0)+1;let stabilizers=0,m=meter();
for(let x=0n;x<b(n);x++){let z=observe(g.rows,x,m);for(let i=0;i<fs.length;i++){check(ev(fs[i],x,m)===ev(g.decoders[i],z,m),"direct");states++}if(old.every(r=>!dot(r,x,m))){let good=true;for(let y=0n;y<b(n)&&good;y++)for(const f of fs)if(ev(f,y,m)!==ev(f,x^y,m)){good=false;break}if(good)stabilizers++}}
check(stabilizers===2**(n-g.rows.length),"rank minimal");
const bad={...g,decoders:g.decoders.map((f,i)=>i?f:f.includes(0n)?f.filter(t=>t!==0n):[...f,0n])};check(!verify(n,fs,old,bad).ok,"tamper decoder");tamper++;
if(g.rounds.length){let rounds=g.rounds.map((r,i)=>i?r:{...r,added:r.added.map((e,j)=>j?e:{...e,d:0n})});check(!verify(n,fs,old,{...g,rounds}).ok,"tamper witness");tamper++}}
let results=[],refused=[],queries=0;
for(let n of [16,24,32,64]){let masks=Array(7).fill(0n);for(let i=0;i<n;i++)masks[i%7]|=b(i);for(let i=n-1;i>0;i--){let j=rand()%(i+1),a=masks.findIndex(r=>has(r,i)),c=masks.findIndex(r=>has(r,j));if(a!==c){masks[a]^=b(i)|b(j);masks[c]^=b(i)|b(j)}}
const targets=[[7n],[11n],[13n],[112n,15n]],fs=targets.map(t=>sub(t,formRows(masks,n,meter()),meter()));let g;try{g=compile(n,fs)}catch(e){if(e.message!=="work cap")throw e;refused.push({n,stage:"formation",reason:e.message});continue}let v=verify(n,fs,[],g);if(!v.ok&&v.reason==="work cap"){refused.push({n,stage:"verification",formation:g.formation,verification:v.work});continue}check(v.ok,v.reason);check(g.rows.length===7,"latent rank");let im=image(g),m=meter(),direct=meter(),acq=meter(),warm=meter(),seen=new Set;
for(let i=0;i<1024;i++){let x=0n;for(let j=0;j<n;j++)if((rand()>>>20)&1)x|=b(j);let h=observe(masks,x,m),z=observe(g.rows,x,acq),y=0n;for(let j=0;j<fs.length;j++){let expected=ev(targets[j],h,m);check(expected===ev(fs[j],x,direct)&&expected===ev(g.decoders[j],z,warm),"heldout");if(expected)y|=b(j)}seen.add(y);queries++}
check([...seen].every(y=>im.labels.has(y)),"image");
// independent exact image in original hidden 7-bit coordinates
let oracle=new Set;for(let h=0n;h<128n;h++){let y=0n;for(let j=0;j<targets.length;j++)if(ev(targets[j],h,m))y|=b(j);oracle.add(y)}check(oracle.size===im.labels.size&&[...oracle].every(y=>im.labels.has(y)),"image oracle");
results.push({n,sourceTerms:fs.reduce((s,t)=>s+t.length,0),rank:g.rows.length,decoderTerms:g.decoders.reduce((s,t)=>s+t.length,0),degrees:g.rounds.map(r=>r.degree),imageCardinality:im.labels.size,nonlinearBits:im.bits,imageWork:im.work,formation:g.formation,verification:v.work,direct:direct.work,acquisition:acq.work,warm:warm.work,total:g.formation+v.work+acq.work+warm.work})}
let refusal=0;try{compile(4,[[7n]],[],1)}catch(e){if(e.message==="work cap")refusal++}try{image({rows:Array(17).fill(1n),decoders:[]})}catch(e){if(e.message==="image rank cap")refusal++}check(refusal===2,"refusals");
return {small,states,tamper,profiles,heldoutQueries:queries,refusal,refused,results}}
return {compile,verify,observe,ev,image,meter,campaign,sub,formRows};
}

if(typeof module!=="undefined") { module.exports=build(); if(require.main===module) console.log(JSON.stringify(module.exports.campaign(),null,2)); }
