function experiment() {
  "use strict";
  const P=257, MAX=5;
  const mod=x=>((x%P)+P)%P;
  const counts=()=>({source:0,field:0,lookup:0,event:0,compare:0,write:0});
  const total=c=>Object.values(c).reduce((a,b)=>a+b,0);
  const add=(a,b,c)=>(c.field++,mod(a+b));
  const mul=(a,b,c)=>(c.field++,mod(a*b));
  const eq=(a,b,c)=>(c.compare++,a===b);
  const read=(a,i,c)=>(c.lookup++,a[i]);
  const assert=(x,m)=>{if(!x)throw Error(m)};
  let seed=19491;
  const rnd=n=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%n};
  // Independent source representation: Horner in the ordinary power basis.
  function source(coeff, corrupt=false) {
    return Array.from({length:P},(_,x)=>{
      let y=0;for(let j=coeff.length-1;j>=0;j--)y=mod(y*x+coeff[j]);
      return mod(y+(corrupt&&x===117?1:0));
    });
  }
  function observe(tab,x,c){c.source++;return tab[x]}
  // Discover Newton coefficients without access to source coefficients.
  function discover(tab,c){
    let a=Array.from({length:MAX+1},(_,i)=>observe(tab,i,c)), out=[];
    while(a.length){out.push(a[0]);a=a.slice(1).map((v,i)=>add(v,-a[i],c))}
    while(out.length>1&&eq(out.at(-1),0,c))out.pop();
    return out;
  }
  // Generic reusable representation, no source values in it.
  // Construct B_j(x)=binom(x,j) modulo P by Pascal recurrence.
  function compile(d,c){
    const b=Array.from({length:P},()=>Array(d+2).fill(0));
    b[0][0]=1;c.write++;
    for(let x=1;x<P;x++){
      b[x][0]=1;c.write++;
      for(let j=1;j<=d+1;j++){
        b[x][j]=add(read(b[x-1],j,c),read(b[x-1],j-1,c),c);c.write++;
      }
    }
    // Independent multiplicative factorial identity, including wrap at P.
    // Since j<P, j! is invertible. Avoid relying on the compiler recurrence.
    for(let x=0;x<P;x++){
      let falling=1,fact=1;
      for(let j=0;j<=d+1;j++){
        if(j){falling=mul(falling,x-j+1,c);fact=mul(fact,j,c)}
        assert(eq(mul(read(b[x],j,c),fact,c),falling,c),"basis identity");
        const diff=add(read(b[(x+1)%P],j,c),-read(b[x],j,c),c);
        assert(eq(diff,j?read(b[x],j-1,c):0,c),"cyclic difference identity");
      }
    }
    return b;
  }
  function evalBasis(b,coeff,x,shift,c){
    let y=0;
    for(let j=0;j<coeff.length;j++)y=add(y,mul(coeff[j],read(b[x],j+shift,c),c),c);
    return y;
  }
  // Independent universal source binding: exhaustive finite domain.
  function qualifies(tab,coeff,b,c){
    for(let x=0;x<P;x++)if(!eq(observe(tab,x,c),evalBasis(b,coeff,x,0,c),c))return false;
    return true;
  }
  // Event history is an external fixture, not inferred from the law.
  // Index is created once per task and verified against the ordered journal.
  function index(events,c){
    let times=[],sums=[0],s=0,prev=-1;
    for(const [t,v] of events){
      c.event+=2;c.compare++;
      assert(Number.isSafeInteger(t)&&t>prev&&Number.isInteger(v)&&v>=0&&v<P,"invalid event");
      prev=t;times.push(t);s=add(s,v,c);sums.push(s);c.write+=2;
    }
    for(let i=events.length-1;i>=0;i--){
      c.event+=2;
      assert(eq(read(times,i,c),events[i][0],c),"event time");
      assert(eq(add(read(sums,i+1,c),-read(sums,i,c),c),events[i][1],c),"event delta");
    }
    return {times,sums};
  }
  function prefix(ix,t,c){
    let l=0,r=ix.times.length;
    while(l<r){let m=Math.floor((l+r)/2);c.compare++;if(read(ix.times,m,c)<t)l=m+1;else r=m}
    return read(ix.sums,l,c);
  }
  function replay(tab,events,x,y,n,c){
    let i=0;
    for(let t=0;t<n;t++){
      y=add(y,observe(tab,x,c),c);
      if(i<events.length){c.compare++;c.event++;if(events[i][0]===t){c.event++;y=add(y,events[i++][1],c)}}
      x=add(x,1,c);
    }
    return [x,y];
  }
  // Independent oracle for large coordinates: sum the entire period and tail.
  function oracle(tab,events,x,y,n,c){
    let sum=0;
    for(let k=0;k<P;k++)sum=add(sum,observe(tab,k,c),c);
    y=add(y,mul(sum,mod(Math.floor(n/P)),c),c);
    for(let k=0;k<n%P;k++)y=add(y,observe(tab,mod(x+k),c),c);
    for(const [t,v] of events){c.event+=2;c.compare++;if(t<n)y=add(y,v,c)}
    return [mod(x+n%P),y];
  }
  function navigate(b,coeff,ix,x,y,n,c){
    const end=add(x,mod(n),c);
    y=add(y,evalBasis(b,coeff,end,1,c),c);
    y=add(y,-evalBasis(b,coeff,x,1,c),c);
    return [end,add(y,prefix(ix,n,c),c)];
  }
  const modes=["eager","fixed","cold","warm","periodic"];
  function campaign(label,degrees,horizons,queries,withPoison){
    const results=Object.fromEntries(modes.map(m=>[m,{cost:counts(),oracle:counts(),qualified:0,refused:0,fallback:0,compiled:0,retainedBytes:0,peakBasisBytes:0}]));
    const vocab=new Map();
    const fixed=compile(1,results.fixed.cost);results.fixed.compiled++;
    results.fixed.retainedBytes=P*3*2;
    let poisonCount=0;
    for(let i=0;i<degrees.length;i++){
      const d=degrees[i],coeff=Array.from({length:d+1},()=>rnd(P));if(!coeff[d])coeff[d]=1;
      const poison=withPoison&&i%7===6;if(poison)poisonCount++;
      const tab=source(coeff,poison),x=rnd(P),y=rnd(P);
      const ns=Array.from({length:queries},(_,k)=>horizons[i%horizons.length]+k*19);
      const events=Array.from({length:12},(_,k)=>[k*83+rnd(70),rnd(P)]);
      for(const mode of modes){
        const r=results[mode],c=r.cost;let b=null,a=null,ix=null,ok=false;
        if(mode==="periodic"){
          // Strong non-learning baseline: any finite source is periodic in x.
          // Build its full cyclic prefix once per task.
          let sums=[0];for(let k=0;k<P;k++){sums.push(add(sums.at(-1),observe(tab,k,c),c));c.write++}
          // Independently check every source increment.
          for(let k=0;k<P;k++)assert(eq(add(read(sums,k+1,c),-read(sums,k,c),c),observe(tab,k,c),c),"period prefix");
          ix=index(events,c);
          for(const n of ns){
            const end=mod(x+n%P),cycles=Math.floor(n/P)+Math.floor((x+n%P)/P);
            let val=add(y,mul(read(sums,P,c),mod(cycles),c),c);
            val=add(val,add(read(sums,end,c),-read(sums,x,c),c),c);
            val=add(val,prefix(ix,n,c),c);
            const expected=oracle(tab,events,x,y,n,r.oracle);
            assert(end===expected[0]&&val===expected[1],"periodic mismatch");
          }
          continue;
        }
        if(mode!=="eager"){
          a=discover(tab,c);let degree=a.length-1;
          if(mode==="fixed"){if(degree<=1)b=fixed}
          else if(mode==="warm"&&vocab.has(degree))b=vocab.get(degree);
          else {b=compile(degree,c);r.compiled++}
          if(b)r.peakBasisBytes=Math.max(r.peakBasisBytes,P*b[0].length*2);
          ok=!!b&&qualifies(tab,a,b,c);
          if(ok){
            r.qualified++;
            if(mode==="warm"&&!vocab.has(degree)){
              vocab.set(degree,b);r.retainedBytes+=P*b[0].length*2;
            }
            ix=index(events,c);
          }else{r.refused++;r.fallback++}
          if(poison)assert(!ok,"false Ground admitted");
        }
        for(const n of ns){
          const got=ok?navigate(b,a,ix,x,y,n,c):replay(tab,events,x,y,n,c);
          const expected=oracle(tab,events,x,y,n,r.oracle);
          assert(got[0]===expected[0]&&got[1]===expected[1],label+" "+mode+" mismatch");
        }
      }
    }
    for(const r of Object.values(results)){r.work=total(r.cost);r.auditWork=total(r.oracle);r.withAudit=r.work+r.auditWork}
    return {label,tasks:degrees.length,queriesPerTask:queries,poisonCount,results};
  }
  const campaigns=[
    campaign("transfer-long",Array.from({length:42},(_,i)=>[1,2,3,5][i%4]),[2048,8192,16384],3,true),
    campaign("short-horizon",Array.from({length:24},(_,i)=>[1,2,3,5][i%4]),[8,16,32],1,true),
    campaign("unfamiliar-degree",Array.from({length:24},(_,i)=>i%6),[1024,4096],2,true)
  ];
  // Further controls: large coordinate, missing history is not recoverable,
  // invalid event sequence refuses, finite-domain wrap independently checked.
  const c=counts(),tab=source([3,7,9,2]),a=discover(tab,c),b=compile(a.length-1,c);
  assert(qualifies(tab,a,b,c),"long law qualification");
  const ev=[[2,9],[100,44],[999999999999,5]],ix=index(ev,c);
  const n=1000000000000,got=navigate(b,a,ix,251,13,n,c);
  const expected=oracle(tab,ev,251,13,n,counts());
  assert(got.join(",")===expected.join(","),"large-coordinate mismatch");
  const omitted=navigate(b,a,index(ev.slice(0,-1),c),251,13,n,c);
  assert(omitted[1]!==got[1],"missing external information counterexample");
  let refused=false;try{index([[2,9],[2,4]],c)}catch{refused=true}
  assert(refused,"duplicate time accepted");
  const adversary=source([3,7,9,2],true);
  assert(discover(adversary,c).join(",")===a.join(","),"counterexample did not match initial observations");
  assert(!qualifies(adversary,a,b,c),"false law accepted");
  return {version:"RGF-001",field:P,maxDegree:MAX,seed:19491,campaigns,controls:{largeCoordinate:n,result:got,omittedEvent:omitted,duplicateTime:"refused",deceptiveSource:"refused",work:total(c)}};
}

console.log(JSON.stringify(experiment(), null, 2));
