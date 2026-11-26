function rgf003(){
"use strict";
const P=2305843009213693951n;
const mod=x=>(x%P+P)%P, assert=(b,m)=>{if(!b)throw Error(m)};
const counts=()=>({field:0,division:0,visits:0,measurements:0});
const total=c=>c.field+c.division+c.visits;
const add=(a,b,c)=>(c.field++,mod(a+b)),mul=(a,b,c)=>(c.field++,mod(a*b));
function inv(a,c){let r=P,s=mod(a),u=0n,v=1n;while(s){c.division++;let q=r/s;[r,s]=[s,r-q*s];c.field+=2;[u,v]=[v,u-q*v]}assert(r===1n,"noninvertible");return mod(u)}
function dot(a,b,c){assert(a.length===b.length,"dot width");let y=0n;for(let i=0;i<a.length;i++)y=add(y,mul(a[i],b[i],c),c);return y}
const zero=n=>Array(n).fill(0n), unit=(n,i)=>zero(n).map((_,j)=>j===i?1n:0n);
const equal=(a,b)=>a.length===b.length&&a.every((x,i)=>x===b[i]);
function project(rows,x,c){return rows.map(r=>dot(r,x,c))}
function axpy(a,b,k,c){return a.map((v,i)=>add(v,mul(k,b[i],c),c))}
function validate(rows,n){assert(rows.length<=128&&rows.every(r=>r.length===n&&r.every(x=>typeof x==="bigint"&&x>=0n&&x<P)),"bad row")}
function form(rows,n,c){
 validate(rows,n);
 const basis=[],pivots=[],reduced=[],codes=[],maps=[];
 // High-pivot forward elimination; keep the selected original covectors.
 for(const original of rows){
  let v=original.slice(),co=zero(rows.length);
  for(let j=0;j<reduced.length;j++){c.visits++;const k=v[pivots[j]];if(k){v=axpy(v,reduced[j],-k,c);co=axpy(co,codes[j],k,c)}}
  const p=v.findLastIndex(x=>x!==0n);
  if(p>=0){const i=basis.length,q=inv(v[p],c);basis.push(original.slice());pivots.push(p);
   reduced.push(v.map(x=>mul(x,q,c)));codes.push(unit(rows.length,i).map((x,j)=>mul(add(x,-co[j],c),q,c)));
   maps.push(unit(rows.length,i));
  }else maps.push(co);
 }
 return {basis,maps:maps.map(r=>r.slice(0,basis.length))};
}
// Independent rank: conventional column-ordered full matrix elimination, not producer's reducer.
function rank(rows,n,c){
 const a=rows.map(r=>r.slice());let r=0;
 for(let j=0;j<n&&r<a.length;j++){let k=r;while(k<a.length&&!a[k][j]){c.visits++;k++}if(k===a.length)continue;
  [a[r],a[k]]=[a[k],a[r]];const q=inv(a[r][j],c);
  for(let i=r+1;i<a.length;i++){const f=mul(a[i][j],q,c);for(let l=j;l<n;l++)a[i][l]=add(a[i][l],-mul(f,a[r][l],c),c)}r++;
 }return r
}
function verify(rows,n,chart,c){
 try{validate(rows,n);validate(chart.basis,n);validate(chart.maps,chart.basis.length);
 if(chart.maps.length!==rows.length||chart.basis.length!==rank(rows,n,c)||rank(chart.basis,n,c)!==chart.basis.length)return false;
 for(let i=0;i<rows.length;i++){let v=zero(n);for(let j=0;j<chart.basis.length;j++)v=axpy(v,chart.basis[j],chart.maps[i][j],c);if(!equal(v,rows[i]))return false}
 return true}catch{return false}
}
function qualify(rows,n,c){const q=form(rows,n,c);assert(verify(rows,n,q,c),"chart refused");return q}
function validateSource(s){assert(Number.isInteger(s.n)&&s.n>=1&&s.n<=128&&s.rows.length<=128&&s.terms.length<=64,"source bound");validate(s.rows,s.n);for(const t of s.terms)assert(typeof t.a==="bigint"&&t.a>=0n&&t.a<P&&t.ids.length<=8&&t.ids.every(i=>Number.isInteger(i)&&i>=0&&i<s.rows.length),"bad term")}
function factors(s,c){let ids=[...new Set(s.terms.filter(t=>t.a!==0n).flatMap(t=>t.ids))].sort((a,b)=>a-b);c.visits+=s.terms.reduce((v,t)=>v+t.ids.length+1,0);return ids}
function chartSource(s,c){validateSource(s);const ids=factors(s,c),q=qualify(ids.map(i=>s.rows[i]),s.n,c);
 const byId=new Map(ids.map((id,i)=>[id,i]));
 return {...q,terms:s.terms.filter(t=>t.a!==0n).map(t=>({a:t.a,ids:t.ids.map(i=>byId.get(i))}))}
}
function evalTerms(terms,vals,c){let y=0n;for(const t of terms){c.visits++;let a=t.a;for(const j of t.ids){c.visits++;a=mul(a,vals[j],c)}y=add(y,a,c)}return y}
function degree(terms){return Math.max(0,...terms.map(t=>t.ids.length))}
function values(x,v,t,c){return axpy(x,v,mod(t),c)}
// Independent of RGF-002 implementation: Newton finite differences, evaluated directly in binomial basis.
function sumNewton(f,d,len,c){let a=Array.from({length:d+1},(_,i)=>f(BigInt(i))),b=1n,y=0n;
 for(let j=0;j<=d;j++){b=mul(mul(b,add(mod(len),-BigInt(j),c),c),inv(BigInt(j+1),c),c);y=add(y,mul(b,a[0],c),c);a=a.slice(1).map((x,i)=>add(x,-a[i],c))}return y
}
// Independent oracle: cumulative Lagrange interpolation, using full source coordinate evaluation.
function sumLagrange(f,d,len,c){let a=[0n];for(let j=0;j<=d;j++)a.push(add(a[j],f(BigInt(j)),c));let y=0n;
 for(let i=0;i<a.length;i++){let num=1n,den=1n;for(let j=0;j<a.length;j++)if(i!==j){num=mul(num,add(mod(len),-BigInt(j),c),c);den=mul(den,BigInt(i-j),c)}y=add(y,mul(a[i],mul(num,inv(den,c),c),c),c)}return y
}
function full(s,task,c,mode){
 let x=task.x.slice(),v=task.v.slice(),y=task.y,t=0n;const d=degree(s.terms);
 function seg(len){if(!len)return;
  if(mode==="eager"){for(let i=0n;i<len;i++){y=add(y,evalTerms(s.terms,project(s.rows,x,c),c),c);x=axpy(x,v,1n,c)}return}
  // Strong baseline: project all referenced forms once per segment, then navigate in factor values.
  let f;if(mode==="factor"){const a=project(s.rows,x,c),b=project(s.rows,v,c);f=i=>evalTerms(s.terms,values(a,b,i,c),c)}
  else f=i=>evalTerms(s.terms,project(s.rows,values(x,v,i,c),c),c);
  y=add(y,(mode==="oracle"?sumLagrange:sumNewton)(f,d,len,c),c);x=values(x,v,len,c);
 }
 for(const e of task.events){seg(e.t-t);v=axpy(v,e.dv,1n,c);y=add(y,e.impulse,c);t=e.t}seg(task.n-t);
 return {y,x,v}
}
function compact(q,task,c){
 let x=project(q.basis,task.x,c),v=project(q.basis,task.v,c),y=task.y,t=0n;const d=degree(q.terms);
 function seg(len){if(!len)return;const a=project(q.maps,x,c),b=project(q.maps,v,c);
 y=add(y,sumNewton(i=>evalTerms(q.terms,values(a,b,i,c),c),d,len,c),c);x=values(x,v,len,c)}
 for(const e of task.events){seg(e.t-t);v=axpy(v,project(q.basis,e.dv,c),1n,c);y=add(y,e.impulse,c);t=e.t}seg(task.n-t);
 return {y,x,v}
}
let seed=231991;function rnd(n){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return (seed>>>8)%n}
const rand=()=>BigInt(rnd(100000)+1);
function makeSource(n,r,m){
 // guarantee independent latent rows by identity block, but disguise via dense linear mixing.
 const latent=Array.from({length:r},(_,i)=>Array.from({length:n},(_,j)=>j<r?(i===j?1n:0n):rand()));
 const rows=Array.from({length:m},(_,i)=>i<r?latent[i].slice():Array.from({length:n},(_,j)=>mod(latent.reduce((a,b,k)=>a+BigInt(1+(i*7+k*11)%19)*b[j],0n))));
 const terms=rows.map((_,i)=>({a:rand(),ids:[i,(i+1)%m,(i+3)%m]}));
 return {n,rows,terms}
}
function makeTask(n,h,events){
 return {x:Array.from({length:n},rand),v:Array.from({length:n},rand),y:rand(),n:h,events:Array.from({length:events},(_,i)=>({t:h*BigInt(i+1)/BigInt(events+1),dv:Array.from({length:n},rand),impulse:rand()}))}
}
function campaign(name,n,r,m,tasks,events){
 const s=makeSource(n,r,m),modes=["full","factor","cold","warm"],out=Object.fromEntries(modes.map(k=>[k,counts()])),audit=counts(),eager=counts(),warm=chartSource(s,out.warm);
 let checks=0,eagerChecks=0;
 for(let i=0;i<tasks;i++){// new coefficients and state, same factor family: retained chart is re-bound to each source
  const src={...s,terms:s.terms.map(t=>({...t,a:rand()}))};
  const task=makeTask(n,i%4===0?64n:10n**24n+BigInt(i),events);
  const ref=full(src,task,audit,"oracle");
  if(task.n<=64n){const e=full(src,task,eager,"eager");assert(e.y===ref.y&&equal(e.x,ref.x)&&equal(e.v,ref.v),"eager");eagerChecks++}
  for(const mode of modes){
   const c=out[mode];let got;
   if(mode==="full"||mode==="factor"){got=full(src,task,c,mode);assert(got.y===ref.y&&equal(got.x,ref.x)&&equal(got.v,ref.v),mode)}
   else{
    let q;
    if(mode==="cold")q=chartSource(src,c);
    else{validateSource(src);const ids=factors(src,c);assert(verify(ids.map(j=>src.rows[j]),src.n,warm,c),"warm rebind");const map=new Map(ids.map((j,k)=>[j,k]));q={...warm,terms:src.terms.map(t=>({a:t.a,ids:t.ids.map(j=>map.get(j))}))}}
    got=compact(q,task,c);assert(got.y===ref.y&&equal(got.x,project(q.basis,ref.x,audit))&&equal(got.v,project(q.basis,ref.v,audit)),mode)
   }checks++;
  }
 }
 return {name,n,rank:warm.basis.length,factors:m,tasks,events,checks,eagerChecks,work:Object.fromEntries(modes.map(k=>[k,total(out[k])])),ledger:out,auditWork:total(audit),eagerAuditWork:total(eager),retainedPayloadBytes:8*(warm.basis.length*n+warm.maps.length*warm.basis.length)}
}
const campaigns=[campaign("dense-low-rank",64,3,16,24,12),campaign("high-rank-control",16,12,16,16,4),campaign("short-journal",64,3,16,16,0)];
// TDL-002 generalization: minimum additional field symbols for new factor chart.
function refine(oldRows,newRows,n,c){
 const all=oldRows.map(r=>r.slice()),extra=[];
 for(const row of newRows){const r=rank(all,n,c);if(rank([...all,row],n,c)>r){all.push(row);extra.push(row)}}
 const chart=qualify([...all,...newRows],n,c);
 assert(chart.basis.length===all.length&&chart.basis.every((r,i)=>equal(r,all[i])),"complement order");
 const maps=chart.maps.slice(all.length);
 return {extra,maps}
}
function checkRefinement(oldRows,newRows,n,p,c){
 const all=[...oldRows,...p.extra];if(p.extra.length!==rank([...oldRows,...newRows],n,c)-rank(oldRows,n,c)||p.maps.length!==newRows.length)return false;
 for(let i=0;i<newRows.length;i++){if(p.maps[i].length!==all.length)return false;let r=zero(n);for(let j=0;j<all.length;j++)r=axpy(r,all[j],p.maps[i][j],c);if(!equal(r,newRows[i]))return false}return true
}
const c=counts(),n=32,s=makeSource(n,5,10),old=qualify(s.rows.slice(0,2),n,c).basis,newRows=qualify(s.rows.slice(1,5),n,c).basis,plan=refine(old,newRows,n,c);
assert(checkRefinement(old,newRows,n,plan,c),"refinement");
let acquisitions=0;
for(let i=0;i<128;i++){
 const x=Array.from({length:n},rand),v=Array.from({length:n},rand),t=10n**24n+BigInt(i);
 const state=values(x,v,t,c);
 // Only the provider has full current state. Observer has old projected state; requests extra covectors.
 const oldState=values(project(old,x,c),project(old,v,c),t,c),received=project(plan.extra,state,c);c.measurements+=received.length;acquisitions+=received.length;
 const next=project(plan.maps,[...oldState,...received],c);assert(equal(next,project(newRows,state,c)),"refinement value");
}
const bad={...plan,maps:plan.maps.map(r=>r.slice())};bad.maps[0][0]=mod(bad.maps[0][0]+1n);
assert(!checkRefinement(old,newRows,n,bad,c),"tampered refinement");
const badChart=qualify(s.rows,n,c);badChart.maps[0][0]=mod(badChart.maps[0][0]+1n);assert(!verify(s.rows,n,badChart,c),"tampered chart");
// Nonminimality counterexample: cancellation in polynomial sum despite independent factor covectors.
const cancellation={n:2,rows:[[1n,0n],[0n,1n]],terms:[{a:1n,ids:[0,1]},{a:P-1n,ids:[1,0]}]};
const cq=chartSource(cancellation,c);assert(cq.basis.length===2&&evalTerms(cancellation.terms,[19n,42n],c)===0n,"cancellation");
// Same old coordinate, different desired coordinate: explicit ambiguity witness on identity block.
const x0=zero(n),x1=unit(n,2);assert(equal(project(old,x0,c),project(old,x1,c))&&!equal(project(newRows,x0,c),project(newRows,x1,c)),"missing observation witness");
return {version:"RGF-003",prime:P.toString(),seed:231991,campaigns,refinement:{oldRank:old.length,newRank:newRows.length,extra:plan.extra.length,states:128,acquisitions,work:total(c)},controls:{tamperedChart:"refused",tamperedRefinement:"refused",missingObservation:"explicit indistinguishable old states",cancellation:"factor rank 2; true sufficient rank 0"}}
}

console.log(JSON.stringify(rgf003(),null,2));
