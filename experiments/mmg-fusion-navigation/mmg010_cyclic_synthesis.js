function synthesize(){
function pop(x){let n=0;while(x){x&=x-1;n++}return n}
function bits(x){let a=[];for(let i=0;x;x>>=1,i++)if(x&1)a.push(i);return a}
function make(n){let d=n*n,id=new Int16Array(d*d*d),count=0;id.fill(-1);let index=(i,j,k)=>(i*d+j)*d+k;
for(let i=0;i<d;i++)for(let j=0;j<d;j++)for(let k=0;k<d;k++){let x=index(i,j,k);if(id[x]<0){id[x]=id[index(j,k,i)]=id[index(k,i,j)]=count++}}
function orbit(a,b,c){let z=0n;for(let i of bits(a))for(let j of bits(b))for(let k of bits(c))z^=1n<<BigInt(id[index(i,j,k)]);return {v:[a,b,c],key:z,w:a===b&&b===c?1:3}}
function target(){let z=0n;for(let i=0;i<n;i++)for(let j=0;j<n;j++)for(let k=0;k<n;k++)z^=1n<<BigInt(id[index(i*n+j,j*n+k,k*n+i)]);return z}
function verify(os){let rows=Array(d).fill(0n),total=0;for(let o of os){let [a,b,c]=o.v,vs=o.w===1?[[a,b,c]]:[[a,b,c],[b,c,a],[c,a,b]];for(let [x,y,z] of vs){total++;let r=0n;for(let i of bits(x))for(let j of bits(y))r^=1n<<BigInt(i*d+j);for(let k of bits(z))rows[k]^=r}}
for(let i=0;i<n;i++)for(let k=0;k<n;k++){let v=0n;for(let j=0;j<n;j++)v^=1n<<BigInt((i*n+j)*d+j*n+k);if(rows[k*n+i]!==v)return false}return total===os.reduce((a,x)=>a+x.w,0)}
function dict(vs){let m=new Map(),size=0;for(let a of vs)for(let b of vs)for(let c of vs){if(a>b||a>c||(a===b&&b!==c)||(a===c&&a!==b&&b<c))continue; // canonical cyclic representative: if a=b<c, rotation (a,c,a) is lex larger, so repair via exact check below
let x=[a,b,c],y=[b,c,a],z=[c,a,b];let cmp=(u,v)=>u[0]-v[0]||u[1]-v[1]||u[2]-v[2];if(cmp(x,y)>0||cmp(x,z)>0)continue;let o=orbit(a,b,c);size++;let old=m.get(o.key);if(o.key&&(!old||o.w<old.w))m.set(o.key,o)}
return {m,size}}
return {n,d,count,orbit,target,verify,dict}}
let g=make(2),vs=Array.from({length:15},(_,i)=>i+1);
// Canonical orbit enumeration independently, including equal first factors.
let singles=vs.map(x=>g.orbit(x,x,x)),triples=[];const cmp=(a,b)=>a[0]-b[0]||a[1]-b[1]||a[2]-b[2];
for(let a of vs)for(let b of vs)for(let c of vs){if(a===b&&b===c)continue;if(cmp([a,b,c],[b,c,a])<=0&&cmp([a,b,c],[c,a,b])<=0)triples.push(g.orbit(a,b,c))}
if(triples.length!==1120)throw Error("bad orbit count");
let sMap=new Map();for(let mask=0;mask<1<<15;mask++){let w=pop(mask);if(w>7)continue;let z=0n;for(let i of bits(mask))z^=singles[i].key;if(!sMap.has(z))sMap.set(z,[]);sMap.get(z).push({mask,w})}
let count=Array(8).fill(0),best=null,min=8,pairs=0;
function check(ts,z,w){for(let x of sMap.get(g.target()^z)||[]){let k=w+x.w;if(k>7)continue;count[k]++;if(k<min){min=k;best=[...ts,...bits(x.mask).map(i=>singles[i])];if(!g.verify(best))throw Error("synthesis bad")}}}
check([],0n,0);for(let i=0;i<triples.length;i++){check([triples[i]],triples[i].key,3);for(let j=0;j<i;j++){pairs++;check([triples[i],triples[j]],triples[i].key^triples[j].key,6)}}
if(min!==7||!best)throw Error("rank7 not found");
// n=3, every support <=2 vector, plus all embedded vectors used in discovered seed.
let h=make(3),embed=(x,ij)=>bits(x).reduce((v,k)=>v|(1<<(ij[Math.floor(k/2)]*3+ij[k%2])),0);
let init=[],idx=[0,1];for(let o of best)init.push(h.orbit(...o.v.map(x=>embed(x,idx))));
for(let i=0;i<3;i++)for(let j=0;j<3;j++)for(let k=0;k<3;k++){if(i<2&&j<2&&k<2)continue;let a=1<<(i*3+j),b=1<<(j*3+k),c=1<<(k*3+i);if(cmp([a,b,c],[b,c,a])<=0&&cmp([a,b,c],[c,a,b])<=0)init.push(h.orbit(a,b,c))}
if(!h.verify(init))throw Error("bad embedded ground");
let v3=Array.from({length:511},(_,i)=>i+1).filter(x=>pop(x)<=2);for(let i=0;i<3;i++)for(let j=i+1;j<3;j++)for(let o of best)for(let x of o.v)v3.push(embed(x,[i,j]));v3=[...new Set(v3)].sort((a,b)=>a-b);
let dictionary=new Map(),orbits=0;
for(let a of v3)for(let b of v3)for(let c of v3){if(cmp([a,b,c],[b,c,a])>0||cmp([a,b,c],[c,a,b])>0)continue;let o=h.orbit(a,b,c);orbits++;if(!o.key)continue;let old=dictionary.get(o.key);if(!old||o.w<old.w)dictionary.set(o.key,o)}
let current=init,events=[],queries=0,passes=0;
function weight(xs){return xs.reduce((a,x)=>a+x.w,0)}
for(let step=0;step<6;step++){passes++;let improvement=null,w0=weight(current);
function consider(indices){let z=0n,w=0;for(let i of indices){z^=current[i].key;w+=current[i].w}let one=dictionary.get(z);queries++;if(one&&one.w<w){let t=current.filter((_,i)=>!indices.includes(i)).concat(one);if(!improvement||weight(t)<weight(improvement))improvement=t}
if(w<=4)return;
for(let [key,x] of dictionary){queries++;let y=dictionary.get(z^key);if(y&&x.w+y.w<w){let t=current.filter((_,i)=>!indices.includes(i)).concat(x,y);if(!improvement||weight(t)<weight(improvement))improvement=t;if(x.w+y.w<=2)break}}
}
for(let i=0;i<current.length;i++)for(let j=0;j<i;j++){consider([i,j]);for(let k=0;k<j;k++)consider([i,j,k])}
if(!improvement||weight(improvement)>=w0)break;if(!h.verify(improvement))throw Error("bad synthesized replacement");current=improvement;events.push(weight(current))}
return {n2:{coordinates:g.count,singletons:singles.length,triple_orbits:triples.length,singleton_subsets:[...sMap.values()].reduce((a,v)=>a+v.length,0),pair_comparisons:pairs,solutions_by_rank:count,min_rank:min,verified:g.verify(best),witness:best.map(({v,w})=>({v,w}))},n3:{coordinates:h.count,vectors:v3.length,orbits,distinct_dictionary:dictionary.size,initial_rank:weight(init),best_rank:weight(current),passes,queries,events,verified:h.verify(current),witness:current.map(({v,w})=>({v,w}))}};
}
console.log(JSON.stringify(synthesize(),null,2));
