function reuseCampaign(api){
"use strict";
const {compile,verify,observe,evalF,meter}=api,bit=i=>1n<<BigInt(i);
const assert=(x,m)=>{if(!x)throw Error(m)};
let seed=180193;const rand=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed};
function word(n){let x=0n;for(let i=0;i<n;i++)if((rand()>>>19)&1)x|=bit(i);return x}
function parity(x){let y=0;while(x){y^=1;x&=x-1n}return y}
function weight(x){let z=0;while(x){z++;x&=x-1n}return z}
function generate(n,overlap){let masks=Array(5).fill(0n);
if(overlap){for(let i=0;i<5;i++)masks[i]=(word(n)&~31n)|bit(i)}
else{let perm=Array.from({length:n},(_,i)=>i);for(let i=n-1;i>0;i--){let j=rand()%(i+1);[perm[i],perm[j]]=[perm[j],perm[i]]}for(let i=0;i<n;i++)masks[i%5]|=bit(perm[i])}
let l=[],p=[],has=(r,i)=>Number((r>>BigInt(i))&1n);
for(let i=0;i<n;i++){if((has(masks[0],i)&has(masks[1],i))^(has(masks[2],i)&has(masks[3],i))^has(masks[4],i))l.push(i);
for(let j=i+1;j<n;j++)if((has(masks[0],i)&has(masks[1],j))^(has(masks[0],j)&has(masks[1],i))^(has(masks[2],i)&has(masks[3],j))^(has(masks[2],j)&has(masks[3],i)))p.push([i,j])}
return {source:{n,c:1,l,p},masks}}
const rows=[];
for(let n of [32,64,128])for(let overlap of [false,true]){
const {source:s,masks}=generate(n,overlap);const g=compile(s),v=verify(s,[],g);assert(v.ok,v.reason);assert(g.rows.length===5,"expected independent five-dimensional quotient");
const direct=meter(),acq=meter(),warm=meter(),checkpoints=[];
const setup=g.formationWork+v.work,srcTerms=s.l.length+s.p.length,decoderTerms=g.decoder.l.length+g.decoder.p.length;
// observe costs one per row, dot costs at most popcount(row)+1.
const perQueryBound=g.rows.reduce((sum,r)=>sum+2+weight(r),0)+decoderTerms;
const guaranteedCrossover=srcTerms>perQueryBound?Math.floor(setup/(srcTerms-perQueryBound))+1:null;
for(let i=1;i<=1024;i++){const x=word(n),h=masks.map(r=>parity(r&x));const oracle=1^(h[0]&h[1])^(h[2]&h[3])^h[4];assert(evalF(s,x,direct)===oracle,"source vs independent generator");assert(evalF(g.decoder,observe(g.rows,x,acq),warm)===oracle,"qualified decoder vs generator");if([128,256,512,1024].includes(i)){const total=setup+acq.work+warm.work;assert(acq.work+warm.work<=i*perQueryBound,"meter bound");if(guaranteedCrossover!==null&&i>=guaranteedCrossover)assert(total<direct.work,"guaranteed crossover");checkpoints.push({queries:i,direct:direct.work,acquisition:acq.work,warm:warm.work,total})}}
rows.push({n,overlap,sourceTerms:srcTerms,rank:g.rows.length,decoderTerms,formation:g.formationWork,verification:v.work,perQueryBound,guaranteedCrossover,checkpoints})
}
let incremental=0;
for(let n=4;n<=12;n++)for(let k=1;k<=3;k++){let {source:s}=generate(n,true);let old=[];for(let i=0;i<k;i++)old.push(bit(i)|bit(n-1));const g=compile(s,old),v=verify(s,old,g);assert(v.ok,v.reason);for(let i=0;i<128;i++){let x=word(n),m=meter();assert(evalF(s,x,m)===evalF(g.decoder,observe(g.rows,x,m),m),"old observer refinement")}incremental++}
return {heldoutQueries:6144,incrementalSources:incremental,incrementalQueries:incremental*128,rows};
}

if(typeof module!=="undefined") { module.exports=reuseCampaign; if(require.main===module) console.log(JSON.stringify(reuseCampaign(require('./quadratic_ground.js')),null,2)); }
