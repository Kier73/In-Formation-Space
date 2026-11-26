function topology(){
const n=2,d=4;
const bits=x=>{let a=[];for(let i=0;x;x>>>=1,i++)if(x&1)a.push(i);return a};
function outer(a,b){let z=0;for(let i of bits(a))z^=b<<(i*d);return z}
function target(q){let z=0;for(let e of bits(q)){let i=e>>1,k=e&1;for(let j=0;j<2;j++)z^=1<<((i*2+j)*d+j*2+k)}return z}
function rank(x){let p=[0,0,0,0],r=0;for(let i=0;i<d;i++){let v=x>>>(i*d)&15;while(v){let j=31-Math.clz32(v);if(!p[j]){p[j]=v;r++;break}v^=p[j]}}return r}
function qouter(a,b){let z=0;for(let i of bits(a))z^=b<<(2*i);return z}
function parity(v){let p=0;while(v){v&=v-1;p^=1}return p}
function verify(ts){let r=[0,0,0,0];for(let [a,b,c] of ts)for(let j of bits(c))r[j]^=outer(a,b);return r.every((x,j)=>x===target(1<<j))}
function span(q){let s=new Set([0]);for(let x of q)for(let y of [...s])s.add(y^x);return s}
function factor2(q){
 let a=[];for(let x=1;x<16;x++)for(let y=1;y<16;y++){let p=outer(x,y),v=target(q)^p;if(rank(v)!==1)continue;let i=31-Math.clz32(v),b2=v>>>(4*(i>>2))&15,a2=0;for(let k=0;k<4;k++)if(v>>>(4*k)&15)a2|=1<<k;
 if(outer(a2,b2)!==v)throw Error("factor");let x1=[x,y],x2=[a2,b2];if(x*16+y<a2*16+b2)a.push([x1,x2])}
 return a
}
const forms=[...new Set([1,2,3].flatMap(a=>[1,2,3].map(b=>qouter(a,b))))];
const factors=new Map(forms.map(q=>[q,factor2(q)]));
if([...factors.values()].some(v=>v.length!==3))throw Error("factor count");
let classes={},examined=0,cases=0,success=0,first=null,profile={};
for(let q1 of forms)for(let q2 of forms)for(let q3 of forms){let prefix=[q1,q2,q3],S=span(prefix);if(S.size!==8)continue;
 for(let q4 of forms){if(S.has(q4))continue;let sep=forms.filter(z=>prefix.every(q=>!parity(q&z))&&parity(z&q4));let c=sep.length?"separable":"entangled";if(!classes[c])classes[c]={flags:0,topologies:0,rankTests:0,successes:0,best:8};classes[c].flags++;cases++;
  let q=[...prefix,q4],out=null;
  for(let A of factors.get(q1))for(let B of factors.get(q2))for(let C of factors.get(q3)){
   let atoms=[...A,...B,...C],v=atoms.map(x=>outer(...x));classes[c].topologies++;
   let t=target(q4),used=0;
   for(let k=0;k<64;k++){if(k){let b=31-Math.clz32(k&-k);used^=1<<b;t^=v[b]}examined++;classes[c].rankTests++;if(rank(t)!==1)continue;
    let j=31-Math.clz32(t),rb=t>>>(4*(j>>2))&15,ra=0;for(let i=0;i<4;i++)if(t>>>(4*i)&15)ra|=1<<i;
    if(outer(ra,rb)!==t)throw Error("resid");
    let partial=atoms.map(([a,b],i)=>[a,b,(1<<Math.floor(i/2))|((used>>i&1)<<3)]).concat([[ra,rb,8]]);
    let raw=partial.map(([a,b,c])=>{let z=0;for(let j=0;j<4;j++){let u=-1;for(let k=1;k<16;k++){let v=0;for(let i of bits(k))v^=q[i];if(v===1<<j){u=k;break}}if(u<0)throw Error("basis");if(parity(u&c))z|=1<<j}return [a,b,z]});
    if(!verify(raw))throw Error("full identity");classes[c].successes++;classes[c].best=7;success++;
    if(!first)first={q,separatorCount:sep.length,atoms,used,residual:[ra,rb],partial,terms:raw};
    if(!out)out=raw;
   }
  }
  if(out)profile[c]=(profile[c]||0)+1;
 }
}
return {forms:forms.length,queryBasisFlags:cases,rankTests:examined,classes,successfulFlags:profile,successfulTopologicalCompletions:success,first};
}
console.log(JSON.stringify(topology(),null,2));
