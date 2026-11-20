/** IGC-001 independent verifier: Thompson epsilon-NFA plus exact product search.
 * Proves all-word language equivalence and pairwise state minimality.
 * Does not import Python or grant execution authority.
 */
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const INTENT='ifs.igc001.trace-intention.v1';
const RECEIPT='ifs.igc001.construction-receipt.v1';
const GROUND='ifs.igc001.minimal-dfa-ground.v1';
function check(v,message){if(!v) throw new Error(message);}
function stable(x){
  if(x===null || typeof x !== 'object') return JSON.stringify(x);
  if(Array.isArray(x)) return '['+x.map(stable).join(',')+']';
  return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+stable(x[k])).join(',')+'}';
}
function digest(x){return createHash('sha256').update(Buffer.from(stable(x),'utf8')).digest('hex');}
function keys(x,items){
  return x && !Array.isArray(x) && typeof x==='object' &&
         Object.keys(x).sort().join('|') === [...items].sort().join('|');
}
function validateIntent(intent){
  check(keys(intent,['schema','alphabet','language','required','forbidden','max_states']) &&
    intent.schema===INTENT, 'intention schema refused');
  const a=intent.alphabet;
  check(Array.isArray(a)&&a.length>=1&&a.length<=8&&
    a.every(s=>typeof s==='string'&&s.length>=1&&s.length<=32&&/^[\x20-\x7e]+$/.test(s))&&
    a.every((s,i)=>i===0 || a[i-1]<s),'alphabet not ordered and unique');
  check(Number.isInteger(intent.max_states)&&intent.max_states>=1&&intent.max_states<=32,
    'state capacity invalid');
  let count=0;
  function ast(node,depth){
    count++;check(depth<=16&&count<=64,'intention AST budget');
    check(node&&typeof node==='object'&&!Array.isArray(node),'invalid AST node');
    if(['empty','epsilon'].includes(node.op)) {
      check(keys(node,['op']),'extra nullary fields'); return;
    }
    if(node.op==='symbol') {
      check(keys(node,['op','value'])&&a.includes(node.value),'unknown symbol');return;
    }
    if(['alt','concat'].includes(node.op)) {
      check(keys(node,['op','args'])&&Array.isArray(node.args)&&
            node.args.length>=1&&node.args.length<=32,'invalid expression arguments');
      node.args.forEach(child=>ast(child,depth+1));return;
    }
    if(node.op==='star'){
      check(keys(node,['op','arg']),'invalid star');ast(node.arg,depth+1);return;
    }
    throw new Error('unrecognized expression operation');
  }
  ast(intent.language,0);
  for(const name of ['required','forbidden']) {
    const list=intent[name];
    check(Array.isArray(list)&&list.length<=32&&list.every(w=>Array.isArray(w)&&
      w.length<=128&&w.every(s=>typeof s==='string'&&a.includes(s))),
      'invalid intent sample');
    const serial=list.map(stable);
    check(new Set(serial).size===list.length,'repeated sample');
  }
}
function nfaFromExpression(expression){
  // A different algorithm from Python's Brzozowski derivative construction.
  const epsilon=[],edges=[];
  function fresh(){let i=epsilon.length;epsilon.push([]);edges.push([]);return i;}
  function compile(node){
    let start=fresh(),end=fresh();
    if(node.op==='empty') return [start,end];
    if(node.op==='epsilon') {epsilon[start].push(end);return [start,end];}
    if(node.op==='symbol') {edges[start].push([node.value,end]);return [start,end];}
    if(node.op==='alt') {
      for(const child of node.args){let [a,b]=compile(child);epsilon[start].push(a);epsilon[b].push(end);}
      return [start,end];
    }
    if(node.op==='concat') {
      let prev=start;
      for(const child of node.args){let [a,b]=compile(child);epsilon[prev].push(a);prev=b;}
      epsilon[prev].push(end);return [start,end];
    }
    if(node.op==='star') {
      const [a,b]=compile(node.arg);
      epsilon[start].push(end,a);epsilon[b].push(a,end);return [start,end];
    }
    throw new Error('unknown expression opcode');
  }
  const [start,end]=compile(expression);
  function closure(states){
    const found=new Set(states);const queue=[...found];
    for(let i=0;i<queue.length;i++) for(const next of epsilon[queue[i]]) {
      if(!found.has(next)){found.add(next);queue.push(next);}
    }
    return [...found].sort((x,y)=>x-y);
  }
  function move(states,sym){
    const next=new Set();
    for(const state of states) for(const [token,to] of edges[state])
      if(token===sym) next.add(to);
    return closure(next);
  }
  function accepts(states){return states.includes(end);}
  function evaluate(word){
    let states=closure([start]);for(const sym of word) states=move(states,sym);
    return accepts(states);
  }
  return {initial:closure([start]),move,accepts,evaluate,states:epsilon.length};
}
function follow(ground,word){
  let state=0;for(const sym of word){
    const index=ground.alphabet.indexOf(sym);
    check(index>=0,'word contains token outside alphabet');
    state=ground.transitions[state][index];
  }
  return [state,ground.accepting[state]];
}
function canonicalPaths(g){
  const paths=Array(g.state_count).fill(null);paths[0]=[];const queue=[0];
  for(let i=0;i<queue.length;i++){
    const state=queue[i];
    for(let j=0;j<g.alphabet.length;j++){
      const to=g.transitions[state][j];
      if(paths[to]===null){paths[to]=[...paths[state],g.alphabet[j]];queue.push(to);}
    }
  }
  return paths;
}
function verifyGround(intent,ground,proof,nfa){
  check(keys(ground,['schema','alphabet','initial_state','state_count','accepting',
                    'transitions','ground_sha256']) && ground.schema===GROUND,
        'Ground descriptor schema refused');
  const {ground_sha256,...groundBody}=ground;
  check(digest(groundBody)===ground_sha256,'Ground descriptor digest refused');
  const n=ground.state_count;
  check(Number.isInteger(n)&&n>=1&&n<=64&&
        ground.initial_state===0 && stable(ground.alphabet)===stable(intent.alphabet)&&
        Array.isArray(ground.accepting)&&ground.accepting.length===n&&
        ground.accepting.every(x=>typeof x==='boolean')&&
        Array.isArray(ground.transitions)&&ground.transitions.length===n&&
        ground.transitions.every(row=>Array.isArray(row)&&row.length===intent.alphabet.length&&
          row.every(x=>Number.isInteger(x)&&x>=0&&x<n)),
        'Ground transition shape refused');
  check(keys(proof,['reachable_prefixes','distinguishing_suffixes']),
        'missing minimality proof');
  const paths=canonicalPaths(ground);
  check(paths.every(x=>x!==null),'Ground has unreachable states');
  check(stable(paths)===stable(proof.reachable_prefixes),'noncanonical reachability proof');
  const suffixes=proof.distinguishing_suffixes;
  check(Array.isArray(suffixes)&&suffixes.length===n*(n-1)/2,'missing pair proof');
  let k=0;
  for(let left=0;left<n;left++) for(let right=left+1;right<n;right++){
    const entry=suffixes[k++];
    check(keys(entry,['left','right','suffix'])&&entry.left===left&&entry.right===right&&
          Array.isArray(entry.suffix)&&entry.suffix.every(s=>intent.alphabet.includes(s)),
          'pairwise distinction evidence malformed');
    const l=follow(ground,[...paths[left],...entry.suffix])[1];
    const r=follow(ground,[...paths[right],...entry.suffix])[1];
    check(l!==r,'two purportedly minimal states cannot be distinguished');
  }
  // Exhaustive reachability of the finite machine/NFA-subset product proves
  // language equivalence for ALL possible strings, not just a sample horizon.
  const init=nfa.initial,queue=[[0,init]];
  const seen=new Set(['0:'+init.join(',')]);
  for(let index=0;index<queue.length;index++){
    const [state,nfaSet]=queue[index];
    check(ground.accepting[state]===nfa.accepts(nfaSet),
          'constructed Ground not equivalent to intention language');
    for(let j=0;j<intent.alphabet.length;j++){
      const nextState=ground.transitions[state][j];
      const nextNfa=nfa.move(nfaSet,intent.alphabet[j]);
      const key=nextState+':'+nextNfa.join(',');
      if(!seen.has(key)){
        seen.add(key);queue.push([nextState,nextNfa]);
        check(queue.length<=100000,'independent equivalence checking budget exhausted');
      }
    }
  }
  return {reachable_pairs:queue.length,minimal_states:n,nfa_states:nfa.states};
}
export function verify(expectedIntent,receipt){
  validateIntent(expectedIntent);
  check(keys(receipt,['payload','sha256'])&&receipt.sha256===digest(receipt.payload),
    'construction receipt self-integrity refused');
  const p=receipt.payload;
  check(p && p.schema===RECEIPT && stable(p.intention)===stable(expectedIntent) &&
        p.intention_sha256===digest(expectedIntent),
        'receiver-owned intention identity mismatch');
  const nfa=nfaFromExpression(expectedIntent.language);
  for(const word of expectedIntent.required)
    if(p.status!=='incompatible_language_constraints')
      check(nfa.evaluate(word),'required behavior differs from expression');
  for(const word of expectedIntent.forbidden)
    if(p.status!=='incompatible_language_constraints')
      check(!nfa.evaluate(word),'forbidden behavior differs from expression');
  if(p.status==='incompatible_language_constraints'){
    check(keys(p,['schema','intention','intention_sha256','status','witness','authority'])&&
          p.authority==='none','incompatibility status has excessive fields');
    const w=p.witness;
    check(keys(w,['word','declared','required_acceptance','language_acceptance'])&&
      ['required','forbidden'].includes(w.declared)&&
      expectedIntent[w.declared].some(x=>stable(x)===stable(w.word))&&
      w.required_acceptance===(w.declared==='required')&&
      nfa.evaluate(w.word)===w.language_acceptance&&
      w.language_acceptance!==w.required_acceptance,
      'invalid incompatibility witness');
    return {status:p.status,witness:w,verified:true};
  }
  check(['realized_under_declared_capacity','insufficient_declared_state_capacity'].includes(p.status),
    'unsupported or unverifiable receipt status');
  check(keys(p,['schema','intention','intention_sha256','status','ground',
                'minimality_certificate','authority'])&&
        p.authority==='mathematical_only_no_host_execution_rights',
        'receipt attempting to convey execution permission');
  const checks=verifyGround(expectedIntent,p.ground,p.minimality_certificate,nfa);
  check((p.status==='realized_under_declared_capacity')===
        (p.ground.state_count<=expectedIntent.max_states),'state budget claim false');
  return {status:p.status, verified:true, ...checks, host_execution_authorized:false};
}
export function navigateRepeat(ground,symbol,count,prefix=[],suffix=[]){
  check(typeof count==='bigint'&&count>=0n,'repeat count requires nonnegative bigint');
  check(ground.alphabet.includes(symbol),'repeat symbol absent');
  let [state]=follow(ground,prefix);
  let power=ground.transitions.map(row=>row[ground.alphabet.indexOf(symbol)]);
  while(count>0n){
    if(count&1n) state=power[state];
    count>>=1n;
    if(count>0n) power=power.map(j=>power[j]);
  }
  for(const s of suffix){
    check(ground.alphabet.includes(s),'unknown suffix token');
    state=ground.transitions[state][ground.alphabet.indexOf(s)];
  }
  return {state,accepting:ground.accepting[state]};
}
if(process.argv[1] && fileURLToPath(import.meta.url)===process.argv[1]){
  try {
    check(process.argv.length===4,'usage: node verify.mjs intent.json receipt.json');
    const file=path=>{
      const b=readFileSync(path);check(b.length<=1024*1024,'oversized receiver document');
      return JSON.parse(b.toString('utf8'));
    };
    const result=verify(file(process.argv[2]),file(process.argv[3]));
    console.log(JSON.stringify(result));
  }catch(error){console.error('REFUSED: '+error.message);process.exitCode=1;}
}
