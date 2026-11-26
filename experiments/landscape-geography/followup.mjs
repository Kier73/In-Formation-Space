// Longer corridor tests and explicitly forced local drought pulses.
function followup(){
 const N=51,L=N*N,m=.05,r=.2,k=.5,b=.04,p=.35,q=.08,lo=.07381095974889079,hi=.9368404925566124;
 const near=Array.from({length:L},(_,i)=>{const x=i%N,y=Math.floor(i/N);return [y*N+(x+1)%N,y*N+(x+N-1)%N,((y+1)%N)*N+x,((y+N-1)%N)*N+x]});
 function run({width=null,radius=7,d=0,duration=0,T=10000}){
  const local=Array.from({length:L},(_,i)=>(i%N-(width===null?25:12))**2+(Math.floor(i/N)-25)**2<=radius**2);
  const adj=near.map((ns,i)=>ns.map((j,a)=>{
    if(width===null||a>1)return j;
    const x=i%N,z=j%N;
    if((x===0&&z===50)||(x===50&&z===0))return i;
    if((x===25&&z===26)||(x===26&&z===25))return width>0&&Math.abs(Math.floor(i/N)-25)<=Math.floor(width/2)?j:i;
    return j;
  }));
  let x=Float64Array.from(local,z=>z&&duration===0?hi:lo),h=x.slice(),g=x.slice(),nx=x.slice(),c=x.slice(),nh=x.slice();
  function mix(a,w,out){for(let i=0;i<L;i++){const [e,z,n,s]=adj[i];out[i]=(1-w)*a[i]+w*(a[e]+a[z]+a[n]+a[s])/4}}
  let maxResidual=0, rows=[];
  for(let t=0;t<=T;t++){
    let dt=0,count=0,right=0,rightMax=0;
    for(let i=0;i<L;i++){g[i]=(1-m)/(1+Math.exp(-(Math.log(x[i]/(1-x[i]))+b+k*(2*h[i]-1)+(t<duration&&local[i]?d:0))))+m/2;if(x[i]>.5){count++;if(i%N>25)right++}if(i%N>25)rightMax=Math.max(rightMax,x[i]);}
    mix(g,p,nx);
    for(let i=0;i<L;i++)c[i]=(1-r)*h[i]+r*nx[i];
    mix(c,q,nh);
    for(let i=0;i<L;i++)dt=Math.max(dt,Math.abs(nx[i]-x[i]),Math.abs(nh[i]-h[i]));
    if([0,duration,50,500,2500,5000,10000,T].includes(t))rows.push({t,dominant:count/L,right:right/(N*25),rightMax,residual:dt});
    if(t===T)break;
    [x,nx]=[nx,x];[h,nh]=[nh,h];
  }
  return {width,radius,d,duration,T,rows};
 }
 const gates=[1,3,5,9].map(width=>run({width}));
 const pulses=[4,5,7,10].flatMap(radius=>[5,8].map(duration=>run({radius,d:1,duration,T:2500})));
 if(gates[0].rows.at(-1).right!==0||gates[1].rows.at(-1).right!==0)throw Error("narrow gate crossing");
 return {gates,pulses};
}
console.log(JSON.stringify(followup(),null,2));
