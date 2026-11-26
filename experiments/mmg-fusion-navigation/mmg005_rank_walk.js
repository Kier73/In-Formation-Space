function campaign(){
const bits=x=>{const a=[];let i=0;while(x){if(x&1n)a.push(i);x>>=1n;i++}return a};
const strassen=[[9,9,9],[12,1,12],[1,10,10],[8,5,5],[3,8,3],[5,3,8],[10,12,1]].map(t=>t.map(BigInt));
function naive(n){let out=[];for(let i=0;i<n;i++)for(let j=0;j<n;j++)for(let k=0;k<n;k++)out.push([1n<<BigInt(i*n+j),1n<<BigInt(j*n+k),1n<<BigInt(i*n+k)]);return out}
function power(a,n,b,m){const nm=n*m;const lift=(x,y)=>{let z=0n;for(const i of bits(x))for(const j of bits(y)){const r=Math.floor(i/n)*m+Math.floor(j/m),c=(i%n)*m+j%m;z|=1n<<BigInt(r*nm+c)}return z};return a.flatMap(x=>b.map(y=>x.map((z,i)=>lift(z,y[i]))))}
function verify(ts,n){const d=n*n, rows=Array(d).fill(0n);for(const [a,b,c] of ts){if(!a||!b||!c||[a,b,c].some(x=>x>>BigInt(d)))return false;let v=0n;for(const i of bits(a))for(const j of bits(b))v|=1n<<BigInt(i*d+j);for(const k of bits(c))rows[k]^=v}
for(let i=0;i<n;i++)for(let k=0;k<n;k++){let expected=0n;for(let j=0;j<n;j++)expected|=1n<<BigInt((i*n+j)*d+j*n+k);if(rows[i*n+k]!==expected)return false}return true}
function reduce(ts){let count=0;for(;;){let changed=false;for(let a=0;a<3;a++){let m=new Map(), b=(a+1)%3,c=(a+2)%3;for(const t of ts){if(!t.every(Boolean)){count++;changed=true;continue}let key=t[b]+":"+t[c];if(m.has(key)){m.get(key)[a]^=t[a];count++;changed=true}else m.set(key,t.slice())}ts=[...m.values()].filter(t=>t.every(Boolean))}if(!changed)return [ts,count]}}
function rng(seed){return n=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)%n}}
function search(n,initial,steps,seed,slack){let rand=rng(seed),best=initial.map(t=>t.slice()),cur=best.map(t=>t.slice()),moves={flip:0,plus:0,reduced:0,restarts:0},events=[],budget=slack; if(!verify(best,n))throw Error("bad seed");let last=0;
for(let step=1;step<=steps;step++){
if(step-last>2500||cur.length>best.length+budget){cur=best.map(t=>t.slice());last=step;moves.restarts++}
let axis=rand(3),b=(axis+1)%3,c=(axis+2)%3, groups=new Map();for(let i=0;i<cur.length;i++){let key=cur[i][axis];if(!groups.has(key))groups.set(key,[]);groups.get(key).push(i)}
let pairs=[...groups.values()].filter(g=>g.length>1),i,j,plus=false;
if(pairs.length&&(cur.length>=best.length+budget||rand(100)<85)){let g=pairs[rand(pairs.length)];i=g[rand(g.length)];do{j=g[rand(g.length)]}while(i===j)}
else if(cur.length<best.length+budget){i=rand(cur.length);do{j=rand(cur.length)}while(i===j);plus=cur[i][axis]!==cur[j][axis]}else continue;
let t=cur[i].slice(),s=cur[j].slice(),u=t.slice(),v=s.slice(),w=null;
if(plus){w=t.slice();w[axis]^=s[axis];u[axis]=s[axis];moves.plus++}else moves.flip++;
u[c]^=s[c];v[b]^=t[b];cur[i]=u;cur[j]=v;if(w)cur.push(w);
let rr=reduce(cur);cur=rr[0];moves.reduced+=rr[1];
if(cur.length<best.length){if(!verify(cur,n))throw Error("bad identity");best=cur.map(t=>t.slice());events.push({step,rank:best.length});last=step}
if(step%1000===0&&!verify(cur,n))throw Error("walk corrupted");
}
let target=0;while(BigInt(target+1)**4n<BigInt(n)**9n)target++;
let bad=best.map(t=>t.slice());bad[0][0]^=1n;if(verify(bad,n))throw Error("tamper accepted");
return {n,initial:initial.length,best:best.length,target,steps,seed,slack,moves,events,verified:verify(best,n),terms:best.map(t=>t.map(String))}}
const jobs=[[2,strassen,10000,1,3],[3,naive(3),60000,17,3],[4,power(strassen,2,strassen,2),100000,31,4],[4,power(strassen,2,strassen,2),100000,42,6],[8,power(power(strassen,2,strassen,2),4,strassen,2),10000,51,4]];
return jobs.map(j=>search(...j));
}
console.log(JSON.stringify(campaign(),null,2));
