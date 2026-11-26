// RRE-004: three-species two-patch metacommunity experiment.
function experiment(){
 const m=.05,r=.2,k=.5,b=.04,T=5000,ps=[0,.001,.003,.01,.03,.06,.1,.2,.3],qs=ps;
 const assert=(v,msg)=>{if(!v)throw Error(msg)};
 function grow(s,adv=.35){
   const [a,z,c,h]=s,v=b+k*(2*h-1),A=a*Math.exp(-v/2),B=z*Math.exp(v/2),C=c*Math.exp(adv-1.5*c),sum=A+B+C;
   return [(1-m)*A/sum+m*(A+B)/sum/2,(1-m)*B/sum+m*(A+B)/sum/2,C/sum];
 }
 function step(s,p,q,adv=.35){
   const u=grow(s[0],adv),v=grow(s[1],adv);
   const out=[u.map((a,i)=>(1-p)*a+p*v[i]),v.map((a,i)=>(1-p)*a+p*u[i])];
   for(let j=0;j<3;j++)assert(Math.abs(out[0][j]+out[1][j]-u[j]-v[j])<1e-12,"seed exchange conservation");
   const h=out.map((a,i)=>(1-r)*s[i][3]+r*a[1]/(a[0]+a[1]));
   const y=out.map((a,i)=>[...a,(1-q)*h[i]+q*h[1-i]]);
   assert(Math.abs(y[0][3]+y[1][3]-h[0]-h[1])<1e-12,"soil exchange conservation");
   for(const a of y)assert(a.every(v=>v>=0&&v<=1+1e-12)&&Math.abs(a[0]+a[1]+a[2]-1)<1e-12,"invalid state");
   return y;
 }
 const dist=(s,t)=>Math.max(...s.flatMap((a,i)=>a.map((v,j)=>Math.abs(v-t[i][j]))));
 const entropy=s=>-s.slice(0,3).reduce((a,v)=>a+(v>0?v*Math.log(v):0),0);
 function measures(s){
   const alpha=(entropy(s[0])+entropy(s[1]))/2,gamma=entropy(s[0].map((v,i)=>(v+s[1][i])/2));
   return {C:s[1][2],rightB:s[1][1]/(s[1][0]+s[1][1]),leftB:s[0][1]/(s[0][0]+s[0][1]),alpha:Math.exp(alpha),gamma:Math.exp(gamma),beta:Math.exp(gamma-alpha),dissimilarity:.5*s[0].slice(0,3).reduce((a,v,i)=>a+Math.abs(v-s[1][i]),0)};
 }
 function run(s,p,q,adv=.35,limit=T,period=1){
   let first=null,rows=[];
   for(let t=0;t<=limit;t++){
    const v=measures(s);
    if(first===null&&v.C>=.1)first=t;
    if([0,10,25,50,100,250,500,1000,limit].includes(t))rows.push({t,...v});
    if(t===limit)break;
    s=step(s,t%period===0?p:0,q,adv);
   }
   const v=measures(s),residual=dist(s,step(s,p,q,adv));
   return {p,q,period,adv,first,final:v,residual:period===1?residual:null,end:s,rows,success:v.C>=.1&&v.rightB<.25&&v.leftB>.75};
 }
 function initialize(adv){
   const base=run([[.07,.73,.2,.9],[.73,.07,.2,.1]],0,0,adv).end;
   const v=base[1];
   return {base,initial:[base[0],[v[0]/(1-v[2]),v[1]/(1-v[2]),0,v[3]]]};
 }
 const {base,initial}=initialize(.35);
 const grid=ps.flatMap(p=>qs.map(q=>run(initial,p,q)));
 const best=grid.filter(x=>x.success).sort((a,b)=>a.first-b.first||b.final.beta-a.final.beta);
 const controls=[run(initial,0,0),run(initial,.01,0),run(initial,.01,.06),run(initial,.1,0),run(initial,0,.1)];
 const schedules=[1,2,5,10,20,50].map(period=>run(initial,.01*period,.003,.35,T,period));
 const sensitivity=[.30,.35,.40,.50].flatMap(adv=>{const {initial}=initialize(adv);return [[.003,.003],[.01,.003],[.03,.003],[.01,.06]].map(([p,q])=>run(initial,p,q,adv))});
 const maxResidual=Math.max(...grid.map(x=>x.residual));
 assert(maxResidual<1e-8,"grid did not settle");
 assert(controls[0].final.C===0&&controls[1].success&&!controls[2].success&&controls[2].final.rightB>.9,"selective connectivity contrast");
 assert(controls[4].final.C===0&&controls[4].final.rightB>.9,"soil-only transition control");
 return {parameters:{m,r,k,b,T,ps,qs},base,initial,grid,best,controls,schedules,sensitivity,maxResidual};
}
console.log(JSON.stringify(experiment(),null,2));
