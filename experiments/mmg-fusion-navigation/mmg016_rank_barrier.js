function barrier(){
const n=2,d=4,seed=[[9,9,9],[12,1,12],[1,10,10],[8,5,5],[3,8,3],[5,3,8],[10,12,1]];
function verify(ts){let rows=[0,0,0,0];for(let [a,b,c] of ts){if(!(a&&b&&c)||[a,b,c].some(x=>x>=16))return false;let z=0;for(let i=0;i<4;i++)if(a>>i&1)z^=b<<(4*i);for(let i=0;i<4;i++)if(c>>i&1)rows[i]^=z}for(let i=0;i<2;i++)for(let k=0;k<2;k++){let z=0;for(let j=0;j<2;j++)z^=1<<((2*i+j)*4+2*j+k);if(z!==rows[i*2+k])return false}return true}
function canonical(t){return t.map(x=>x.slice()).sort((a,b)=>a[0]-b[0]||a[1]-b[1]||a[2]-b[2])}
const id=t=>t.map(x=>x.join(",")).join(";");
function reduction(ts){for(;;){let n=ts.length;for(let a=0;a<3;a++){let b=(a+1)%3,c=(a+2)%3,m=new Map();for(let x of ts){if(!x.every(Boolean))continue;let key=16*x[b]+x[c];if(m.has(key))m.get(key)[a]^=x[a];else m.set(key,x.slice())}ts=[...m.values()].filter(x=>x.every(Boolean))}if(ts.length===n)return canonical(ts)}}
function move(ts,a,i,j){let b=(a+1)%3,c=(a+2)%3,x=ts[i],y=ts[j],u=x.slice(),v=y.slice(),out=ts.map(t=>t.slice());if(x[a]!==y[a]){let w=x.slice();w[a]^=y[a];u[a]=y[a];out.push(w)}u[c]^=y[c];v[b]^=x[b];out[i]=u;out[j]=v;return reduction(out)}
function inspect(ts){let hist={},distinct=new Set(),lower=0,neutral=0,src=id(ts);for(let a=0;a<3;a++)for(let i=0;i<ts.length;i++)for(let j=0;j<ts.length;j++){if(i===j)continue;let out=move(ts,a,i,j),k=id(out);if(!verify(out))throw Error("invalid neighbor");hist[out.length]=(hist[out.length]||0)+1;distinct.add(k);if(out.length<ts.length)lower++;if(out.length===ts.length&&k!==src)neutral++}return {hist,distinct:distinct.size,lower,neutral,queries:3*ts.length*(ts.length-1)}}
let s=1258303;function rand(n){s^=s<<13;s^=s>>>17;s^=s<<5;return (s>>>0)%n}
let root=canonical(seed),ts=root,path=[root],found=null,tested=0,proposals=0,seen=new Set(),bestWeak=null;
// Expand from the optimum; independently check a candidate's actual outgoing edges.
for(let trial=0;trial<180000;trial++){
 if(trial%20===0){ts=root;path=[root]}
 let a=rand(3),i=rand(ts.length),j=rand(ts.length-1);if(j>=i)j++;let out=move(ts,a,i,j);proposals++;if(out.length>11)continue;ts=out;path.push(out);
 if(ts.length<8||ts.length>10)continue;
 let k=id(ts);if(seen.has(k))continue;seen.add(k);
 let repeats=[0,1,2].reduce((a,b)=>a+ts.length-new Set(ts.map(x=>x[b])).size,0);
 if(repeats>2)continue;
 let p=inspect(ts);tested++;
 if(!p.lower&&(!bestWeak||p.neutral<bestWeak.inspection.neutral))bestWeak={ground:ts,inspection:p};
 if(p.lower===0&&p.neutral===0){found={ground:ts,inspection:p,rootPath:path.slice(),repeats,at:trial};break}
}
// A path from root to found is not automatically reversible after reductions. BFS forward up to +2 rank.
if(found){let src=found.ground,cap=src.length+2,q=[src],par=new Map([[id(src),null]]),goal=null,expanded=0,maxNodes=45000;
 for(let i=0;i<q.length&&q.length<maxNodes&&!goal;i++){let t=q[i],key=id(t);expanded++;for(let a=0;a<3&&!goal;a++)for(let j=0;j<t.length&&!goal;j++)for(let k=0;k<t.length;k++){if(j===k)continue;let u=move(t,a,j,k),z=id(u);if(u.length>cap||par.has(z))continue;par.set(z,{prev:key,action:[a,j,k],ground:u});q.push(u);if(u.length<src.length){goal=z;break}if(q.length>=maxNodes)break}}
 let witness=[];if(goal){let z=goal;while(par.get(z)){let e=par.get(z);witness.push({action:e.action,ground:e.ground,rank:e.ground.length});z=e.prev}witness.reverse();let t=src;for(let e of witness){t=move(t,...e.action);if(id(t)!==id(e.ground)||!verify(t))throw Error("path verification")}}
 found.escape={expanded,visited:par.size,cap,witness};
}
return {proposals,tested,found,bestWeak};
}
console.log(JSON.stringify(barrier(),null,2));
