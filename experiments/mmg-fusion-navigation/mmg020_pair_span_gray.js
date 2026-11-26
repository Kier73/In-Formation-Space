function scan(data){
const bits=x=>{let a=[];for(let i=0;x;x>>=1n,i++)if(x&1n)a.push(i);return a};
function outer(a,b,d){let v=0n;for(let i of bits(a))v^=b<<BigInt(i*d);return v}
function factor(v,d){let a=0n,b=0n,m=(1n<<BigInt(d))-1n;for(let i=0;i<d;i++){let x=v&m;v>>=BigInt(d);if(x){if(b&&x!==b)return null;b=x;a|=1n<<BigInt(i)}}return a?[a,b]:null}
function verify(t,n){let d=n*n,z=Array(d).fill(0n);for(let [a,b,c] of t){if(!a||!b||!c||[a,b,c].some(x=>x>>BigInt(d)))return false;let v=outer(a,b,d);for(let k of bits(c))z[k]^=v}for(let i=0;i<n;i++)for(let k=0;k<n;k++){let v=0n;for(let j=0;j<n;j++)v^=1n<<BigInt((i*n+j)*d+j*n+k);if(v!==z[i*n+k])return false}return true}
function basis(){let m=new Map();return {m,reduce(x,t=0n){while(x){let p=x.toString(2).length-1,q=m.get(p);if(!q)break;x^=q[0];t^=q[1]}return [x,t]},add(x,t=0n){let [v,z]=this.reduce(x,t);if(!v)return false;m.set(v.toString(2).length-1,[v,z]);return true}}}
function compress(ts,n){let d=n*n,r=ts.length,axes=[];
for(let a=0;a<3;a++){let b=(a+1)%3,c=(a+2)%3,B=basis();for(let i=0;i<r;i++)B.add(outer(ts[i][b],ts[i][c],d),1n<<BigInt(i));if(B.m.size!==r){axes.push({a,dependent:true});continue}
 // Enumerate rank-one matrices in the ENTIRE pair span by intersecting with each fixed-left-factor row space.
 let atoms=[],tests=0,checkedLeft=0,projectionXors=0;
 const echelon=[...B.m].sort((x,y)=>y[0]-x[0]).map(([p,[v]])=>[1n<<BigInt(p),v]);
 function project(x){for(let [p,v] of echelon)if(x&p)x^=v;return x}
 const table=Array.from({length:d},(_,i)=>Array.from({length:d},(_,j)=>project(1n<<BigInt(i*d+j))));
 function visit(u,columns){checkedLeft++;let Q=basis(),nulls=[];for(let j=0;j<d;j++){let [v,t]=Q.reduce(columns[j],1n<<BigInt(j));if(v)Q.m.set(v.toString(2).length-1,[v,t]);else nulls.push(t);tests++}
 for(let mask=1;mask<2**nulls.length;mask++){let v=0n;for(let j=0;j<nulls.length;j++)if(mask>>j&1)v^=nulls[j];let [res,coords]=B.reduce(outer(u,v,d));if(res||!coords)throw Error("bad atom");atoms.push({p:[u,v],coords})}}
 if(d<=16){let cols=Array(d).fill(0n),u=0n;for(let k=1;k<2**d;k++){let bit=31-Math.clz32(k&-k);u^=1n<<BigInt(bit);for(let j=0;j<d;j++){cols[j]^=table[bit][j];projectionXors++}visit(u,cols)}}
 else{let left=[...new Set(ts.map(t=>t[b]))],sample=new Set(left);for(let i=0;i<d;i++)sample.add(1n<<BigInt(i));for(let i=0;i<left.length;i++)for(let j=0;j<i;j++)sample.add(left[i]^left[j]);let x=217391+a;while(sample.size<16384){x^=x<<13;x^=x>>>17;x^=x<<5;let u=BigInt(x>>>0)&((1n<<BigInt(d))-1n);if(u)sample.add(u)}
 for(let u of sample){let cols=Array(d).fill(0n);for(let i of bits(u))for(let j=0;j<d;j++){cols[j]^=table[i][j];projectionXors++}visit(u,cols)}}
  let unit=atoms.filter(x=>bits(x.coords).length===1).length;
 // Every hyperplane containing the target slice space is a nonzero vector in the free-leg dual code.
 let D=basis(),nulls=[];for(let i=0;i<r;i++){let [v,t]=D.reduce(ts[i][a],1n<<BigInt(i));if(v)D.m.set(v.toString(2).length-1,[v,t]);else nulls.push(t)}
 // Entire dual code only for small dimension; else check low weight and single null basis rows.
 let rels=[],seen=new Set(),limit=nulls.length<=20?2**nulls.length:0;
 if(limit){let z=0n;for(let j=1;j<limit;j++){let p=31-Math.clz32(j&-j);z^=nulls[p];rels.push(z)}}
 else {for(let v of nulls)rels.push(v);for(let i=0;i<nulls.length;i++)for(let j=i+1;j<nulls.length;j++)rels.push(nulls[i]^nulls[j]);}
 let minSpan=r,checked=0;if(unit===r&&atoms.length===r){axes.push({a,tests,checkedLeft,projectionXors,atoms:atoms.length,unit,completeLeft:d<=16,dualDimension:nulls.length,checked:0,completeDual:false,onlyIncumbentAtoms:true,success:false});continue}for(let z of rels){let K=basis(),sel=[];for(let atom of atoms){let v=z&atom.coords,parity=0;while(v){v&=v-1n;parity^=1}if(parity)continue;if(K.add(atom.coords,1n<<BigInt(sel.length)))sel.push(atom);if(sel.length===r-1)break}checked++;minSpan=Math.min(minSpan,sel.length);
 if(sel.length!==r-1)continue;
 let cols=Array(sel.length).fill(0n);for(let j=0;j<d;j++){let v=0n;for(let i=0;i<r;i++)if(ts[i][a]>>BigInt(j)&1n)v|=1n<<BigInt(i);let [rem,tag]=K.reduce(v);if(rem)throw Error("target not included");for(let i of bits(tag))cols[i]|=1n<<BigInt(j)}
 let out=[];for(let i=0;i<sel.length;i++)if(cols[i]){let t=[];t[a]=cols[i];t[b]=sel[i].p[0];t[c]=sel[i].p[1];out.push(t)}if(out.length>=r||!verify(out,n))throw Error("bad result");axes.push({a,tests,checkedLeft,projectionXors,completeLeft:d<=16,atoms:atoms.length,unit,dualDimension:nulls.length,checked,completeDual:!!limit,minSpan,success:true});return {axes,out}
 }
 axes.push({a,tests,checkedLeft,projectionXors,completeLeft:d<=16,atoms:atoms.length,unit,dualDimension:nulls.length,checked,completeDual:!!limit,minSpan,success:false});
}return {axes}}
let inputs=data.hot.map(x=>({label:"rank"+x.best,n:x.n,t:x.terms.map(t=>t.map(BigInt))}));return inputs.map(({label,n,t})=>{if(!verify(t,n))throw Error("seed");let initial=t.length,z=compress(t,n);if(z.out)t=z.out;return {label,n,initial,best:t.length,axes:z.axes,verified:verify(t,n),terms:t.map(x=>x.map(String))}})
}
const fs=require('node:fs'),path=require('node:path');console.log(JSON.stringify(scan({hot:JSON.parse(fs.readFileSync(path.join(__dirname,'mmg012_results.json'),'utf8'))}),null,2));
