function escape(src){
 const id=t=>t.map(x=>x.join(",")).join(";");
 const canonical=t=>t.map(x=>x.slice()).sort((a,b)=>a[0]-b[0]||a[1]-b[1]||a[2]-b[2]);
 function verify(ts){let rows=[0,0,0,0];for(let [a,b,c] of ts){if(!(a&&b&&c)||[a,b,c].some(x=>x>=16))return false;let z=0;for(let i=0;i<4;i++)if(a>>i&1)z^=b<<(4*i);for(let i=0;i<4;i++)if(c>>i&1)rows[i]^=z}for(let i=0;i<2;i++)for(let k=0;k<2;k++){let z=0;for(let j=0;j<2;j++)z^=1<<((2*i+j)*4+2*j+k);if(z!==rows[i*2+k])return false}return true}
 function reduction(ts){for(;;){let n=ts.length;for(let a=0;a<3;a++){let b=(a+1)%3,c=(a+2)%3,m=new Map();for(let x of ts){if(!x.every(Boolean))continue;let key=16*x[b]+x[c];if(m.has(key))m.get(key)[a]^=x[a];else m.set(key,x.slice())}ts=[...m.values()].filter(x=>x.every(Boolean))}if(ts.length===n)return canonical(ts)}}
 function move(ts,a,i,j){let b=(a+1)%3,c=(a+2)%3,x=ts[i],y=ts[j],u=x.slice(),v=y.slice(),out=ts.map(t=>t.slice());if(x[a]!==y[a]){let w=x.slice();w[a]^=y[a];u[a]=y[a];out.push(w)}u[c]^=y[c];v[b]^=x[b];out[i]=u;out[j]=v;return reduction(out)}
 function run(cap,seed,budget){let s=seed;function rand(n){s^=s<<13;s^=s>>>17;s^=s<<5;return (s>>>0)%n}
 let ts=src,path=[],best=src.length,accepted=0,attempts=0;
 for(let trial=0;trial<budget;trial++){attempts++;if(trial%160===0){ts=src;path=[]}let a=rand(3),i,j,g=new Map();for(let k=0;k<ts.length;k++){let x=ts[k][a];if(!g.has(x))g.set(x,[]);g.get(x).push(k)}let gs=[...g.values()].filter(x=>x.length>1);if(gs.length&&(ts.length===cap||rand(100)<75)){let t=gs[rand(gs.length)];i=t[rand(t.length)];do{j=t[rand(t.length)]}while(i===j)}else{i=rand(ts.length);j=rand(ts.length-1);if(j>=i)j++}
 let out=move(ts,a,i,j);if(out.length>cap||id(out)===id(ts))continue;ts=out;accepted++;path.push({action:[a,i,j],rank:out.length,ground:out});if(!verify(out))throw Error("invalid move");if(out.length<best){best=out.length;let check=src;for(let p of path){check=move(check,...p.action);if(id(check)!==id(p.ground))throw Error("bad path")}return {cap,seed,budget,attempts,accepted,best,witness:path}}
 }return {cap,seed,budget,attempts,accepted,best,witness:[]}
 }
 let results=[];for(let cap of [9,10,11]){let r=run(cap,8729+cap,250000);results.push(r);if(r.best<8)break}return results;
}
const fs=require('node:fs'),path=require('node:path');console.log(JSON.stringify(escape(JSON.parse(fs.readFileSync(path.join(__dirname,'mmg016_results.json'),'utf8')).found.ground),null,2));
