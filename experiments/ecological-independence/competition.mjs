// RRE-005: two complementary species competing for finite recruitment slots.
function competition(){
 const N=12,K=32,T=120,reps=120,ps=[.08,.2,.7,1],rhos=[0,.5],layouts=["alternate","cluster"];
 function rng(seed){let a=seed>>>0;return()=>{a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return ((t^(t>>>14))>>>0)/4294967296}}
 function trial(rep,p,rho,layout,retain){
  const w=rng(1000000+rep*19),u=rng(3000000+rep*31),n=new Int32Array(2*N).fill(8),m=new Int32Array(2*N),dry=new Uint8Array(N);
  const ext=[null,null];let avg=0;
  const good=(i,s)=>(layout==="alternate"?i%2===0:i<6)===(s===0);
  for(let t=0;t<T;t++){
   const shared=w(),common=w();m.fill(0);let births=0;
   for(let i=0;i<N;i++){
    const z=w();dry[i]=+((shared<rho?common:z)<(dry[i]?.65:.15));
    const f=dry[i]?.18:1,a=n[i]*(good(i,0)?3.2:.75)*f,b=n[N+i]*(good(i,1)?3.2:.75)*f;
    const total=a+b,prob=1-Math.exp(-total/K);
    for(let j=0;j<K;j++){
     const x=u(),y=u(),d=u(),v=u();if(x>=prob)continue;
     const s=y*total<a?0:1;
     let dest=d<p/2?(i+N-1)%N:d<p?(i+1)%N:i;
     if(retain&&good(i,s)&&!good(dest,s)&&v<.9)dest=i;
     m[s*N+dest]++;births++;
    }
   }
   let total=0;for(let s=0;s<2;s++){let sum=0;for(let i=0;i<N;i++){n[s*N+i]=m[s*N+i];sum+=m[s*N+i]}total+=sum;if(sum===0&&ext[s]===null)ext[s]=t+1;if(ext[s]!==null&&sum!==0)throw Error("extinction not absorbing")}
   if(total!==births)throw Error("dispersal conservation");
   avg+=total;if(!total)break;
  }
  return {ext,avg:avg/T};
 }
 function summarize(p,rho,layout,retain=false){
  const a=Array.from({length:reps},(_,i)=>trial(i+2000,p,rho,layout,retain));
  const bothAlive=a.filter(x=>x.ext.every(t=>t===null)).length,neitherAlive=a.filter(x=>x.ext.every(t=>t!==null)).length;
  return {p,rho,layout,retain,bothAlive,neitherAlive,oneAlive:reps-bothAlive-neitherAlive,meanAbundance:a.reduce((v,x)=>v+x.avg,0)/reps,extinctionTimes:a.map(x=>x.ext)};
 }
 const grid=layouts.flatMap(layout=>rhos.flatMap(rho=>ps.map(p=>summarize(p,rho,layout))));
 const retention=[.2,.7,1].map(p=>summarize(p,.5,"alternate",true));
 return {parameters:{N,K,T,reps,seedStart:2000},grid,retention};
}
console.log(JSON.stringify(competition(),null,2));
