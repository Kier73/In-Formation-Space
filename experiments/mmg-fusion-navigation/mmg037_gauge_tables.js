function gaugeSearch(data){
const members=x=>Array.from({length:9},(_,i)=>i).filter(i=>x&(1<<i));
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

let random=rng(20261124);
function pack(a,b,k){let n=b**k,d=b*b,out=new Uint8Array(n*n);for(let i=0;i<n;i++)for(let j=0;j<n;j++){let x=i,y=j,q=0,stride=1;for(let h=0;h<k;h++){q+=((x%b)*b+y%b)*stride;stride*=d;x=Math.floor(x/b);y=Math.floor(y/b)}out[q]=a[i*n+j]}return out}
function unpack(a,b,k){let n=b**k,d=b*b,out=new Uint8Array(n*n);for(let i=0;i<n;i++)for(let j=0;j<n;j++){let x=i,y=j,q=0,stride=1;for(let h=0;h<k;h++){q+=((x%b)*b+y%b)*stride;stride*=d;x=Math.floor(x/b);y=Math.floor(y/b)}out[i*n+j]=a[q]}return out}
function axis(x,dims,a,c,back,ledger){let pre=dims.slice(0,a).reduce((x,y)=>x*y,1),post=dims.slice(a+1).reduce((x,y)=>x*y,1),n=dims[a],o=back?c.inputs:c.forms.length,out=new Uint8Array(pre*o*post);
for(let i=0;i<pre;i++)for(let j=0;j<post;j++){let v=Array.from({length:n},(_,t)=>x[(i*n+t)*post+j]),y;if(back){let z=rev(c,v);y=z.out;ledger.add+=z.adds}else{y=fwd(c,v);ledger.add+=c.gates.length}for(let t=0;t<o;t++)out[(i*o+t)*post+j]=y[t]}
dims[a]=o;return out}
function product(b,k,compiled){let n=b**k,d=b*b,r=compiled.terms.length,A=Uint8Array.from({length:n*n},()=>random(2)),B=Uint8Array.from({length:n*n},()=>random(2)),ledger={add:0,mul:0};let l=pack(A,b,k),rr=pack(B,b,k),ds=Array(k).fill(d),es=ds.slice();for(let a=0;a<k;a++){l=axis(l,ds,a,compiled.circuits[0],false,ledger);rr=axis(rr,es,a,compiled.circuits[1],false,ledger)}for(let i=0;i<l.length;i++){l[i]&=rr[i];ledger.mul++}for(let a=k-1;a>=0;a--)l=axis(l,ds,a,compiled.circuits[2],true,ledger);let C=unpack(l,b,k);for(let i=0;i<n;i++)for(let j=0;j<n;j++){let z=0;for(let h=0;h<n;h++)z^=A[i*n+h]&B[h*n+j];if(z!==C[i*n+j])throw Error("dense output")}let expected=compiled.total*(r**k-d**k)/(r-d);if(ledger.add!==expected||ledger.mul!==r**k)throw Error("cost");return {b,k,n,coordinates:n*n,...ledger,total:ledger.add+ledger.mul,prior_additions:(b===2?18:175)*(r**k-d**k)/(r-d),verified:true}}



function independent(ts){let n=3,d=9,checks=0;for(let i=0;i<d;i++)for(let j=0;j<d;j++){let out=0;for(let [u,v,w] of ts)if((u>>i&1)&&(v>>j&1))out^=w;let expected=i%n===Math.floor(j/n)?1<<(Math.floor(i/n)*n+j%n):0;if(out!==expected)return false;checks++}return checks}

function mul(a,b){let z=0;for(let i=0;i<3;i++)for(let j=0;j<3;j++)for(let k=0;k<3;k++)if((a>>(3*i+k)&1)&&(b>>(3*k+j)&1))z^=1<<(3*i+j);return z}
function tr(x){let z=0;for(let i=0;i<3;i++)for(let j=0;j<3;j++)if(x>>(i*3+j)&1)z|=1<<(j*3+i);return z}
function rank(x){let p=[0,0,0],r=0;for(let i=0;i<3;i++){let v=x>>(3*i)&7;while(v){let j=31-Math.clz32(v);if(!p[j]){p[j]=v;r++;break}v^=p[j]}}return r}
let gl=Array.from({length:511},(_,i)=>i+1).filter(x=>rank(x)===3),id=273;
let perms=gl.filter(x=>members(x).length===3),seen=new Set(),reps=[];
for(let x of [id,...gl]){if(seen.has(x))continue;reps.push(x);for(let p of perms)seen.add(mul(p,x))}
if(gl.length!==168||perms.length!==6||reps.length!==28||seen.size!==168)throw Error("group");
const inv=new Map(gl.map(x=>[x,gl.find(y=>mul(x,y)===id&&mul(y,x)===id)]));if([...inv.values()].some(x=>x===undefined))throw Error("inverse");
let res=[];
for(let s of data){let ts=s.best.terms,r=ts.length;if(independent(ts)!==81)throw Error("seed");let tables=[],evaluations=0;
 for(let a=0;a<3;a++){let table=[];for(let p of reps){let row=[];for(let q of reps){let forms=ts.map(t=>a===2?tr(mul(mul(p,tr(t[a])),inv.get(q))):mul(mul(p,t[a]),inv.get(q)));let best=null;for(let h=0;h<6;h++){let x=prune(greedy(forms,9,random));evaluations++;if(!best||x.gates.length<best.gates.length)best=x}row.push(best)}table.push(row)}tables.push(table)}
 let best=s.best,initial=best.total,bestGauge=null,minimum=Infinity,distribution={},lookups=0;
 for(let i=0;i<28;i++)for(let j=0;j<28;j++)for(let k=0;k<28;k++){let circuits=[tables[0][i][j],tables[1][j][k],tables[2][k][i]],cost=circuits.reduce((v,x)=>v+x.gates.length,r-9);lookups+=3;distribution[cost]=(distribution[cost]||0)+1;minimum=Math.min(minimum,cost);if(cost<best.total){let terms=ts.map((_,t)=>circuits.map(x=>x.forms[t]));if(independent(terms)!==81)throw Error("gauge");best={circuits,adds:circuits.map(x=>x.gates.length),total:cost,terms};bestGauge=[reps[i],reps[j],reps[k]]}}
 for(let x of best.circuits)test(x);if(independent(best.terms)!==81)throw Error("final");
 let runs=[];for(let k=1;k<=4;k++){let v=product(3,k,best);delete v.prior_additions;runs.push(v)}
 res.push({rank:r,initial,optimized:best.total,minimumInSampledCircuitTables:minimum,gauge:bestGauge,groupSize:gl.length,representatives:reps.length,tableCells:3*28*28,localCircuitSyntheses:evaluations,combinations:28**3,lookups,distribution,best,runs})
}
return res
}
const fs=require('node:fs'),path=require('node:path');console.log(JSON.stringify(gaugeSearch(JSON.parse(fs.readFileSync(path.join(__dirname,'mmg034_results.json'),'utf8'))),null,2));
