function quotient(api){
"use strict";
const {compile,verify,observe,ev,meter}=api,b=i=>1n<<BigInt(i),check=(x,s)=>{if(!x)throw Error(s)};
function output(ds,z,m){let y=0n;for(let i=0;i<ds.length;i++){m.tick();if(ev(ds[i],z,m))y|=b(i)}return y}
function construct(g,oldCount,cap=40000000){let m=meter(cap),r=g.rows.length;check(r<=16&&Number.isInteger(oldCount)&&oldCount>=1&&oldCount<=g.decoders.length,"image domain");let groups=new Map;for(let z=0n;z<b(r);z++){m.tick();let y=output(g.decoders,z,m),old=y&(b(oldCount)-1n),next=y>>BigInt(oldCount);if(!groups.has(old))groups.set(old,new Map);let p=groups.get(old);if(!p.has(next))p.set(next,z)}
const ordered=[...groups].sort((a,c)=>a[0]<c[0]?-1:1).map(([old,values])=>({old,values:[...values].sort((a,c)=>a[0]<c[0]?-1:1).map(([next,z])=>({next,z}))}));
let max=Math.max(...ordered.map(x=>x.values.length)),count=ordered.reduce((s,x)=>s+x.values.length,0);return {groups:ordered,oldBits:Math.ceil(Math.log2(ordered.length)),extraBits:Math.ceil(Math.log2(max)),jointBits:Math.ceil(Math.log2(count)),count,work:m.work}}
function audit(g,oldCount,q,cap=40000000){let m=meter(cap);try{check(g.rows.length<=16&&Number.isInteger(oldCount)&&oldCount>=1&&oldCount<=g.decoders.length&&q&&Array.isArray(q.groups)&&q.groups.length>0,"shape");let map=new Map;let max=0,count=0;for(const group of q.groups){check(typeof group.old==="bigint"&&group.old>=0n&&group.old<b(oldCount)&&!map.has(group.old)&&Array.isArray(group.values)&&group.values.length>0,"group");let s=new Set;map.set(group.old,s);for(const v of group.values){m.tick();check(typeof v.next==="bigint"&&v.next>=0n&&v.next<b(g.decoders.length-oldCount)&&!s.has(v.next)&&typeof v.z==="bigint"&&v.z>=0n&&v.z<b(g.rows.length),"entry");let y=output(g.decoders,v.z,m);check((y&(b(oldCount)-1n))===group.old&&(y>>BigInt(oldCount))===v.next,"section");s.add(v.next);count++}max=Math.max(max,s.size)}
for(let z=0n;z<b(g.rows.length);z++){let y=output(g.decoders,z,m);check(map.get(y&(b(oldCount)-1n))?.has(y>>BigInt(oldCount)),"coverage")}
check(q.count===count&&q.oldBits===Math.ceil(Math.log2(map.size))&&q.extraBits===Math.ceil(Math.log2(max))&&q.jointBits===Math.ceil(Math.log2(count)),"minimal bits");return {ok:true,work:m.work}}catch(e){return {ok:false,work:m.work,reason:e.message}}}
function encode(q,old,next){let i=q.groups.findIndex(g=>g.old===old);check(i>=0,"unknown old");let j=q.groups[i].values.findIndex(v=>v.next===next);check(j>=0,"unknown next");return [i,j]}
function decode(q,i,j){check(Number.isInteger(i)&&Number.isInteger(j)&&i>=0&&j>=0&&i<q.groups.length&&j<q.groups[i].values.length,"unknown coordinate");let g=q.groups[i];return {old:g.old,next:g.values[j].next,z:g.values[j].z}}
function campaign(){let n=32,masks=Array(7).fill(0n);for(let i=0;i<n;i++)masks[i%7]|=b(i);
const original=[[7n],[11n],[13n],[112n,15n]],forms=api.formRows(masks,n,meter()),old=original.map(f=>api.sub(f,forms,meter()));
let reports=[],all=0,tamper=0;
for(const [name,newTargets] of [["derived",[[7n,11n],[7n,13n]]],["latent parity",[[1n]]],["latent pair",[[1n],[2n]]],["new independent coordinate",null]]){
let newer=newTargets?newTargets.map(f=>api.sub(f,forms,meter())):[[b(0)],[b(1)]];
const g=compile(n,[...old,...newer]),v=verify(n,[...old,...newer],[],g);check(v.ok,v.reason);const q=construct(g,old.length),a=audit(g,old.length,q);check(a.ok,a.reason);let m=meter();
for(let z=0n;z<b(g.rows.length);z++){let y=output(g.decoders,z,m),o=y&15n,p=y>>4n,[i,j]=encode(q,o,p),rec=decode(q,i,j);check(rec.old===o&&rec.next===p,"roundtrip");all++}
let bad={...q,groups:q.groups.map((v,i)=>i?v:{...v,values:v.values.slice(1)})};check(!audit(g,old.length,bad).ok,"missing image");tamper++;
let bad2={...q,extraBits:q.extraBits+1};check(!audit(g,old.length,bad2).ok,"forged bit claim");tamper++;
let witness=null;for(const group of q.groups)if(group.values.length>1){let [a,c]=group.values;witness={old:String(group.old),next:[String(a.next),String(c.next)],z:[String(a.z),String(c.z)]};break}
reports.push({name,rank:g.rows.length,oldClasses:q.groups.length,jointClasses:q.count,oldBits:q.oldBits,extraBits:q.extraBits,jointBits:q.jointBits,witness,formation:g.formation,verification:v.work,imageWork:q.work,imageVerification:a.work})}
return {all,tamper,reports}}
return {construct,audit,encode,decode,campaign}
}

if(typeof module!=="undefined") { module.exports=quotient; if(require.main===module) console.log(JSON.stringify(quotient(require('./higher_derivative.js')).campaign(),null,2)); }
