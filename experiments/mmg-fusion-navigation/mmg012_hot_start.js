function hotStart(sources){
 const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
 const randgen=s=>n=>{s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)%n};
 const outer=(a,b,d)=>{let z=0n;for(let i of bits(a))z^=b<<BigInt(i*d);return z};
 const transpose=(x,n)=>bits(x).reduce((v,i)=>v|(1n<<BigInt((i%n)*n+Math.floor(i/n))),0n);
 function parse(s,n){return s.trim().split(/\r?\n/).filter(x=>x.trim()).map(line=>{let g=[...line.matchAll(/\(([^()]*)\)/g)];if(g.length!==3)throw Error("parse "+line);return g.map((m,a)=>{let v=0n;for(let t of m[1].matchAll(/([abc])(\d)(\d)/g)){if(t[1]!=="abc"[a])throw Error("leg");v^=1n<<BigInt((Number(t[2])-1)*n+Number(t[3])-1)}if(!v)throw Error("zero");return v})})}
 function slices(n,axis){let d=n*n,rows=Array(d).fill(0n);for(let i=0;i<n;i++)for(let j=0;j<n;j++)for(let k=0;k<n;k++){let q=[i*n+j,j*n+k,i*n+k];rows[q[axis]]^=1n<<BigInt(q[(axis+1)%3]*d+q[(axis+2)%3])}return rows}
 function verify(t,n){let d=n*n,z=Array(d).fill(0n);for(let [a,b,c] of t){if(!a||!b||!c||[a,b,c].some(x=>x>>BigInt(d)))return false;let q=outer(a,b,d);for(let i of bits(c))z[i]^=q}return z.every((v,i)=>v===slices(n,2)[i])}
 function basis(){let m=new Map();return {m,reduce(x,tag=0n){while(x){let p=x.toString(2).length-1,q=m.get(p);if(!q)break;x^=q[0];tag^=q[1]}return [x,tag]},add(x,tag=0n){let [v,t]=this.reduce(x,tag);if(!v)return false;m.set(v.toString(2).length-1,[v,t]);return true}}}
 // canonical quotient remainder must eliminate all pivots, not only the leading one.
 function project(b,x){for(let [p,q] of [...b.m].sort((a,b)=>b[0]-a[0]))if((x>>BigInt(p))&1n)x^=q[0];return x}
 function repair(t,n,axis,drop,random,mode){let d=n*n,b=(axis+1)%3,c=(axis+2)%3,keep=t.filter((_,i)=>!drop.has(i)).map(x=>[x[b],x[c]]),old=t.filter((_,i)=>drop.has(i));let K=basis();let pairs=[];for(let x of keep)if(K.add(outer(...x,d)))pairs.push(x);let target=slices(n,axis),def=basis(),rs=target.map(v=>project(K,v));for(let v of rs)def.add(v);let deficit=def.m.size;
 let C=basis(),newPairs=[],queries=0,eligible=0;
 let left=[...new Set(t.map(x=>x[b]))],right=[...new Set(t.map(x=>x[c]))];
 // Search in an incumbent-independent dictionary of local basis vectors as well.
 for(let j=0;j<d;j++){let x=1n<<BigInt(j);if(!left.includes(x))left.push(x);if(!right.includes(x))right.push(x)}
 if(mode==="expanded"){for(let j=0;j<24;j++){let a=left[random(left.length)]^left[random(left.length)],b=right[random(right.length)]^right[random(right.length)];if(a&&!left.includes(a))left.push(a);if(b&&!right.includes(b))right.push(b)}}
 let all=[];for(let x of left)for(let y of right)all.push([x,y]);
 for(let i=all.length-1;i>0;i--){let j=random(i+1);[all[i],all[j]]=[all[j],all[i]]}
 // exact residual membership: only atoms in deficit subspace can be a minimal completion.
 for(let x of all){if(C.m.size===deficit)break;queries++;let v=project(K,outer(...x,d));if(!v||def.reduce(v)[0])continue;eligible++;if(C.add(v))newPairs.push(x)}
 let novelty=newPairs.filter(x=>!old.some(t=>t[b]===x[0]&&t[c]===x[1])).length;
 let preFallback=C.m.size; // complete using original atoms where they lie inside residual; may not suffice.
 for(let x of old){if(C.m.size===deficit)break;let y=[x[b],x[c]],v=project(K,outer(...y,d));if(v&&!def.reduce(v)[0]&&C.add(v))newPairs.push(y)}
 if(C.m.size!==deficit)return {status:"incomplete",deficit,queries,eligible,preFallback,novelty};
 pairs.push(...newPairs);let B=basis();for(let i=0;i<pairs.length;i++)if(!B.add(outer(...pairs[i],d),1n<<BigInt(i)))throw Error("nonindependent");
 let cols=Array(pairs.length).fill(0n);for(let j=0;j<target.length;j++){let [v,tag]=B.reduce(target[j]);if(v)throw Error("unspanned target");for(let i of bits(tag))cols[i]|=1n<<BigInt(j)}
 let out=[];for(let i=0;i<pairs.length;i++)if(cols[i]){let z=[];z[axis]=cols[i];z[b]=pairs[i][0];z[c]=pairs[i][1];out.push(z)}if(!verify(out,n))throw Error("repair wrong");
 return {status:"complete",deficit,queries,eligible,preFallback,novelty,out};
 }
 function run(s){let n=s.n,raw=parse(s.content,n);let ts=verify(raw,n)?raw:raw.map(([a,b,c])=>[a,b,transpose(c,n)]);if(!verify(ts,n))throw Error("seed identity "+n);let initial=ts.length,best=ts.map(t=>t.slice()),random=randgen(20261124+n),cur=best,stats={attempts:0,complete:0,incomplete:0,novel:0,queries:0,eligible:0,removedDebt:0,maxDrop:0,improvements:[],deficits:{},completeNovel:0};
 let target=0;while(BigInt(target+1)**4n<BigInt(n)**9n)target++;
 // Strictly rank-decreasing admissions, equal-rank changes allowed for exploration.
 for(let i=0;i<120;i++){if(i%12===0)cur=best.map(t=>t.slice());let axis=random(3),sizes=[2,3,4,6,8,Math.min(n*n+2,cur.length-1)],q=sizes[i%sizes.length];let drop=new Set();while(drop.size<q)drop.add(random(cur.length));let r=repair(cur,n,axis,drop,random,i%2?"expanded":"base");stats.attempts++;stats.queries+=r.queries;stats.eligible+=r.eligible;stats.maxDrop=Math.max(stats.maxDrop,q);stats.removedDebt+=q;let key=q+":"+r.deficit;stats.deficits[key]=(stats.deficits[key]||0)+1;if(r.status==="incomplete"){stats.incomplete++;continue}stats.complete++;if(r.novelty){stats.novel++;stats.completeNovel+=r.novelty}if(r.out.length<=cur.length){cur=r.out;if(cur.length<best.length){best=cur.map(t=>t.slice());stats.improvements.push({attempt:i,rank:best.length})}}}
 let bad=best.map(t=>t.slice());bad[0][0]^=1n;if(verify(bad,n))throw Error("tamper accepted");return {n,source:s.path,source_sha:s.sha,initial,best:best.length,strict_target:target,quadratic_target:n*n,...stats,verified:verify(best,n),terms:best.map(t=>t.map(String))};
 }
 return sources.map(run)
}
const fs=require('node:fs');const path=require('node:path');
console.log(JSON.stringify(hotStart(JSON.parse(fs.readFileSync(path.join(__dirname,'mmg012_seeds.json'),'utf8'))),null,2));
