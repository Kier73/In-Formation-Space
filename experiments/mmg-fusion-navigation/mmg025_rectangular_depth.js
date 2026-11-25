function rectangle(data){
const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
const pop=x=>bits(BigInt(x)).length;
const key=s=>s.join(",");
const strassen=[[9,9,9],[12,1,12],[1,10,10],[8,5,5],[3,8,3],[5,3,8],[10,12,1]].map(t=>t.map(BigInt));
function tensor(a,n,b,m){let d=n*m;function lift(x,y){let z=0n;for(let i of bits(x))for(let j of bits(y))z|=1n<<BigInt((Math.floor(i/n)*m+Math.floor(j/m))*d+(i%n)*m+j%m);return z}return a.flatMap(x=>b.map(y=>x.map((v,j)=>lift(v,y[j]))))}
function verify(t,s){let [a,b,c]=s,U=a*b,V=b*c,W=a*c,z=Array(W).fill(0n);for(let [x,y,w] of t){if(!x||!y||!w||x>>BigInt(U)||y>>BigInt(V)||w>>BigInt(W))return false;let p=0n;for(let i of bits(x))p^=y<<BigInt(i*V);for(let k of bits(w))z[k]^=p}for(let i=0;i<a;i++)for(let k=0;k<c;k++){let p=0n;for(let j=0;j<b;j++)p^=1n<<BigInt((i*b+j)*V+j*c+k);if(z[i*c+k]!==p)return false}return true}
function naive(s){let [a,b,c]=s,t=[];for(let i=0;i<a;i++)for(let j=0;j<b;j++)for(let k=0;k<c;k++)t.push([1n<<BigInt(i*b+j),1n<<BigInt(j*c+k),1n<<BigInt(i*c+k)]);return t}
function project(x,n,rows,cols){let v=0n;for(let i=0;i<rows.length;i++)for(let j=0;j<cols.length;j++)if(x>>BigInt(rows[i]*n+cols[j])&1n)v|=1n<<BigInt(i*cols.length+j);return v}
function merge(ts){for(;;){let prev=ts.length;for(let a=0;a<3;a++){let b=(a+1)%3,c=(a+2)%3,m=new Map;for(let t of ts){if(!t.every(Boolean))continue;let k=t[b]+":"+t[c];if(m.has(k))m.get(k)[a]^=t[a];else m.set(k,t.slice())}ts=[...m.values()].filter(t=>t.every(Boolean))}if(ts.length===prev)return ts}}
function embed(t,ss,s,axis,delta){let [a,b,c]=s,[x,y,z]=ss,offset=[0,0,0];offset[axis]=delta;let maps=[[x,y,a,b,offset[0],offset[1]],[y,z,b,c,offset[1],offset[2]],[x,z,a,c,offset[0],offset[2]]];return t.map(t=>t.map((v,i)=>{let [r,col,R,C,dr,dc]=maps[i],out=0n;for(let j of bits(v))out|=1n<<BigInt((Math.floor(j/col)+dr)*C+j%col+dc);return out}))}
function lower(s){let [a,b,c]=s;return Math.max(a*b+c-1,b*c+a-1,a*c+b-1)}
let sources=[{label:"Strassen",n:2,t:strassen},{label:"rank24",n:3,t:data.closed.results.find(x=>x.n===3).terms.map(t=>t.map(BigInt))},{label:"rank47",n:4,t:data.hot.find(x=>x.n===4).terms.map(t=>t.map(BigInt))},{label:"Strassen-squared",n:4,t:tensor(strassen,2,strassen,2)}];
let best=new Map(),counts={},projected=0,checked=0,improvements=0,shapeList=[];
for(let a=1;a<=4;a++)for(let b=1;b<=4;b++)for(let c=1;c<=4;c++){let s=[a,b,c];shapeList.push(s);best.set(key(s),{s,t:naive(s),source:"outer-product"})}
for(let {label,n,t} of sources){if(!verify(t,[n,n,n]))throw Error("seed");let M=1<<n;counts[label]={projections:0,improvements:0};for(let i=1;i<M;i++)for(let j=1;j<M;j++)for(let k=1;k<M;k++){let I=bits(BigInt(i)),J=bits(BigInt(j)),K=bits(BigInt(k)),s=[I.length,J.length,K.length],out=merge(t.map(([x,y,z])=>[project(x,n,I,J),project(y,n,J,K),project(z,n,I,K)]));projected++;counts[label].projections++;let old=best.get(key(s));if(out.length<old.t.length){if(!verify(out,s))throw Error("project");checked++;improvements++;counts[label].improvements++;best.set(key(s),{s,t:out,source:label,masks:[i,j,k]})}}}
let before=Object.fromEntries([...best].map(([k,v])=>[k,v.t.length])),splits=0,splitImprovements=0;
shapeList.sort((s,t)=>s.reduce((a,b)=>a+b)-t.reduce((a,b)=>a+b));
for(let s of shapeList){for(let axis=0;axis<3;axis++)for(let k=1;k<s[axis];k++){let x=s.slice(),y=s.slice();x[axis]=k;y[axis]-=k;let A=best.get(key(x)),B=best.get(key(y)),out=merge(embed(A.t,x,s,axis,0).concat(embed(B.t,y,s,axis,k)));splits++;if(out.length<best.get(key(s)).t.length){if(!verify(out,s))throw Error("split");checked++;splitImprovements++;best.set(key(s),{s,t:out,source:"split",axis,split:k,parents:[key(x),key(y)]})}}}
let paths=[];
for(let n of [2,3,4]){let seq=[];for(let k=1;k<=n;k++){let v=best.get(key([n,k,n])),r=v.t.length,full=v.s.reduce((x,y)=>x*y,1);let target=0;while(BigInt(target+1)**4n<BigInt(full)**3n)target++;seq.push({depth:k,shape:v.s,rank:r,lower:lower(v.s),quadraticFloor:n*n,strictCyclicTarget:target,source:v.source,rankBeforeSplit:before[key(v.s)],terms:v.t.map(x=>x.map(String))});if(!verify(v.t,v.s))throw Error("final");checked++}paths.push({n,seq})}
return {projected,checked,counts,improvements,splits,splitImprovements,shapes:shapeList.map(s=>{let v=best.get(key(s));if(!verify(v.t,s)||v.t.length<lower(s))throw Error("shape");return {shape:s,rank:v.t.length,lower:lower(s),source:v.source,terms:v.t.map(t=>t.map(String))}}),paths}
}
const fs=require('node:fs'),path=require('node:path');const read=x=>JSON.parse(fs.readFileSync(path.join(__dirname,x),'utf8'));console.log(JSON.stringify(rectangle({closed:read('mmg021_results.json'),hot:read('mmg012_results.json')}),null,2));
