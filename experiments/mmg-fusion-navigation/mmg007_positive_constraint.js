function experiment(){
const mod=(x,p)=>(x%p+p)%p;
function rng(seed){return n=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)%n}}
function inv(a,p){for(let i=1;i<p;i++)if(a*i%p===1)return i;throw Error("nonunit")}
function mat(a,b,p){return [mod(a[0]*b[0]+a[1]*b[2],p),mod(a[0]*b[1]+a[1]*b[3],p),mod(a[2]*b[0]+a[3]*b[2],p),mod(a[2]*b[1]+a[3]*b[3],p)]}
function eq(a,b){return a.length===b.length&&a.every((x,i)=>x===b[i])}
function diagonalGrounds(p){
 let count={split:0,repeated:0,nonsplit:0},verified=0,examples={},spaces=[];
 const lines=[[0,1],...Array.from({length:p},(_,t)=>[1,t])];
 for(let b=0;b<p;b++)for(let c=0;c<p;c++)for(let d=0;d<p;d++){
  let first=[b,c,d].find(x=>x!==0);if(first!==1)continue;
  let a=[0,b,c,d],eig=[];
  for(const [x,y] of lines)for(let l=0;l<p;l++)if(mod(b*y-l*x,p)===0&&mod(c*x+d*y-l*y,p)===0)eig.push({v:[x,y],l});
  let kind=eig.length===2?"split":eig.length===1?"repeated":"nonsplit";count[kind]++;
  if(!examples[kind])examples[kind]={operator:a,eig};
  if(kind!=="split")continue;
  let [[x,y],[z,t]]=eig.map(e=>e.v),s=[x,z,y,t],h=inv(mod(x*t-y*z,p),p),si=[mod(t*h,p),mod(-z*h,p),mod(-y*h,p),mod(x*h,p)];
  if(!eq(mat(si,s,p),[1,0,0,1]))throw Error("bad inverse");
  if(!eq(mat(mat(si,a,p),s,p),[eig[0].l,0,0,eig[1].l]))throw Error("bad ground");
  // For every alpha,beta and all four right-input basis matrices, formal bilinear identity.
  for(let alpha=0;alpha<p;alpha++)for(let beta=0;beta<p;beta++){
   let aa=[alpha,mod(beta*b,p),mod(beta*c,p),mod(alpha+beta*d,p)],l=eig.map(e=>mod(alpha+beta*e.l,p));
   for(let q=0;q<4;q++){let bb=Array.from({length:4},(_,i)=>Number(i===q)),e=mat(si,bb,p),out=mat(s,[e[0]*l[0]%p,e[1]*l[0]%p,e[2]*l[1]%p,e[3]*l[1]%p],p);if(!eq(out,mat(aa,bb,p)))throw Error("wrong product");verified++}
  }
  spaces.push({a,eig,s,si});
 }
 if(count.split!==p*(p+1)/2||count.repeated!==p+1||count.nonsplit!==p*(p-1)/2)throw Error("classification count");
 return {p,spaces:Object.values(count).reduce((a,b)=>a+b),...count,verified,examples};
}
function discover(gens){
 const k=gens.length,n=2**k;if(k>20)throw Error("oversized");let seen=new Int32Array(n).fill(-1),loc=new Int32Array(n);let checks=0;
 for(const g of gens){if(g.length!==n||new Set(g).size!==n||g.some(v=>!Number.isInteger(v)||v<0||v>=n))throw Error("invalid permutation")}
 loc[0]=0;seen[0]=0;
 for(let a=1;a<n;a++){let bit=a&-a,j=31-Math.clz32(bit),x=gens[j][loc[a^bit]];if(seen[x]!==-1)throw Error("dependent orbit");loc[a]=x;seen[x]=a}
 for(let a=0;a<n;a++)for(let j=0;j<k;j++){checks++;if(gens[j][loc[a]]!==loc[a^(1<<j)])throw Error("noncommuting/noninvolutive generator")}
 return {loc,seen,checks};
}
function hadamard(a,n,cols,p,ledger){for(let h=1;h<n;h*=2)for(let i=0;i<n;i+=2*h)for(let j=0;j<h;j++)for(let c=0;c<cols;c++){let u=(i+j)*cols+c,v=u+h*cols,x=a[u],y=a[v];a[u]=mod(x+y,p);a[v]=mod(x-y,p);ledger.add+=2}}
function run(p,k,seed){
 const n=2**k,random=rng(seed),labels=Array.from({length:n},(_,i)=>i);for(let i=n-1;i>0;i--){let j=random(i+1);[labels[i],labels[j]]=[labels[j],labels[i]]}
 const gens=Array.from({length:k},(_,j)=>{let a=new Int32Array(n);for(let x=0;x<n;x++)a[labels[x]]=labels[x^(1<<j)];return Array.from(a)});
 const {loc,seen,checks}=discover(gens),a=Array.from({length:n},()=>random(p)),b=Array.from({length:n*n},()=>random(p));
 // a is indexed by physical orbit point reached from physical anchor 0.
 const u=Array.from(loc,x=>a[x]),v=new Int32Array(n*n),ledger={add:0,mul:0,scale:0};
 for(let i=0;i<n;i++)for(let j=0;j<n;j++)v[i*n+j]=b[loc[i]*n+j];
 hadamard(u,n,1,p,ledger);hadamard(v,n,n,p,ledger);
 for(let i=0;i<n;i++)for(let j=0;j<n;j++){v[i*n+j]=u[i]*v[i*n+j]%p;ledger.mul++}
 hadamard(v,n,n,p,ledger);let scale=inv(n%p,p),out=new Int32Array(n*n);
 for(let i=0;i<n;i++)for(let j=0;j<n;j++){let z=v[i*n+j];if(scale!==1){z=z*scale%p;ledger.scale++}out[loc[i]*n+j]=z}
 let full=n<=128,tests=full?n*n:512;
 for(let q=0;q<tests;q++){let i=full?Math.floor(q/n):random(n),j=full?q%n:random(n),acc=0;for(let h=0;h<n;h++)acc+=a[loc[seen[i]^seen[h]]]*b[h*n+j];if(acc%p!==out[i*n+j])throw Error("bad product")}
 let strictBudget=2*n*n*k+n*k+2*n*n,total=ledger.add+ledger.mul+ledger.scale;if(total>strictBudget||ledger.mul!==n*n)throw Error("budget violated");
 // Validate a dense left operand against the discovered ground, when supplied densely.
 let leftChecks=0;function admit(A){for(let i=0;i<n;i++)for(let j=0;j<n;j++){leftChecks++;if(A[i*n+j]!==a[loc[seen[i]^seen[j]]])return false}return true}
 const A=Array.from({length:n*n},(_,q)=>a[loc[seen[Math.floor(q/n)]^seen[q%n]]]);if(!admit(A))throw Error("good source rejected");A[n*n-1]=(A[n*n-1]+1)%p;if(admit(A))throw Error("bad source accepted");
 let reject=0;if(k>=2){let dependent=gens.map(g=>g.slice());dependent[1]=dependent[0].slice();try{discover(dependent);throw Error("accepted dependent")}catch(e){if(e.message==="accepted dependent")throw e;reject++}let damaged=gens.map(g=>g.slice());[damaged[0][0],damaged[0][1]]=[damaged[0][1],damaged[0][0]];try{discover(damaged);throw Error("accepted damaged")}catch(e){if(e.message==="accepted damaged")throw e;reject++}}
 return {p,n,k,seed,structural_checks:checks,source_admission_checks:leftChecks,rejected_generator_controls:reject,full_oracle:full,oracle_coordinates:tests,...ledger,total,budget:strictBudget,output_checksum:out.reduce((h,x)=>(Math.imul(h,16777619)^x)>>>0,2166136261)};
}
let tiny=[2,3,5,7].map(diagonalGrounds);
let runs=[];for(let p of [3,5,7])for(let k=1;k<=7;k++)runs.push(run(p,k,20261125+p*100+k));for(let k=8;k<=10;k++)runs.push(run(3,k,20261125+k));
let characteristicTwoRejected=false;try{inv(0,2)}catch(e){characteristicTwoRejected=true}
return {tiny,runs,characteristicTwoRejected};
}
console.log(JSON.stringify(experiment(),null,2));
