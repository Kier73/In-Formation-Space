// Phase-complete, cycle-aware audit of pulsed seed exchange.
function scheduleAudit(){
 const m=.05,r=.2,k=.5,b=.04,q=.003;
 function step(s,p){
  const g=s.map(([a,z,c,h])=>{const v=b+k*(2*h-1),A=a*Math.exp(-v/2),B=z*Math.exp(v/2),C=c*Math.exp(.35-1.5*c),u=A+B+C;return [(1-m)*A/u+m*(A+B)/u/2,(1-m)*B/u+m*(A+B)/u/2,C/u]});
  const y=g.map((a,i)=>a.map((v,j)=>(1-p)*v+p*g[1-i][j]));
  const h=y.map((a,i)=>(1-r)*s[i][3]+r*a[1]/(a[0]+a[1]));
  return y.map((a,i)=>[...a,(1-q)*h[i]+q*h[1-i]]);
 }
 const initial=[[.057440410309950514,.8520095305629551,.0905500591270944,.9368404925566126],[.9261890402511093,.07381095974889075,0,.07381095974889079]];
 const dist=(s,t)=>Math.max(...s.flatMap((a,i)=>a.map((v,j)=>Math.abs(v-t[i][j]))));
 const results=[];
 for(const period of [1,2,5,10,20,50]){
  const phases=[];
  for(let phase=0;phase<period;phase++){
   let s=initial,first=null,oldCycle=null,cycle=[],rescueSustained=null,lastBelow=null;
   for(let t=0;t<=5000+period;t++){
    const C=s[1][2];
    if(first===null&&C>=.1)first=t;
    if(C<.1)lastBelow=t;
    if(t===5000)oldCycle=s;
    if(t>=5000&&t<5000+period)cycle.push({C,B:s[1][1]/(s[1][0]+s[1][1]),leftB:s[0][1]/(s[0][0]+s[0][1]),diff:.5*s[0].slice(0,3).reduce((v,a,j)=>v+Math.abs(a-s[1][j]),0)});
    if(t===5000+period)break;
    s=step(s,t%period===phase?.01*period:0);
   }
   const residual=dist(oldCycle,s);
   phases.push({phase,first,sustained:lastBelow+1,minC:Math.min(...cycle.map(x=>x.C)),maxC:Math.max(...cycle.map(x=>x.C)),maxB:Math.max(...cycle.map(x=>x.B)),minLeftB:Math.min(...cycle.map(x=>x.leftB)),minDiff:Math.min(...cycle.map(x=>x.diff)),residual});
  }
  const summary={period,phases,firstMin:Math.min(...phases.map(x=>x.first)),firstMax:Math.max(...phases.map(x=>x.first)),sustainedMin:Math.min(...phases.map(x=>x.sustained)),sustainedMax:Math.max(...phases.map(x=>x.sustained)),minC:Math.min(...phases.map(x=>x.minC)),maxB:Math.max(...phases.map(x=>x.maxB)),minLeftB:Math.min(...phases.map(x=>x.minLeftB)),minDiff:Math.min(...phases.map(x=>x.minDiff)),maxResidual:Math.max(...phases.map(x=>x.residual))};
  summary.allPhasesSuccessful=summary.minC>=.1&&summary.maxB<.25&&summary.minLeftB>.75;
  if(summary.maxResidual>1e-10)throw Error("cycle not converged");
  results.push(summary);
 }
 return results;
}
console.log(JSON.stringify(scheduleAudit(),null,2));
