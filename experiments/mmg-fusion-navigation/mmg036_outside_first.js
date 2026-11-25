function outsideFirst(s){
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
  let state=91917+n*100+a,rand=k=>{state^=state<<13;state^=state>>>17;state^=state<<5;return(state>>>0)%k};
  let families=multi.map(g=>{let H=basis(),anchor=g[0],used=[anchor],ds=[];for(let x of g.slice(1)){let v=x.t^anchor.t;if(H.add(v)){used.push(x);ds.push(v)}}return {q:anchor.q,used,ds}}).filter(x=>x.ds.length>0&&x.ds.length<=12);
  let attempts=0,upperScreens=0,fitTrials=0,bestGain=-99,success=null,maxOptimism=-99,screenedByDim=0,pairCount=0,near=0;
  function pattern(groups){let vs=groups.flatMap(g=>g.ds),k=vs.length;if(k>12){screenedByDim++;return null}
   let rows=Array(r).fill(0),m=new Map();for(let j=0;j<k;j++)for(let i of bits(vs[j]))rows[i]|=1<<j;
   for(let i=0;i<r;i++){let v=rows[i];if(!v)continue;let z=m.get(v);if(!z){z=new Map();m.set(v,z)}z.set(ts[i][a],(z.get(ts[i][a])||0)+1)}
   let upper=0;for(let z of m.values())upper+=Math.max(...z.values());return {vs,k,rows,m,upper,margin:upper-k-groups.length}
  }
  function fit(groups,P,tries){attempts++;maxOptimism=Math.max(maxOptimism,P.margin);
   // Full-support optimistic screen. A zero coefficient may enable a smaller subset, not ruled out here.
   if(P.margin<=0){upperScreens++;return}
   let rows=P.rows.map((v,i)=>[v,ts[i][a]]).filter(x=>x[0]);let k=P.k;
   for(let h=0;h<tries;h++){fitTrials++;let order=rows.slice();for(let i=order.length-1;i>0;i--){let j=rand(i+1);[order[i],order[j]]=[order[j],order[i]]}
    let piv=new Map();for(let [v,t] of order){while(v){let p=31-Math.clz32(v),z=piv.get(p);if(!z){piv.set(p,[v,t]);break}v^=z[0];t^=z[1]}}
    function value(v){let t=0n;for(let p=k-1;p>=0;p--)if(v>>>p&1){let z=piv.get(p);if(z){v^=z[0];t^=z[1]}}return t}
    let old=ts.map(t=>t.slice()),newTerms=[],off=0;for(let g of groups){let anchor=0n;for(let j=0;j<g.ds.length;j++){let u=value(1<<(off+j));anchor^=u;if(u){let t=[];t[a]=u;t[b]=g.used[j+1].u;t[c]=g.used[j+1].v;newTerms.push(t)}}if(anchor){let t=[];t[a]=anchor;t[b]=g.used[0].u;t[c]=g.used[0].v;newTerms.push(t)}off+=g.ds.length}
    let removed=0;for(let i=0;i<r;i++){old[i][a]^=value(P.rows[i]);if(!old[i][a])removed++}
    let gain=removed-newTerms.length;bestGain=Math.max(bestGain,gain);if(gain===0)near++;
    if(gain>0){let out=old.filter(t=>t[a]).concat(newTerms);if(out.length!==r-gain||!verify(out))throw Error("outside-first verify");success={rank:out.length,terms:out.map(t=>t.map(String)),groups:groups.map(g=>({quotient:String(g.q),size:g.used.length,directions:g.ds.map(String)})),removed,added:newTerms.length,margin:P.margin};return}
   }
  }
  let singles=[];for(let g of families){let P=pattern([g]);singles.push({g,margin:P.margin,upper:P.upper});fit([g],P,32);if(success)break}
  if(!success){singles.sort((a,b)=>b.margin-a.margin||b.g.ds.length-a.g.ds.length);let pool=singles.slice(0,80).map(x=>x.g);for(let i=0;i<pool.length&&!success;i++)for(let j=0;j<i;j++){let x=pool[i],y=pool[j];if(x.q===y.q)continue;pairCount++;let P=pattern([x,y]);if(P)fit([x,y],P,48);if(success)break}
   for(let i=0;i<3000&&!success;i++){let x=families[rand(families.length)],y=families[rand(families.length)];if(x.q===y.q)continue;pairCount++;let P=pattern([x,y]);if(P)fit([x,y],P,32)}
  }
  reports.push({axis:a,tested,low,inside:atoms.length,groups:multi.length,families:families.length,attempts,upperScreens,fitTrials,pairCount,screenedByDim,maxOptimism,bestGain:bestGain===-99?null:bestGain,near,success});
  if(success)return {n,initial:r,best:success.rank,reports,terms:success.terms,verified:true}
 }
 return {n,initial:r,best:r,reports,terms:s.terms,verified:true}
}
const fs=require('node:fs'),path=require('node:path');const read=x=>JSON.parse(fs.readFileSync(path.join(__dirname,x),'utf8'));const n=Number(process.argv[2]||4);const s=n===3?{...read('mmg021_results.json').results.find(x=>x.n===3),n:3}:read('mmg012_results.json').find(x=>x.n===n);console.log(JSON.stringify(outsideFirst(s),null,2));
