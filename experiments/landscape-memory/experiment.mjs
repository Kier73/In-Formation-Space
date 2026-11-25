// RRE-002: annual plant/soil feedback and drought legacy toy model.
function legacyExperiment(){
 const m=.05, r=.2, initial={x:.1,h:.1}, eps=1e-12;
 const logistic=z=>1/(1+Math.exp(-z));
 function step(s,k,b=0,d=0){
   const x=(1-m)*logistic(Math.log(s.x/(1-s.x))+b+d+k*(2*s.h-1))+m/2;
   const h=(1-r)*s.h+r*x;
   if(!(x>0&&x<1&&h>0&&h<1))throw Error("invalid state");
   return {x,h};
 }
 function run(s,n,k,b=0,d=0){for(let i=0;i<n;i++)s=step(s,k,b,d);return s}
 const dist=(a,b)=>Math.max(Math.abs(a.x-b.x),Math.abs(a.h-b.h));
 const equilibrate=(s,k,b)=>run(s,20000,k,b);
 const ks=[0,.06,.10,.12,.25,.5,1], biases=[-.04,0,.04], strengths=[.25,.5,1,1.5,2], durations=[1,2,3,5];
 const grid=[];
 for(const k of ks)for(const b of biases){
   const low=equilibrate(initial,k,b),high=equilibrate({x:.9,h:.9},k,b);
   const cases=[];
   for(const d of strengths)for(const n of durations){
     const post=run(low,n,k,b,d),end=equilibrate(post,k,b);
     cases.push({d,n,post,end,residual:dist(end,step(end,k,b)),difference:end.x-low.x,switched:Math.abs(high.x-low.x)>.05&&dist(end,high)<1e-7});
   }
   grid.push({k,b,low,high,gap:high.x-low.x,lowResidual:dist(low,step(low,k,b)),highResidual:dist(high,step(high,k,b)),cases});
 }
 const k=.5,b=0,low=equilibrate(initial,k,b),high=equilibrate({x:.9,h:.9},k,b);
 const trials=[];
 for(const d of strengths)for(const n of durations){
   const post=run(low,n,k,b,d);
   trials.push({d,n,post,full:equilibrate(post,k,b),soilOnly:equilibrate({x:low.x,h:post.h},k,b),plantsOnly:equilibrate({x:post.x,h:low.h},k,b)});
 }
 const chosen=trials.find(t=>t.d===1.5&&t.n===3);
 const trajectory=(s,k,b)=>{const rows=[{season:0,...s}];for(let i=1;i<=150;i++){s=step(s,k,b);if([1,2,3,5,10,20,40,80,150].includes(i))rows.push({season:i,...s})}return rows};
 const comparison={full:trajectory(chosen.post,k,b),soilOnly:trajectory({x:low.x,h:chosen.post.h},k,b),plantsOnly:trajectory({x:chosen.post.x,h:low.h},k,b),control:trajectory(low,k,b)};
 const nullLow=equilibrate(initial,0,0),nullPost=run(nullLow,3,0,0,1.5);
 const nullEnd=equilibrate(nullPost,0,0);
 if(dist(nullEnd,nullLow)>eps)throw Error("null did not recover");
 const maxResidual=Math.max(...grid.flatMap(g=>[g.lowResidual,g.highResidual,...g.cases.map(c=>c.residual)]));
 if(maxResidual>1e-7)throw Error("candidate not stationary "+maxResidual);
 if(grid.filter(g=>g.b===0).some(g=>Math.abs(g.low.x+g.high.x-1)>1e-8))throw Error("symmetry broken");
 return {parameters:{m,r,ks,biases,strengths,durations,equilibrationSeasons:20000},maxResidual,grid,chosen,comparison,transplants:trials,nullControl:{low:nullLow,post:nullPost,end:nullEnd,trajectory:trajectory(nullPost,0,0)}};
}
console.log(JSON.stringify(legacyExperiment(),null,2));
