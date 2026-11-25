function lift(s){
 const n=s.n,d=n*n,ts=s.terms.map(t=>t.map(BigInt)),r=ts.length;
 const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
 function parity(x){let q=0;while(x){x&=x-1n;q^=1}return q}
 function outer(a,b){let z=0n;for(let i of bits(a))z^=b<<BigInt(i*d);return z}
 function basis(){let m=new Map();return {m,reduce(x,t=0n){while(x){let p=x.toString(2).length-1,q=m.get(p);if(!q)break;x^=q[0];t^=q[1]}return [x,t]},add(x,t=0n){let [v,z]=this.reduce(x,t);if(!v)return false;m.set(v.toString(2).length-1,[v,z]);return true}}}
 function verify(t){let z=Array(d).fill(0n);for(let [a,b,c] of t){if(!a||!b||!c||[a,b,c].some(x=>x>>BigInt(d)))return false;let v=outer(a,b);for(let k of bits(c))z[k]^=v}for(let i=0;i<n;i++)for(let k=0;k<n;k++){let v=0n;for(let j=0;j<n;j++)v^=1n<<BigInt((i*n+j)*d+j*n+k);if(v!==z[i*n+k])return false}return true}
 let reports=[];
 if(!verify(ts))throw Error("seed");
 for(let axis=0;axis<3;axis++){
  let b=(axis+1)%3,c=(axis+2)%3,B=basis();for(let i=0;i<r;i++)B.add(outer(ts[i][b],ts[i][c]),1n<<BigInt(i));if(B.m.size!==r)throw Error("independence");
  let echelon=[...B.m].sort((x,y)=>y[0]-x[0]).map(([p,[v,t]])=>[1n<<BigInt(p),v,t]);
  function project(x){let t=0n;for(let [p,v,z] of echelon)if(x&p){x^=v;t^=z}return [x,t]}
  let groups=new Map(),inside=[],uniqueDiff=new Map(),pairs=0,maxGroup=0,atoms=0;
  for(let u=1n;u<1n<<BigInt(d);u++){let tab=Array.from({length:d},(_,j)=>project(outer(u,1n<<BigInt(j)))),q=0n,t=0n,v=0n;
   for(let j=1;j<2**d;j++){let p=31-Math.clz32(j&-j);q^=tab[p][0];t^=tab[p][1];v^=1n<<BigInt(p);let atom={u,v,t};atoms++;if(!q)inside.push(atom);else{let g=groups.get(q);if(!g){g=[];groups.set(q,g)}g.push(atom)}}
  }
  // All differences between two outside atoms sharing a nonzero quotient.
  for(let g of groups.values()){maxGroup=Math.max(maxGroup,g.length);for(let i=0;i<g.length;i++)for(let j=0;j<i;j++){pairs++;let h=g[i].t^g[j].t;if(h&&!uniqueDiff.has(h))uniqueDiff.set(h,[g[i],g[j]])}}
  const T=Array.from({length:d},(_,j)=>ts.reduce((v,x,i)=>v|(((x[axis]>>BigInt(j))&1n)<<BigInt(i)),0n));
  // Enumerate all dual constraints of support up to 4, then paired intersections.
  let rels=[],sum=new Map();for(let i=0;i<r;i++)for(let j=i+1;j<r;j++){let z=ts[i][axis]^ts[j][axis],m=(1n<<BigInt(i))|(1n<<BigInt(j));if(!z)rels.push(m);if(!sum.has(z))sum.set(z,[]);sum.get(z).push([i,j,m]);for(let k=j+1;k<r;k++)if(z===ts[k][axis])rels.push(m|(1n<<BigInt(k)))}
  for(let g of sum.values())for(let [i,j,m] of g)for(let [k,l,z] of g)if(j<k)rels.push(m|z);
  let checks=0,defOne=0,diffQueries=0,maxGain=0,success=null;
  const pass=rels.map(z=>inside.filter(a=>!parity(a.t&z)));
  for(let i=0;i<rels.length&&!success;i++)for(let j=0;j<i&&!success;j++){
   let z=rels[i],w=rels[j],K=basis(),sel=[];checks++;
   for(let a of pass[i])if(!parity(a.t&w)&&K.add(a.t,1n<<BigInt(sel.length)))sel.push(a);
   if(sel.length>r-3)continue;
   let missing=basis();for(let t of T)missing.add(K.reduce(t)[0]); // reduce may leave other pivot bits: use canonical projection below instead.
   let ec=[...K.m].sort((x,y)=>y[0]-x[0]).map(([p,[v]])=>[1n<<BigInt(p),v]);
   function rem(x){for(let [p,v] of ec)if(x&p)x^=v;return x}
   missing=basis();for(let t of T)missing.add(rem(t));
   if(missing.m.size!==1)continue;defOne++;let want=[...missing.m.values()][0][0];
   for(let [h,pair] of uniqueDiff){diffQueries++;if(parity(h&z)||parity(h&w)||rem(h)!==want)continue;
    let C=basis();for(let a of sel)C.add(a.t,1n<<BigInt(C.m.size));if(!C.add(h,1n<<BigInt(sel.length)))throw Error("bad difference");
    let cols=Array(sel.length+1).fill(0n);for(let k=0;k<d;k++){let [v,tag]=C.reduce(T[k]);if(v)throw Error("target missing");for(let l of bits(tag))cols[l]|=1n<<BigInt(k)}
    let out=[];function term(a,f){if(!f)return;let t=[];t[axis]=f;t[b]=a.u;t[c]=a.v;out.push(t)}
    sel.forEach((a,k)=>term(a,cols[k]));pair.forEach(a=>term(a,cols.at(-1)));if(out.length>=r||!verify(out))throw Error("invalid lift");
    success={rank:out.length,terms:out.map(x=>x.map(String)),axis,dual:[String(z),String(w)],insideUsed:sel.length,difference:String(h),outside:pair.map(a=>[String(a.u),String(a.v)])};break;
   }
  }
  reports.push({axis,atoms,inside:inside.length,nonzeroCosets:groups.size,maxGroup,pairs,uniqueDifferences:uniqueDiff.size,relations:rels.length,checks,defOne,diffQueries,success});
  if(success)return {initial:r,best:success.rank,reports,verified:true,terms:success.terms};
 }
 return {initial:r,best:r,reports,verified:true,terms:s.terms}
}
const fs=require('node:fs'),path=require('node:path');const s=JSON.parse(fs.readFileSync(path.join(__dirname,'mmg021_results.json'),'utf8')).results.find(x=>x.n===3);console.log(JSON.stringify(lift(s),null,2));
