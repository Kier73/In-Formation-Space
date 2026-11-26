function distinctnessCampaign(){
function partitions(n){let out=[];function go(a,m){if(a.length===n){out.push(a.slice());return}for(let j=0;j<=m+1;j++){a.push(j);go(a,Math.max(m,j));a.pop()}}go([0],0);return out}
function disjoint(p,q){for(let i=0;i<p.length;i++)for(let j=0;j<i;j++)if(p[i]===p[j]&&q[i]===q[j])return 0;return 1}
function sizes(p){let c=[];for(const a of p)c[a]=(c[a]||0)+1;return c}
function factorial(n){let z=1n;for(let i=2;i<=n;i++)z*=BigInt(i);return z}
function mobius(p){let x=1n;for(const c of sizes(p))x*=((c-1)%2?-1n:1n)*factorial(c-1);return x}
function choose(n,k){let x=1n;for(let j=1;j<=k;j++)x=x*BigInt(n-j+1)/BigInt(j);return x}
function count(n,p){let a=[1n];for(let i=1;i<=n;i++){let t=0n;for(let j=1;j<=Math.min(i,p);j++)t+=choose(i-1,j-1)*a[i-j];a.push(t)}return a[n]}
function rank2(m){let basis=new Map();for(const r of m){let x=0n;for(let j=0;j<r.length;j++)if(r[j])x|=1n<<BigInt(j);while(x){let pivot=x.toString(2).length-1;if(basis.has(pivot))x^=basis.get(pivot);else{basis.set(pivot,x);break}}}return basis.size}
function rank(m,p){let rows=m.map(r=>Int16Array.from(r)),r=0,n=rows.length;for(let j=0;j<n&&r<n;j++){let i=r;while(i<n&&!rows[i][j])i++;if(i===n)continue;[rows[i],rows[r]]=[rows[r],rows[i]];let inv=1;while(rows[r][j]*inv%p!==1)inv++;for(let k=j;k<n;k++)rows[r][k]=rows[r][k]*inv%p;for(i=r+1;i<n;i++){let v=rows[i][j];if(!v)continue;for(let k=j;k<n;k++)rows[i][k]=(rows[i][k]-v*rows[r][k]+p*p)%p}r++}return r}
let tests=[];for(let n=1;n<=7;n++){let ps=partitions(n),m=ps.map(a=>ps.map(b=>disjoint(a,b)));for(const p of n===7?[2]:[2,3,5,7,11]){let r=p===2?rank2(m):rank(m,p),pred=Number(count(n,p)),diag=ps.filter(a=>mobius(a)%BigInt(p)!==0n).length;if(r!==pred||r!==diag)throw Error("partition rank mismatch");tests.push({n,p,bell:ps.length,rank:r})}}
let checks=0;for(let hi=0;hi<256;hi++)for(let lo=0;lo<256;lo++){let a=Array.from({length:4},(_,i)=>(hi>>(2*i))&3),b=Array.from({length:4},(_,i)=>(lo>>(2*i))&3);let truth=Number(new Set(a.map((x,i)=>4*x+b[i])).size===4);if(truth!==disjoint(a,b))throw Error("wrong bit-plane identity");checks++}
let rows=[];for(let w=1;w<=8;w++){let n=2**w;rows.push({w,records:n,record_cut_lower:choose(n,n/2).toString(),bit_plane_rank_2:count(n,2).toString(),bit_plane_rank_3:count(n,3).toString(),bit_plane_rank_5:count(n,5).toString(),bell:count(n,n).toString()})}return {tests,checks,rows};
}
console.log(JSON.stringify(distinctnessCampaign(),null,2));
