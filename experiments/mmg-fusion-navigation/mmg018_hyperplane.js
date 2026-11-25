function experiment(data){
const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
function outer(a,b,d){let v=0n;for(let i of bits(a))v^=b<<BigInt(i*d);return v}
function factor(v,d){let b=0n,a=0n,m=(1n<<BigInt(d))-1n;for(let i=0;i<d;i++){let row=v&m;v>>=BigInt(d);if(row){if(b&&row!==b)return null;b=row;a|=1n<<BigInt(i)}}return a?[a,b]:null}
function verify(ts,n){let d=n*n,rows=Array(d).fill(0n);for(let [a,b,c] of ts){if(!a||!b||!c||[a,b,c].some(x=>x>>BigInt(d)))return false;let v=outer(a,b,d);for(let k of bits(c))rows[k]^=v}for(let i=0;i<n;i++)for(let k=0;k<n;k++){let v=0n;for(let j=0;j<n;j++)v^=1n<<BigInt((i*n+j)*d+j*n+k);if(v!==rows[i*n+k])return false}return true}
function basis(){let m=new Map();return {m,reduce(x,t=0n){while(x){let p=x.toString(2).length-1,q=m.get(p);if(!q)break;x^=q[0];t^=q[1]}return [x,t]},add(x,t=0n){let [v,z]=this.reduce(x,t);if(!v)return false;m.set(v.toString(2).length-1,[v,z]);return true}}}
function one(ts,n,a){
 const b=(a+1)%3,c=(a+2)%3,r=ts.length,d=n*n,vs=ts.map(t=>outer(t[b],t[c],d)),ind=basis();
 for(let v of vs)ind.add(v);
 if(ind.m.size!==r)return {axis:a,dependent:true,rank:ind.m.size};
 let atoms=[],index=Array.from({length:r},()=>[]),tested=0,relations=[],rel2=0,rel3=0,rel4=0;
 function add(idx,v){tested++;let p=factor(v,d);if(!p)return;let o={idx,p,mask:idx.reduce((x,i)=>x|(1n<<BigInt(i)),0n)};for(let i of idx)index[i].push(o);atoms.push(o)}
 let pairs=new Map();
 for(let i=0;i<r;i++)for(let j=i+1;j<r;j++){let x=ts[i][a]^ts[j][a];if(!x){relations.push([i,j]);rel2++}if(!pairs.has(x))pairs.set(x,[]);pairs.get(x).push([i,j]);add([i,j],vs[i]^vs[j]);for(let k=j+1;k<r;k++){if((x^ts[k][a])===0n){relations.push([i,j,k]);rel3++}add([i,j,k],vs[i]^vs[j]^vs[k])}}
 for(let v of pairs.values())for(let [i,j] of v)for(let [k,l] of v){if(j<k){relations.push([i,j,k,l]);rel4++}}
 let queries=0,maxGain=0,near=0;
 for(let rel of relations){let w=rel.length,R=new Map(rel.map((i,j)=>[i,j])),pool=new Set(rel.flatMap(i=>index[i])),B=basis(),selected=[];
 for(let o of pool){queries++;let v=0n;for(let i of o.idx)if(R.has(i))v^=1n<<BigInt(R.get(i));if(!v||bits(v).length%2)continue;if(B.add(v)){selected.push(o);if(B.m.size===w-1)break}}
 maxGain=Math.max(maxGain,B.m.size);if(B.m.size===w-2)near++;
 if(B.m.size!==w-1)continue;
 let kept=[];for(let i=0;i<r;i++)if(!R.has(i))kept.push({mask:1n<<BigInt(i),p:[ts[i][b],ts[i][c]]});kept.push(...selected);
 let C=basis();for(let i=0;i<kept.length;i++)if(!C.add(kept[i].mask,1n<<BigInt(i)))throw Error("basis fail");
 let cols=Array(kept.length).fill(0n);for(let k=0;k<d;k++){let x=0n;for(let i=0;i<r;i++)if(ts[i][a]>>BigInt(k)&1n)x|=1n<<BigInt(i);let [v,t]=C.reduce(x);if(v)throw Error("missing target");for(let i of bits(t))cols[i]|=1n<<BigInt(k)}
 let out=[];for(let i=0;i<kept.length;i++)if(cols[i]){let t=[];t[a]=cols[i];t[b]=kept[i].p[0];t[c]=kept[i].p[1];out.push(t)}if(out.length>=r||!verify(out,n))throw Error("bad compression");
 return {axis:a,tested,atoms:atoms.length,relations:relations.length,rel2,rel3,rel4,queries,maxGain,near,success:true,support:rel,selected:selected.map(x=>x.idx),out}
 }
 return {axis:a,tested,atoms:atoms.length,relations:relations.length,rel2,rel3,rel4,queries,maxGain,near,success:false}
}
let seed=[[9n,9n,9n],[12n,1n,12n],[1n,10n,10n],[8n,5n,5n],[3n,8n,3n],[5n,3n,8n],[10n,12n,1n]];
let ctrl=seed.slice(1).concat([[9n,9n,1n],[9n,9n,8n]]);
let inputs=[{label:"split-control",n:2,t:ctrl},{label:"barrier8",n:2,t:data.barrier.found.ground.map(t=>t.map(BigInt))},{label:"rank25",n:3,t:data.prior.runs.find(x=>x.best===25).terms.map(t=>t.map(BigInt))},...data.hot.map(x=>({label:"rank"+x.best,n:x.n,t:x.terms.map(t=>t.map(BigInt))}))];
return inputs.map(({label,n,t})=>{if(!verify(t,n))throw Error("bad seed");let initial=t.length,passes=[];for(let j=0;j<5;j++){let improved=false;for(let a=0;a<3;a++){let {out,...rec}=one(t,n,a);passes.push({rank:t.length,...rec});if(out){t=out;improved=true;break}}if(!improved)break}if(label==="split-control"&&t.length!==7)throw Error("control failed");return {label,n,initial,best:t.length,passes,verified:verify(t,n),terms:t.map(x=>x.map(String))}})
}
const fs=require('node:fs'),path=require('node:path');const read=x=>JSON.parse(fs.readFileSync(path.join(__dirname,x),'utf8'));console.log(JSON.stringify(experiment({hot:read('mmg012_results.json'),prior:read('mmg017_results.json'),barrier:read('mmg016_results.json')}),null,2));
