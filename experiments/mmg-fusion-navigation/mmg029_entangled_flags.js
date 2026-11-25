function entangled(data){
 const bits=x=>{let a=[];for(let i=0;x;x>>>=1,i++)if(x&1)a.push(i);return a};
 const rng=s=>n=>{s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)%n};
 function run(n,seed,order,policy,seedNum){
  const d=n*n,mask=(1n<<BigInt(d))-1n,rand=rng(seedNum),ts=seed.map(t=>t.map(BigInt));let rankTests=0,verified=0,queries=[],records=[],branches=0;
  function outer(a,b){let v=0n;for(let i of bits(a))v^=BigInt(b)<<BigInt(i*d);return v}
  function target(q){let t=0n;for(let e of bits(q)){let i=Math.floor(e/n),k=e%n;for(let j=0;j<n;j++)t^=1n<<BigInt((i*n+j)*d+j*n+k)}return t}
  // Store reduced row as basis vector; its coordinate tag is a unit vector.
  function fac(v,only=false){let piv=new Int32Array(d),idx=new Int32Array(d),L=[],R=[];for(let i=0;i<d;i++){let x=Number(v&mask),t=0;v>>=BigInt(d);while(x){let j=31-Math.clz32(x);if(!piv[j]){piv[j]=x;idx[j]=1<<R.length;L.push(0);R.push(x);t^=idx[j];break}x^=piv[j];t^=idx[j]}if(!only)for(let k of bits(t))L[k]|=1<<i}return only?R.length:L.map((a,i)=>[a,R[i]])}
  function rank(v){rankTests++;return fac(v,true)}
  function basis(atoms){let m=new Map();for(let i=0;i<atoms.length;i++){let v=outer(...atoms[i]),tag=1n<<BigInt(i);while(v){let p=v.toString(2).length-1,q=m.get(p);if(!q){m.set(p,[v,tag]);break}v^=q[0];tag^=q[1]}}return {m,solve(v){let tag=0n;while(v){let p=v.toString(2).length-1,q=m.get(p);if(!q)return null;v^=q[0];tag^=q[1]}return tag}}}
  function realize(atoms,Q){let B=basis(atoms),c=Array(atoms.length).fill(0n);for(let j=0;j<Q.length;j++){let tag=B.solve(target(Q[j]));if(tag===null)throw Error("missing");for(let i=0;i<atoms.length;i++)if(tag>>BigInt(i)&1n)c[i]|=1n<<BigInt(j)}
   let out=atoms.map(([a,b],i)=>[BigInt(a),BigInt(b),c[i]]).filter(t=>t[2]);let z=Array(Q.length).fill(0n);for(let [a,b,c] of out){let p=outer(Number(a),Number(b));for(let j=0;j<Q.length;j++)if(c>>BigInt(j)&1n)z[j]^=p}for(let j=0;j<Q.length;j++)if(z[j]!==target(Q[j]))throw Error("verify");verified++;return out}
  function key(atoms){return atoms.map(t=>t.join(":")).sort().join(";")}
  function unique(atoms){let m=new Map;for(let x of atoms)m.set(x.join(":"),x);return [...m.values()]}
  function addResidual(atoms,q,variant){
   let T=target(q),values=atoms.map(x=>outer(...x)),r=atoms.length;
   if(basis(atoms).solve(T)!==null)return {atoms,added:0,used:0};
   let v=T,best=rank(T),chosen=0n;
   if(r<=10){let p=T,prev=0n;for(let i=1;i<2**r;i++){let bit=31-Math.clz32(i&-i);p^=values[bit];prev^=1n<<BigInt(bit);let k=rank(p);if(k<best||k===best&&variant&&rand(8)===0){best=k;v=p;chosen=prev}}}
   else{
    let starts=variant?3:1;for(let restart=0;restart<starts;restart++){let p=T,sel=0n;if(restart)for(let j=0;j<r;j++)if(rand(5)===0){p^=values[j];sel^=1n<<BigInt(j)}
     let k=rank(p);for(let pass=0;pass<4;pass++){let move=null,low=k;for(let i=0;i<r;i++){let w=p^values[i],h=rank(w);if(h<low){low=h;move=[i]}}
      if(!move&&variant){for(let j=0;j<Math.min(80,r*r);j++){let a=rand(r),b=rand(r);if(a===b)continue;let h=rank(p^values[a]^values[b]);if(h<low){low=h;move=[a,b]}}}
      if(!move)break;for(let i of move){p^=values[i];sel^=1n<<BigInt(i)}k=low;
     }
     if(k<best||k===best&&variant&&rand(2)){best=k;v=p;chosen=sel}
    }
   }
   let f=fac(v);if(f.length!==best)throw Error("rank factor");
   if(variant&&f.length>1)for(let j=0;j<4*f.length;j++){let a=rand(f.length),b=rand(f.length);if(a===b)continue;f[a][0]^=f[b][0];f[b][1]^=f[a][1]}
   let w=0n;for(let p of f)w^=outer(...p);if(w!==v)throw Error("factor change");
   let out=unique(atoms.concat(f)),used=0;for(let i=0;i<r;i++)if(chosen>>BigInt(i)&1n)used++;
   return {atoms:out,added:out.length-atoms.length,used}
  }
  function incumbent(Q){return unique(ts.filter(t=>Q.some(q=>{let x=t[2]&BigInt(q),p=0;while(x){x&=x-1n;p^=1}return p})).map(t=>[Number(t[0]),Number(t[1])]))}
  let archive=[{atoms:[],route:[]}];
  for(let k=0;k<order.length;k++){let q=order[k];queries.push(q);let cand=[];
   for(let prev of archive)for(let v=0;v<(policy==="canonical"?1:3);v++){let z=addResidual(prev.atoms,q,v);branches++;let out=realize(z.atoms,queries);cand.push({atoms:z.atoms,rank:out.length,route:prev.route.concat({added:z.added,used:z.used,source:"carry"}),terms:out})}
   if(policy==="hybrid"){let atoms=incumbent(queries),out=realize(atoms,queries);cand.push({atoms,rank:out.length,route:[{source:"incumbent-reset",depth:k+1}],terms:out});branches++}
   cand.sort((a,b)=>a.rank-b.rank||a.atoms.length-b.atoms.length);let next=[],seen=new Set();for(let x of cand){let id=key(x.atoms);if(seen.has(id))continue;seen.add(id);next.push(x);if(next.length===(policy==="canonical"?1:4))break}archive=next;
   let best=archive[0];records.push({depth:k+1,query:q,rank:best.rank,atoms:best.atoms.length,route:best.route,incumbentRank:incumbent(queries).length,archive:archive.length});
  }
  let best=archive[0],out=realize(best.atoms,queries);
  let Q=new Map();for(let j=0;j<d;j++){let x=queries[j],tag=1n<<BigInt(j);while(x){let p=31-Math.clz32(x),v=Q.get(p);if(!v){Q.set(p,[x,tag]);break}x^=v[0];tag^=v[1]}}if(Q.size!==d)throw Error("not full basis");
  let raw=out.map(([a,b,c])=>{let z=0n;for(let j=0;j<d;j++){let x=1<<j,tag=0n;while(x){let p=31-Math.clz32(x),v=Q.get(p);x^=v[0];tag^=v[1]}let p=tag&c,t=0;while(p){p&=p-1n;t^=1}if(t)z|=1n<<BigInt(j)}return [a,b,z]});
  let dense=Array(d).fill(0n);for(let [a,b,c] of raw)for(let j=0;j<d;j++)if(c>>BigInt(j)&1n)dense[j]^=outer(Number(a),Number(b));for(let j=0;j<d;j++)if(dense[j]!==target(1<<j))throw Error("dense identity");
  return {n,policy,seed:seedNum,initialFloor:n,finalRank:raw.length,integrated:records.reduce((a,x)=>a+x.rank,0),rankTests,verified,branches,records,terms:raw.map(t=>t.map(String))}
 }
 function qouter(u,v,n){let q=0;for(let i of bits(u))q|=v<<(i*n);return q}
 function parity(x){let p=0;while(x){x&=x-1;p^=1}return p}
 function flag(n,seed,mode){let d=n*n,forms=[];for(let u=1;u<1<<n;u++)for(let v=1;v<1<<n;v++)forms.push(qouter(u,v,n));let rand=rng(seed),H=0;for(let i=0;i<n;i++)H|=1<<(i*n+i);let chosen=[],piv=new Map();
 function add(x){let q=x;while(q){let j=31-Math.clz32(q);if(!piv.has(j)){piv.set(j,q);chosen.push(x);return true}q^=piv.get(j)}return false}
 let candidates=mode==="trace"?forms.filter(q=>!parity(q&H)):forms.slice();
 for(let i=candidates.length-1;i>0;i--){let j=rand(i+1);[candidates[i],candidates[j]]=[candidates[j],candidates[i]]}
 for(let q of candidates)add(q);
 if(mode==="trace"){if(chosen.length!==d-1)throw Error("trace span");for(let q of forms)if(parity(q&H)&&add(q))break}
 if(chosen.length!==d)throw Error("basis");let sep=chosen.map((q,i)=>forms.filter(z=>parity(z&q)&&chosen.slice(0,i).every(x=>!parity(x&z))).length);return {chosen,sep}
 }
 let results=[];for(let n of [3,4]){let seed=n===3?data.closed.results.find(x=>x.n===3).terms:data.hot.find(x=>x.n===4).terms;for(let mode of ["random","trace"])for(let i=0;i<6;i++){let f=flag(n,20261900+n*100+i,mode);let r=run(n,seed,f.chosen,"adaptive",20262000+n*100+i);results.push({...r,mode,queryOrder:f.chosen,separators:f.sep})}}return results
}
const fs=require('node:fs'),path=require('node:path');const read=x=>JSON.parse(fs.readFileSync(path.join(__dirname,x),'utf8'));console.log(JSON.stringify(entangled({closed:read('mmg021_results.json'),hot:read('mmg012_results.json')}),null,2));
