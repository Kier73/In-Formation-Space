"use strict";

/*
 * CGS-003: independent arithmetic checker for CGS-001 section reports.
 * Does NOT import the producer solver. Checks internal mathematical
 * consistency only. It does not authenticate observations or signers.
 */
function reject(message) { throw new Error("invalid section certificate: " + message); }
const m = (n,p) => ((n % p) + p) % p;
function validPrime(p) {
  if (!Number.isSafeInteger(p) || p < 2 || p > 65521) return false;
  for (let d=2; d*d<=p; d++) if (p%d===0) return false;
  return true;
}
// Independent extended-Euclidean inverse, unlike the producer's exponentiation.
function inverseNumber(a,p) {
  let t=0, nt=1, r=p, nr=a;
  while(nr!==0) {
    const q=Math.floor(r/nr);
    [t,nt]=[nt,t-q*nt];
    [r,nr]=[nr,r-q*nr];
  }
  if(r!==1) reject("singular map");
  return m(t,p);
}
const compose = (f,g,p) => [m(f[0]*g[0],p),m(f[0]*g[1]+f[1],p)];
const inv = (f,p) => {
  const z=inverseNumber(f[0],p);
  return [z,m(-z*f[1],p)];
};
const same = (a,b) => Array.isArray(a) && Array.isArray(b) &&
  a.length===2 && b.length===2 && a[0]===b[0] && a[1]===b[1];
const sorted = (a,b) => a<b?-1:a>b?1:0;
function verify(report) {
  if (!report || report.schema!=="ifs.contextual-ground-sections/0.1")
    reject("wrong schema");
  const p=report.field,vs=report.vertices,es=report.edges,root=report.root;
  if (!validPrime(p)) reject("invalid prime");
  if (!Array.isArray(vs) || !vs.length ||
      vs.some(v=>typeof v!=="string" || !v.length) ||
      new Set(vs).size!==vs.length ||
      vs.join("\u0000")!==[...vs].sort().join("\u0000") ||
      !vs.includes(root)) reject("invalid vertices");
  if (!Array.isArray(es) || !Array.isArray(report.tree_edges) ||
      !Array.isArray(report.cycles)) reject("invalid record arrays");
  const ids=new Set(),vertices=new Set(vs),byId=new Map();
  for(const e of es) {
    if(!e || typeof e.id!=="string" || !e.id || ids.has(e.id) ||
       !vertices.has(e.from) || !vertices.has(e.to) ||
       !Number.isInteger(e.a) || !Number.isInteger(e.b) ||
       e.a<1 || e.a>=p || e.b<0 || e.b>=p) reject("invalid edge");
    ids.add(e.id);
    byId.set(e.id,e);
  }
  if(es.map(e=>e.id).join("\u0000")!==[...ids].sort(sorted).join("\u0000"))
    reject("noncanonical edge order");
  const tree=report.tree_edges;
  if(tree.length!==vs.length-1 || new Set(tree).size!==tree.length ||
     tree.some(id=>!ids.has(id)) || tree.join("\u0000")!==[...tree].sort(sorted).join("\u0000"))
    reject("invalid spanning tree edges");
  const maps=report.tree_maps;
  if (!maps || typeof maps!=="object" || Array.isArray(maps) ||
      Object.keys(maps).length!==vs.length ||
      vs.some(v=>!Object.hasOwn(maps,v))) reject("invalid tree map keys");
  for(const v of vs) {
    const f=maps[v];
    if(!Array.isArray(f) || f.length!==2 ||
       !Number.isInteger(f[0]) || !Number.isInteger(f[1]) ||
       f[0]<1 || f[0]>=p || f[1]<0 || f[1]>=p) reject("invalid tree map");
  }
  if(!same(maps[root],[1,0])) reject("root map must be identity");
  const neighbours=new Map(vs.map(v=>[v,[]]));
  for(const id of tree) {
    const e=byId.get(id);
    neighbours.get(e.from).push(e.to);
    neighbours.get(e.to).push(e.from);
    if(!same(maps[e.to], compose([e.a,e.b],maps[e.from],p)))
      reject("tree edge and chart disagree");
  }
  const reached=new Set([root]),queue=[root];
  for(let i=0;i<queue.length;i++){
    for(const v of neighbours.get(queue[i])){
      if(!reached.has(v)){reached.add(v);queue.push(v);}
    }
  }
  if(reached.size!==vs.length) reject("tree disconnected");

  const expectedCycleEdges=es.map(e=>e.id).filter(id=>!tree.includes(id));
  if(report.cycles.length!==expectedCycleEdges.length ||
     report.cycles.some((c,i)=>!c || c.edge!==expectedCycleEdges[i]))
    reject("missing or extra cycles");
  let point=null, source=null, obstruction=null, flat=true;
  for(const c of report.cycles) {
    const e=byId.get(c.edge);
    const holonomy=compose(inv(maps[e.to],p),
      compose([e.a,e.b],maps[e.from],p),p);
    if(!same(c.holonomy,holonomy)) reject("forged holonomy");
    if(!same(holonomy,[1,0])) flat=false;
    let constraint;
    if(same(holonomy,[1,0])) constraint={kind:"any"};
    else if(holonomy[0]===1) {
      constraint={kind:"none"};
      if(obstruction===null) obstruction=[c.edge];
    } else {
      const x=m(-holonomy[1]*inverseNumber(m(holonomy[0]-1,p),p),p);
      constraint={kind:"point",value:x};
      if(point===null){point=x;source=c.edge;}
      else if(point!==x && obstruction===null) obstruction=[source,c.edge];
    }
    if(!c.constraint || c.constraint.kind!==constraint.kind ||
       (constraint.kind==="point" && c.constraint.value!==constraint.value))
      reject("forged fixed-point constraint");
  }
  const status=obstruction!==null?"empty":point===null?"all":"singleton";
  const count=status==="empty"?0:status==="all"?p:1;
  if(report.flat!==flat || report.status!==status ||
     report.section_count!==count ||
     report.root_value!==(status==="singleton"?point:null) ||
     !Array.isArray(report.obstruction_edges) ||
     report.obstruction_edges.join("\u0000")!==(obstruction||[]).join("\u0000"))
    reject("forged conclusion or witness");
  return {verified:true, field:p, root, checked_edges:es.length,
    checked_cycles:expectedCycleEdges.length, flat, status, section_count:count};
}
module.exports={verify};
if(require.main===module) {
  if(process.argv.length!==3) {
    process.stderr.write("usage: node verifier.js <certificates.json>\n");
    process.exitCode=2;
  } else {
    const fs=require("node:fs");
    const data=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
    if(!Array.isArray(data)) reject("expected array");
    process.stdout.write(JSON.stringify(data.map(verify),null,2)+"\n");
  }
}
