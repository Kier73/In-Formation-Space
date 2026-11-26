"use strict";
function experiment(api,arithmetic){
 const B=BigInt, assert=(x,m)=>{if(!x)throw Error(m)}, mod=(x,m)=>((x%m)+m)%m;
 const gcd=(a,b)=>b?gcd(b,a%b):a,lcm=(a,b)=>a/gcd(a,b)*b;
 const choose=(n,k)=>{if(n<B(k))return 0n;let z=1n;for(let i=1;i<=k;i++)z=z*(n-B(i-1))/B(i);return z};
 const evalLine=(s,t)=>s[0]+s[1]*t;
 const stats=()=>({residues:0,patternTerms:0,polynomialSamples:0,overlapPieces:0,regimes:0,querySteps:0,partialPatterns:0,expandedModelRecords:0});
 function slots(raw,count){
  assert(raw.length>0&&raw.length<=8,"slots");
  let a=0n,d=0n;
  const out=raw.map(x=>{
   const n=B(x.n),dn=B(x.dn),m=x.kind===2?256:x.v.length;
   assert((x.kind===1&&m>=1&&m<=16||x.kind===2&&x.v.length===2)&&x.dv.length===x.v.length&&[...x.v,...x.dv].every(v=>Number.isInteger(v)&&v>=0&&v<256),"descriptor");
   assert(n>=B(x.kind===2?1:m)&&n+dn*(count-1n)>=B(x.kind===2?1:m),"length");
   const s={...x,n,dn,m,start:[a,d],end:[a+n,d+dn]};a+=n;d+=dn;return s;
  });
  return {out,A:a,D:d};
 }
 function period(s){let L=s.m;for(const v of s.dv)L=lcm(L,256/gcd(256,v));return L}
 function pattern(s,t){const v=s.v.map((x,i)=>Number(mod(B(x)+B(s.dv[i])*t,256n)));return s.kind===2?Array.from({length:256},(_,j)=>(v[0]+j*v[1])&255):v}
 // A joint local pattern, with offset into each independently described leaf.
 function productPattern(a,b,t,start,meter,partial=false){
  const p=pattern(a,t),q=pattern(b,t),m=lcm(p.length,q.length),oa=Number(mod(start-evalLine(a.start,t),B(p.length))),ob=Number(mod(start-evalLine(b.start,t),B(q.length)));
  if(partial)meter.partialPatterns++;
  meter.patternTerms+=m;
  assert(meter.patternTerms<=12000000,"pattern budget");
  let sums=[0n],mom=[0n];
  for(let i=0;i<m;i++){let z=B(p[(oa+i)%p.length]*q[(ob+i)%q.length]);sums.push(sums.at(-1)+z);mom.push(mom.at(-1)+B(i)*z)}
  return {m:B(m),sums,mom};
 }
 // Local sum and first moment with respect to j=0 at overlap start.
 function local(p,n){
  assert(n>=0n,"overlap");const q=n/p.m,r=Number(n%p.m),s=p.sums.at(-1),j=p.mom.at(-1);
  return [q*s+p.sums[r],q*j+p.m*choose(q,2)*s+q*p.m*p.sums[r]+p.mom[r]];
 }
 function compile(Araw,Braw,count,meter){
  count=B(count);assert(count>0n&&count<=10n**30n,"count");
  const a=slots(Araw,count),b=slots(Braw,count);assert(a.A===b.A&&a.D===b.D,"unaligned outer geometry");
  const geo=t=>a.A*t+a.D*choose(t,2);
  const cuts=new Set([0n,count]),ends=x=>[[0n,0n],...x.out.map(s=>s.end)];
  for(const x of ends(a))for(const y of ends(b)){
   const pred=t=>evalLine(x,t)>=evalLine(y,t),v=pred(0n);
   if(pred(count-1n)===v)continue;
   let lo=0n,hi=count-1n;while(lo+1n<hi){let mid=(lo+hi)/2n;if(pred(mid)===v)lo=mid;else hi=mid}
   cuts.add(hi);
  }
  const order=[...cuts].sort((a,b)=>a<b?-1:a>b?1:0),regions=[];
  for(let h=0;h<order.length-1;h++){
   const lo=order[h],hi=order[h+1],countR=hi-lo,parts=[];
   for(const x of a.out)for(const y of b.out){
    const left=evalLine(x.start,lo)>=evalLine(y.start,lo)?x.start:y.start;
    const right=evalLine(x.end,lo)>=evalLine(y.end,lo)?y.end:x.end;
    const len=[right[0]-left[0],right[1]-left[1]];
    if(evalLine(len,lo)<0n||evalLine(len,hi-1n)<0n)continue;
    if(evalLine(len,lo)===0n&&evalLine(len,hi-1n)===0n)continue;
    parts.push({x,y,left,len});meter.overlapPieces++;
   }
   const L=parts.reduce((s,p)=>lcm(s,lcm(period(p.x),period(p.y))),1);
   assert(L<=4096,"joint residue budget");
   const R=Number(countR<B(L)?countR:B(L)),pref=Array.from({length:2},()=>Array.from({length:4},()=>[0n]));
   for(let r=0;r<R;r++){
    meter.residues++;
    const t0=lo+B(r),K=(hi-1n-t0)/B(L)+1n,deg=Math.min(4,Number(K>4n?4n:K));
    const vals=Array.from({length:2},()=>[]);
    for(const p of parts){
     const start=evalLine(p.left,t0),pat=productPattern(p.x,p.y,t0,start,meter);
     for(let k=0;k<deg;k++){
      const t=t0+B(k)*B(L),off=evalLine(p.left,t),n=evalLine(p.len,t),[s,j]=local(pat,n),w=(geo(t)+off)*s+j;
      vals[0][k]=(vals[0][k]??0n)+s;vals[1][k]=(vals[1][k]??0n)+w;meter.polynomialSamples++;
     }
    }
    for(let m=0;m<2;m++){
     let v=vals[m];
     for(let d=0;d<4;d++){
      const f=v.length?v[0]:0n;pref[m][d].push(pref[m][d].at(-1)+f);v=v.slice(1).map((x,i)=>x-v[i]);
     }
    }
   }
   function full(t){
    const k=t-lo,Q=k/B(L),Rema=Number(k%B(L));
    return pref.map(ds=>ds.reduce((z,p,d)=>z+choose(Q,d+1)*(Q?p[L]:0n)+choose(Q,d)*p[Rema],0n));
   }
   regions.push({lo,hi,parts,full,total:full(hi),L});meter.regimes++;
  }
  const n=geo(count);
  function prefix(x){
   assert(x>=0n&&x<=n,"coordinate");let t0=0n,t1=count;
   if(x===n)t0=count;
   else while(t0+1n<t1){meter.querySteps++;let t=(t0+t1)/2n;if(geo(t)<=x)t0=t;else t1=t}
   let v=[0n,0n];
   for(const r of regions){
    if(t0>=r.hi){v=v.map((z,i)=>z+r.total[i]);continue}
    const sums=r.full(t0);v=v.map((z,i)=>z+sums[i]);
    const rest=x-geo(t0);
    for(const p of r.parts){const start=evalLine(p.left,t0),len=evalLine(p.len,t0);if(start>=rest||len===0n)continue;
     const k=rest-start<len?rest-start:len,pat=productPattern(p.x,p.y,t0,start,meter,true),[s,j]=local(pat,k);
     v[0]+=s;v[1]+=(geo(t0)+start)*s+j;
    }
    break;
   }
   return v;
  }
  return {n,prefix,range(a,b){assert(a<=b,"range order");const x=prefix(a),y=prefix(b);return y.map((z,i)=>z-x[i])},cuts:order.map(String),periods:regions.map(r=>r.L)};
 }
 // Independent finite expansion from uncompiled local laws.
 function raw(slots,count){
  const out=[];
  for(let t=0;t<count;t++)for(const s of slots){
   const v=s.v.map((x,i)=>(x+s.dv[i]*t)&255),n=s.n+s.dn*t;
   for(let j=0;j<n;j++)out.push(s.kind===2?(v[0]+v[1]*j)&255:v[j%v.length]);
  }return out;
 }
 const finite={cases:0,bytes:0,ranges:0,marginalChecks:0,regimes:0,overlapPieces:0,residues:0,setupTerms:0,queryTerms:0,expandedModelRecords:0};
 function finiteCase(a,b,count,sourceA=null){
  const m=stats(),ix=compile(a,b,count,m),setup=m.patternTerms,x=sourceA??raw(a,count),y=raw(b,count);
  assert(x.length===y.length&&B(x.length)===ix.n,"extent");
  const p=[0n],w=[0n],s=[0n];for(let i=0;i<x.length;i++){let z=B(x[i]*y[i]);p.push(p.at(-1)+z);w.push(w.at(-1)+B(i)*z);s.push(s.at(-1)+B(x[i]))}
  const old=arithmetic.index([{kind:"model",count,slots:a}],arithmetic.meter());
  let seed=17+x.length;const next=()=>seed=(Math.imul(seed,1664525)+1013904223)>>>0;
  for(let j=0;j<64;j++){let l=j===0?0:next()%(x.length+1),r=j===0?x.length:next()%(x.length+1);if(l>r)[l,r]=[r,l];
   const v=ix.range(B(l),B(r));assert(v[0]===p[r]-p[l]&&v[1]===w[r]-w[l],"finite joint");assert(old.range(B(l),B(r))===s[r]-s[l],"predecessor marginal");finite.ranges++;finite.marginalChecks++;
  }
  finite.cases++;finite.bytes+=x.length;finite.setupTerms+=setup;finite.queryTerms+=m.patternTerms-setup;
  for(const k of ["regimes","overlapPieces","residues","expandedModelRecords"])finite[k]+=m[k];
 }
 for(let i=0;i<12;i++){
  const f=api.fixture(1701+7919*i,"drifting"),bs=api.decode(api.compile(f.rs).wire);
  assert(bs.length===1&&bs[0].kind==="model","CLT013 model");
  const a=bs[0].slots,count=bs[0].count,N=a.reduce((z,s)=>z+s.n,0),D=a.reduce((z,s)=>z+s.dn,0);
  const b=[{kind:1,n:45,dn:0,v:[i+1,29,31],dv:[7,3,9]},{kind:1,n:N-45,dn:D,v:[81,17,7,3,9],dv:[1,2,3,4,5]}];
  finiteCase(a,b,count,f.source);
 }
 // Explicitly crossing and shrinking internal boundaries; outer geometry
 // still agrees. Independent byte oracle covers every region.
 finiteCase([{kind:1,n:16,dn:2,v:[5,9,11],dv:[1,2,3]},{kind:1,n:80,dn:-1,v:[7,4],dv:[5,8]}],[{kind:1,n:70,dn:-2,v:[8,3,2,1,9],dv:[5,9,7,1,2]},{kind:1,n:26,dn:3,v:[5,8],dv:[2,6]}],30);
 // Large source: independently declared geometry; crossing at t=1000000.
 const count=10n**12n+39n;
 const a=[{kind:2,n:257,dn:3,v:[17,11],dv:[9,6]},{kind:1,n:3000050,dn:1,v:[7,13,41],dv:[1,2,3]}];
 const b=[{kind:1,n:1000257,dn:2,v:[3,7,9,1],dv:[2,7,3,11]},{kind:1,n:2000050,dn:2,v:[6,8,2],dv:[7,3,1]}];
 const m=stats(),ix=compile(a,b,count,m),setup={...m};
 // Independent per-cycle oracle: sweep boundaries without compiled overlap
 // or polynomial tables, then use one product pattern and block arithmetic.
 function cycle(t,limit=null){
  const G=3000307n*t+4n*choose(t,2);
  let ia=0,ib=0,pa=0n,pb=0n,pos=0n,total=0n,weighted=0n;
  const vals=s=>s.v.map((v,i)=>Number((B(v)+B(s.dv[i])*t)%256n));
  const n=s=>B(s.n)+B(s.dn)*t;
  while(ia<a.length&&ib<b.length){
   let x=a[ia],y=b[ib],ea=pa+n(x),eb=pb+n(y),end=ea<eb?ea:eb;
   if(limit!==null&&end>limit)end=limit;
   const len=end-pos;
   let vx=vals(x),vy=vals(y),mx=x.kind===2?256:vx.length,my=y.kind===2?256:vy.length,P=lcm(mx,my),z=0n,w=0n,tail=0n,tailw=0n;
   const Q=len/B(P),R=len%B(P);
   for(let j=0;j<P;j++){
    const u=Number((pos-pa+B(j))%B(mx)),v=Number((pos-pb+B(j))%B(my));
    const k=B((x.kind===2?(vx[0]+u*vx[1])&255:vx[u])*(y.kind===2?(vy[0]+v*vy[1])&255:vy[v]));
    z+=k;w+=B(j)*k;if(B(j)<R){tail+=k;tailw+=B(j)*k}
   }
   let s=Q*z+tail,j=Q*w+B(P)*Q*(Q-1n)/2n*z+Q*B(P)*tail+tailw;
   total+=s;weighted+=(G+pos)*s+j;pos=end;if(limit!==null&&pos===limit)break;
   if(pos===ea){ia++;pa=ea}if(pos===eb){ib++;pb=eb}
  }
  return [total,weighted];
 }
 // Verify large prefixes with separately specified crossing and a
 // nonminimal joint period. Symmetrize the cubic weighted sequence:
 // f(q)+f(K-1-q) is quadratic; sum that using three samples.
 function oracle(T){
  let ans=[0n,0n];const stride=768n;
  for(const [lo,hi0] of [[0n,1000000n],[1000000n,count]]){
   const hi=T<hi0?T:hi0;if(hi<=lo)continue;
   for(let r=lo;r<hi&&r<lo+stride;r++){
    const K=(hi-1n-r)/stride+1n,first=cycle(r),last=cycle(r+(K-1n)*stride);
    ans[0]+=K*(first[0]+last[0])/2n;
    if(K<=2n){ans[1]+=K===1n?first[1]:first[1]+last[1];continue}
    const sym=q=>cycle(r+q*stride)[1]+cycle(r+(K-1n-q)*stride)[1];
    const s0=first[1]+last[1],s1=sym(1n),s2=sym(2n);
    const twice=K*s0+choose(K,2)*(s1-s0)+choose(K,3)*(s2-2n*s1+s0);
    assert(twice%2n===0n,"oracle parity");ans[1]+=twice/2n;
   }
  }
  return ans;
 }
 let largeChecks=0;
 for(const t of [0n,1000000n,count-1n,count]){
  const expected=oracle(t),off=3000307n*t+4n*choose(t,2),actual=ix.prefix(off);
  assert(actual.every((v,i)=>v===expected[i]),"large prefix");largeChecks++;
  if(t<count){const k=123n,partial=cycle(t,k),v=ix.prefix(off+k);assert(v.every((z,i)=>z===expected[i]+partial[i]),"large partial");largeChecks++}
 }
 let refused=0;
 for(const [bad,ct] of [[[{...b[0],n:b[0].n+1},b[1]],count],[[{...b[0],dn:-2},b[1]],count]])try{compile(a,bad,ct,stats())}catch(e){refused++}
 assert(refused===2,"refusal");
 const result=ix.prefix(ix.n);
 return {finite,large:{cycles:String(count),logicalBytes:String(ix.n),cuts:ix.cuts,periods:ix.periods,innerProduct:String(result[0]),weightedProduct:String(result[1]),setup,query:{steps:m.querySteps-setup.querySteps,patternTerms:m.patternTerms-setup.patternTerms,partialPatterns:m.partialPatterns-setup.partialPatterns},independentPrefixChecks:largeChecks},controls:{unalignedOrInvalidRefused:refused}};
}
if(require.main===module)console.log(JSON.stringify(experiment(require("../hierarchical_selector_grounds/clt013.js").experiment("api"),require("../selector_arithmetic/clt014.js").experiment(null,"api")),null,2));
module.exports={experiment};
