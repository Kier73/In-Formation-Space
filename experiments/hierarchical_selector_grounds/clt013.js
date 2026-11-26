"use strict";
// CLT-013: hierarchical variable-geometry selector Grounds.
function experiment(mode){
 const assert=(c,m)=>{if(!c)throw Error(m)}, mod=x=>((x%256)+256)%256;
 const same=(a,b)=>a.kind===b.kind&&a.n===b.n&&a.v.length===b.v.length&&a.v.every((x,i)=>x===b.v[i]);
 const byte=(r,j)=>r.kind===2?mod(r.v[0]+r.v[1]*j):r.v[j%r.v.length];
 const flatBytes=rs=>12+rs.reduce((s,r)=>s+5+(r.kind===1?1:0)+r.v.length,0);
 const dictBytes=rs=>12+2*rs.length+[...new Map(rs.map(r=>[JSON.stringify(r),r])).values()].reduce((s,r)=>s+5+(r.kind===1?1:0)+r.v.length,0);
 function fixture(seed,family){
  let r=seed;const next=()=>r=(Math.imul(r,1664525)+1013904223)>>>0;
  const make=(p,q,regime,constant=false)=>{
   const specs=Array.from({length:p},(_,i)=>{let kind=i%2?1:2,len=kind===2?2:2**(1+(next()%3));return {kind,n:24+next()%29,d:constant?0:next()%3,v:Array.from({length:len},()=>next()%256),dv:Array.from({length:len},()=>constant?0:next()%9)}});
   // Raw source construction is independent of the fitted coefficient arrays.
   const rs=[];
   for(let t=0;t<q;t++)for(const s of specs){
    const n=s.n+s.d*t,v=s.v.map((x,i)=>mod(x+s.dv[i]*t));
    rs.push({kind:s.kind,n,v});
   }
   return rs;
  };
  const q=24+next()%9,p=3+next()%3;
  let rs=make(p,q,0,family==="constant");
  if(family==="piecewise")rs=rs.concat(make(2+next()%3,19+next()%8,1));
  if(family==="mutated"){let i=Math.floor(rs.length*0.75);rs[i]={...rs[i],v:rs[i].v.map((v,j)=>j===0?v^1:v)}}
  if(family==="irregular")rs=rs.map((s,i)=>({...s,n:25+next()%50,v:s.v.map(()=>next()>>>24)}));
  const source=Uint8Array.from(rs.flatMap(r=>Array.from({length:r.n},(_,i)=>byte(r,i))));
  assert(source.length<=65536,"VLM extent");
  return {rs,source};
 }
 function infer(rs,start,period,stats,constantOnly=false){
  if(rs.length-start<3*period)return null;
  const slots=[];
  for(let j=0;j<period;j++){
   const a=rs[start+j],b=rs[start+j+period];stats.probeRecords+=2;
   if(a.kind!==b.kind||a.v.length!==b.v.length)return null;
   const dn=b.n-a.n,dv=b.v.map((v,k)=>mod(v-a.v[k]));
   if(constantOnly&&(dn||dv.some(x=>x)))return null;
   slots.push({kind:a.kind,n:a.n,dn,v:a.v.slice(),dv});
  }
  const at=(t,j)=>{const s=slots[j];return {kind:s.kind,n:s.n+s.dn*t,v:s.v.map((v,k)=>mod(v+s.dv[k]*t))}};
  let i=start;
  for(;i<rs.length;i++){stats.checkRecords++;const t=Math.floor((i-start)/period),j=(i-start)%period;if(!same(rs[i],at(t,j)))break}
  const count=Math.floor((i-start)/period);
  if(i<rs.length)stats.rejections++;
  if(count<3)return null;
  return {kind:"model",count,slots,records:count*period,firstMismatch:i<rs.length?i:null};
 }
 const modelCost=b=>1+4+1+b.slots.reduce((s,x)=>s+1+4+4+1+2*x.v.length,0);
 const literalCost=b=>1+4+b.rs.reduce((s,r)=>s+5+(r.kind===1?1:0)+r.v.length,0);
 const cost=b=>b.kind==="model"?modelCost(b):literalCost(b);
 function compile(rs,constantOnly=false){
  const stats={probeRecords:0,checkRecords:0,rejections:0,modelBlocks:0,retainedMismatchBoundaries:0};
  const blocks=[];let i=0;
  while(i<rs.length){
   let best=null;
   if(blocks.length<6)for(let p=1;p<=8;p++){
    const c=infer(rs,i,p,stats,constantOnly);if(!c)continue;
    const saving=flatBytes(rs.slice(i,i+c.records))-12+5-cost(c);
    if(saving>0&&(!best||c.records>best.records||(c.records===best.records&&cost(c)<cost(best))))best=c;
   }
   if(!best){blocks.push({kind:"literal",rs:rs.slice(i)});break}
   blocks.push(best);stats.modelBlocks++;if(best.firstMismatch!==null)stats.retainedMismatchBoundaries++;i+=best.records;
  }
  const wire=encode(blocks);
  return {blocks,wire,stats};
 }
 // Actual canonical binary descriptor stream. No implicit per-leaf offsets.
 // Header HSG1, block count u32; each model is count, period, then slots.
 function encode(blocks){
  const out=[72,83,71,49],u8=x=>out.push(x&255),u32=x=>{for(let i=0;i<4;i++)u8(x>>>(8*i))};
  u32(blocks.length);
  for(const b of blocks){
   if(b.kind==="literal"){u8(0);u32(b.rs.length);for(const r of b.rs){u8(r.kind);u32(r.n);if(r.kind===1)u8(r.v.length);for(const v of r.v)u8(v)}}
   else{u8(1);u32(b.count);u8(b.slots.length);for(const s of b.slots){u8(s.kind);u32(s.n);u32(s.dn);u8(s.v.length);for(const v of s.v)u8(v);for(const d of s.dv)u8(d)}}
  }
  return Uint8Array.from(out);
 }
 function decode(w){
  let i=0;const get=()=>{assert(i<w.length,"truncated");return w[i++]},u32=()=>{let v=0;for(let j=0;j<4;j++)v|=get()<<(8*j);return v>>>0};
  assert([72,83,71,49].every(x=>get()===x),"magic");const nb=u32();assert(nb>0&&nb<=7,"blocks");
  const bs=[];let records=0,extent=0;
  const take=(n)=>Array.from({length:n},get);
  const check=(kind,n,k)=>assert((kind===1&&k>=1&&k<=16&&k<=n||kind===2&&k===2)&&n>=1&&n<=65536,"descriptor");
  for(let b=0;b<nb;b++){
   const tag=get(),count=u32();assert(count>=1&&count<=65536,"count");
   if(tag===0){
    const rs=[];for(let k=0;k<count;k++){const kind=get(),n=u32(),l=kind===1?get():2;check(kind,n,l);rs.push({kind,n,v:take(l)});extent+=n}records+=count;bs.push({kind:"literal",rs});
   }else{
    assert(tag===1,"tag");const p=get();assert(p>=1&&p<=8,"period");const slots=[];
    for(let j=0;j<p;j++){const kind=get(),n=u32(),dn=u32()|0,l=get();check(kind,n,l);check(kind,n+dn*(count-1),l);slots.push({kind,n,dn,v:take(l),dv:take(l)});extent+=count*n+dn*count*(count-1)/2}
    records+=p*count;bs.push({kind:"model",count,slots});
   }
   assert(extent<=65536&&records<=65536,"extent");
  }
  assert(i===w.length,"trailing");return bs;
 }
 const sum=(r)=>r.kind==="literal"?r.rs.reduce((s,g)=>s+g.n,0):prefixCycles(r,r.count);
 function prefixCycles(b,t){return b.slots.reduce((s,g)=>s+g.n*t+g.dn*t*(t-1)/2,0)}
 function record(b,t,j){const s=b.slots[j];return {kind:s.kind,n:s.n+s.dn*t,v:s.v.map((v,i)=>mod(v+s.dv[i]*t))}}
 // Selector arithmetic: quadratic cycle prefix, binary search over cycle
 // coordinates, then at most p local lengths. No flattened boundary index.
 function locate(bs,offset,stats){
  for(const b of bs){stats.blocks++;const n=sum(b);if(offset>=n){offset-=n;continue}
   if(b.kind==="literal"){for(const r of b.rs){stats.local++;if(offset<r.n)return [r,offset];offset-=r.n}}
   else{let lo=0,hi=b.count;while(lo+1<hi){stats.cycleSearch++;const mid=(lo+hi)>>1;if(prefixCycles(b,mid)<=offset)lo=mid;else hi=mid}
    offset-=prefixCycles(b,lo);for(let j=0;j<b.slots.length;j++){stats.local++;const r=record(b,lo,j);if(offset<r.n)return [r,offset];offset-=r.n}}
  }
  throw Error("outside extent");
 }
 function expand(bs){const out=[];for(const b of bs)if(b.kind==="literal")out.push(...b.rs);else for(let t=0;t<b.count;t++)for(let j=0;j<b.slots.length;j++)out.push(record(b,t,j));return out}
 // Independent verifier compares decoded descriptions to original bytes,
 // not just candidate records. Exhaustive here, not a proof of extrapolation.
 function qualify(bs,source){
  let pos=0;
  for(const r of expand(bs))for(let j=0;j<r.n;j++){
   const y=r.kind===2?(r.v[0]+r.v[1]*j)&255:r.v[j%r.v.length];
   if(pos>=source.length||source[pos++]!==y)return false;
  }
  return pos===source.length;
 }
 function run(){
  const results={},nativeCases=[];
  for(const family of ["constant","drifting","piecewise","mutated","irregular"]){
   let s={cases:0,sourceBytes:0,records:0,flatWire:0,dictionaryBytes:0,constantWire:0,adaptiveWire:0,modelBlocks:0,mismatchBoundaries:0,probeRecords:0,checkRecords:0,rejections:0,verifiedBytes:0,queryChecks:0,cycleSearch:0,local:0,blocks:0,tamperRejected:0};
   for(let k=0;k<12;k++){
    const {rs,source}=fixture(1701+7919*k,family),c=compile(rs),fixed=compile(rs,true);
    // Retain the flat VLG1 route if the new wire loses. For direct comparison,
    // the decoder is still exercised on every candidate, even losing routes.
    const bs=decode(c.wire),fs=decode(fixed.wire);
    assert(qualify(bs,source)&&qualify(fs,source),"qualification");
    const flat=flatBytes(rs),use=c.wire.length<flat;
    let st={blocks:0,cycleSearch:0,local:0},r=seeded(17+k);
    for(let q=0;q<128;q++){let x=q===0?0:q===1?source.length-1:r()%source.length;let [g,j]=locate(bs,x,st);assert(byte(g,j)===source[x],"coordinate result");s.queryChecks++}
    if(use){const altered=c.wire.slice();altered[altered.length-1]^=1;let rejected=false;try{rejected=!qualify(decode(altered),source)}catch(e){rejected=true}assert(rejected,"tamper accepted");s.tamperRejected++}
    if(k===0)nativeCases.push({family,records:rs,source:Array.from(source),candidateRecords:expand(bs),wire:Array.from(c.wire)});
    s.cases++;s.sourceBytes+=source.length;s.records+=rs.length;s.flatWire+=flat;s.dictionaryBytes+=dictBytes(rs);s.constantWire+=Math.min(flat,fixed.wire.length);s.adaptiveWire+=Math.min(flat,c.wire.length);s.modelBlocks+=c.stats.modelBlocks;s.mismatchBoundaries+=c.stats.retainedMismatchBoundaries;s.probeRecords+=c.stats.probeRecords;s.checkRecords+=c.stats.checkRecords;s.rejections+=c.stats.rejections;s.verifiedBytes+=source.length;s.cycleSearch+=st.cycleSearch;s.local+=st.local;s.blocks+=st.blocks;
   }
   results[family]=s;
  }
  assert(results.drifting.adaptiveWire<results.drifting.constantWire&&results.piecewise.modelBlocks>=24,"no selector reuse");
  assert(results.irregular.adaptiveWire===results.irregular.flatWire,"irregular fallback");
  return {results,nativeCases};
 }
 function seeded(s){return ()=>s=(Math.imul(s,1664525)+1013904223)>>>0}
 if(mode==='api')return {fixture,compile,decode};
 return run();
}
if(require.main===module){const e=experiment();console.log(JSON.stringify(process.argv.includes("--native-cases")?e.nativeCases:e.results,null,2))}
module.exports={experiment};
