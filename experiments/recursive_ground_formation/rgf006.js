function rgf006(){
"use strict";
const P=2305843009213693951n,D=4,K=D+1,ok=(x,s)=>{if(!x)throw Error(s)};
const mod=x=>(x%P+P)%P, C=()=>({field:0,division:0,visits:0,exponent:0}),cost=c=>Object.values(c).reduce((a,b)=>a+b,0);
const A=(a,b,c)=>(c.field++,mod(a+b)),M=(a,b,c)=>(c.field++,mod(a*b));
const zeros=n=>Array(n).fill(0n),unit=(n,i)=>zeros(n).map((_,j)=>i===j?1n:0n),eq=(a,b)=>a.length===b.length&&a.every((v,i)=>v===b[i]);
function pow(a,n,p,c){let z=1n;a=(a%p+p)%p;while(n){c.exponent++;if(n&1n){z=z*a%p;c.field++}a=a*a%p;c.field++;n>>=1n}return z}
function inv(a,c){let r=P,s=mod(a),u=0n,v=1n;while(s){c.division++;let q=r/s;[r,s]=[s,r-q*s];[u,v]=[v,u-q*v];c.field+=2}ok(r===1n,"inverse");return mod(u)}
function dot(a,b,c){ok(a.length===b.length,"shape");let y=0n;for(let i=0;i<a.length;i++){c.visits++;if(a[i]&&b[i])y=A(y,M(a[i],b[i],c),c)}return y}
const mv=(T,x,c)=>T.map(r=>dot(r,x,c));
function mm(a,b,c){return a.map(r=>Array.from({length:b[0]?.length||0},(_,j)=>dot(r,b.map(t=>t[j]),c)))}
function matpow(T,t,c){let R=T.map((_,i)=>unit(T.length,i));while(t){c.exponent++;if(t&1n)R=mm(T,R,c);t>>=1n;if(t)T=mm(T,T,c)}return R}
function features(x,c){return Array.from({length:K},(_,i)=>M(pow(x[0],BigInt(D-i),P,c),pow(x[1],BigInt(i),P,c),c))}
const f=[1n,0n,0n,0n,1n], I=[[1n,0n],[0n,1n]], R=[[0n,P-1n],[1n,0n]], S=[[2n,0n],[0n,2n]], H=[[1n,1n],[0n,1n]], Z=[[0n,0n],[0n,0n]];
const edge=[
 {name:"calm-rotate",from:0,to:0,T:R},{name:"calm-scale",from:0,to:0,T:S},
 {name:"enter-rich-reset",from:0,to:1,T:Z},{name:"rich-rotate",from:1,to:1,T:R},
 {name:"rich-scale",from:1,to:1,T:S},{name:"rich-shear",from:1,to:1,T:H},
 {name:"leave-rich",from:1,to:0,T:I}];
// Homogeneous polynomial pullback: degree stays fixed under linear actions.
function lift(T,c){return Array.from({length:K},(_,i)=>{let a=[1n];for(let j=0;j<D;j++){let b=zeros(a.length+1),r=T[j<D-i?0:1];for(let k=0;k<a.length;k++){b[k]=A(b[k],M(a[k],r[0],c),c);b[k+1]=A(b[k+1],M(a[k],r[1],c),c)}a=b}return a})}
function basis(rows,c){let B=[],p=[];for(let a of rows){let v=a.slice();for(let i=0;i<B.length;i++){c.visits++;let q=v[p[i]];if(q)v=v.map((x,j)=>A(x,-M(q,B[i][j],c),c))}
 let j=v.findIndex(x=>x!==0n);if(j<0)continue;let q=inv(v[j],c);B.push(v.map(x=>M(x,q,c)));p.push(j)}
 for(let j=B.length-1;j>=0;j--)for(let i=0;i<j;i++){let q=B[i][p[j]];if(q)B[i]=B[i].map((x,k)=>A(x,-M(q,B[j][k],c),c))}
 return {B,p}}
function form(c){const L=edge.map(e=>lift(e.T,c)),q=[basis([f],c),basis([f],c)];let rounds=0;
 while(true){let n=q.map((g,i)=>basis([...g.B,...edge.flatMap((e,j)=>e.from===i?mm(q[e.to].B,L[j],c):[])],c));rounds++;let stable=n.every((g,i)=>g.B.length===q[i].B.length);q.splice(0,2,...n);if(stable)break}
 const maps=edge.map((e,j)=>mm(q[e.to].B,L[j],c).map(r=>q[e.from].p.map(i=>r[i])));
 return {L,q,maps,decode:q.map(g=>g.p.map(i=>f[i])),rounds}}
function rank(rows,c){let a=rows.map(r=>r.slice()),r=0;for(let j=K-1;j>=0&&r<a.length;j--){let k=r;while(k<a.length&&!a[k][j]){k++;c.visits++}if(k===a.length)continue;[a[k],a[r]]=[a[r],a[k]];let invp=inv(a[r][j],c);for(let i=r+1;i<a.length;i++){let v=M(a[i][j],invp,c);for(let k=0;k<=j;k++)a[i][k]=A(a[i][k],-M(v,a[r][k],c),c)}r++}return r}
// Independent feature evaluation by direct repeated product, not lift or exponentiation.
function directFeatures(x,c){return Array.from({length:K},(_,i)=>{let a=1n;for(let j=0;j<D;j++)a=M(a,x[j<D-i?0:1],c);return a})}
function verify(g,c){try{
 ok(g.q.length===2&&g.maps.length===edge.length&&g.L.length===edge.length,"count");
 // Independent minimality: grow independent raw word pullbacks using projective evaluation vectors.
 // Evaluation at D+1 distinct t is injective on homogeneous degree D polynomials.
 const samples=Array.from({length:K},(_,i)=>[1n,BigInt(31+i)]);
 for(let j=0;j<edge.length;j++)for(const x of samples)ok(eq(mv(g.L[j],directFeatures(x,c),c),directFeatures(mv(edge[j].T,x,c),c)),"lift identity");
 // Separate low-dimensional rank routine and raw-word queue on certified lifts.
 const span=[[f.slice()],[f.slice()]],front=[[0,f.slice()],[1,f.slice()]];
 for(let k=0;k<front.length;k++){let [target,r]=front[k];for(let j=0;j<edge.length;j++){let e=edge[j];if(e.to!==target)continue;let row=Array.from({length:K},(_,i)=>dot(r,g.L[j].map(t=>t[i]),c));
 let old=span[e.from];if(rank([...old,row],c)>old.length){old.push(row);front.push([e.from,row])}}}
 for(let i=0;i<2;i++){let B=g.q[i].B;ok(B.length===span[i].length&&rank(B,c)===B.length&&rank([...B,...span[i]],c)===B.length,"minimality");
 for(const x of samples)ok(dot(g.decode[i],mv(B,directFeatures(x,c),c),c)===dot(f,directFeatures(x,c),c),"decoder")}
 for(let j=0;j<edge.length;j++){let e=edge[j];for(const x of samples){let a=mv(g.q[e.from].B,directFeatures(x,c),c),b=mv(g.q[e.to].B,directFeatures(mv(e.T,x,c),c),c);ok(eq(mv(g.maps[j],a,c),b),"phase transition")}}
 return true}catch{return false}}
function global(c,L){let g=basis([f],c);while(true){let b=basis([...g.B,...L.flatMap(T=>mm(g.B,T,c))],c);if(b.B.length===g.B.length)return g;g=b}}
function engine(Ts,c){const caches=Ts.map(T=>[T]);return {apply(i,t,x,c){let j=0;while(t){c.exponent++;if(!caches[i][j])caches[i].push(mm(caches[i][j-1],caches[i][j-1],c));if(t&1n)x=mv(caches[i][j],x,c);t>>=1n;j++}return x},entries:()=>caches.reduce((a,b)=>a+b.reduce((s,T)=>s+T.reduce((v,r)=>v+r.length,0),0),0)}}
function oracle(x,j,t,c){let e=edge[j];if(e.T===R){for(let i=0;i<Number(t%4n);i++)x=[mod(-x[1]),x[0]];return x}
 if(e.T===S){let a=pow(2n,t,P,c);return x.map(v=>M(a,v,c))}
 if(e.T===H)return [A(x[0],M(mod(t),x[1],c),c),x[1]];
 if(e.T===Z)return t?zeros(2):x;return x}
let seed=74319;function rnd(n){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return (seed>>>8)%n}
const rand=()=>BigInt(1+rnd(100000));
function campaign(name,N,blocks,rich){
 const formation=C(),qualification=C(),full=C(),fixed=C(),fluid=C(),audit=C();
 let g=form(formation);ok(verify(g,qualification),"qualification");
 let globalChart=global(fixed,g.L);ok(globalChart.B.length===5,"global rank");
 const maps=edge.map((_,j)=>mm(globalChart.B,g.L[j],fixed).map(r=>globalChart.p.map(i=>r[i])));
 // Verify static route too on independent evaluation points.
 for(let j=0;j<edge.length;j++)for(let k=0;k<K;k++){let x=[1n,BigInt(k+11)];ok(eq(mv(maps[j],mv(globalChart.B,directFeatures(x,fixed),fixed),fixed),mv(globalChart.B,directFeatures(mv(edge[j].T,x,fixed),fixed),fixed)),"global transition")}
 const base=engine(edge.map(e=>e.T),full),stat=engine(maps,fixed),dyn=engine(g.maps,fluid);
 let checks=0,switches=0,reseeds=0,crossover=null;
 for(let i=0;i<N;i++){
  let x=[rand(),rand()],a=x.slice(),b=mv(globalChart.B,features(x,fixed),fixed),mode=rich?1:0,z=mv(g.q[mode].B,features(x,fluid),fluid);
  for(let j=0;j<blocks;j++){
   // Rich -> calm, calm -> rich only via reset. Independent external reseed allowed after reset.
   let e=mode===0?(rich&&j%23===22?2:j%2):(j%7===6?6:j%3+3);
   let t=edge[e].from===edge[e].to?(i%8===0?BigInt(1+rnd(5)):10n**24n+BigInt(rnd(1000))):1n;
   x=oracle(x,e,t,audit);a=base.apply(e,t,a,full);b=stat.apply(e,t,b,fixed);
   z=dyn.apply(e,t,z,fluid);if(edge[e].to!==mode)switches++;mode=edge[e].to;
   const ref=dot(f,directFeatures(x,audit),audit);
   ok(eq(a,x)&&dot(f,features(a,full),full)===ref,"full output");
   ok(eq(b,mv(globalChart.B,directFeatures(x,audit),audit))&&dot(globalChart.p.map(i=>f[i]),b,fixed)===ref,"fixed output");
   ok(eq(z,mv(g.q[mode].B,directFeatures(x,audit),audit))&&dot(g.decode[mode],z,fluid)===ref,"fluid output");checks+=3;
   if(e===2){x=[rand(),rand()];a=x.slice();full.visits+=2;fixed.visits+=2;fluid.visits+=2;b=mv(globalChart.B,features(x,fixed),fixed);z=mv(g.q[mode].B,features(x,fluid),fluid);reseeds++}
  }
  if(crossover===null&&cost(formation)+cost(qualification)+cost(fluid)<cost(full))crossover=i+1
 }
 return {name,tasks:N,blocksPerTask:blocks,checks,switches,reseeds,phaseRanks:g.q.map(q=>q.B.length),staticRank:globalChart.B.length,closureRounds:g.rounds,crossover,work:{full:cost(full),fixed:cost(fixed)+cost(formation),fluid:cost(fluid)+cost(formation)+cost(qualification),formation:cost(formation),qualification:cost(qualification),fluidRuntime:cost(fluid),audit:cost(audit)},cacheEntries:{full:base.entries(),fixed:stat.entries(),fluid:dyn.entries()}}
}
const campaigns=[campaign("calm-reuse",48,32,false),campaign("mixed-morphology",32,64,true),campaign("single-use",1,2,false)];
// Independent exhaustive partition over F_17; check all finite state transitions.
const p=17,sm=x=>(x%p+p)%p,Q=([x,y])=>sm(x**4+y**4),states=Array.from({length:p*p},(_,i)=>[Math.floor(i/p),i%p]),acts=[([x,y])=>[sm(-y),x],([x,y])=>[sm(2*x),sm(2*y)],()=>[0,0],([x,y])=>[sm(x+y),y]];
function partition(n){let lab=states.map(Q),rounds=0;while(true){let map=new Map(),next=states.map((s,i)=>{let k=[lab[i],...acts.slice(0,n).map(a=>{let [x,y]=a(s);return lab[x*p+y]})].join(",");if(!map.has(k))map.set(k,map.size);return map.get(k)});rounds++;if(map.size===new Set(lab).size)return {classes:map.size,rounds};lab=next}}
let comparisons=0;for(const s of states){let q=Q(s);for(let j=0;j<3;j++){ok(Q(acts[j](s))===[q,sm(16*q),0][j],"finite morph");comparisons++}}
const small={states:states.length,comparisons,base:partition(3),shear:partition(4)};
ok(small.base.classes===13&&small.shear.classes===73,"partition");
const c=C(),g=form(c);ok(verify(g,c),"valid");
let bad={...g,maps:g.maps.map(T=>T.map(r=>r.slice()))};bad.maps[0][0][0]=mod(bad.maps[0][0][0]+1n);ok(!verify(bad,c),"bad transition");
ok(Q([1,0])===Q([0,1])&&Q(acts[3]([1,0]))!==Q(acts[3]([0,1])),"surprise shear");
// Nonlinear radial action F(x)=Q(x)x, Q homogeneous degree 4. Exact scalar law Q(F(x))=Q(x)^5.
const radial=C(),raw=C(),radialAudit=C();let radialChecks=0;
function scalarJump(z,t,c){if(!t)return z;if(z===0n)return 0n;return pow(z,pow(5n,t,P-1n,c),P,c)}
function rawJump(x,t,c){if(!t)return x;let q=dot(f,features(x,c),c);if(q===0n)return zeros(2);
 // exponent (5^t-1)/4 mod p-1; compute mod 4(p-1) before exact divide.
 let e=(pow(5n,t,4n*(P-1n),c)-1n)/4n;c.division++;let a=pow(q,e,P,c);return x.map(v=>M(a,v,c))}
for(let i=0;i<96;i++){let x=i===0?zeros(2):[rand(),rand()],t=i%4===0?BigInt(i%9):10n**24n+BigInt(i);
 let q=dot(f,features(x,radial),radial),z=scalarJump(q,t,radial),y=rawJump(x,t,raw);ok(z===dot(f,directFeatures(y,radialAudit),radialAudit),"radial output");
 if(t<10n){let v=x.slice();for(let k=0n;k<t;k++){let a=dot(f,directFeatures(v,radialAudit),radialAudit);v=v.map(b=>M(a,b,radialAudit))}ok(eq(v,y),"radial eager")}
 radialChecks++}
return {version:"RGF-006",prime:P.toString(),degree:D,seed:74319,campaigns,small,radial:{tasks:96,checks:radialChecks,scalarWork:cost(radial),fullStateWork:cost(raw),auditWork:cost(radialAudit)},controls:{alteredPhaseMap:"refused",surpriseShear:"counterexample",reset:"requires no discarded coordinate; reseed explicitly external",zeroRadial:"checked"}}
}

console.log(JSON.stringify(rgf006(),null,2));
