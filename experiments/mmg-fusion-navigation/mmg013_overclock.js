function overclock(seeds){
 const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
 const randgen=s=>n=>{s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)%n};
 const outer=(a,b,d)=>{let z=0n;for(let i of bits(a))z^=b<<BigInt(i*d);return z};
 const mk=()=>new Map();
 function reduce(B,x,tag=0n){while(x){let p=x.toString(2).length-1,v=B.get(p);if(!v)break;x^=v[0];tag^=v[1]}return [x,tag]}
 function add(B,x,tag=0n){let [v,t]=reduce(B,x,tag);if(!v)return false;B.set(v.toString(2).length-1,[v,t]);return true}
 function projector(B){let a=[...B].sort((x,y)=>y[0]-x[0]).map(([i,[v]])=>[1n<<BigInt(i),v]);return x=>{for(let [mask,v] of a)if(x&mask)x^=v;return x}}
 function slices(n,a){let d=n*n,out=Array(d).fill(0n);for(let i=0;i<n;i++)for(let j=0;j<n;j++)for(let k=0;k<n;k++){let v=[i*n+j,j*n+k,i*n+k];out[v[a]]^=1n<<BigInt(v[(a+1)%3]*d+v[(a+2)%3])}return out}
 function verify(ts,n){let d=n*n,out=Array(d).fill(0n);for(let [a,b,c] of ts){if(!a||!b||!c||[a,b,c].some(x=>x>>BigInt(d)))return false;let v=outer(a,b,d);for(let j of bits(c))out[j]^=v}return out.every((v,i)=>v===slices(n,2)[i])}
 function frame(ts,n,a,keep){let d=n*n,b=(a+1)%3,c=(a+2)%3,K=mk(),pairs=[];for(let i of keep){let x=[ts[i][b],ts[i][c]];if(add(K,outer(...x,d)))pairs.push(x)}let P=projector(K),D=mk(),target=slices(n,a);for(let v of target)add(D,P(v));return {a,b,c,d,pairs,P,D,target,floor:pairs.length+D.size}}
 function choose(n,k,r){let xs=Array.from({length:n},(_,i)=>i);for(let i=0;i<k;i++){let j=i+r(n-i);[xs[i],xs[j]]=[xs[j],xs[i]]}return xs.slice(0,k)}
 function realize(F,atoms,n){let pairs=F.pairs.concat(atoms),B=mk(),keep=[];for(let x of pairs){let i=keep.length;if(add(B,outer(...x,F.d),1n<<BigInt(i)))keep.push(x)}let cols=Array(keep.length).fill(0n);for(let j=0;j<F.target.length;j++){let [v,t]=reduce(B,F.target[j]);if(v)return null;for(let i of bits(t))cols[i]|=1n<<BigInt(j)}let out=[];for(let i=0;i<keep.length;i++)if(cols[i]){let t=[];t[F.a]=cols[i];t[F.b]=keep[i][0];t[F.c]=keep[i][1];out.push(t)}if(!verify(out,n))throw Error("formal repair");return out}
 function search(F,ts,n,budget,random){let Q=projector(F.D),inside=mk(),atoms=[],groups=new Map(),queries=0;let left=[...new Set(ts.map(x=>x[F.b]))],right=[...new Set(ts.map(x=>x[F.c]))];for(let i=0;i<F.d;i++){let x=1n<<BigInt(i);if(!left.includes(x))left.push(x);if(!right.includes(x))right.push(x)}
 for(let i=0;i<32;i++){let x=left[random(left.length)]^left[random(left.length)],y=right[random(right.length)]^right[random(right.length)];if(x&&!left.includes(x))left.push(x);if(y&&!right.includes(y))right.push(y)}
 for(let x of left)for(let y of right){queries++;let v=F.P(outer(x,y,F.d));if(!v)continue;let c=Q(v);if(!c){if(add(inside,v))atoms.push([x,y]);continue}let g=groups.get(c);if(!g){g=[];groups.set(c,g)}g.push({v,p:[x,y]})}
 let direct=inside.size,remaining=F.D.size-direct,largest=0,best=null;
 if(!remaining)best=realize(F,atoms,n);
 if(!best&&F.floor+1<=budget){for(let g of groups.values()){if(g.length<2)continue;let B=new Map(inside),used=[],anchor=g[0];for(let x of g.slice(1)){let v=x.v^anchor.v;if(add(B,v))used.push(x.p);if(B.size===F.D.size)break}largest=Math.max(largest,B.size-direct);if(B.size===F.D.size){let r=realize(F,atoms.concat(anchor.p,used),n);if(r&&r.length<=budget&&(!best||r.length<best.length))best=r}}}
 return {queries,direct,remaining,largest,groups:groups.size,best};
 }
 return seeds.map(s=>{let n=s.n,ts=s.terms.map(t=>t.map(BigInt)),r=ts.length,rand=randgen(4913+n);if(!verify(ts,n))throw Error("seed");
 let screens=[];for(let k of [...new Set([0,Math.max(1,s.strict_target-n*n),s.strict_target,Math.floor(r/2),r-8,r-4])].sort((a,b)=>a-b)){let floors=[];for(let i=0;i<30;i++){let F=frame(ts,n,i%3,choose(r,k,rand));floors.push(F.floor)}screens.push({retained:k,min:Math.min(...floors),max:Math.max(...floors),targetEligible:floors.filter(x=>x<=s.strict_target).length,samples:30})}
 let controls={calls:0,eligible:0,queries:0,insideComplete:0,cosetComplete:0,near:0,maxCosetGain:0,improvements:[],lowestFloor:r};let best=ts;
 for(let i=0;i<48;i++){let keep=choose(r,Math.max(0,r-n*n-2-(i%3)*3),rand),F=frame(ts,n,i%3,keep);controls.calls++;controls.lowestFloor=Math.min(controls.lowestFloor,F.floor);if(F.floor>r-1)continue;controls.eligible++;let z=search(F,ts,n,r-1,rand);controls.queries+=z.queries;controls.maxCosetGain=Math.max(controls.maxCosetGain,z.largest);if(z.remaining===0)controls.insideComplete++;else if(z.best)controls.cosetComplete++;if(z.largest>0)controls.near++;if(z.best&&z.best.length<best.length){best=z.best;controls.improvements.push({trial:i,rank:best.length})}}
 // Synthetic nonzero-coset control: F2^2, target span (1,0) from atoms (0,1),(1,1).
 let D=mk();add(D,1n);let Q=projector(D);if(Q(2n)!==Q(3n)||Q(2n)===0n||reduce(D,2n^3n)[0])throw Error("coset control");
 return {n,rank:r,target:s.strict_target,output_floor:n*n,screens,coset:controls,best:best.length,verified:verify(best,n),synthetic_coset_control:true,terms:best.map(t=>t.map(String))}
 })
}
const fs=require('node:fs'),path=require('node:path');console.log(JSON.stringify(overclock(JSON.parse(fs.readFileSync(path.join(__dirname,'mmg012_results.json'),'utf8'))),null,2));
