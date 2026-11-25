function blockExperiment(){
const mod=(x,p)=>(x%p+p)%p;
function rng(seed){return n=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)%n}}
function discover(n,edges){if(n%2)throw Error("even side required");const adj=Array.from({length:n},()=>[]);for(const [x,y] of edges){if(!Number.isInteger(x)||!Number.isInteger(y)||x<0||y<0||x>=n||y>=n||x===y)throw Error("bad edge");adj[x].push(y);adj[y].push(x)}let visited=new Uint8Array(n),blocks=[];for(let i=0;i<n;i++)if(!visited[i]){let q=[i];visited[i]=1;for(let j=0;j<q.length;j++)for(const y of adj[q[j]])if(!visited[y]){visited[y]=1;q.push(y)}if(q.length!==2)throw Error("block budget requires components of size two");blocks.push(q)}return blocks}
function compile(n,blocks,A,B,p){let C=new Int32Array(n*n),ledger={add:0,mul:0};let add=(a,b)=>{ledger.add++;return mod(a+b,p)},sub=(a,b)=>{ledger.add++;return mod(a-b,p)},mul=(a,b)=>{ledger.mul++;return a*b%p};
for(const [i,j] of blocks){const a=A[i*n+i],b=A[i*n+j],c=A[j*n+i],d=A[j*n+j];
const l=[add(a,d),add(c,d),a,d,add(a,b),sub(c,a),sub(b,d)];
for(let k=0;k<n;k+=2){let e=B[i*n+k],f=B[i*n+k+1],g=B[j*n+k],h=B[j*n+k+1];
const r=[add(e,h),e,sub(f,h),sub(g,e),h,add(e,f),add(g,h)];
const [m1,m2,m3,m4,m5,m6,m7]=l.map((x,t)=>mul(x,r[t]));
C[i*n+k]=add(sub(add(m1,m4),m5),m7);C[i*n+k+1]=add(m3,m5);C[j*n+k]=add(m2,m4);C[j*n+k+1]=add(add(sub(m1,m2),m3),m6);
}}
return {C,ledger}}
function admit(A,n,blocks){let id=new Int32Array(n);blocks.forEach((b,i)=>b.forEach(j=>id[j]=i));for(let i=0;i<n;i++)for(let j=0;j<n;j++)if(id[i]!==id[j]&&A[i*n+j]!==0)return false;return true}
let formal=0;for(const p of [2,3,5,7])for(let a=0;a<4;a++)for(let b=0;b<4;b++){let A=Array.from({length:4},(_,i)=>+(i===a)),B=Array.from({length:4},(_,i)=>+(i===b)),{C}=compile(2,[[0,1]],A,B,p);for(let i=0;i<2;i++)for(let j=0;j<2;j++)if(C[i*2+j]!==mod(A[i*2]*B[j]+A[i*2+1]*B[2+j],p))throw Error("basis mismatch");formal++}
let runs=[];for(const p of [2,3,5])for(const n of [4,8,16,32,64,128,256,512,1024]){let random=rng(7123+p*100+n),labels=Array.from({length:n},(_,i)=>i);for(let i=n-1;i>0;i--){let j=random(i+1);[labels[i],labels[j]]=[labels[j],labels[i]]}let edges=Array.from({length:n/2},(_,j)=>[labels[2*j],labels[2*j+1]]),blocks=discover(n,edges),A=new Int32Array(n*n),B=Int32Array.from({length:n*n},()=>random(p));for(const b of blocks)for(const i of b)for(const j of b)A[i*n+j]=random(p);
if(!admit(A,n,blocks))throw Error("admission");let {C,ledger}=compile(n,blocks,A,B,p);for(const [i,j] of blocks)for(let k=0;k<n;k++){if(C[i*n+k]!==mod(A[i*n+i]*B[i*n+k]+A[i*n+j]*B[j*n+k],p)||C[j*n+k]!==mod(A[j*n+i]*B[i*n+k]+A[j*n+j]*B[j*n+k],p))throw Error("oracle mismatch")}
let cap=7*n*n/4,totalCap=5*n*n+5*n/2;if(ledger.mul!==cap||ledger.add+ledger.mul!==totalCap||2*n*n<=cap)throw Error("ledger");
let rejects=0;A[blocks[0][0]*n+blocks[1][0]]=1;if(admit(A,n,blocks))throw Error("tamper admitted");rejects++;
try{discover(n,[...edges,[blocks[0][0],blocks[1][0]]]);throw Error("bad accepted")}catch(e){if(e.message==="bad accepted")throw e;rejects++}
runs.push({p,n,blocks:blocks.length,oracle_coordinates:n*n,product_cap:cap,field_op_cap:totalCap,products:ledger.mul,additions:ledger.add,total:ledger.mul+ledger.add,classical_block_products:2*n*n,classical_block_ops:3*n*n,rejects});
}
return {formal_basis_cases:formal,runs};
}
console.log(JSON.stringify(blockExperiment(),null,2));
