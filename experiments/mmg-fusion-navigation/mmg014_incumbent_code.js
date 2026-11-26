function profile(seeds){
const pop32=x=>{x=x-((x>>>1)&0x55555555);x=(x&0x33333333)+((x>>>2)&0x33333333);return Math.imul((x+(x>>>4))&0x0f0f0f0f,0x01010101)>>>24};
const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
function rank(v){let b=new Map;for(let x of v){while(x){let p=x.toString(2).length-1;if(b.has(p))x^=b.get(p);else{b.set(p,x);break}}}return b.size}
function randgen(s){return n=>{s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)%n}}
function outer(a,b,d){let x=0n;for(let i of bits(a))x^=b<<BigInt(i*d);return x}
function sliceRows(n,a){let d=n*n,o=Array(d).fill(0n);for(let i=0;i<n;i++)for(let j=0;j<n;j++)for(let k=0;k<n;k++){let v=[i*n+j,j*n+k,i*n+k];o[v[a]]^=1n<<BigInt(v[(a+1)%3]*d+v[(a+2)%3])}return o}
function enumerate(ts,n,a){let d=n*n,r=ts.length,words=Math.ceil(r/32),cols=Array.from({length:d},()=>new Uint32Array(words));for(let i=0;i<r;i++)for(let j of bits(ts[i][a]))cols[j][i>>>5]|=1<<(i&31);
let cur=new Uint32Array(words),hist=Array(r+1).fill(0),min=r,checks=0;
for(let x=1;x<2**d;x++){let j=31-Math.clz32(x&-x),w=0;for(let i=0;i<words;i++){cur[i]^=cols[j][i];w+=pop32(cur[i])}hist[w]++;if(w<min)min=w;checks++}
if(hist[0])throw Error("noninjective code");
const griesmer=h=>{let v=0;for(let i=0;i<h;i++)v+=Math.ceil(min/2**i);return v};
let out=[];let count=1;for(let k=0;k<=r;k++){count+=hist[k];let maxH=0;while(maxH<d&&griesmer(maxH+1)<=k&&2**(maxH+1)<=count)maxH++;out.push({retained:k,maxIntersectionDimension:maxH,rankFloor:k+d-maxH})}
return {axis:a,minDistance:min,checks,hist,profile:out}}
return seeds.map(s=>{let n=s.n,ts=s.terms.map(t=>t.map(BigInt)),r=ts.length,d=n*n,random=randgen(12025+n),axes=[];for(let a=0;a<3;a++){let b=(a+1)%3,c=(a+2)%3,products=ts.map(t=>outer(t[b],t[c],d)),rankPairs=rank(products);if(rankPairs!==r)throw Error("dependent incumbent pairs");let checks=0;
for(let i=0;i<300;i++){let keep=[];for(let j=0;j<r;j++)if(random(r)<i%r)keep.push(j);let set=new Set(keep),d1=rank(keep.map(j=>products[j]).concat(sliceRows(n,a))),d2=keep.length+rank(ts.filter((_,j)=>!set.has(j)).map(t=>t[a]));if(d1!==d2)throw Error("code floor mismatch");checks++}
let p=enumerate(ts,n,a);let maxRetained=p.profile.filter(x=>x.rankFloor<=s.strict_target).at(-1)?.retained??-1;axes.push({...p,rankPairs,identityChecks:checks,maxRetainedBound:maxRetained,minDiscardBound:r-maxRetained})}
return {n,r,target:s.strict_target,axes}
})
}
const fs=require('node:fs'),path=require('node:path');console.log(JSON.stringify(profile(JSON.parse(fs.readFileSync(path.join(__dirname,'mmg012_results.json'),'utf8'))),null,2));
