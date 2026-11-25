function adaptive(data){
const rng=s=>n=>{s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)%n};
function run(c,policy,seed){
 let n=c.n,d=n*n,random=rng(seed),start=c.terms.map(t=>t.map(BigInt)),r0=start.length,cap=r0+c.debt,budget=c.budget,used=0,ledger={},STOP={},attempts=0,events=[],phases=[],committed=0,fitSteps=0,exploreSteps=0,compressionCalls=0,compressionHits=0;
 function tick(kind,k=1){if(used+k>budget)throw STOP;used+=k;ledger[kind]=(ledger[kind]||0)+k}
 function bits(x){let a=[];for(let i=0;x;x>>=1n,i++){tick("bit");if(x&1n)a.push(i)}return a}
 function outer(a,b){let z=0n;for(let i of bits(a)){tick("xor");z^=b<<BigInt(i*d)}return z}
 function verify(ts){let z=Array(d).fill(0n);for(let [a,b,c] of ts){tick("verify");if(!a||!b||!c||[a,b,c].some(x=>x>>BigInt(d)))return false;let v=outer(a,b);for(let k of bits(c)){tick("xor");z[k]^=v}}for(let i=0;i<n;i++)for(let k=0;k<n;k++){let v=0n;for(let j=0;j<n;j++){tick("verify");v^=1n<<BigInt((i*n+j)*d+j*n+k)}if(z[i*n+k]!==v)return false}return true}
 function normalize(t){for(;;){let old=t.length;for(let a=0;a<3;a++){let b=(a+1)%3,c=(a+2)%3,m=new Map();for(let x of t){tick("term");if(!x.every(Boolean))continue;let k=x[b]+":"+x[c];tick("map",2);if(m.has(k))m.get(k)[a]^=x[a];else m.set(k,x.slice())}t=[...m.values()].filter(x=>x.every(Boolean));tick("term",m.size)}if(t.length===old)return t}}
 function mutate(t){let a=random(3),b=(a+1)%3,c=(a+2)%3,m=new Map();for(let i=0;i<t.length;i++){tick("term");let k=t[i][a];tick("map",3);if(!m.has(k))m.set(k,[]);m.get(k).push(i)}let g=[...m.values()].filter(x=>x.length>1);tick("term",m.size);let i,j;if(g.length&&(t.length>=cap||random(100)<75)){let p=g[random(g.length)];i=p[random(p.length)];j=p[random(p.length-1)];if(i===j)j=p[p.length-1]}else if(t.length<cap){i=random(t.length);j=random(t.length-1);if(j>=i)j++}else return null;
 let u=t[i].slice(),v=t[j].slice(),out=t.map(x=>x.slice());tick("term",out.length);if(u[a]!==v[a]){let w=u.slice();w[a]^=v[a];u[a]=v[a];out.push(w)}u[c]^=v[c];v[b]^=t[i][b];out[i]=u;out[j]=v;out=normalize(out);return out.length<=cap?out:null}
 function candidate(t){tick("term",3*t.length);let forms=t.map(x=>x.join(","));forms.sort((a,b)=>{tick("compare");return a<b?-1:a>b?1:0});let f=new Set();let potential=0;for(let a=0;a<3;a++){let m=new Map();for(let x of t){tick("map",4);let key=x[a];potential+=m.get(key)||0;m.set(key,(m.get(key)||0)+1);f.add(a+":"+x[(a+1)%3]+":"+x[(a+2)%3])}}return {t,id:forms.join(";"),f,potential}}
 const distances=new WeakMap();
 function dist(a,b){if(a===b)return 0;tick("map",2);let row=distances.get(a);if(row?.has(b))return row.get(b);let k=0;for(let x of a.f){tick("map");if(b.f.has(x))k++}let v=1-k/(a.f.size+b.f.size-k);if(!row){row=new WeakMap();distances.set(a,row)}row.set(b,v);let rev=distances.get(b);if(!rev){rev=new WeakMap();distances.set(b,rev)}rev.set(a,v);tick("map",4);return v}
 // Exact dependence compression: arbitrary linear relation among pair atoms, not just duplicate pairs.
 function quotient(t,a){let b=(a+1)%3,c=(a+2)%3,M=new Map(),out=[];for(let x of t){let v=outer(x[b],x[c]),tag=0n;while(v){tick("pivot");let p=v.toString(2).length-1,q=M.get(p);if(!q){M.set(p,[v,tag^(1n<<BigInt(out.length))]);out.push(x.slice());break}v^=q[0];tag^=q[1]}if(!v){for(let i of bits(tag)){tick("xor");out[i][a]^=x[a]}}}tick("term",out.length);return out.filter(x=>x.every(Boolean))}
 let best=start,root=candidate(start),archive=[root],seen=new Set([root.id]),phase=policy==="eager"?"fit":"explore",age=0,window=[],baseBest=r0;
 function change(p){if(p===phase)return;phase=p;age=0;window=[];baseBest=best.length;phases.push({attempts,work:used,phase});if(p==="fit"){let q=candidate(best);if(!archive.some(x=>x.id===q.id))archive.push(q);archive.sort((a,b)=>{tick("compare");return a.t.length-b.t.length||b.potential-a.potential});archive=archive.slice(0,6)}}
 function admit(t){if(t.length<best.length){if(!verify(t))throw Error("invalid");best=t;events.push({attempts,work:used,rank:t.length})}}
 try{
 if(!verify(start))throw Error("bad seed");
 while(used<budget){
  attempts++;age++;tick("proposal");
  if(policy==="periodic"){if(phase==="explore"&&age>=128)change("fit");else if(phase==="fit"&&age>=64)change("explore")}
  if(policy==="adaptive"){let novelty=window.length?window.reduce((s,x)=>s+x.n,0)/window.length:1,opp=window.length?window.reduce((s,x)=>s+x.p,0)/window.length:0;tick("controller",window.length*2+1);
   if(phase==="explore"&&age>=24&&(novelty<0.55||opp>0.6||age>=192))change("fit");
   else if(phase==="fit"&&age>=24&&(best.length<baseBest||age>=96))change("explore");
  }
  if(phase==="fit")fitSteps++;else exploreSteps++;
  let p=archive[random(archive.length)],t=mutate(p.t),novel=0,potential=0;
  if(t){admit(t);
   // Same compression opportunity offered to every policy every 16 fitting proposals.
   if(phase==="fit"&&age%16===0){compressionCalls++;let q=t;for(let a=0;a<3;a++)q=quotient(q,a);if(q.length<t.length){compressionHits++;if(!verify(q))throw Error("bad quotient");t=q;admit(t)}}
   let x=candidate(t);potential=+(x.potential>p.potential);tick("map");if(!seen.has(x.id)){tick("map");seen.add(x.id);novel=1;let pool=archive.concat(x);
    if(pool.length>6){if(phase==="fit"){pool.sort((a,b)=>{tick("compare");return a.t.length-b.t.length||b.potential-a.potential||a.id.localeCompare(b.id)});pool.pop()}
    else{let choose=[x],rest=pool.filter(y=>y!==x);while(choose.length<6){let k=0,v=-1;for(let j=0;j<rest.length;j++){let q=1;for(let y of choose){tick("compare");q=Math.min(q,dist(y,rest[j]))}if(q>v){k=j;v=q}}choose.push(rest.splice(k,1)[0])}pool=choose}}
    archive=pool;committed++;
   }
  }
  window.push({n:novel,p:potential});if(window.length>32)window.shift();tick("controller");
 }
 }catch(e){if(e!==STOP)throw e}
 return {label:c.label,n,policy,seed,initial:r0,best:best.length,cap,budget,used,ledger,attempts,committed,fitSteps,exploreSteps,compressionCalls,compressionHits,phaseChanges:phases.length,events,terms:best.map(t=>t.map(String))}
}
let cases=[{label:"barrier8",n:2,terms:data.barrier.found.ground,debt:1,budget:2500000,reps:5},{label:"rank24",n:3,terms:data.closed.results.find(x=>x.n===3).terms,debt:4,budget:4000000,reps:5},...data.hot.map(x=>({label:"rank"+x.best,n:x.n,terms:x.terms,debt:4,budget:4000000,reps:3}))];
let results=[];for(let c of cases)for(let i=0;i<c.reps;i++)for(let p of ["eager","periodic","adaptive"])results.push(run(c,p,20261125+c.n*100+i));return results
}
const fs=require('node:fs'),path=require('node:path');const read=x=>JSON.parse(fs.readFileSync(path.join(__dirname,x),'utf8'));console.log(JSON.stringify(adaptive({closed:read('mmg021_results.json'),barrier:read('mmg016_results.json'),hot:read('mmg012_results.json')}),null,2));
