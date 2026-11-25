"use strict";
function experiment(core){
 const B=BigInt,ok=(v,m)=>{if(!v)throw Error(m)},abs=x=>x<0n?-x:x,gcd=(a,b)=>b===0n?a:gcd(b,a%b),tri=x=>x*(x-1n)/2n,mod=(x,m)=>((x%m)+m)%m;
 const sum=(ss,key)=>ss.reduce((z,s)=>z+B(s[key]),0n),P=(s,t)=>sum(s,"n")*t+sum(s,"dn")*tri(t),len=(s,t)=>B(s.n)+B(s.dn)*t;
 function validate(ss,n){
  ok(Array.isArray(ss)&&ss.length>=1&&ss.length<=8&&n>=1n&&n<=10n**30n,"domain");
  for(const s of ss){ok((s.kind===1&&s.v.length>=1&&s.v.length<=16||s.kind===2&&s.v.length===2)&&s.v.length===s.dv.length&&[...s.v,...s.dv].every(v=>Number.isInteger(v)&&v>=0&&v<=255),"descriptor");const m=B(s.kind===1?s.v.length:1);ok(len(s,0n)>=m&&len(s,n-1n)>=m,"length")}
 }
 function sync(a,b,na,nb,sa=0n,sb=0n){
  na=B(na);nb=B(nb);validate(a,na);validate(b,nb);ok(sa>=0n&&sa<na&&sb>=0n&&sb<nb,"start");
  const refuse=(reason,extra={})=>({status:"UNRESOLVED",reason,...extra});
  if(P(a,sa)!==P(b,sb))return refuse("different-start-coordinate");
  const da=sum(a,"dn"),db=sum(b,"dn"),ca=2n*(sum(a,"n")+da*sa)-da,cb=2n*(sum(b,"n")+db*sb)-db;
  let choices=[];
  if(ca!==0n&&cb!==0n&&(ca>0n)===(cb>0n)){let g=gcd(abs(ca),abs(cb));choices.push([abs(cb)/g,abs(ca)/g])}
  else if(ca===0n&&cb===0n)for(let k=1n;k<=8n;k++)for(let l=1n;l<=8n;l++)if(gcd(k,l)===1n)choices.push([k,l]);
  choices=choices.filter(([k,l])=>da*k*k===db*l*l&&ca*k===cb*l);
  if(!choices.length)return refuse("no-qualified-affine-stride");
  choices.sort((x,y)=>x[0]+x[1]<y[0]+y[1]?-1:x[0]+x[1]>y[0]+y[1]?1:0);
  const [k,l]=choices[0],strides=[String(k),String(l)];
  if(k*B(a.length)>8n||l*B(b.length)>8n)return refuse("supercycle-slot-budget",{strides});
  const qa=(na-sa)/k,qb=(nb-sb)/l,Q=qa<qb?qa:qb;
  if(!Q)return refuse("no-complete-common-cycle");
  function regroup(ss,start,stride){
   let out=[];for(let j=0n;j<stride;j++)for(const s of ss){let t=start+j;out.push({kind:s.kind,n:len(s,t),dn:B(s.dn)*stride,v:s.v.map((x,i)=>Number(mod(B(x)+B(s.dv[i])*t,256n))),dv:s.dv.map(d=>Number(mod(B(d)*stride,256n)))})}return out;
  }
  const x=regroup(a,sa,k),y=regroup(b,sb,l),origin=P(a,sa),end=P(a,sa+k*Q);
  ok(end===P(b,sb+l*Q)&&P(x,Q)===end-origin&&P(y,Q)===end-origin,"geometry proof");
  const m=core.stats(),ix=core.compile(x,y,Q,m);
  return {status:"EXACT",strides,Q,origin,end,remaining:[na-sa-k*Q,nb-sb-l*Q],slots:[x.length,y.length],m,range(u,v){ok(u>=origin&&v<=end&&u<=v,"outside qualified window");let z=ix.range(u-origin,v-origin);return [z[0],z[1]+origin*z[0]]}};
 }
 const s=(n,dn,v,dv)=>({kind:1,n,dn,v,dv});
 const a=[s(5,3,[3,7],[64,128]),s(7,6,[2,11,5],[128,64,0])],b=[s(3,1,[9,1],[64,0]),s(4,3,[5,8,2],[128,64,128])];
 function raw(ss,n){let out=[];for(let t=0n;t<B(n);t++)for(const s of ss){let p=s.v.map((v,i)=>Number(mod(B(v)+B(s.dv[i])*t,256n)));for(let j=0;j<Number(len(s,t));j++)out.push(p[j%p.length])}return out}
 const finite={cases:0,ranges:0,operatorChecks:0,partialWindows:0,shiftedWindows:0,setupTerms:0,queryTerms:0,tailRefusals:0};
 function test(a,b,na,nb,sa=0n,sb=0n){
  const x=raw(a,na),y=raw(b,nb),g=sync(a,b,na,nb,sa,sb);ok(g.status==="EXACT","finite alignment: "+g.reason);const setup=g.m.patternTerms;
  const p=[0n],w=[0n];for(let i=0;i<Math.min(x.length,y.length);i++){let z=B(x[i]*y[i]);p.push(p.at(-1)+z);w.push(w.at(-1)+B(i)*z)}
  let n=Number(g.end-g.origin),start=Number(g.origin),seed=n+31;const next=()=>seed=(Math.imul(seed,1664525)+1013904223)>>>0;
  for(let j=0;j<64;j++){let l=j===0?0:next()%(n+1),h=j===0?n:next()%(n+1);if(l>h)[l,h]=[h,l];l+=start;h+=start;let z=g.range(B(l),B(h));ok(z[0]===p[h]-p[l]&&z[1]===w[h]-w[l],"raw comparison");finite.ranges++;finite.operatorChecks+=2}
  finite.cases++;finite.shiftedWindows+=Number(g.origin!==0n);finite.setupTerms+=setup;finite.queryTerms+=g.m.patternTerms-setup;
  if(g.remaining.some(x=>x!==0n)){finite.partialWindows++;let reject=false;try{g.range(g.origin,g.end+1n)}catch(e){reject=true}ok(reject,"tail");finite.tailRefusals++}
 }
 for(let i=3;i<15;i++){test(a,b,2*i,3*i);test(a,b,2*i+1,3*i+2)}
 test(a,b,24,36,4n,6n);
 const c=[s(3,0,[1,2,3],[0,0,0])],d=[s(5,0,[5,7],[64,128])];test(c,d,35,21);test(d,c,21,35);
 const T=10n**12n+39n,g=sync(a,b,2n*T,3n*T);ok(g.status==="EXACT","large");const setup={...g.m};
 // Independent native-cycle overlap sweep and local residue counting.
 function cycle(u){
  function records(ss,k){const out=[];let pos=0n;for(let j=0n;j<k;j++)for(const s of ss){let t=k*u+j,n=len(s,t);out.push({s,t,lo:pos,hi:pos+n});pos+=n}return out}
  const x=records(a,2n),y=records(b,3n),origin=P(a,2n*u);let i=0,j=0,z=0n,w=0n;
  while(i<x.length&&j<y.length){const A=x[i],B0=y[j],lo=A.lo>B0.lo?A.lo:B0.lo,hi=A.hi<B0.hi?A.hi:B0.hi;
   if(hi>lo){const m=B(A.s.v.length),n=B(B0.s.v.length),L=m*n/gcd(m,n);
    for(let r=0n;r<L&&r<hi-lo;r++){const K=(hi-lo-1n-r)/L+1n,p=Number((lo+r-A.lo)%m),q=Number((lo+r-B0.lo)%n),v=mod(B(A.s.v[p])+B(A.s.dv[p])*A.t,256n)*mod(B(B0.s.v[q])+B(B0.s.dv[q])*B0.t,256n);z+=v*K;w+=v*(K*(origin+lo+r)+L*tri(K))}
   }
   if(A.hi<=B0.hi)i++;if(B0.hi<=A.hi)j++;
  }return [z,w];
 }
 // Qualify fixed ordering after 16 common cycles independently.
 function lines(ss,k){let a=0n,d=0n,out=[[a,d]];for(let j=0n;j<k;j++)for(const s of ss){a+=len(s,j);d+=B(s.dn)*k;out.push([a,d])}return out}
 for(const x of lines(a,2n))for(const y of lines(b,3n)){const f=t=>x[0]-y[0]+(x[1]-y[1])*t;ok(f(16n)*f(T-1n)>=0n,"tail crossing")}
 const C=(n,k)=>{let z=1n;if(n<B(k))return 0n;for(let i=1;i<=k;i++)z=z*(n-B(i-1))/B(i);return z};
 function oracle(t){
  let z=[0n,0n];for(let i=0n;i<t&&i<16n;i++){let v=cycle(i);z=z.map((x,j)=>x+v[j])}
  for(let r=16n;r<t&&r<64n;r++){const L=48n,K=(t-1n-r)/L+1n,f=cycle(r),l=cycle(r+(K-1n)*L);z[0]+=K*(f[0]+l[0])/2n;
   if(K<=2n){z[1]+=K===1n?f[1]:f[1]+l[1];continue}
   const sym=q=>cycle(r+q*L)[1]+cycle(r+(K-1n-q)*L)[1],a=f[1]+l[1],b=sym(1n),c=sym(2n);
   const twice=K*a+C(K,2)*(b-a)+C(K,3)*(c-2n*b+a);ok(twice%2n===0n,"parity");z[1]+=twice/2n;
  }return z;
 }
 let checks=0;for(const t of [0n,1n,16n,1234567n,T-1n,T]){let v=g.range(0n,P(a,2n*t)),o=oracle(t);ok(v.every((x,i)=>x===o[i]),"large oracle");checks+=2}
 const controls=[sync(a,[s(7,5,[1],[0])],12,12),sync([s(101,0,[1],[0])],[s(103,0,[2],[0])],103,101),sync(a,b,24,36,1n,1n),sync(c,d,1,1)];ok(controls.every(c=>c.status==="UNRESOLVED"),"negative");
 const z=g.range(0n,g.end);
 return {finite,large:{nativeCycles:[String(2n*T),String(3n*T)],commonCycles:String(T),strides:g.strides,regroupedSlots:g.slots,logicalBytes:String(g.end),dot:String(z[0]),weighted:String(z[1]),setup,query:{patternTerms:g.m.patternTerms-setup.patternTerms,steps:g.m.querySteps-setup.querySteps},independentChecks:checks},controls};
}
if(require.main===module)console.log(JSON.stringify(experiment(require("../bilinear_selector_grounds/clt015.js").experiment(null,null,"api")),null,2));
module.exports={experiment};
