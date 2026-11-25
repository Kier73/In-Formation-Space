"use strict";
// CLT-003 finite residual subspace acquisition. No external dependencies.
function experiment(){
  const n=8,N=1<<n;
  const insist=(p,m)=>{if(!p)throw Error(m)};
  let rng=0x1234abcd;
  const rand=()=>{rng^=rng<<13;rng^=rng>>>17;rng^=rng<<5;return rng>>>0};
  const masks=[3,5,10,17,36,72,144,97,134,56,193,161,7,112,200];
  const base=x=>((x&1)^((x>>4)&1)^Number((x&42)===42));
  // Private target generator. The learner is given only scalar residual observations.
  function oracle(coeff,bump=-1){
    let calls=0,weighted=0;
    return {
      ask(x){insist(Number.isInteger(x)&&x>=0&&x<N,"bad coordinate");calls++;weighted+=cost(x);
        let v=base(x);
        for(let j=0;j<masks.length;j++)if((coeff>>j)&1)v^=Number((x&masks[j])===masks[j]);
        return v^Number(x===bump);
      },
      accounting(){return {calls,weighted}}
    };
  }
  function cost(x){return 1+((x*73+19)%31)}
  const stats={trainingReads:0,vectorXorCells:0,trainingPivotChecks:0,planBasisCellReads:0,planRowReductions:0};
  class Atlas{
    constructor(){this.rows=[]}
    add(v){
      const r=v.slice();
      for(const {pivot,row} of this.rows){
        stats.trainingPivotChecks++;
        if(r[pivot])for(let i=0;i<N;i++){r[i]^=row[i];stats.vectorXorCells++}
      }
      const pivot=r.indexOf(1);
      if(pivot<0)return false;
      this.rows.push({pivot,row:r});return true;
    }
    plan(weighted){
      const r=this.rows.length, rows=[], pivots=Array(r).fill(0);
      const order=Array.from({length:N},(_,x)=>x).sort((a,b)=>weighted?cost(a)-cost(b)||a-b:a-b);
      for(const x of order){
        let m=0;
        for(let j=0;j<r;j++){m|=this.rows[j].row[x]<<j;stats.planBasisCellReads++}
        let k=m;
        for(let j=r-1;j>=0;j--)if(k&(1<<j)){
          if(pivots[j]){k^=pivots[j];stats.planRowReductions++}
          else{pivots[j]=k;rows.push({x,m});break}
        }
        if(rows.length===r)break;
      }
      insist(rows.length===r,"basis not independently observable");
      return rows;
    }
    predict(source,plan){
      const r=this.rows.length;
      const pivots=Array(r).fill(0), vals=Array(r).fill(0), seen=new Map();
      let work=0;
      for(const {x,m} of plan){
        let k=m, v=source.ask(x)^base(x);seen.set(x,v);
        for(let j=r-1;j>=0;j--)if(k&(1<<j)){
          if(pivots[j]){k^=pivots[j];v^=vals[j];work++}
          else{pivots[j]=k;vals[j]=v;break}
        }
      }
      let coeff=0;
      for(let j=0;j<r;j++){
        insist(pivots[j]!==0,"insufficient probes");
        let v=vals[j];
        for(let k=0;k<j;k++)if(pivots[j]&(1<<k)){v^=(coeff>>k)&1;work++}
        coeff|=v<<j;
      }
      const residual=new Uint8Array(N);
      for(let j=0;j<r;j++)if((coeff>>j)&1)for(let x=0;x<N;x++){residual[x]^=this.rows[j].row[x];work++}
      return {residual,seen,work,status:"CONDITIONAL"};
    }
  }
  function full(source){
    return Uint8Array.from({length:N},(_,x)=>source.ask(x)^base(x))
  }
  function audit(source,pred){
    const actual=new Uint8Array(N);let errors=0;
    for(let x=0;x<N;x++){
      actual[x]=pred.seen.has(x)?pred.seen.get(x):source.ask(x)^base(x);
      errors+=Number(actual[x]!==pred.residual[x]);
    }
    return {actual,errors,status:errors?"REJECT":"VERIFIED_TABLE"};
  }
  const atlas=new Atlas(), used=new Set();
  let trainingWeighted=0;
  function train(c){
    const s=oracle(c),v=full(s);stats.trainingReads+=s.accounting().calls;trainingWeighted+=s.accounting().weighted;return atlas.add(v)
  }
  const choose=(bits,top=0)=>{
    let c;
    do{c=(rand()&((1<<bits)-1))|top}while(!c||used.has(c));
    used.add(c);return c
  };
  for(let i=0;i<18;i++)train(choose(12));
  insist(atlas.rows.length===12,"prior cohort did not span 12 dimensions");
  const trainInitial=stats.trainingReads;
  const cleanCases=Array.from({length:64},()=>choose(12));
  function evaluate(cases,plan){
    let queries=0,weighted=0,work=0,verified=0,rejected=0,errors=0,fullCalls=0,fullCost=0;
    for(const c of cases){
      const s=oracle(c),p=atlas.predict(s,plan),before=s.accounting(),a=audit(s,p);
      queries+=before.calls;weighted+=before.weighted;work+=p.work;
      if(a.errors)rejected++;else verified++;
      errors+=a.errors;
      fullCalls+=s.accounting().calls;fullCost+=s.accounting().weighted;
      insist(s.accounting().calls===N,"audit did not cover source");
    }
    return {cases:cases.length,queries,weighted,work,verified,rejected,errors,fullCalls,fullCost};
  }
  const weighted=atlas.plan(true),unweighted=atlas.plan(false);
  const initialWeighted=evaluate(cleanCases,weighted),initialUnweighted=evaluate(cleanCases,unweighted);
  insist(initialWeighted.verified===64&&initialUnweighted.verified===64,"in-span failure");
  insist(initialWeighted.weighted<=initialUnweighted.weighted,"weighted greed failed");
  // Hold out a point mutation outside the queried set. Never retain an unverified prediction.
  const bumped=Array.from({length:N},(_,x)=>x).find(x=>!weighted.some(p=>p.x===x));
  const bumpSource=oracle(cleanCases[0],bumped),bp=atlas.predict(bumpSource,weighted),ba=audit(bumpSource,bp);
  insist(ba.errors===1,"hidden mutation not detected");
  // Independently selected three new directions. All are outside the learned span.
  const expansion=[];
  for(let j=12;j<15;j++){
    const c=choose(12,1<<j),s=oracle(c),p=atlas.predict(s,atlas.plan(true)),a=audit(s,p);
    insist(a.errors>0,"novel direction not rejected");
    const old=atlas.rows.length;insist(atlas.add(a.actual),"novel direction not added");
    expansion.push({rankBefore:old,rankAfter:atlas.rows.length,wrongPredictedCells:a.errors,sourceReads:s.accounting().calls,sourceCost:s.accounting().weighted});
  }
  const novelCases=Array.from({length:128},()=>choose(15));
  const newPlan=atlas.plan(true),expanded=evaluate(novelCases,newPlan);
  insist(expanded.verified===128,"expanded basis failure");
  // Compare against independently acquired complete observations, not a lookup of targets.
  const directCost=Array.from({length:N},(_,x)=>cost(x)).reduce((a,b)=>a+b,0);
  const trainingAndExpansion=stats.trainingReads+expansion.reduce((s,e)=>s+e.sourceReads,0);
  const trainingAndExpansionCost=trainingWeighted+expansion.reduce((s,e)=>s+e.sourceCost,0);
  return {domain:N,initialRank:12,expandedRank:atlas.rows.length,initialTrainingSources:18,initialTrainingReads:trainInitial,initialTrainingCost:trainingWeighted,initialWeighted,initialUnweighted,hiddenMutation:{coordinate:bumped,errors:ba.errors,admitted:false},expansion,expanded,trainingAndExpansion,trainingAndExpansionCost,fullSourceCost:directCost,stats,conditionalBreakEven:{initialReads:Math.ceil(trainInitial/(N-12)),expandedReads:Math.ceil(trainingAndExpansion/(N-15)),expandedWeighted:Math.ceil(trainingAndExpansionCost/(directCost-expanded.weighted/expanded.cases))}};
}
if (require.main === module) console.log(JSON.stringify(experiment(),null,2));
module.exports={experiment};
