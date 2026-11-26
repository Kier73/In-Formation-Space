function benchmark(seeds){
 const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
 const rng=s=>n=>{s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)%n};
 function naive(n){let a=[];for(let i=0;i<n;i++)for(let j=0;j<n;j++)for(let k=0;k<n;k++)a.push([1n<<BigInt(i*n+j),1n<<BigInt(j*n+k),1n<<BigInt(i*n+k)]);return a}
 const strassen=[[9,9,9],[12,1,12],[1,10,10],[8,5,5],[3,8,3],[5,3,8],[10,12,1]].map(t=>t.map(BigInt));
 function verify(t,n){let d=n*n,z=Array(d).fill(0n);for(let [a,b,c] of t){if(!a||!b||!c||[a,b,c].some(x=>x>>BigInt(d)))return false;let v=0n;for(let i of bits(a))v^=b<<BigInt(i*d);for(let k of bits(c))z[k]^=v}for(let i=0;i<n;i++)for(let k=0;k<n;k++){let v=0n;for(let j=0;j<n;j++)v^=1n<<BigInt((i*n+j)*d+j*n+k);if(z[i*n+k]!==v)return false}return true}
 function reduce(t){for(;;){let n=t.length;for(let a=0;a<3;a++){let b=(a+1)%3,c=(a+2)%3,m=new Map();for(let x of t){if(!x.every(Boolean))continue;let k=x[b]+":"+x[c];if(m.has(k))m.get(k)[a]^=x[a];else m.set(k,x.slice())}t=[...m.values()].filter(x=>x.every(Boolean))}if(t.length===n)return t}}
 function move(t,random,cap){let a=random(3),b=(a+1)%3,c=(a+2)%3,m=new Map();for(let i=0;i<t.length;i++){let k=t[i][a];if(!m.has(k))m.set(k,[]);m.get(k).push(i)}let groups=[...m.values()].filter(g=>g.length>1),i,j,plus=false;if(groups.length&&(t.length>=cap||random(100)<78)){let g=groups[random(groups.length)];i=g[random(g.length)];do{j=g[random(g.length)]}while(i===j)}else if(t.length<cap){i=random(t.length);do{j=random(t.length)}while(i===j);plus=t[i][a]!==t[j][a]}else return null;
 let x=t[i].slice(),y=t[j].slice(),u=x.slice(),v=y.slice(),out=t.map(x=>x.slice());if(plus){let w=x.slice();w[a]^=y[a];u[a]=y[a];out.push(w)}u[c]^=y[c];v[b]^=x[b];out[i]=u;out[j]=v;out=reduce(out);return out.length<=cap?out:null}
 function id(t){return t.map(x=>x.join(",")).sort().join(";")}
 function features(t){let f=new Set();for(let x of t)for(let a=0;a<3;a++)f.add(a+":"+x[(a+1)%3]+":"+x[(a+2)%3]);return f}
 function similarity(a,b){let k=0;for(let x of a)if(b.has(x))k++;return k/(a.size+b.size-k)}
 function candidate(t,root){let f=features(t);return {t,id:id(t),f,dist:1-similarity(f,root)}}
 function trial(n,start,reference,policy,seed,steps){let random=rng(seed),cap=start.length+4,root=features(start),best=start,archive=[candidate(start,root)],unique=new Set([archive[0].id]),events=[],hits={},attempts=0,admitted=0,rankDebt=0,meanDistance=0,maxDistance=0,atLeastReference=0;const W=6;
 if(!verify(start,n))throw Error("initial");
 for(let i=1;i<=steps;i++){let p=archive[random(archive.length)],t=move(p.t,random,cap);attempts++;if(!t)continue;let x=candidate(t,root);if(unique.has(x.id))continue;unique.add(x.id);
 if(t.length<best.length){if(!verify(t,n))throw Error("bad witness");best=t;events.push([i,t.length])}
 for(let target of [start.length-1,reference,reference-1])if(t.length<=target&&hits[target]===undefined)hits[target]=i;
 let pool=archive.concat(x);
 if(pool.length>W){
  if(policy==="eager"){pool.sort((a,b)=>a.t.length-b.t.length||b.dist-a.dist||a.id.localeCompare(b.id));pool.pop()}
  else{ // rank-independent max-min pair-space diversity; first anchor is newest, not lowest rank
   let chosen=[x],rest=pool.filter(z=>z!==x);
   while(chosen.length<W){let bestI=0,bestD=-1;for(let j=0;j<rest.length;j++){let d=Math.min(...chosen.map(q=>1-similarity(q.f,rest[j].f)));if(d>bestD){bestD=d;bestI=j}}chosen.push(rest.splice(bestI,1)[0])}pool=chosen;
  }
 }
 if(pool.includes(x)){admitted++;rankDebt+=Math.max(0,x.t.length-best.length);meanDistance+=x.dist;maxDistance=Math.max(maxDistance,x.dist)}
 archive=pool;
 if(i%1000===0){for(let q of archive)if(!verify(q.t,n))throw Error("archive invalid")}
 }
 if(!verify(best,n))throw Error("bad best");
 return {n,policy,seed,steps,initial:start.length,reference,cap,best:best.length,events,hits,unique:unique.size,admitted,meanDebt:rankDebt/Math.max(1,admitted),meanDistance:meanDistance/Math.max(1,admitted),maxDistance,terms:best.map(t=>t.map(String))}
 }
 let cases=[{n:2,t:naive(2),ref:7},{n:3,t:naive(3),ref:23},{n:4,t:seeds[0].terms.map(t=>t.map(BigInt)),ref:47}];
 let runs=[];for(let c of cases)for(let s=0;s<5;s++)for(let p of ["eager","lazy"])runs.push(trial(c.n,c.t,c.ref,p,20261124+100*c.n+s, c.n===4?4000:6000));
 return runs
}
const fs=require('node:fs'),path=require('node:path');console.log(JSON.stringify(benchmark(JSON.parse(fs.readFileSync(path.join(__dirname,'mmg012_results.json'),'utf8'))),null,2));
