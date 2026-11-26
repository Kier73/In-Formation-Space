// RRE-001: illustrative two-layer rainfall and plant competition model.
// Run: node experiment.mjs > results.json
function experiment(){
  const periods=[1,3,6,12,24,40], days=240, total=360;
  function assert(condition,message){if(!condition)throw Error(message)}
  function simulate(period,phase,p,initial=.5){
    let s=0,d=0,f=initial, rainSum=0,evapSum=0,drainSum=0,uptakeSum=0,runoffSum=0,maxResidual=0;
    for(let t=0;t<days;t++){
      const before=s+d;
      const rain=t%period===phase?total*period/days:0; rainSum+=rain;
      s+=rain;d+=Math.max(0,s-p.cap);s=Math.min(s,p.cap);
      const runoff=Math.max(0,d-45);d-=runoff;runoffSum+=runoff;
      const evap=Math.min(s,p.evap);s-=evap;evapSum+=evap;
      const drainage=d*p.drain;d-=drainage;drainSum+=drainage;
      const shallowDemand=1.6*f*s/(s+2);
      const deepTopDemand=.4*(1-f)*s/(s+2);
      const factor=shallowDemand+deepTopDemand>0?Math.min(1,s/(shallowDemand+deepTopDemand)):1;
      const a=shallowDemand*factor,bTop=deepTopDemand*factor;
      const bDeep=Math.min(d,1.2*(1-f)*d/(d+3));
      s-=a+bTop;d-=bDeep;uptakeSum+=a+bTop+bDeep;
      const ga=.10*a/f,gb=.10*(bTop+bDeep)/(1-f)-.015;
      const x=f*Math.exp(ga),y=(1-f)*Math.exp(gb);
      f=x/(x+y);
      maxResidual=Math.max(maxResidual,Math.abs(before+rain-runoff-evap-drainage-a-bTop-bDeep-s-d));
      assert(s>=-1e-10&&d>=-1e-10&&f>0&&f<1,"invalid state");
    }
    const balance=rainSum-evapSum-drainSum-uptakeSum-runoffSum-s-d;
    assert(Math.abs(rainSum-total)<1e-9,"unequal rainfall");
    assert(Math.abs(balance)<1e-8&&maxResidual<1e-9,"mass conservation failed");
    return {deepShare:1-f,evap:evapSum,drain:drainSum,uptake:uptakeSum,runoff:runoffSum,stored:s+d,balance,maxResidual};
  }
  const avg=(a)=>a.reduce((x,y)=>x+y,0)/a.length;
  const mean=(period,p,initial=.5)=>{
    const r=Array.from({length:period},(_,phase)=>simulate(period,phase,p,initial));
    const summary={};for(const key of ["deepShare","evap","drain","uptake","runoff","stored"])summary[key]=avg(r.map(x=>x[key]));
    summary.minDeepShare=Math.min(...r.map(x=>x.deepShare));summary.maxDeepShare=Math.max(...r.map(x=>x.deepShare));
    summary.maxResidual=Math.max(...r.map(x=>Math.max(Math.abs(x.balance),x.maxResidual)));
    return summary;
  };
  const base={cap:12,evap:1.2,drain:.05};
  const baseline=periods.map(period=>({period,event:total*period/days,...mean(period,base)}));
  const sweep=[];
  for(const cap of [6,12,24])for(const evap of [.6,1.2,1.8])for(const drain of [.015,.05,.12]){
    const p={cap,evap,drain};
    const values=periods.map(period=>({period,...mean(period,p)}));
    sweep.push({...p,daily:values[0].deepShare,period24:values[4].deepShare,delta:values[4].deepShare-values[0].deepShare,peakPeriod:values.reduce((a,b)=>b.deepShare>a.deepShare?b:a).period,values});
  }
  const reverse=sweep.filter(x=>x.delta<0);
  const sensitivity=[.1,.5,.9].map(initialShallow=>({initialShallow,daily:mean(1,base,initialShallow).deepShare,period24:mean(24,base,initialShallow).deepShare}));
  const maxResidual=Math.max(...sweep.flatMap(x=>x.values.map(y=>y.maxResidual)));
  return {days,total,periods,base,baseline,sweep,summary:{cells:sweep.length,positive:sweep.filter(x=>x.delta>0).length,negative:reverse.length,minDelta:Math.min(...sweep.map(x=>x.delta)),maxDelta:Math.max(...sweep.map(x=>x.delta)),peakPeriods:Object.fromEntries(periods.map(p=>[p,sweep.filter(x=>x.peakPeriod===p).length])),maxResidual},sensitivity};
}
console.log(JSON.stringify(experiment(), null, 2));
