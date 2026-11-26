// Independent short-form implementation and mechanism controls.
function controls(){
  const days=240,total=360;
  function share(period,cap,evap,drain,identical=false){
    let shares=[];
    for(let phase=0;phase<period;phase++){
      let s=0,d=0,f=.5;
      for(let t=0;t<days;t++){
        s+=t%period===phase?total*period/days:0;d=Math.min(45,d+Math.max(0,s-cap));s=Math.min(s,cap);
        s-=Math.min(s,evap);d*=1-drain;
        const a=1.6*f*s/(s+2),b=(identical?1.6:.4)*(1-f)*s/(s+2);
        const ratio=a+b?Math.min(1,s/(a+b)):1;
        const c=identical?0:Math.min(d,1.2*(1-f)*d/(d+3));
        s-=(a+b)*ratio;d-=c;
        const x=f*Math.exp(.1*a*ratio/f),y=(1-f)*Math.exp(.1*(b*ratio+c)/(1-f)-(identical?0:.015));f=x/(x+y);
      }
      shares.push(1-f);
    }
    return shares.reduce((a,b)=>a+b,0)/period;
  }
  const cases=[
    {name:"baseline",cap:12,evap:1.2,drain:.05},
    {name:"large upper storage",cap:100,evap:1.2,drain:.05},
    {name:"rapid deep drainage",cap:12,evap:1.2,drain:.95},
    {name:"identical strategies",cap:12,evap:1.2,drain:.05,identical:true}
  ];
  const results=cases.map(p=>({...p,values:[1,3,6,12,24,40].map(period=>({period,share:share(period,p.cap,p.evap,p.drain,p.identical)}))}));
  if(Math.abs(results[0].values[4].share-.9976221451044819)>1e-12)throw Error("baseline mismatch");
  if(results[3].values.some(x=>Math.abs(x.share-.5)>1e-12))throw Error("identical strategies diverged");
  return results;
}
console.log(JSON.stringify(controls(), null, 2));
