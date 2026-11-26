"use strict";
function observatory(){
"use strict";
const assert=(v,m)=>{if(!v)throw Error(m)},sum=a=>a.reduce((s,v)=>s+v,0),dot=(a,b)=>sum(a.map((v,i)=>v*b[i])),round=x=>Math.round(x*1e6)/1e6;
const library=[
 {id:"live-respiration",label:"Live algae respiration",c:[4,0,0]},
 {id:"detrital-decay",label:"Detrital oxygen demand",c:[0,4,0]},
 {id:"temperature",label:"Temperature-associated demand",c:[0,0,4]},
 {id:"live-and-decay",label:"Mixed live/decay demand",c:[2,2,0]},
 {id:"live-and-temperature",label:"Mixed live/temperature demand",c:[2,0,2]},
 {id:"decay-and-temperature",label:"Mixed decay/temperature demand",c:[0,2,2]}
];
const actions=[
 {id:"algae",delta:[1,0,0],cost:1,label:"Change live-algae index only"},
 {id:"detritus",delta:[0,1,0],cost:1,label:"Change detritus index only"},
 {id:"temperature",delta:[0,0,1],cost:2,label:"Change temperature index only"},
 {id:"algae-detritus",delta:[1,1,0],cost:2,label:"Change algae and detritus together"},
 {id:"algae-temperature",delta:[1,0,1],cost:3,label:"Change algae and temperature together"},
 {id:"strong-algae",delta:[2,0,0],cost:3,label:"Larger algae-index contrast"},
 {id:"strong-detritus",delta:[0,2,0],cost:3,label:"Larger detritus-index contrast"},
 {id:"passive",delta:[1,1,1],cost:1,label:"Observe coupled environmental change"}
];
const auditActions=[actions[0],actions[1],actions[2],{id:"joint-audit",delta:[2,2,0],cost:4,label:"Reserved joint-response challenge"}];
const worlds=[...library.map(h=>({id:h.id,known:true,demand:x=>dot(h.c,x)})),
 {id:"interaction-outside-library",known:false,demand:x=>2*x[0]+2*x[1]+3*(x[0]-x[2])*(x[1]-x[2])},
 {id:"opposing-response-outside-library",known:false,demand:x=>-4*x[0]+4*x[1]+4*x[2]},
 {id:"unseen-threshold-outside-library",known:false,demand:x=>4*x[0]+(x[1]-x[2]>3?12:0)}
];
function rng(seed){let x=seed>>>0;return ()=>{x=(Math.imul(x,1664525)+1013904223)>>>0;return x/4294967296;};}
const single=[1,2,1],paired=[1,4,6,4,1],noise=r=>[-1,0,0,1][Math.floor(r()*4)];
function likelihood(error,contrast){const weights=contrast?paired:single,offset=contrast?2:1;return weights[error+offset]||0;}
function entropy(p){return -sum(p.filter(x=>x>0).map(x=>x*Math.log2(x)));}
const normalize=w=>{const n=sum(w);return n?w.map(x=>x/n):w.map(()=>0);};
const prior=()=>library.map(()=>1/library.length);
function update(p,means,y,contrast){
 return normalize(p.map((v,i)=>v*likelihood(y-means[i],contrast)));
}
const support=p=>library.filter((_,i)=>p[i]>0).map(h=>h.id);
function information(p,action){
 const means=library.map(h=>dot(h.c,action.delta)),outcomes=[...new Set(means.flatMap(m=>[-2,-1,0,1,2].map(e=>m+e)))];let conditional=0;
 for(const y of outcomes){const q=p.map((v,i)=>v*likelihood(y-means[i],true)/16),py=sum(q);if(py)conditional+=py*entropy(normalize(q));}
 return Math.max(0,entropy(p)-conditional);
}
function choose(p,menu,remaining,policy,r,step){
 const valid=menu.filter(a=>a.cost<=remaining);if(!valid.length)return null;
 if(policy==="passive")return valid.find(a=>a.id==="passive")||null;
 if(policy==="random")return valid[Math.floor(r()*valid.length)];
 if(policy==="fixed")return valid.find(a=>a.id==="algae")||null;
 if(policy==="balanced"){const ids=["algae","detritus","temperature"];for(let j=0;j<ids.length;j++){const a=valid.find(a=>a.id===ids[(step+j)%ids.length]);if(a)return a;}return null;}
 const ranked=valid.map(a=>({a,info:information(p,a)})).sort((x,y)=>y.info/y.a.cost-x.info/x.a.cost||x.a.cost-y.a.cost||x.a.id.localeCompare(y.a.id,"en"));
 return ranked[0].info>1e-12?ranked[0].a:null;
}
// Simulator is a separate closure: observer sees only recorded standardized
// measurements and intervention contrasts, never world ID or demand function.
function apparatus(world,seed){
 const r=rng(seed),auditR=rng(seed^0x4be77319);return {
  natural(day){const k=2+(day%5);return {day,x:[k,k,k],y:world.demand([k,k,k])+noise(r)};},
  experiment(action,serial,stage){
   const k=3+(serial%3),control=[k,k,k],treated=control.map((v,i)=>v+action.delta[i]);
   const stream=stage==="reserved-audit"?auditR:r;const c=world.demand(control)+noise(stream),t=world.demand(treated)+noise(stream);
   return {stage,serial,action:action.id,delta:action.delta.slice(),cost:action.cost,control,treated,controlReading:c,treatedReading:t,contrast:t-c};
  }
 };
}
function state(p){const ids=support(p);return {status:ids.length===0?"model-library-rejected":ids.length===1?"one-model-survives":"unresolved",survivors:ids,posterior:p.map(round)};}
function observe(instrument,policy,seed,budget=8){
 let p=prior();const natural=[],ledger=[],r=rng(seed^0x7b42),menu=actions;
 for(let i=0;i<8;i++){const o=instrument.natural(i);p=update(p,library.map(h=>dot(h.c,o.x)),o.y,false);natural.push(o);}
 const observational=state(p);let spent=0;
 while(spent<budget&&support(p).length>1){
  const action=choose(p,menu,budget-spent,policy,r,ledger.length);if(!action)break;
  const predictions=library.map(h=>dot(h.c,action.delta)),before=state(p),gain=information(p,action);
  const o=instrument.experiment(action,ledger.length,"exploration");spent+=action.cost;
  p=update(p,predictions,o.contrast,true);
  ledger.push({question:action.label+"; which candidate contrasts survive?",predictions:library.map((h,i)=>({id:h.id,mean:predictions[i],range:[predictions[i]-2,predictions[i]+2]})),expectedInformationBits:round(gain),before,observation:o,after:state(p)});
 }
 const exploration=state(p),audit=[];
 // Reserved audit schedule independent of adaptive selection. Fresh
 // measurements even for previously used intervention types.
 for(let i=0;i<auditActions.length;i++){
  const a=auditActions[i],before=state(p),o=instrument.experiment(a,100+i,"reserved-audit"),means=library.map(h=>dot(h.c,a.delta));
  p=update(p,means,o.contrast,true);audit.push({before,observation:o,predictedMeans:means,after:state(p)});
 }
 const final=state(p),questions=[];
 if(final.status==="model-library-rejected")questions.push({kind:"model-inadequacy",text:"Which omitted mechanism could explain the incompatible contrasts? Propose a new model and reserve fresh evidence before admitting it.",evidence:[...ledger.map(x=>x.observation),...audit.map(x=>x.observation)]});
 else if(final.status==="unresolved"){const candidate=choose(p,menu,Infinity,"adaptive",r,0);questions.push({kind:"unresolved-discrimination",text:candidate?candidate.label+"; discriminate the remaining candidate laws.":"The offered intervention menu cannot separate the surviving models.",survivors:final.survivors});}
 else questions.push({kind:"external-validity",text:"Which new perturbation or environmental context could falsify the surviving model? Survival is conditional on this candidate library and noise assumption.",survivors:final.survivors});
 return {policy,budget,spent,natural,observational,ledger,exploration,audit,auditCost:sum(auditActions.map(a=>a.cost)),final,questions};
}
function replay(record){
 let p=prior();for(const o of record.natural)p=update(p,library.map(h=>dot(h.c,o.x)),o.y,false);
 assert(JSON.stringify(state(p))===JSON.stringify(record.observational),"natural replay");
 for(const e of [...record.ledger,...record.audit]){
  const o=e.observation;assert(o.contrast===o.treatedReading-o.controlReading&&o.treated.every((v,i)=>v-o.control[i]===o.delta[i]),"contrast provenance");
  assert(JSON.stringify(state(p))===JSON.stringify(e.before),"state continuity");
  p=update(p,library.map(h=>dot(h.c,o.delta)),o.contrast,true);
  assert(JSON.stringify(state(p))===JSON.stringify(e.after),"likelihood replay");
 }
 assert(JSON.stringify(state(p))===JSON.stringify(record.final),"final replay");return true;
}
// Prospective coverage challenge, separated from the policy comparison.
// It tests an explicitly new environmental context, not an inferred field intervention.
const newContext={id:"detritus-context-expansion",delta:[0,4,0],cost:6,label:"Extend the detritus contrast beyond the original menu"};
const coverage=[];for(let seed=1;seed<=40;seed++){
 const w=worlds.at(-1),r=observe(apparatus(w,seed*7919),"adaptive",seed);
 const a=apparatus(w,seed*7919^0x21ca9).experiment(newContext,200,"new-context");
 const remaining=r.final.survivors.filter(id=>Math.abs(a.contrast-dot(library.find(h=>h.id===id).c,a.delta))<=2);
 assert(remaining.length===0,"new context excludes surviving models");coverage.push({seed,previous:r.final.survivors,observation:a,remaining});
}
const policies=["adaptive","balanced","random","fixed","passive"],summary=[],examples=[];
for(const policy of policies){
 let known=0,unique=0,wrongUnique=0,unresolved=0,falseRejected=0,preUnique=0,outside=0,rejected=0,missed=0,spent=0,knownSpent=0,experiments=0,knownFinal=0;const byWorld=[];
 for(const w of worlds){
  let identified=0,refused=0,ambiguous=0,one=0,used=0;
  for(let seed=1;seed<=40;seed++){
   const run=observe(apparatus(w,seed*7919),policy,seed);
   assert(run.observational.survivors.length===library.length,"observational nonidentifiability");
   assert(run.spent<=run.budget&&replay(run),"reproducible ledger");
   spent+=run.spent;used+=run.spent;experiments+=run.ledger.length;
   if(run.final.status==="model-library-rejected")refused++;
   else if(run.final.status==="one-model-survives")one++;else ambiguous++;
   if(w.known){known++;knownSpent+=run.spent;assert(run.final.survivors.includes(w.id),"true known model eliminated");if(run.exploration.status==="one-model-survives")preUnique++;
    if(run.final.status==="one-model-survives"){if(run.final.survivors[0]===w.id){unique++;identified++;}else wrongUnique++;}
    else if(run.final.status==="unresolved")unresolved++;else falseRejected++;
   }else{outside++;if(run.final.status==="model-library-rejected")rejected++;else missed++;}
   if(policy==="adaptive"&&seed===1)examples.push({truthForEvaluationOnly:w.id,record:run});
  }
  byWorld.push({world:w.id,known:w.known,identified,refused,ambiguous,one,meanExplorationCost:round(used/40)});
 }
 summary.push({policy,known,preUnique,unique,wrongUnique,unresolved,falseRejected,outside,rejected,missed,meanExplorationCost:round(spent/(known+outside)),meanKnownExplorationCost:round(knownSpent/known),meanExperiments:round(experiments/(known+outside)),auditCost:sum(auditActions.map(a=>a.cost)),byWorld});
}
// Controls: no-op observation cannot discriminate; unknown is absorbing;
// tampered retained evidence is rejected by replay; threshold world is
// indistinguishable throughout this bounded experiment menu by construction.
assert(information(prior(),actions.at(-1))<1e-10,"passive information");
assert(update(library.map(()=>0),library.map(()=>0),0,true).every(x=>x===0),"rejection absorbing");
const bad=JSON.parse(JSON.stringify(examples[0].record));bad.audit[0].observation.contrast+=1;let refused=false;try{replay(bad);}catch{refused=true;}assert(refused,"tampered contrast");
return {version:"LO-001",scope:"synthetic standardized indices; no field data",library,actions,auditActions,summary,examples,coverageChallenge:{action:newContext,records:coverage,refused:coverage.length},controls:{passiveNonidentifiability:true,unknownAbsorbing:true,tamperedContrastRefused:true}};
}
module.exports=observatory;
if(require.main===module)console.log(JSON.stringify(observatory(),null,2));
