// Root bracketing, local Jacobian stability and paired histories.
function stabilityCheck(){
 const m=.05,r=.2,k=.5;
 const logistic=z=>1/(1+Math.exp(-z));
 function step(s,k,d=0){
  const x=(1-m)*logistic(Math.log(s.x/(1-s.x))+d+k*(2*s.h-1))+m/2;
  return {x,h:(1-r)*s.h+r*x};
 }
 function root(k,lo,hi){
  const F=x=>step({x,h:x},k).x-x;
  if(F(lo)*F(hi)>0)throw Error("not bracketed");
  for(let i=0;i<60;i++){const mid=(lo+hi)/2;if(F(lo)*F(mid)<=0)hi=mid;else lo=mid}
  return (lo+hi)/2;
 }
 function eig(x,k){
   const p=(x-m/2)/(1-m),A=(1-m)*p*(1-p)/(x*(1-x)),B=2*k*(1-m)*p*(1-p);
   const trace=A+1-r+r*B,det=A*(1-r),disc=Math.sqrt(trace*trace-4*det);
   return [(trace+disc)/2,(trace-disc)/2];
 }
 const lo=root(k,.025,.49),hi=root(k,.51,.975),roots=[lo,.5,hi].map(x=>({x,eigenvalues:eig(x,k)}));
 if(!(roots[0].eigenvalues[0]<1&&roots[1].eigenvalues[0]>1&&roots[2].eigenvalues[0]<1))throw Error("stability pattern mismatch");
 const run=(s,n,d=0)=>{for(let i=0;i<n;i++)s=step(s,k,d);return s};
 const base={x:lo,h:lo},pulses=[{d:1,n:5},{d:1.5,n:3}];
 const comparisons=pulses.map(({d,n})=>{
   const post=run(base,n,d);
   const variants={both:post,plantsOnly:{x:post.x,h:lo},soilOnly:{x:lo,h:post.h},control:base};
   const trajectories=Object.fromEntries(Object.entries(variants).map(([name,state])=>{
     const rows=[{season:0,...state}];
     for(let t=1;t<=150;t++){state=step(state,k);if([1,2,3,5,10,20,40,80,150].includes(t))rows.push({season:t,...state})}
     return [name,rows];
   }));
   return {d,n,post,trajectories};
 });
 if(Math.abs(comparisons[0].post.x-comparisons[1].post.x)>.001)throw Error("cover match not close");
 const end=(i,key)=>comparisons[i].trajectories[key].at(-1).x;
 if(!(end(0,"both")>.9&&end(0,"plantsOnly")<.1&&end(0,"soilOnly")<.1&&end(1,"both")<.1))throw Error("joint legacy test failed");
 return {criticalFeedback:2*m/(1-m),roots,comparisons};
}
console.log(JSON.stringify(stabilityCheck(),null,2));
