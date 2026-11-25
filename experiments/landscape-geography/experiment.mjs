// RRE-003: spatial plant-soil dynamics, shape and barrier controls.
function geography(){
 const N=51,L=N*N,m=.05,r=.2,k=.5,b=.04,p=.35,q=.08,T=2500;
 const near=Array.from({length:L},(_,i)=>{const x=i%N,y=Math.floor(i/N);return [y*N+(x+1)%N,y*N+(x+N-1)%N,((y+1)%N)*N+x,((y+N-1)%N)*N+x]});
 const xcoord=i=>i%N,ycoord=i=>Math.floor(i/N);
 function eq(start,b,k){let x=start,h=start;for(let i=0;i<2000;i++){x=(1-m)/(1+Math.exp(-(Math.log(x/(1-x))+b+k*(2*h-1))))+m/2;h=(1-r)*h+r*x}return x}
 const lo=eq(.1,b,k),hi=eq(.9,b,k);
 const masks={
  disk4:i=>(xcoord(i)-25)**2+(ycoord(i)-25)**2<=16,
  disk5:i=>(xcoord(i)-25)**2+(ycoord(i)-25)**2<=25,
  strip:i=>Math.abs(ycoord(i)-25)<=1&&Math.abs(xcoord(i)-25)<=13,
  fragments:i=>[9,25,41].some(x=>Math.abs(xcoord(i)-x)<=1)&&[9,25,41].some(y=>Math.abs(ycoord(i)-y)<=1),
  left:i=>(xcoord(i)-12)**2+(ycoord(i)-25)**2<=49
 };
 const times=[0,25,50,100,200,300,500,800,1200,1800,2500];
 function run(name,mask,{width=null,bias=b,feedback=k,dispersal=p,soil=q}={}){
  const low=eq(.1,bias,feedback),high=eq(.9,bias,feedback);
  // All initial states use distinct equilibria of the reference model,
  // including the no-feedback intervention.
  let x=Float64Array.from({length:L},(_,i)=>mask(i)?hi:lo),h=x.slice();
  const count=Array.from({length:L},(_,i)=>Number(mask(i))).reduce((a,b)=>a+b);
  const adj=near.map((ns,i)=>ns.map((j,d)=>{
   if(width===null||d>1)return j;
   const a=xcoord(i),c=xcoord(j),y=ycoord(i);
   if((a===0&&c===50)||(a===50&&c===0))return i;
   if((a===25&&c===26)||(a===26&&c===25))return width>0&&Math.abs(y-25)<=Math.floor(width/2)?j:i;
   return j;
  }));
  for(let i=0;i<L;i++)for(const j of adj[i])if(!adj[j].includes(i))throw Error("asymmetric edge");
  function mix(a,w,out){
   let before=0,after=0;
   for(let i=0;i<L;i++){const [e,z,n,s]=adj[i];out[i]=(1-w)*a[i]+w*(a[e]+a[z]+a[n]+a[s])/4;before+=a[i];after+=out[i]}
   if(Math.abs(before-after)>1e-8)throw Error("mix not conservative");
  }
  let growth=new Float64Array(L),newX=new Float64Array(L),condition=new Float64Array(L),newH=new Float64Array(L);
  const trajectory=[],snapshots={};
  for(let t=0;t<=T;t++){
   if(times.includes(t)){
    let n=0,ln=0,rn=0,avg=0,maxRight=0,min=1,max=0;
    for(let i=0;i<L;i++){const v=x[i];if(v>.5){n++;if(xcoord(i)<=25)ln++;else rn++}avg+=v;min=Math.min(min,v);max=Math.max(max,v);if(xcoord(i)>25)maxRight=Math.max(maxRight,v)}
    trajectory.push({t,dominant:n/L,left:ln/(26*N),right:rn/(25*N),mean:avg/L,min,max,maxRight});
    if([0,500,2500].includes(t))snapshots[t]=Array.from({length:N},(_,y)=>Array.from({length:N},(_,xx)=>x[y*N+xx]>.5?"#":".").join(""));
   }
   if(t===T)break;
   for(let i=0;i<L;i++)growth[i]=(1-m)/(1+Math.exp(-(Math.log(x[i]/(1-x[i]))+bias+feedback*(2*h[i]-1))))+m/2;
   mix(growth,dispersal,newX);
   for(let i=0;i<L;i++)condition[i]=(1-r)*h[i]+r*newX[i];
   mix(condition,soil,newH);
   [x,newX]=[newX,x];[h,newH]=[newH,h];
  }
  return {name,width,bias,feedback,dispersal,soil,initialCount:count,low,high,trajectory,snapshots};
 }
 const results=[
  run("disk radius 4",masks.disk4),run("disk radius 5",masks.disk5),run("equal area strip",masks.strip),run("equal area fragments",masks.fragments),
  ...[0,1,3,5,9,15,51].map(width=>run("gate "+width,masks.left,{width})),
  run("no plant-soil feedback",masks.disk5,{feedback:0}),
  run("no dispersal or soil diffusion",masks.disk5,{dispersal:0,soil:0})
 ];
 const end=i=>results[i].trajectory.at(-1);
 if(results[1].initialCount!==81||results[2].initialCount!==81||results[3].initialCount!==81)throw Error("unequal area");
 if(!(end(0).dominant===0&&end(1).dominant>.8&&end(3).dominant===0&&end(4).right===0&&end(10).right>.5))throw Error("expected contrast failed");
 if(Math.abs(end(11).max-end(11).min)>1e-8)throw Error("null remains heterogeneous");
 if(Math.abs(end(12).dominant-results[12].trajectory[0].dominant)>1e-12)throw Error("isolated patch changed");
 return {parameters:{N,L,m,r,k,b,p,q,T,lo,hi},results};
}
console.log(JSON.stringify(geography(),null,2));
