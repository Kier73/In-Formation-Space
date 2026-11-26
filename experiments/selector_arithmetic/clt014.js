"use strict";
function experiment(api){
 const assert=(p,m)=>{if(!p)throw Error(m)}, B=BigInt, mod=(x,m)=>((x%m)+m)%m;
 const gcd=(a,b)=>{a=Math.abs(a);b=Math.abs(b);while(b){let t=a%b;a=b;b=t}return a},lcm=(a,b)=>a/gcd(a,b)*b;
 const tri=n=>n*(n-1n)/2n;
 const meter=()=>({residueEntries:0,patternTerms:0,cycleSearch:0,slotReads:0,prefixCalls:0,expandedRecords:0});
 function normalize(s,count){
  const n=B(s.n),d=B(s.dn),v=s.v.slice(),dv=s.dv.slice();
  assert(count>0n&&count<=10n**30n&&n>0n&&n+d*(count-1n)>0n,"extent");
  assert((s.kind===1&&v.length>=1&&v.length<=16&&n>=B(v.length)&&n+d*(count-1n)>=B(v.length)||s.kind===2&&v.length===2)&&dv.length===v.length&&[...v,...dv].every(x=>Number.isInteger(x)&&x>=0&&x<256),"slot");
  return {kind:s.kind,n,d,v,dv};
 }
 function parameters(s,t){return s.v.map((v,i)=>Number(mod(B(v)+B(s.dv[i])*t,256n)))}
 function pattern(s,t,m){const v=parameters(s,t);return s.kind===2?Array.from({length:m},(_,i)=>(v[0]+i*v[1])&255):v}
 function length(s,t){return s.n+s.d*t}
 function slotIndex(s,count,stats){
  const m=s.kind===2?256:s.v.length;
  let L=m/gcd(m,Number(mod(s.d,B(m))));
  for(const d of s.dv)L=lcm(L,256/gcd(256,d));
  assert(L>=1&&L<=4096,"residue bound");
  const a=[0n],d=[0n];
  // Only build residues that occur within the admitted interval; do not
  // construct a hypothetical negative-length leaf beyond a shrinking range.
  const R=Number(count<B(L)?count:B(L));
  for(let r=0;r<R;r++){
   stats.residueEntries++;const p=pattern(s,B(r),m);stats.patternTerms+=p.length;
   const total=B(p.reduce((x,y)=>x+y,0)),n=length(s,B(r)),rem=Number(n%B(m));
   a.push(a[a.length-1]+n/B(m)*total+B(p.slice(0,rem).reduce((x,y)=>x+y,0)));
   d.push(d[d.length-1]+s.d*B(L)/B(m)*total);
  }
  function full(t){
   assert(t>=0n&&t<=count,"cycle domain");stats.prefixCalls++;
   const q=t/B(L),r=Number(t%B(L));
   if(q===0n)return a[r];
   return q*a[L]+tri(q)*d[L]+a[r]+q*d[r];
  }
  function partial(t,n){
   stats.slotReads++;assert(t>=0n&&t<count&&n>=0n&&n<=length(s,t),"partial domain");
   const p=pattern(s,t,m);stats.patternTerms+=p.length;
   const total=B(p.reduce((a,b)=>a+b,0));return n/B(m)*total+B(p.slice(0,Number(n%B(m))).reduce((a,b)=>a+b,0));
  }
  return {full,partial,s,L,entries:R};
 }
 function blockIndex(b,stats){
  if(b.kind==="literal"){
   const ends=[0n],totals=[0n],slots=[];
   for(const r of b.rs){stats.expandedRecords++;const x=slotIndex(normalize({...r,dn:0,dv:r.v.map(()=>0)},1n),1n,stats);slots.push(x);ends.push(ends.at(-1)+B(r.n));totals.push(totals.at(-1)+x.full(1n))}
   return {n:ends.at(-1),total:totals.at(-1),prefix(x){
    if(x===ends.at(-1))return totals.at(-1);
    let lo=0,hi=slots.length;while(lo+1<hi){stats.cycleSearch++;const m=(lo+hi)>>1;if(ends[m]<=x)lo=m;else hi=m}
    return totals[lo]+slots[lo].partial(0n,x-ends[lo]);
   }};
  }
  const count=B(b.count),ss=b.slots.map(s=>slotIndex(normalize(s,count),count,stats));
  const A=ss.reduce((a,x)=>a+x.s.n,0n),D=ss.reduce((a,x)=>a+x.s.d,0n);
  const geometry=t=>A*t+D*tri(t);
  const cycles=t=>ss.reduce((a,x)=>a+x.full(t),0n);
  const n=geometry(count),total=cycles(count);
  return {n,total,prefix(x){
   if(x===n)return total;
   let lo=0n,hi=count;
   while(lo+1n<hi){stats.cycleSearch++;let m=(lo+hi)/2n;if(geometry(m)<=x)lo=m;else hi=m}
   let z=cycles(lo),rest=x-geometry(lo);
   for(const s of ss){let len=length(s.s,lo),k=rest<len?rest:len;z+=s.partial(lo,k);rest-=k;if(rest===0n)break}
   return z;
  }};
 }
 function index(bs,stats){
  assert(bs.length>=1&&bs.length<=7,"blocks");
  const ix=bs.map(b=>blockIndex(b,stats)),n=ix.reduce((a,b)=>a+b.n,0n);
  function prefix(x){assert(x>=0n&&x<=n,"range");let z=0n;for(const b of ix){if(x<=b.n)return z+b.prefix(x);z+=b.total;x-=b.n}return z}
  return {n,prefix,range(a,b){assert(a<=b,"order");return prefix(b)-prefix(a)}};
 }
 function flatOracle(bytes){let p=[0n];for(const x of bytes)p.push(p.at(-1)+B(x));return p}
 let small={objects:0,bytes:0,rangeChecks:0,residueEntries:0,patternTerms:0,cycleSearch:0,expandedRecords:0,modelRecords:0};
 for(const family of ["constant","drifting","piecewise","mutated","irregular"])for(let k=0;k<12;k++){
  const f=api.fixture(1701+7919*k,family),bs=api.decode(api.compile(f.rs).wire),m=meter(),ix=index(bs,m),p=flatOracle(f.source);
  assert(ix.n===B(f.source.length),"extent");
  let r=17+k;const next=()=>r=(Math.imul(r,1664525)+1013904223)>>>0;
  for(let j=0;j<128;j++){
   let a=j===0?0:next()%(f.source.length+1),b=j===0?f.source.length:next()%(f.source.length+1);if(a>b)[a,b]=[b,a];
   assert(ix.range(B(a),B(b))===p[b]-p[a],"CLT013 range");small.rangeChecks++;
  }
  small.objects++;small.bytes+=f.source.length;small.modelRecords+=bs.filter(b=>b.kind==="model").reduce((a,b)=>a+b.count*b.slots.length,0);
  for(const key of ["residueEntries","patternTerms","cycleSearch","expandedRecords"])small[key]+=m[key];
 }
 // Independent arithmetic oracle for the large declared family. Each
 // residue class contributes the average of its first and last leaf sums,
 // rather than the precompiled slope/prefix table. Fixed 256*m stride is
 // deliberately nonminimal and computed from scratch on each query.
 function localOracle(s,t,n){
  const v=s.v.map((x,i)=>Number((B(x)+B(s.dv[i])*t)%256n));
  const m=s.kind===2?256:v.length;
  let one=0n,rem=0n;for(let j=0;j<m;j++){let x=B(s.kind===2?(v[0]+j*v[1])%256:v[j]);one+=x;if(B(j)<n%B(m))rem+=x}
  return n/B(m)*one+rem;
 }
 function oracleCycles(slots,t){
  let total=0n;
  for(const s of slots){
   const stride=B(256*(s.kind===2?1:s.v.length));
   for(let r=0n;r<stride&&r<t;r++){
    let k=(t-1n-r)/stride+1n,last=r+(k-1n)*stride;
    let a=localOracle(s,r,B(s.n)+B(s.dn)*r),b=localOracle(s,last,B(s.n)+B(s.dn)*last);
    assert(k*(a+b)%2n===0n,"oracle parity");total+=k*(a+b)/2n;
   }
  }
  return total;
 }
 const count=10n**12n+39n,slots=[{kind:2,n:257,dn:3,v:[17,11],dv:[9,6]},{kind:1,n:37,dn:2,v:[7,13,41],dv:[1,2,3]},{kind:1,n:81,dn:1,v:[1,2,3,4,5],dv:[0,7,13,9,2]}];
 const m=meter(),ix=index([{kind:"model",count,slots}],m);
 const setup={...m};
 const G=t=>slots.reduce((a,s)=>a+B(s.n)*t+B(s.dn)*tri(t),0n);
 const offsets=[0n,1n,255n,256n,10n**6n+7n,count-1n];
 let verified=0;
 for(const t of offsets){
  const prefix=oracleCycles(slots,t);
  let off=G(t),z=prefix;
  for(const s of slots){let len=B(s.n)+B(s.dn)*t;let k=len/2n;assert(ix.prefix(off+k)===z+localOracle(s,t,k),"large interior");verified++;z+=localOracle(s,t,len);off+=len;assert(ix.prefix(off)===z,"large boundary");verified++}
 }
 const total=oracleCycles(slots,count);assert(ix.prefix(ix.n)===total,"large total");verified++;
 // Shrinking lengths (a different signed geometry), short extent (< period),
 // and a non-power-of-two payload period checked on original bytes.
 let edgeChecks=0;
 for(const count of [1n,3n,129n]){
  const slot={kind:1,n:700,dn:-3,v:[11,31,9,4,7,23,13],dv:[1,0,7,2,4,8,3]};
  const ix=index([{kind:"model",count,slots:[slot]}],meter());
  let bytes=[];for(let t=0n;t<count;t++){const s=normalize(slot,count),p=parameters(s,t);for(let j=0;j<Number(length(s,t));j++)bytes.push(p[j%p.length])}
  const p=flatOracle(bytes);for(let i=0;i<=bytes.length;i+=317){assert(ix.prefix(B(i))===p[i],"shrinking");edgeChecks++}
  assert(ix.prefix(ix.n)===p.at(-1),"shrinking end");edgeChecks++;
 }
 let refused=0;for(const b of [{kind:"model",count:10n,slots:[{kind:1,n:3,dn:-1,v:[1,2],dv:[0,0]}]},{kind:"model",count:10n**31n,slots}])try{index([b],meter())}catch(e){refused++}
 assert(refused===2,"invalid extent");
 return {small,large:{cycles:count.toString(),logicalRecords:(count*B(slots.length)).toString(),logicalBytes:ix.n.toString(),exactSum:total.toString(),setup,query:{cycleSearch:m.cycleSearch-setup.cycleSearch,patternTerms:m.patternTerms-setup.patternTerms,prefixCalls:m.prefixCalls-setup.prefixCalls,slotReads:m.slotReads-setup.slotReads},verified,declaredLaw:true},controls:{shrinkingAndShortRangeChecks:edgeChecks,invalidExtentRefusals:refused}};
}
if(require.main===module)console.log(JSON.stringify(experiment(require("../hierarchical_selector_grounds/clt013.js").experiment("api")),null,2));
module.exports={experiment};
