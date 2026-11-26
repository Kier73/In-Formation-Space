function campaign(){
const bits=x=>{let a=[],i=0;while(x){if(x&1n)a.push(i);x>>=1n;i++}return a};
const randgen=s=>n=>{s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)%n};
const dim=([a,b,c])=>[a*b,b*c,a*c];
const strassen=[[9,9,9],[12,1,12],[1,10,10],[8,5,5],[3,8,3],[5,3,8],[10,12,1]].map(t=>t.map(BigInt));
function naive([a,b,c]){let t=[];for(let i=0;i<a;i++)for(let j=0;j<b;j++)for(let k=0;k<c;k++)t.push([1n<<BigInt(i*b+j),1n<<BigInt(j*c+k),1n<<BigInt(i*c+k)]);return t}
function outer(x,y,d){let z=0n;for(let i of bits(x))z^=y<<BigInt(i*d);return z}
function verify(ts,s){let [a,b,c]=s,[u,v,w]=dim(s),rows=Array(w).fill(0n);for(let t of ts){if(!t.every((x,i)=>x>0n&&x>>BigInt([u,v,w][i])===0n))return false;let z=outer(t[0],t[1],v);for(let k of bits(t[2]))rows[k]^=z}for(let i=0;i<a;i++)for(let k=0;k<c;k++){let z=0n;for(let j=0;j<b;j++)z^=1n<<BigInt((i*b+j)*v+j*c+k);if(rows[i*c+k]!==z)return false}return true}
function embedded(s,t,src,offset){let [a,b,c]=s,[x,y,z]=src,[i,j,k]=offset;let pairs=[[y,b,i,j],[z,c,j,k],[z,c,i,k]];return t.map((q,l)=>{let [old,newd,dr,dc]=pairs[l],v=0n;for(let h of bits(q))v|=1n<<BigInt((Math.floor(h/old)+dr)*newd+h%old+dc);return v})}
function seed(s){let [a,b,c]=s,ts=naive(s);for(let i=0;i+1<a;i+=2)for(let j=0;j+1<b;j+=2)for(let k=0;k+1<c;k+=2){let del=new Set(naive([2,2,2]).map(t=>embedded(s,t,[2,2,2],[i,j,k]).join(",")));ts=ts.filter(t=>!del.has(t.join(",")));ts.push(...strassen.map(t=>embedded(s,t,[2,2,2],[i,j,k])))}return ts}
function quotient(ts,s,axis){let b=(axis+1)%3,c=(axis+2)%3,d=dim(s)[c],basis=new Map(),out=[],removed=0,work=0;
for(let t of ts){if(!t.every(Boolean)){removed++;continue}let v=outer(t[b],t[c],d),m=0n;while(v){let pivot=v.toString(2).length-1;let q=basis.get(pivot);if(!q){let i=out.length;basis.set(pivot,[v,m^(1n<<BigInt(i))]);out.push(t.slice());break}v^=q[0];m^=q[1];work++}
if(!v){for(let i of bits(m))out[i][axis]^=t[axis];removed++}}
return {ts:out.filter(t=>t.every(Boolean)),removed,work}}
function compress(ts,s){let removed=0,work=0;for(;;){let len=ts.length;for(let a=0;a<3;a++){let q=quotient(ts,s,a);ts=q.ts;removed+=q.removed;work+=q.work}if(ts.length===len)return {ts,removed,work}}}
function bound(s){let [a,b,c]=s;return Math.max(a*b+c-1,b*c+a-1,a*c+b-1)}
function target(s){let v=BigInt(s[0]*s[1]*s[2]),r=0;while(BigInt(r+1)**4n<v**3n)r++;return r}
function walk(s,start,steps,seedval,useQ){let rand=randgen(seedval),cur=start.map(t=>t.slice()),best=cur.map(t=>t.slice()),events=[],qCalls=0,qRem=0,qWork=0,stepsDone=0,slack=3,last=0; if(!verify(cur,s))throw Error("bad seed");
for(let step=1;step<=steps;step++){if(step-last>1500||cur.length>best.length+slack){cur=best.map(t=>t.slice());last=step}if(best.length===bound(s))break;stepsDone++;
let a=rand(3),b=(a+1)%3,c=(a+2)%3,groups=new Map();for(let i=0;i<cur.length;i++){let v=cur[i][a];if(!groups.has(v))groups.set(v,[]);groups.get(v).push(i)}let gs=[...groups.values()].filter(g=>g.length>1),i,j,plus=false;
if(gs.length&&(cur.length>=best.length+slack||rand(100)<85)){let g=gs[rand(gs.length)];i=g[rand(g.length)];do{j=g[rand(g.length)]}while(i===j)}else if(cur.length<best.length+slack){i=rand(cur.length);do{j=rand(cur.length)}while(i===j);plus=cur[i][a]!==cur[j][a]}else continue;
let t=cur[i].slice(),u=cur[j].slice(),v=t.slice(),w=u.slice();if(plus){let extra=t.slice();extra[a]^=u[a];v[a]=u[a];cur.push(extra)}v[c]^=u[c];w[b]^=t[b];cur[i]=v;cur[j]=w;cur=cur.filter(t=>t.every(Boolean));
if(useQ&&(step%8===0||cur.length<best.length)){let q=compress(cur,s);cur=q.ts;qCalls++;qRem+=q.removed;qWork+=q.work}else{
for(let axis=0;axis<3;axis++){let m=new Map(),p=(axis+1)%3,q=(axis+2)%3;for(let t of cur){let key=t[p]+":"+t[q];if(m.has(key))m.get(key)[axis]^=t[axis];else m.set(key,t.slice())}cur=[...m.values()].filter(t=>t.every(Boolean))}
}
if(cur.length<best.length){if(!verify(cur,s))throw Error("invalid reduction");best=cur.map(t=>t.slice());events.push([step,best.length]);last=step}
if(step%1000===0&&!verify(cur,s))throw Error("invalid walk")}
if(!verify(best,s))throw Error("bad end");return {shape:s,initial:start.length,best:best.length,target:target(s),lower:bound(s),steps:stepsDone,seed:seedval,quotient:useQ,qCalls,qRem,qWork,events,terms:best.map(t=>t.map(String))}}
let tests=0; // Explicit nonduplicate dependence: xy+xz+x(y+z)=0.
let control=[[1n,1n,1n],[2n,1n,2n],[4n,1n,3n]],q=quotient(control,[2,2,2],0);
if(q.ts.length!==2||q.removed!==1)throw Error("quotient control");
function signature(ts,s){let [a,b,c]=dim(s),rows=Array(c).fill(0n);for(let t of ts)for(let i of bits(t[2]))rows[i]^=outer(t[0],t[1],b);return rows.join(",")}
if(signature(control,[2,2,2])!==signature(q.ts,[2,2,2]))throw Error("control equality");
let r=randgen(7301);for(let j=0;j<500;j++){let s=[2,2,2],t=Array.from({length:12},()=>Array.from({length:3},()=>BigInt(r(15)+1)));let q=compress(t,s);if(signature(t,s)!==signature(q.ts,s))throw Error("random quotient");tests++}
let cases=[];for(let s of [[2,2,2],[2,2,3],[2,3,3],[2,3,4],[3,3,3],[3,3,4],[4,4,4]]){let start=seed(s);for(let i=0;i<2;i++)cases.push(walk(s,start,18000,101+s[0]*100+s[1]*10+s[2]+i,i===1))}
let prune=0,feasible=0,shapes=0;for(let a=1;a<=24;a++)for(let b=a;b<=24;b++)for(let c=b;c<=24;c++){if(a*b*c===1)continue;shapes++;if(bound([a,b,c])>target([a,b,c]))prune++;else feasible++}
return {random_quotient_tests:tests,nonduplicate_control:true,shapes,pruned_by_slice_bound:prune,not_pruned:feasible,cases};
}
console.log(JSON.stringify(campaign(),null,2));
