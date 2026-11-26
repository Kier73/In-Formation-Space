function sparseLift(s){
 const n=s.n,d=n*n,r=s.terms.length,ts=s.terms.map(t=>t.map(BigInt)),mask=(1n<<BigInt(d))-1n;
 const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
 function outer(a,b){let z=0n;for(let i of bits(a))z^=b<<BigInt(i*d);return z}
 function parity(x){let p=0;while(x){x&=x-1n;p^=1}return p}
 function basis(){let m=new Map();return {m,add(v,t=0n){while(v){let p=v.toString(2).length-1,q=m.get(p);if(!q){m.set(p,[v,t]);return true}v^=q[0];t^=q[1]}return false},solve(v){let t=0n;while(v){let p=v.toString(2).length-1,q=m.get(p);if(!q)return null;v^=q[0];t^=q[1]}return t},projector(){let p=[...m].sort((a,b)=>b[0]-a[0]).map(([p,[v,t]])=>[1n<<BigInt(p),v,t]);return v=>{let t=0n;for(let [bit,w,z] of p)if(v&bit){v^=w;t^=z}return [v,t]}}}}
 function fact(v){let rows=[],L=[],piv=[];for(let i=0;i<d;i++){let x=Number(v&mask),t=0;v>>=BigInt(d);while(x){let p=31-Math.clz32(x),j=piv.indexOf(p);if(j<0){if(rows.length===2)return null;piv.push(p);rows.push(x);L.push(0);t^=1<<(rows.length-1);break}x^=rows[j];t^=1<<j}for(let j=0;j<rows.length;j++)if(t>>j&1)L[j]|=1<<i}return L.map((a,i)=>[BigInt(a),BigInt(rows[i])])}
 function verify(t){let z=Array(d).fill(0n);for(let [a,b,c] of t){if(!a||!b||!c)return false;let v=outer(a,b);for(let j of bits(c))z[j]^=v}for(let i=0;i<n;i++)for(let j=0;j<n;j++){let v=0n;for(let h=0;h<n;h++)v^=1n<<BigInt((i*n+h)*d+h*n+j);if(v!==z[i*n+j])return false}return true}
 if(!verify(ts))throw Error("seed");
 let reports=[];
 for(let a=0;a<3;a++){
  let b=(a+1)%3,c=(a+2)%3,V=ts.map(t=>outer(t[b],t[c])),B=basis();for(let i=0;i<r;i++)B.add(V[i],1n<<BigInt(i));if(B.m.size!==r)throw Error("independent");let Q=B.projector(),inside=new Map(),groups=new Map(),cache=new Map(),tested=[0,0,0,0,0],low=[0,0,0,0,0];
  function register(u,v){let key=u+":"+v;if(cache.has(key))return cache.get(key);let [q,t]=Q(outer(u,v)),o={u,v,q,t,key};cache.set(key,o);if(q===0n)inside.set(key,o);return o}
  for(let t of ts)register(t[b],t[c]);
  function visit(x,weight){tested[weight]++;let f=fact(x);if(!f||f.length===0)return;low[weight]++;let sum=0n;for(let z of f)sum^=outer(...z);if(sum!==x)throw Error("factor verify");if(f.length===1){register(...f[0]);return}
   let [[u,v],[w,z]]=f;for(let [p,q] of [[[u,v],[w,z]],[[u^w,v],[w,z^v]],[[u,v^z],[u^w,z]]]){let A=register(...p),C=register(...q);if(A.q!==C.q)throw Error("coset");if(A.q){let g=groups.get(A.q);if(!g){g=new Map();groups.set(A.q,g)}g.set(A.key,A);g.set(C.key,C)}}
  }
  for(let i=0;i<r;i++)for(let j=i+1;j<r;j++){let x=V[i]^V[j];visit(x,2);for(let k=j+1;k<r;k++){let y=x^V[k];visit(y,3);for(let l=k+1;l<r;l++)visit(y^V[l],4)}}
  let atoms=[...inside.values()],multi=[...groups.values()].map(g=>[...g.values()]).sort((x,y)=>y.length-x.length),hist={};for(let g of multi)hist[g.length]=(hist[g.length]||0)+1;
  let T=Array.from({length:d},(_,j)=>ts.reduce((v,x,i)=>v|(((x[a]>>BigInt(j))&1n)<<BigInt(i)),0n));
  let rels=[],pairs=new Map();for(let i=0;i<r;i++)for(let j=i+1;j<r;j++){let z=ts[i][a]^ts[j][a],m=(1n<<BigInt(i))|(1n<<BigInt(j));if(!z)rels.push(m);if(!pairs.has(z))pairs.set(z,[]);pairs.get(z).push([i,j,m]);for(let k=j+1;k<r;k++)if(z===ts[k][a])rels.push(m|(1n<<BigInt(k)))}
  for(let g of pairs.values())for(let [i,j,m] of g)for(let [k,l,z] of g)if(j<k)rels.push(m|z);
  let checks=0,groupChecks=0,atomTests=0,spanChecks=0,deficits={},bestRemaining=99,maxGain=0,success=null,truncated=false;
  let pass=rels.map(z=>atoms.filter(x=>!parity(x.t&z)));
  for(let i=0;i<rels.length&&!success&&!truncated;i++)for(let j=0;j<i&&!success&&!truncated;j++){
   let z=rels[i],w=rels[j],K=basis(),sel=[];checks++;for(let x of pass[i])if(!parity(x.t&w)&&K.add(x.t))sel.push(x);
   let P=K.projector(),D=basis(),want=[];for(let x of T){let v=P(x)[0];if(D.add(v))want.push(v)}let miss=D.m.size;deficits[miss]=(deficits[miss]||0)+1;
   if(!miss)throw Error("unexpected in-space solution");
   for(let g of multi){if(g.length<=miss)break;if(groupChecks>=2000000){truncated=true;break}groupChecks++;let bins=[[],[],[],[]];for(let x of g){bins[parity(x.t&z)|(parity(x.t&w)<<1)].push(x);atomTests++}
    for(let bin of bins){if(bin.length<=miss)continue;let anchor=bin[0],H=basis(),used=[];for(let x of bin.slice(1)){let v=P(x.t^anchor.t)[0];if(H.add(v))used.push(x)}if(H.m.size<miss)continue;spanChecks++;let PP=H.projector(),R=basis();for(let v of want)R.add(PP(v)[0]);maxGain=Math.max(maxGain,miss-R.m.size);bestRemaining=Math.min(bestRemaining,R.m.size);if(R.m.size)continue;
     let A=sel.map(x=>({x,v:x.t})).concat([anchor,...used].map(x=>({x,v:x.t|(1n<<BigInt(r))}))),J=basis(),keep=[];for(let x of A)if(J.add(x.v,1n<<BigInt(keep.length)))keep.push(x);if(keep.length>=r)throw Error("rank cap");
     let cols=Array(keep.length).fill(0n);for(let k=0;k<d;k++){let v=J.solve(T[k]);if(v===null)throw Error("target");for(let i of bits(v))cols[i]|=1n<<BigInt(k)}let out=[];for(let i=0;i<keep.length;i++)if(cols[i]){let t=[];t[a]=cols[i];t[b]=keep[i].x.u;t[c]=keep[i].x.v;out.push(t)}if(!verify(out)||out.length>=r)throw Error("bad reduction");
     success={rank:out.length,terms:out.map(x=>x.map(String)),constraints:[String(z),String(w)],missing:miss,inside:sel.length,usedOutside:used.length+1,groupSize:g.length};break
    }if(success)break
   }
  }
  reports.push({axis:a,tested,low,inside:atoms.length,uniqueAtoms:cache.size,groups:multi.length,hist,dualRelations:rels.length,checks,groupChecks,atomTests,spanChecks,deficits,maxGain,bestRemaining:bestRemaining===99?null:bestRemaining,truncated,success});
  if(success)return {n,initial:r,best:success.rank,reports,terms:success.terms,verified:true}
 }
 return {n,initial:r,best:r,reports,terms:s.terms,verified:true}
}
const fs=require('node:fs'),path=require('node:path');console.log(JSON.stringify(sparseLift(JSON.parse(fs.readFileSync(path.join(__dirname,'mmg012_results.json'),'utf8')).find(x=>x.n===4)),null,2));
