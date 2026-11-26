function optimize(){
const bit=x=>1<<(x-1), pop=x=>{let k=0;for(;x;x&=x-1)k++;return k}, members=x=>Array.from({length:31},(_,i)=>i).filter(i=>x&(1<<i));
const xs=Array.from({length:15},(_,i)=>i+1),start=xs.filter(x=>pop(x)===1).reduce((a,x)=>a|bit(x),0);
let state=[start],parent=new Map([[start,null]]);for(let i=0;i<state.length;i++){let mask=state[i],v=xs.filter(x=>mask&bit(x));for(let j=0;j<v.length;j++)for(let k=0;k<j;k++){let a=v[j],b=v[k],c=a^b;if(mask&bit(c))continue;let next=mask|bit(c);if(!parent.has(next)){parent.set(next,[mask,a,b,c]);state.push(next)}}}
let cache=new Map();
function exact(forms){let mask=forms.reduce((a,x)=>a|bit(x),0);let res=cache.get(mask);if(!res){let m=state.find(x=>(x&mask)===mask),g=[];while(m!==start){let [last,a,b,c]=parent.get(m);g.push([a,b,c]);m=last}res=g.reverse();cache.set(mask,res)}return {inputs:4,forms,gates:res}}
function tr(x){return (x&9)|((x&2)<<1)|((x&4)>>1)}
function mm(x,y){let z=0;for(let i=0;i<2;i++)for(let j=0;j<2;j++)for(let k=0;k<2;k++)if((x&(1<<(i*2+k)))&&(y&(1<<(k*2+j))))z^=1<<(i*2+j);return z}
const gl=xs.filter(x=>xs.some(y=>mm(x,y)===9&&mm(y,x)===9)),inv=x=>gl.find(y=>mm(x,y)===9);
function verify(ts,n){let d=n*n,rows=Array(d).fill(0n);for(let [a,b,c] of ts){let p=0n;for(let i of members(a))p^=BigInt(b)<<BigInt(i*d);for(let k of members(c))rows[k]^=p}for(let i=0;i<n;i++)for(let k=0;k<n;k++){let p=0n;for(let j=0;j<n;j++)p^=1n<<BigInt((i*n+j)*d+j*n+k);if(rows[i*n+k]!==p)return false}return true}
const original=[[9,9,9],[12,1,12],[1,10,10],[8,5,5],[3,8,3],[5,3,8],[10,12,1]];
const cyclic=[[2,4,15],[4,15,2],[15,2,4],[1,1,1],[10,10,10],[12,12,12],[14,14,14]].map(([a,b,c])=>[a,b,tr(c)]);
if(!verify(original,2)||!verify(cyclic,2))throw Error("bad rank7");
function compile2(ts){let forms=[0,1,2].map(i=>ts.map(t=>t[i]));let circuits=forms.map(exact),adds=circuits.map(x=>x.gates.length);return {circuits,adds,total:adds.reduce((a,x)=>a+x,3)}}
let histogram={},best=null,checked=0;
for(let seed of [original,cyclic])for(let p of gl)for(let q of gl)for(let r of gl){let ts=seed.map(([a,b,c])=>[mm(mm(p,a),inv(q)),mm(mm(q,b),inv(r)),tr(mm(mm(r,tr(c)),inv(p)))]);if(!verify(ts,2))throw Error("gauge failed");let v=compile2(ts);histogram[v.total]=(histogram[v.total]||0)+1;checked++;if(!best||v.total<best.total)best={...v,terms:ts,gauge:[p,q,r],seed:seed===original?"standard":"cyclic"}}
function rng(seed){return n=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)%n}}
function greedy(forms,d,random){
 let gates=[],available=new Set(Array.from({length:d},(_,i)=>1<<i)),res=forms.map(m=>members(m).map(i=>1<<i));
 for(;;){let freq=new Map();for(let row of res)for(let i=0;i<row.length;i++)for(let j=0;j<i;j++){let a=Math.min(row[i],row[j]),b=Math.max(row[i],row[j]),c=a^b;if(!c||row.includes(c))continue;let key=a*1024+b;if(!freq.has(key))freq.set(key,{a,b,c,count:0});freq.get(key).count++}
 let score=0,choices=[];for(let x of freq.values()){let gain=x.count-(available.has(x.c)?0:1);if(gain>score){score=gain;choices=[x]}else if(gain===score&&score>0)choices.push(x)}if(score<=0)break;let x=choices[random(choices.length)];if(!available.has(x.c)){gates.push([x.a,x.b,x.c]);available.add(x.c)}for(let i=0;i<res.length;i++){let row=res[i];if(row.includes(x.a)&&row.includes(x.b)&&!row.includes(x.c))res[i]=row.filter(z=>z!==x.a&&z!==x.b).concat(x.c)}}
 for(let row of res){while(row.length>1){let a=row.pop(),b=row.pop(),c=a^b;if(!c)continue;if(!available.has(c)){gates.push([a,b,c]);available.add(c)}row.push(c)}}
 if(forms.some(x=>!available.has(x)))throw Error("greedy missing form");return {inputs:d,forms,gates}
}
function prune(c){let needed=new Set(c.forms),g=[];for(let i=c.gates.length-1;i>=0;i--){let t=c.gates[i];if(needed.has(t[2])){g.push(t);needed.add(t[0]);needed.add(t[1])}}return {...c,gates:g.reverse()}}
function fwd(c,values){let m=new Map();for(let i=0;i<c.inputs;i++)m.set(1<<i,values[i]);for(let [a,b,z] of c.gates){if(!m.has(a)||!m.has(b)||m.has(z))throw Error("bad circuit");m.set(z,m.get(a)^m.get(b))}return c.forms.map(x=>m.get(x))}
function rev(c,values){let m=new Map(),adds=0;function acc(x,y){if(m.has(x)){m.set(x,m.get(x)^y);adds++}else m.set(x,y)}for(let i=0;i<c.forms.length;i++)acc(c.forms[i],values[i]);for(let i=c.gates.length-1;i>=0;i--){let [a,b,z]=c.gates[i];if(!m.has(z))throw Error("dead gate");let v=m.get(z);acc(a,v);acc(b,v)}return {out:Array.from({length:c.inputs},(_,i)=>m.get(1<<i)||0),adds}}
function test(c){for(let i=0;i<c.inputs;i++){let v=Array.from({length:c.inputs},(_,j)=>+(i===j));if(fwd(c,v).some((x,j)=>x!==((c.forms[j]>>i)&1)))throw Error("encoder identity")}for(let j=0;j<c.forms.length;j++){let v=Array.from({length:c.forms.length},(_,i)=>+(i===j));let a=rev(c,v);if(a.out.some((x,i)=>x!==((c.forms[j]>>i)&1)))throw Error("transpose identity");if(a.adds!==c.gates.length+c.forms.length-c.inputs)throw Error("transpose ledger")}}
for(let c of best.circuits)test(c);
const walk3=[[224,385,82],[216,24,18],[72,36,391],[56,8,26],[438,390,437],[40,9,90],[192,390,144],[200,63,18],[438,130,439],[27,32,405],[65,292,5],[32,65,72],[288,256,55],[146,146,2],[446,6,437],[195,32,37],[128,54,130],[288,457,64],[3,325,1],[211,290,437],[7,320,1],[365,2,439],[101,256,432],[392,9,64],[2,45,1],[448,384,194]];
if(!verify(walk3,3))throw Error("bad prior");
let random=rng(20261125),d=9,r=26,base3=walk3.reduce((a,t)=>a+t.reduce((b,x)=>b+pop(x)-1,0),r-d),best3=null;
function compile3(ts){let circuits=[0,1,2].map(a=>prune(greedy(ts.map(t=>t[a]),9,random)));let adds=circuits.map(x=>x.gates.length);return {circuits,adds,total:adds.reduce((a,x)=>a+x,17),terms:ts}}
for(let j=0;j<100;j++){let c=compile3(walk3);if(!best3||c.total<best3.total)best3=c}
let initial3=best3.total,current=best3,improvements=[],attempts=0;
for(let step=0;step<1200;step++){let a=random(3),b=(a+1)%3,c=(a+2)%3,ts=current.terms.map(t=>t.slice()),pairs=[];for(let i=0;i<ts.length;i++)for(let j=0;j<i;j++)if(ts[i][a]===ts[j][a])pairs.push([i,j]);if(!pairs.length)continue;let [i,j]=pairs[random(pairs.length)];if(random(2))[i,j]=[j,i];ts[i][c]^=ts[j][c];ts[j][b]^=ts[i][b];if(ts.some(t=>!t.every(Boolean)))continue;attempts++;let next=compile3(ts);if(next.total<=current.total||random(100)<2)current=next;if(next.total<best3.total){if(!verify(ts,3))throw Error("bad flip");best3=next;improvements.push([step,next.total])}if(step%100===99)current=best3}
if(!verify(best3.terms,3))throw Error("rank changed");for(let c of best3.circuits)test(c);
function pack(a,b,k){let n=b**k,d=b*b,out=new Uint8Array(n*n);for(let i=0;i<n;i++)for(let j=0;j<n;j++){let x=i,y=j,q=0,stride=1;for(let h=0;h<k;h++){q+=((x%b)*b+y%b)*stride;stride*=d;x=Math.floor(x/b);y=Math.floor(y/b)}out[q]=a[i*n+j]}return out}
function unpack(a,b,k){let n=b**k,d=b*b,out=new Uint8Array(n*n);for(let i=0;i<n;i++)for(let j=0;j<n;j++){let x=i,y=j,q=0,stride=1;for(let h=0;h<k;h++){q+=((x%b)*b+y%b)*stride;stride*=d;x=Math.floor(x/b);y=Math.floor(y/b)}out[i*n+j]=a[q]}return out}
function axis(x,dims,a,c,back,ledger){let pre=dims.slice(0,a).reduce((x,y)=>x*y,1),post=dims.slice(a+1).reduce((x,y)=>x*y,1),n=dims[a],o=back?c.inputs:c.forms.length,out=new Uint8Array(pre*o*post);
for(let i=0;i<pre;i++)for(let j=0;j<post;j++){let v=Array.from({length:n},(_,t)=>x[(i*n+t)*post+j]),y;if(back){let z=rev(c,v);y=z.out;ledger.add+=z.adds}else{y=fwd(c,v);ledger.add+=c.gates.length}for(let t=0;t<o;t++)out[(i*o+t)*post+j]=y[t]}
dims[a]=o;return out}
function product(b,k,compiled){let n=b**k,d=b*b,r=compiled.terms.length,A=Uint8Array.from({length:n*n},()=>random(2)),B=Uint8Array.from({length:n*n},()=>random(2)),ledger={add:0,mul:0};let l=pack(A,b,k),rr=pack(B,b,k),ds=Array(k).fill(d),es=ds.slice();for(let a=0;a<k;a++){l=axis(l,ds,a,compiled.circuits[0],false,ledger);rr=axis(rr,es,a,compiled.circuits[1],false,ledger)}for(let i=0;i<l.length;i++){l[i]&=rr[i];ledger.mul++}for(let a=k-1;a>=0;a--)l=axis(l,ds,a,compiled.circuits[2],true,ledger);let C=unpack(l,b,k);for(let i=0;i<n;i++)for(let j=0;j<n;j++){let z=0;for(let h=0;h<n;h++)z^=A[i*n+h]&B[h*n+j];if(z!==C[i*n+j])throw Error("dense output")}let expected=compiled.total*(r**k-d**k)/(r-d);if(ledger.add!==expected||ledger.mul!==r**k)throw Error("cost");return {b,k,n,coordinates:n*n,...ledger,total:ledger.add+ledger.mul,prior_additions:(b===2?18:175)*(r**k-d**k)/(r-d),verified:true}}
let runs=[];for(let k=1;k<=6;k++)runs.push(product(2,k,best));for(let k=1;k<=4;k++)runs.push(product(3,k,best3));
return {two:{states:state.length,gauges:checked,histogram,best},three:{uncached_transpose_baseline:base3,initial_cse:initial3,flip_attempts:attempts,improvements,best:best3},runs};
}
console.log(JSON.stringify(optimize(),null,2));
