// RRE-005: finite populations, stochastic dispersal and shared disturbances.
function experiment(){
 const N=12,K=32,T=120,reps=180,ps=[0,.08,.2,.7,1],rhos=[0,.5],layouts=["uniform","alternate","cluster"];
 function rng(seed){let a=seed>>>0;return()=>{a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return ((t^(t>>>14))>>>0)/4294967296}}
 const good=(i,h)=>h==="uniform"||(h==="alternate"?i%2===0:i<6);
 function trial(rep,p,rho,h,retain){
  const w=rng(1000000+rep*19),u=rng(2000000+rep*31),n=new Int32Array(N).fill(16),m=new Int32Array(N),dry=new Uint8Array(N);
  let ext=null,resc=0,loss=0,avg=0;
  for(let t=0;t<T;t++){
   const shared=w(),common=w();m.fill(0);let births=0;
   for(let i=0;i<N;i++){const z=w();dry[i]=+((shared<rho?common:z)<(dry[i]?.65:.15));
    const R=(good(i,h)?3.2:.75)*(dry[i]?.18:1),prob=1-Math.exp(-R*n[i]/K);
    for(let j=0;j<K;j++){const a=u(),d=u(),v=u();if(a>=prob)continue;let dest=d<p/2?(i+N-1)%N:d<p?(i+1)%N:i;if(retain&&good(i,h)&&!good(dest,h)&&v<.9)dest=i;m[dest]++;births++}
   }
   let sum=0;
   for(let i=0;i<N;i++){if(n[i]===0&&m[i]>0)resc++;if(n[i]>0&&m[i]===0)loss++;n[i]=m[i];sum+=n[i]}
   if(sum!==births)throw Error("dispersal conservation");
   avg+=sum;if(sum===0){ext=t+1;break}
  }
  return {ext,resc,loss,avg:avg/T};
 }
 const mean=a=>a.reduce((v,x)=>v+x,0)/a.length;
 function summary(p,rho,layout,retain=false){
   const a=Array.from({length:reps},(_,i)=>trial(i+1000,p,rho,layout,retain));
   const count=a.filter(x=>x.ext!==null).length,frac=count/reps,z=1.959963984540054,den=1+z*z/reps,center=(frac+z*z/(2*reps))/den,margin=z*Math.sqrt(frac*(1-frac)/reps+z*z/(4*reps*reps))/den;
   return {p,rho,layout,retain,extinct:count,ci95:[Math.max(0,center-margin),Math.min(1,center+margin)],meanAbundance:mean(a.map(x=>x.avg)),meanLocalRescue:mean(a.map(x=>x.resc)),meanLocalLoss:mean(a.map(x=>x.loss)),survival:Array.from({length:6},(_,i)=>{const t=(i+1)*20;return {t,alive:a.filter(x=>x.ext===null||x.ext>t).length}}),extinctionTimes:a.map(x=>x.ext)};
 }
 const grid=layouts.flatMap(h=>rhos.flatMap(rho=>ps.map(p=>summary(p,rho,h))));
 const retention=rhos.flatMap(rho=>[.2,.7,1].map(p=>summary(p,rho,"alternate",true)));
 const get=(h,rho,p)=>grid.find(x=>x.layout===h&&x.rho===rho&&x.p===p);
 if(!(get("uniform",0,0).extinct>get("uniform",0,.2).extinct&&get("alternate",.5,.2).extinct<get("alternate",.5,.7).extinct&&get("cluster",.5,.7).extinct<get("alternate",.5,.7).extinct))throw Error("pilot contrast not reproduced");
 return {parameters:{N,K,T,reps,ps,rhos,layouts,seedStart:1000},grid,retention};
}
console.log(JSON.stringify(experiment(),null,2));
