function scale(prior){
 const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
 const rng=s=>n=>{s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)%n};
 const seed=prior.results.find(x=>x.rank===7),mask=15n;
 function verify(ts,k){let d=2*k,z=Array(4).fill(0n);for(let [a,b,c] of ts){if(!a||!b||!c||a>>BigInt(d)||b>>BigInt(d)||c>>4n)return false;let v=0n;for(let i of bits(a))v^=b<<BigInt(i*d);for(let j of bits(c))z[j]^=v}for(let i=0;i<2;i++)for(let j=0;j<2;j++){let w=0n;for(let h=0;h<k;h++)w^=1n<<BigInt((i*k+h)*d+h*2+j);if(w!==z[i*2+j])return false}return true}
 function build(k){let out=[],P=[],q=0;for(;q+1<k;q+=2){let f=(x,leg)=>bits(BigInt(x)).reduce((v,i)=>v|(1n<<BigInt(leg===0?Math.floor(i/2)*k+q+i%2:(q+Math.floor(i/2))*2+i%2)),0n);
  for(let [a,b,c] of seed.terms)out.push([f(a,0),f(b,1),BigInt(c)]);
  P.push(out.length-7,out.length-6,out.length-5,out.length-4)
 }
 if(q<k){for(let i=0;i<2;i++)for(let j=0;j<2;j++){if(i===j)P.push(out.length);out.push([1n<<BigInt(i*k+q),1n<<BigInt(q*2+j),1n<<BigInt(i*2+j)])}}
 if(!verify(out,k))throw Error("base identity");return {out,P}
 }
 function scramble(ts,k,seed){let random=rng(seed),t=ts.map(x=>x.slice()),ops=0;
  // Common inner basis changes on encoded covectors preserve the full T_{2,k,2} tensor.
  // a inner vector -> E_{i,j} a, b inner vector -> E_{j,i} b.
  for(let h=0;h<8*k;h++){let i=random(k),j=random(k);if(i===j)continue;for(let x of t){for(let row=0;row<2;row++)if(x[0]>>BigInt(row*k+j)&1n)x[0]^=1n<<BigInt(row*k+i);for(let col=0;col<2;col++)if(x[1]>>BigInt(2*i+col)&1n)x[1]^=1n<<BigInt(2*j+col)}ops++}
  return {t,ops}
 }
 function run(k){let {out,P}=build(k),prefix=P.length,remaining=out.length-prefix,lb=2*k+Math.ceil(3*k/2);if(prefix!==2*k||out.length!==lb)throw Error("budget");let {t,ops}=scramble(out,k,7731+k);if(!verify(t,k))throw Error("scramble");
 let idx=new Set(P),diagonal=t.map(([a,b,c],i)=>[a,b,c&9n]).filter(x=>x[2]);if(diagonal.length!==prefix||P.some(i=>!(t[i][2]&9n))||t.some((x,i)=>!idx.has(i)&&(x[2]&9n)))throw Error("prefix admission");
 let rand=rng(12345+k),samples=128;function parity(x){let p=0;while(x){x&=x-1n;p^=1}return p}
 for(let s=0;s<samples;s++){let A=0n,B=0n;for(let i=0;i<2*k;i++){if(rand(2))A|=1n<<BigInt(i);if(rand(2))B|=1n<<BigInt(i)}let got=0n;for(let [a,b,c] of t)if(parity(a&A)&&parity(b&B))got^=c;let want=0n;for(let i=0;i<2;i++)for(let j=0;j<2;j++){let v=0;for(let h=0;h<k;h++)v^=Number((A>>BigInt(i*k+h)&1n)&(B>>BigInt(2*h+j)&1n));want|=BigInt(v)<<BigInt(i*2+j)}if(got!==want)throw Error("dense oracle")}
 return {shape:[2,k,2],prefix,remaining,lower:lb,rank:t.length,naive:4*k,saved:4*k-t.length,basisChanges:ops,oracleCases:samples,verified:true,terms:t.map(x=>x.map(String))}
 }
 return Array.from({length:12},(_,i)=>run(i+1)).concat([16,24,32,64,128].map(run))
}
const fs=require('node:fs'),path=require('node:path');console.log(JSON.stringify(scale(JSON.parse(fs.readFileSync(path.join(__dirname,'mmg030_results.json'),'utf8'))),null,2));
