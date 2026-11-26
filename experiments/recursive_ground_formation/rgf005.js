function rgf005(){
"use strict";
const P=2305843009213693951n,D=3,MAX=48;
const m=x=>(x%P+P)%P, ok=(b,s)=>{if(!b)throw Error(s)};
const C=()=>({field:0,division:0,visits:0}),cost=c=>c.field+c.division+c.visits;
const A=(a,b,c)=>(c.field++,m(a+b)),M=(a,b,c)=>(c.field++,m(a*b));
const zero=n=>Array(n).fill(0n),unit=(n,i)=>zero(n).map((_,j)=>i===j?1n:0n);
const same=(a,b)=>a.length===b.length&&a.every((x,i)=>x===b[i]);
function inv(a,c){let r=P,s=m(a),u=0n,v=1n;while(s){c.division++;let q=r/s;[r,s]=[s,r-q*s];[u,v]=[v,u-q*v];c.field+=2}ok(r===1n,"inverse");return m(u)}
function dot(a,b,c){ok(a.length===b.length,"dot");let x=0n;for(let j=0;j<a.length;j++){c.visits++;if(a[j]&&b[j])x=A(x,M(a[j],b[j],c),c)}return x}
const proj=(B,x,c)=>B.map(r=>dot(r,x,c));
function axpy(a,b,q,c){return a.map((x,i)=>A(x,M(b[i],q,c),c))}
function dual(b,T,c){let r=zero(b.length);for(let i=0;i<b.length;i++){c.visits++;if(b[i])for(let j=0;j<b.length;j++){c.visits++;if(T[i][j])r[j]=A(r[j],M(b[i],T[i][j],c),c)}}return r}
const key=i=>i.slice().sort((a,b)=>a-b).join(","),ids=s=>s===""?[]:s.split(",").map(Number);
function put(p,s,a,c){c.visits++;let b=A(p.get(s)||0n,a,c);if(b)p.set(s,b);else p.delete(s);ok(p.size<=50000,"term cap")}
function poly(raw,c){let p=new Map();for(const t of raw)put(p,key(t.i),t.a,c);return p}
function ev(p,x,c){let y=0n;for(const [s,a] of p){c.visits++;let b=a;for(const i of ids(s))b=M(b,x[i],c);y=A(y,b,c)}return y}
function grad(p,n,c){let g=new Map();for(const [s,a] of p){let t=ids(s);for(let j=0;j<t.length;j++){let k=key(t.filter((_,i)=>i!==j));if(!g.has(k))g.set(k,zero(n));g.get(k)[t[j]]=A(g.get(k)[t[j]],a,c);c.visits++}}return [...g.values()]}
function gradCheck(raw,n,c){let g=new Map();for(const t of raw){let ex=new Map();for(const i of t.i){c.visits++;ex.set(i,(ex.get(i)||0)+1)}for(const [j,count] of ex){let z=[];for(const [i,e] of ex)for(let k=0;k<e-(i===j?1:0);k++)z.push(i);let s=key(z);if(!g.has(s))g.set(s,zero(n));let r=g.get(s);r[j]=A(r[j],M(t.a,BigInt(count),c),c)}}return [...g.values()]}
function validate(s,c){ok(Number.isInteger(s.n)&&s.n>=1&&s.n<=MAX&&s.actions.length>=1&&s.actions.length<=4&&s.raw.length<=50000,"source bounds");
const field=x=>typeof x==="bigint"&&x>=0n&&x<P;
for(const t of s.raw){c.visits+=1+t.i.length;ok(field(t.a)&&t.i.length<=D&&t.i.every(i=>Number.isInteger(i)&&i>=0&&i<s.n),"source polynomial")}
for(const a of s.actions){ok(a.T.length===s.n&&a.b.length===s.n&&a.b.every(field),"action shape");for(const r of a.T){c.visits+=r.length;ok(r.length===s.n&&r.every(field),"action row")}}}
function closure(g,actions,n,c){
 let B=[],p=[],images=0;
 function insert(row){let v=row.slice();for(let j=0;j<B.length;j++){c.visits++;if(v[p[j]])v=axpy(v,B[j],-v[p[j]],c)}
 let i=v.findIndex(a=>a!==0n);if(i<0)return;let q=inv(v[i],c);B.push(v.map(a=>M(a,q,c)));p.push(i)}
 for(const r of g)insert(r);const initial=B.length;
 for(let i=0;i<B.length;i++)for(const a of actions){insert(dual(B[i],a.T,c));images++}
 for(let j=B.length-1;j>=0;j--)for(let i=0;i<j;i++)if(B[i][p[j]])B[i]=axpy(B[i],B[j],-B[i][p[j]],c);
 return {B,p,initial,images}
}
function restrict(f,p,c){let q=new Map(),index=new Map(p.map((j,i)=>[j,i]));for(const [s,a] of f){let t=ids(s);c.visits+=1+t.length;if(t.every(i=>index.has(i)))put(q,key(t.map(i=>index.get(i))),a,c)}return q}
function form(s,c){validate(s,c);let f=poly(s.raw,c),g=closure(grad(f,s.n,c),s.actions,s.n,c);let {B,p}=g;
 return {...g,q:restrict(f,p,c),actions:s.actions.map(a=>({T:B.map(b=>{let r=dual(b,a.T,c);return p.map(i=>r[i])}),b:proj(B,a.b,c)}))}
}
// Independent saturation: right-pivot elimination, column-index dual multiplication.
function independent(g,actions,n,c){
 let piv=new Map(),queue=[];
 function ins(row){let v=row.slice();for(let j=n-1;j>=0;j--){c.visits++;if(!v[j])continue;
  if(piv.has(j)){let r=piv.get(j),f=M(v[j],inv(r[j],c),c);for(let k=0;k<=j;k++)v[k]=A(v[k],-M(f,r[k],c),c)}
  else{piv.set(j,v);queue.push(v);return}}}
 for(const r of g)ins(r);
 for(let i=0;i<queue.length;i++)for(const a of actions){let v=Array.from({length:n},(_,j)=>dot(queue[i],a.T.map(r=>r[j]),c));ins(v)}
 return queue.length
}
function verify(s,g,c){try{
 validate(s,c);const r=g.B.length,n=s.n,field=x=>typeof x==="bigint"&&x>=0n&&x<P;
 ok(r<=n&&g.B.every(b=>b.length===n&&b.every(field))&&g.actions.length===s.actions.length&&g.q instanceof Map,"chart");
 ok(independent(gradCheck(s.raw,n,c),s.actions,n,c)===r&&independent(g.B,[],n,c)===r,"minimum rank");
 // Check all original polynomial coefficients, independent substitution.
 let out=new Map(),visits=0;
 for(const [s,a] of g.q){let t=ids(s);ok(key(t)===s&&t.length<=D&&t.every(i=>Number.isInteger(i)&&i>=0&&i<r)&&field(a)&&a!==0n,"q term");
  function rec(j,l,v){if(j===t.length){put(out,key(l),v,c);return}for(let i=0;i<n;i++){c.visits++;ok(++visits<=4000000,"expansion budget");if(g.B[t[j]][i])rec(j+1,[...l,i],M(v,g.B[t[j]][i],c))}}
  rec(0,[],a)
 }
 let ordered=s.raw.map(t=>({s:key(t.i),a:t.a})).sort((a,b)=>a.s.localeCompare(b.s)),ref=new Map();
 for(let i=0;i<ordered.length;){let j=i,a=0n;while(j<ordered.length&&ordered[j].s===ordered[i].s){a=A(a,ordered[j++].a,c);c.visits++}if(a)ref.set(ordered[i].s,a);i=j}
 ok(out.size===ref.size&&[...ref].every(([k,v])=>out.get(k)===v),"polynomial identity");
 for(let k=0;k<s.actions.length;k++){let a=s.actions[k],b=g.actions[k];ok(b.T.length===r&&b.b.length===r&&b.T.every(t=>t.length===r&&t.every(field))&&b.b.every(field),"induced action shape");
  for(let i=0;i<r;i++){let lhs=Array.from({length:n},(_,j)=>dot(g.B[i],a.T.map(t=>t[j]),c));let rhs=Array.from({length:n},(_,j)=>dot(b.T[i],g.B.map(t=>t[j]),c));ok(same(lhs,rhs)&&dot(g.B[i],a.b,c)===b.b[i],"action identity")}}
 return true
 }catch{return false}}
function sparse(a,c){return {T:a.T.map(r=>r.flatMap((v,j)=>{c.visits++;return v?[[j,v]]:[]})),b:a.b.slice()}}
function apply(a,x,c){return a.T.map((r,i)=>{let z=a.b[i];for(const [j,v] of r){c.visits++;z=A(z,M(v,x[j],c),c)}return z})}
function compose(a,b,c){let T=[],bias=[];for(let i=0;i<a.T.length;i++){let r=new Map(),v=a.b[i];for(const [j,w] of a.T[i]){c.visits++;v=A(v,M(w,b.b[j],c),c);for(const [k,t] of b.T[j]){c.visits++;let z=A(r.get(k)||0n,M(w,t,c),c);if(z)r.set(k,z);else r.delete(k)}}T.push([...r]);bias.push(v)}return {T,b:bias}}
function processor(actions,c){let powers=actions.map(a=>[sparse(a,c)]);return {powers,run(x,word,c){let observations=[];for(const [i,count] of word){ok(Number.isInteger(i)&&i>=0&&i<powers.length&&typeof count==="bigint"&&count>=0n&&count<1n<<128n,"word");let t=count,j=0;while(t){c.visits++;if(!powers[i][j])powers[i].push(compose(powers[i][j-1],powers[i][j-1],c));if(t&1n)x=apply(powers[i][j],x,c);t>>=1n;j++}observations.push(x.slice())}return observations}}}
let seed=76129;function rnd(n){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return (seed>>>8)%n}
const rand=()=>BigInt(1+rnd(23));
function fixture(n,r,degree){
 // Hidden invertible shear w=Cx, x_i=w_i-shear_i*w_spectators. Source explicitly expanded.
 let H=Array.from({length:n},(_,i)=>unit(n,i));for(let i=0;i<r;i++)for(let j=r;j<n;j++)if((j-r)%4===i%4)H[i][j]=rand();
 let K=H.map((row,i)=>row.map((a,j)=>i<r&&j>=r?m(-a):a));
 let latent=[];
 for(let a=0;a<3;a++){
 let idx=Array.from({length:n},(_,i)=>i),scale=Array.from({length:n},rand),b=Array.from({length:n},rand);
 for(let i=0;i<r;i++)idx[i]=a===0?(i+1)%r:a===1?(i+r-1)%r:i;
 for(let i=r;i<n;i++)idx[i]=r+(i-r+(a===1?1:2))%(n-r||1);
 latent.push({idx,scale,b})
 }
 let setup=C();let actions=latent.map(l=>{let W=l.idx.map((j,i)=>H[j].map(v=>M(v,l.scale[i],setup)));return {T:K.map(row=>Array.from({length:n},(_,j)=>dot(row,W.map(t=>t[j]),setup))),b:proj(K,l.b,setup)}});
 let raw=[],row=H[0];
 function expand(j,i,a){if(j===degree){raw.push({i,a});return}for(let k=0;k<n;k++)if(row[k])expand(j+1,[...i,k],m(a*row[k]))}
 expand(0,[],1n);raw.push({i:[],a:7n});
 // Cancellation outside the true observation.
 raw.push({i:[n-1],a:13n},{i:[n-1],a:P-13n});
 return {s:{n,actions,raw},H,K,latent,degree,fixtureWork:cost(setup)}
}
// Independent oracle in hidden weighted-permutation chart, not source matrix powers.
function latentStep(l,x,c){return l.idx.map((j,i)=>A(M(l.scale[i],x[j],c),l.b[i],c))}
function latentPower(l,x,t,c){let idx=l.idx.slice(),a=l.scale.slice(),b=l.b.slice();while(t){if(t&1n)x=idx.map((j,i)=>A(M(a[i],x[j],c),b[i],c));let I=idx.map(j=>idx[j]),A2=idx.map((j,i)=>M(a[i],a[j],c)),B2=idx.map((j,i)=>A(M(a[i],b[j],c),b[i],c));idx=I;a=A2;b=B2;t>>=1n;c.visits++}return x}
function oracle(f,x,word,c){let w=proj(f.H,x,c),out=[];for(const [a,n] of word){w=latentPower(f.latent[a],w,n,c);let v=7n,z=1n;for(let k=0;k<f.degree;k++)z=M(z,w[0],c);v=A(v,z,c);out.push({x:proj(f.K,w,c),y:v})}return out}
function fixtureCheck(f,c){for(let a=0;a<f.s.actions.length;a++)for(let j=-1;j<f.s.n;j++){let x=j<0?zero(f.s.n):unit(f.s.n,j);let source=apply(sparse(f.s.actions[a],c),x,c);ok(same(proj(f.H,source,c),latentStep(f.latent[a],proj(f.H,x,c),c)),"fixture action identity")}}
function campaign(name,n,r,N){
 let f=fixture(n,r,3),s=f.s,formation=C(),qualification=C(),full=C(),compact=C(),audit=C(),fixtureAudit=C(),eager=C();
 fixtureCheck(f,fixtureAudit);validate(s,full);let fpoly=poly(s.raw,full);let g=form(s,formation);ok(g.initial===1&&g.B.length===r,"hidden closure rank");ok(verify(s,g,qualification),"qualification");
 let fp=processor(s.actions,full),cp=processor(g.actions,compact),crossover=null,checks=0,shortChecks=0;
 for(let i=0;i<N;i++){
 let x=Array.from({length:n},rand),word=Array.from({length:5},(_,j)=>[rnd(3),i%5===0?BigInt(1+rnd(7)):10n**24n+BigInt(rnd(100000))]);
 let ref=oracle(f,x,word,audit),fs=fp.run(x,word,full),cs=cp.run(proj(g.B,x,compact),word,compact);
 for(let j=0;j<word.length;j++){ok(same(fs[j],ref[j].x)&&ev(fpoly,fs[j],full)===ref[j].y,"full oracle");
 ok(same(cs[j],proj(g.B,ref[j].x,audit))&&ev(g.q,cs[j],compact)===ref[j].y,"compact oracle");checks+=2}
 if(i%5===0){let y=x.slice();for(let j=0;j<word.length;j++){let [a,t]=word[j];for(let k=0n;k<t;k++)y=apply(sparse(s.actions[a],eager),y,eager);ok(same(y,ref[j].x),"eager");shortChecks++}}
 if(crossover===null&&cost(formation)+cost(qualification)+cost(compact)<cost(full))crossover=i+1
 }
 let entries=p=>p.powers.reduce((n,a)=>n+a.reduce((s,b)=>s+b.b.length+b.T.reduce((u,r)=>u+r.length,0),0),0);
 return {name,n,instantRank:g.initial,causalRank:g.B.length,closureImages:g.images,tasks:N,checks,shortChecks,crossover,work:{full:cost(full),compact:cost(formation)+cost(qualification)+cost(compact),formation:cost(formation),qualification:cost(qualification),compactRuntime:cost(compact),oracle:cost(audit),fixtureAudit:cost(fixtureAudit),eager:cost(eager)},cacheFieldEntries:{full:entries(fp),compact:entries(cp)},ledger:{full,compact,formation,qualification,audit,fixtureAudit,eager}}
}
const campaigns=[campaign("hidden-causal-rank-four",32,4,24),campaign("hidden-causal-rank-eight",32,8,16),campaign("full-rank-control",12,12,12),campaign("single-use-control",32,4,1)];
const c=C(),f=fixture(16,4,3),s=f.s,g=form(s,c);ok(verify(s,g,c),"control source");
let instant=form({...s,actions:[{T:Array.from({length:s.n},(_,i)=>unit(s.n,i)),b:zero(s.n)}]},c);
ok(instant.B.length===1&&!verify(s,instant,c),"instant chart accepted");
let bad={...g,actions:g.actions.map(a=>({T:a.T.map(r=>r.slice()),b:a.b.slice()}))};bad.actions[0].b[0]=m(bad.actions[0].b[0]+1n);ok(!verify(s,bad,c),"bad induced bias");
let wrong={...g,q:new Map(g.q)};wrong.q.set("",m((wrong.q.get("")||0n)+1n));ok(!verify(s,wrong,c),"bad observation");
let changed={...s,actions:s.actions.map(a=>({T:a.T.map(r=>r.slice()),b:a.b.slice()}))};changed.actions[0].b[0]=m(changed.actions[0].b[0]+1n);ok(!verify(changed,g,c),"stale source accepted");
let x=zero(s.n),y=unit(s.n,1),p=poly(s.raw,c),a=sparse(s.actions[0],c);ok(ev(p,x,c)===ev(p,y,c)&&ev(p,apply(a,x,c),c)!==ev(p,apply(a,y,c),c),"future ambiguity");
let xx=Array.from({length:s.n},rand),ab=processor(s.actions,c),v1=ab.run(xx,[[0,1n],[2,1n]],c).at(-1),v2=ab.run(xx,[[2,1n],[0,1n]],c).at(-1);ok(!same(v1,v2),"action order");
let constant={...s,raw:[{i:[],a:9n}]},z=form(constant,c);ok(z.B.length===0&&verify(constant,z,c)&&ev(z.q,[],c)===9n,"constant");
return {version:"RGF-005",prime:P.toString(),seed:76129,campaigns,controls:{instantChart:"refused",changedActionBias:"refused",changedObservation:"refused",staleSource:"refused",futureAmbiguity:"observed",noncommutingOrder:"observed",constantRank:0}}
}

console.log(JSON.stringify(rgf005(),null,2));
