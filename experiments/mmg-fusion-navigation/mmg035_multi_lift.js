function multiLift(s,limit=48){
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
  for(let i=0;i<r;i++)for(let j=i+1;j<r;j++){let x=V[i]^V[j];visit(x,2);for(let k=j+1;k<r;k++){let y=x^V[k];visit(y,3);if(n<=4)for(let l=k+1;l<r;l++)visit(y^V[l],4)}}
  let atoms=[...inside.values()],multi=[...groups.values()].map(g=>[...g.values()]).sort((x,y)=>y.length-x.length),hist={};for(let g of multi)hist[g.length]=(hist[g.length]||0)+1;
  let T=Array.from({length:d},(_,j)=>ts.reduce((v,x,i)=>v|(((x[a]>>BigInt(j))&1n)<<BigInt(i)),0n));
  let rels=[],pairs=new Map();for(let i=0;i<r;i++)for(let j=i+1;j<r;j++){let z=ts[i][a]^ts[j][a],m=(1n<<BigInt(i))|(1n<<BigInt(j));if(!z)rels.push(m);if(!pairs.has(z))pairs.set(z,[]);pairs.get(z).push([i,j,m]);for(let k=j+1;k<r;k++)if(z===ts[k][a])rels.push(m|(1n<<BigInt(k)))}
  for(let g of pairs.values())for(let [i,j,m] of g)for(let [k,l,z] of g)if(j<k)rels.push(m|z);
  // Three independent dual restrictions pay for two independent external quotient directions.
  let state=90731+n*100+a,random=k=>{state^=state<<13;state^=state>>>17;state^=state<<5;return(state>>>0)%k},triples=[],seen=new Set();
  for(let h=0;h<limit*50&&triples.length<limit;h++){if(rels.length<3)break;let z=[rels[random(rels.length)],rels[random(rels.length)],rels[random(rels.length)]];let D=basis();if(!z.every(x=>D.add(x)))continue;let key=z.map(String).sort().join(":");if(!seen.has(key)){seen.add(key);triples.push(z)}}
  let checks=0,groupChecks=0,pairChecks=0,maxGain=0,closest=null,deficits={},success=null;
  for(let z of triples){checks++;let K=basis(),sel=[];for(let x of atoms)if(z.every(v=>!parity(x.t&v))&&K.add(x.t))sel.push(x);let P=K.projector(),D=basis(),want=[];for(let x of T){let v=P(x)[0];if(D.add(v))want.push(v)}let miss=D.m.size;deficits[miss]=(deficits[miss]||0)+1;if(!miss)continue;
   let options=[];
   for(let g of multi){groupChecks++;let bins=Array.from({length:8},()=>[]);for(let x of g){let tag=0;for(let j=0;j<3;j++)tag|=parity(x.t&z[j])<<j;bins[tag].push(x)}
    for(let bin of bins){if(bin.length<2)continue;let H=basis(),used=[bin[0]],vec=[];for(let x of bin.slice(1)){let v=P(x.t^bin[0].t)[0];if(H.add(v)){vec.push(v);used.push(x)}}if(!vec.length)continue;
     let HP=H.projector(),R=basis();for(let v of want)R.add(HP(v)[0]);let gain=miss-R.m.size;if(gain||vec.length>=Math.ceil(miss/2))options.push({q:bin[0].q,used,vec,gain});
    }
   }
   options.sort((a,b)=>b.gain-a.gain||b.vec.length-a.vec.length);options=options.slice(0,48);
   for(let i=0;i<options.length&&!success;i++)for(let j=0;j<i;j++){let x=options[i],y=options[j];if(x.q===y.q||x.vec.length+y.vec.length<miss)continue;pairChecks++;let H=basis();for(let v of x.vec.concat(y.vec))H.add(v);if(H.m.size<miss)continue;let HP=H.projector(),R=basis();for(let v of want)R.add(HP(v)[0]);maxGain=Math.max(maxGain,miss-R.m.size);closest=closest===null?R.m.size:Math.min(closest,R.m.size);if(R.m.size)continue;
    let A=sel.map(x=>({x,v:x.t})).concat(x.used.map(x=>({x,v:x.t|(1n<<BigInt(r))})),y.used.map(x=>({x,v:x.t|(1n<<BigInt(r+1))}))),J=basis(),keep=[];for(let x of A)if(J.add(x.v,1n<<BigInt(keep.length)))keep.push(x);if(keep.length>=r)throw Error("rank cap");
    let cols=Array(keep.length).fill(0n);for(let k=0;k<d;k++){let v=J.solve(T[k]);if(v===null)throw Error("target");for(let i of bits(v))cols[i]|=1n<<BigInt(k)}let out=[];for(let i=0;i<keep.length;i++)if(cols[i]){let t=[];t[a]=cols[i];t[b]=keep[i].x.u;t[c]=keep[i].x.v;out.push(t)}if(!verify(out)||out.length>=r)throw Error("bad reduction");
    success={rank:out.length,terms:out.map(x=>x.map(String)),constraints:z.map(String),missing:miss,inside:sel.length,outside:[x.used.length,y.used.length]};break;
   }
   if(success)break;
  }
  reports.push({axis:a,tested,low,inside:atoms.length,uniqueAtoms:cache.size,groups:multi.length,hist,dualRelations:rels.length,checks,groupChecks,pairChecks,deficits,maxGain,closest,success});
  if(success)return {n,initial:r,best:success.rank,reports,terms:success.terms,verified:true}
 }
 return {n,initial:r,best:r,reports,terms:s.terms,verified:true}
}
const fs=require('node:fs'),path=require('node:path');const read=x=>JSON.parse(fs.readFileSync(path.join(__dirname,x),'utf8'));const n=Number(process.argv[2]||4);const s=n===3?{...read('mmg021_results.json').results.find(x=>x.n===3),n:3}:read('mmg012_results.json').find(x=>x.n===n);console.log(JSON.stringify(multiLift(s),null,2));
