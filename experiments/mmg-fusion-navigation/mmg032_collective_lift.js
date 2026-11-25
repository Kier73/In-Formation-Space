function collective(s){
 const n=s.n,d=n*n,r=s.terms.length,ts=s.terms.map(t=>t.map(BigInt));
 const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
 function outer(a,b){let z=0n;for(let i of bits(a))z^=b<<BigInt(i*d);return z}
 function parity(x){x^=x>>>16;x^=x>>>8;x^=x>>>4;return (0x6996>>>(x&15))&1}
 function bigbasis(){let m=new Map();return {m,add(v,t){while(v){let p=v.toString(2).length-1,q=m.get(p);if(!q){m.set(p,[v,t]);return true}v^=q[0];t^=q[1]}return false}}}
 function b32(){let p=new Int32Array(r+1),size=0;return {p,get size(){return size},add(v){while(v){let i=31-Math.clz32(v);if(!p[i]){p[i]=v;size++;return true}v^=p[i]}return false},rem(v){for(let i=r;i>=0;i--)if((v>>>i&1)&&p[i])v^=p[i];return v}}}
 function verify(t){let z=Array(d).fill(0n);for(let [a,b,c] of t){let v=outer(a,b);for(let j of bits(c))z[j]^=v}for(let i=0;i<n;i++)for(let j=0;j<n;j++){let v=0n;for(let h=0;h<n;h++)v^=1n<<BigInt((i*n+h)*d+h*n+j);if(v!==z[i*n+j])return false}return true}
 let reports=[];
 if(!verify(ts))throw Error("seed");
 for(let axis=0;axis<3;axis++){
  let b=(axis+1)%3,c=(axis+2)%3,B=bigbasis();for(let i=0;i<r;i++)B.add(outer(ts[i][b],ts[i][c]),1<<i);if(B.m.size!==r)throw Error("independent");
  let ec=[...B.m].sort((x,y)=>y[0]-x[0]).map(([p,[v,t]])=>[1n<<BigInt(p),v,t]);
  function project(v){let t=0;for(let [p,x,z] of ec)if(v&p){v^=x;t^=z}return [v,t]}
  let inside=[],groups=new Map();
  for(let u=1n;u<1n<<BigInt(d);u++){let tab=Array.from({length:d},(_,j)=>project(outer(u,1n<<BigInt(j)))),q=0n,t=0,v=0n;for(let j=1;j<2**d;j++){let p=31-Math.clz32(j&-j);q^=tab[p][0];t^=tab[p][1];v^=1n<<BigInt(p);let a={u,v,t};if(!q)inside.push(a);else{let g=groups.get(q);if(!g){g=[];groups.set(q,g)}g.push(a)}}}
  let hist={},multi=[...groups.values()].filter(g=>g.length>=2).sort((a,b)=>b.length-a.length);
  for(let g of groups.values())hist[g.length]=(hist[g.length]||0)+1;
  const T=Array.from({length:d},(_,j)=>ts.reduce((v,x,i)=>v|Number(x[axis]>>BigInt(j)&1n)<<i,0));
  let rels=[],sum=new Map();for(let i=0;i<r;i++)for(let j=i+1;j<r;j++){let z=ts[i][axis]^ts[j][axis],m=(1<<i)|(1<<j);if(!z)rels.push(m);if(!sum.has(z))sum.set(z,[]);sum.get(z).push([i,j,m]);for(let k=j+1;k<r;k++)if(z===ts[k][axis])rels.push(m|(1<<k))}
  for(let g of sum.values())for(let [i,j,m] of g)for(let [k,l,z] of g)if(j<k)rels.push(m|z);
  let dualChecks=0,groupChecks=0,atomTests=0,spanChecks=0,deficits={},maxGain=0,bestDef=99,success=null,groupBudget=7000000,truncated=false;
  const pass=rels.map(z=>inside.filter(a=>!parity(a.t&z)));
  for(let i=0;i<rels.length&&!success&&!truncated;i++)for(let j=0;j<i&&!success&&!truncated;j++){
   let z=rels[i],w=rels[j],K=b32(),sel=[];dualChecks++;for(let a of pass[i])if(!parity(a.t&w)&&K.add(a.t))sel.push(a);
   let D=b32(),want=[];for(let t of T){let v=K.rem(t);if(D.add(v))want.push(v)}
   let miss=D.size;deficits[miss]=(deficits[miss]||0)+1;if(miss===0)throw Error("closure unexpectedly succeeded");
   for(let g of multi){if(g.length<=miss)break;if(++groupChecks>groupBudget){truncated=true;break}
    let bins=[[],[],[],[]];for(let a of g){bins[parity(a.t&z)|(parity(a.t&w)<<1)].push(a);atomTests++}
    for(let bin of bins){if(bin.length<=miss)continue;let anchor=bin[0],H=b32(),used=[];for(let a of bin.slice(1)){let v=K.rem(a.t^anchor.t);if(H.add(v))used.push(a)}
     if(H.size<miss)continue;spanChecks++;let remain=b32();for(let t of want)remain.add(H.rem(t));maxGain=Math.max(maxGain,miss-remain.size);bestDef=Math.min(bestDef,remain.size);if(remain.size)continue;
     // Construct supporting span in K plus a single new outside coordinate.
     let atoms=sel.map(a=>({a,coord:a.t})).concat([anchor,...used].map(a=>({a,coord:a.t|(1<<r)})));
     let piv=new Map(),keep=[];for(let x of atoms){let v=x.coord,tag=1n<<BigInt(keep.length);while(v){let p=31-Math.clz32(v),q=piv.get(p);if(!q){piv.set(p,[v,tag]);keep.push(x);break}v^=q[0];tag^=q[1]}}
     if(keep.length>=r)throw Error("dimension");
     let cols=Array(keep.length).fill(0n);for(let k=0;k<d;k++){let v=T[k],tag=0n;while(v){let p=31-Math.clz32(v),q=piv.get(p);if(!q)throw Error("target");v^=q[0];tag^=q[1]}for(let l of bits(tag))cols[l]|=1n<<BigInt(k)}
     let out=[];for(let k=0;k<keep.length;k++)if(cols[k]){let a=keep[k].a,t=[];t[axis]=cols[k];t[b]=a.u;t[c]=a.v;out.push(t)}if(out.length>=r||!verify(out))throw Error("bad lift");success={rank:out.length,terms:out.map(x=>x.map(String)),constraints:[z,w],missing:miss,groupSize:g.length,usedOutside:used.length+1,inside:sel.length};break
    }if(success)break;
   }
  }
  reports.push({axis,inside:inside.length,groups:groups.size,multiGroups:multi.length,hist,relations:rels.length,dualChecks,groupChecks,atomTests,spanChecks,deficits,maxGain,bestDef:bestDef===99?null:bestDef,truncated,success});
  if(success)return {initial:r,best:success.rank,reports,terms:success.terms,verified:true}
 }
 return {initial:r,best:r,reports,terms:s.terms,verified:true}
}
const fs=require('node:fs'),path=require('node:path');const s=JSON.parse(fs.readFileSync(path.join(__dirname,'mmg021_results.json'),'utf8')).results.find(x=>x.n===3);console.log(JSON.stringify(collective(s),null,2));
