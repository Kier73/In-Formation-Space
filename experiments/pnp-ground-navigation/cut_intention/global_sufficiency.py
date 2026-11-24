"""CIG-017 global sufficiency: proof-directed decoder synthesis and a paired miter.

An affine derivation or a source-proved Boolean circuit proves a decoder on all
models. Otherwise use the actual CIG-008 checked paired CNF. Never infer a
missing decoder or count from a decision. See independent verifier.
"""
from collections import defaultdict, deque
from itertools import combinations, product
from composed_ground import canonical, extract, compile_ground, digest
from verify_global_sufficiency import verify, contract


def bits(mask):
    while mask:
        b = mask & -mask; yield b.bit_length()-1; mask ^= b


def truth(clause, x):
    return int(any(bool(x & (1 << (abs(l)-1))) == (l>0) for l in clause))


def paired(n, source, q, f):
    k = len(q)+1; rows = []
    for side in range(2):
        def lit(l): return (abs(l)+side*n)*(1 if l>0 else -1)
        rows.extend(tuple(map(lit,c)) for c in source)
        for j,c in enumerate((*q,f)):
            z=2*n+side*k+j+1; r=tuple(map(lit,c))
            rows.append((-z,*r)); rows.extend((z,-l) for l in r)
    for j in range(k):
        a=2*n+j+1;b=a+k
        rows.extend(((a,b),(-a,-b)) if j==k-1 else ((-a,b),(a,-b)))
    return 2*n+2*k, rows


def affine_decoder(source,q,f):
    # Eliminate private columns only; track sparse source-row provenance as
    # bitsets, so the verifier can replay only the equations actually used.
    eqs,_=extract(source); observed={abs(c[0]):j for j,c in enumerate(q) if len(c)==1}
    visible=sum(1<<(v-1) for v in observed); basis={}; visits=0
    for i,(m,b) in enumerate(eqs):
        proof=1<<i
        while m & ~visible:
            p=(m & ~visible & -(m & ~visible)).bit_length()-1
            if p not in basis:
                basis[p]=(m,b,proof);break
            a,c,e=basis[p];m^=a;b^=c;proof^=e;visits+=1
    terms=[]; used=set()
    for l in f:
        m=1<<(abs(l)-1);b=0;proof=0
        while m & ~visible:
            p=(m & ~visible & -(m & ~visible)).bit_length()-1
            if p not in basis:return None
            a,c,e=basis[p];m^=a;b^=c;proof^=e;visits+=1
        js=sorted(observed[v+1] for v in bits(m))
        constant=b ^ int(l<0) ^ (sum(q[j][0]<0 for j in js)%2)
        ids=list(bits(proof));used.update(ids)
        terms.append(dict(inputs=js,constant=constant,proof=ids))
    mapping={i:j for j,i in enumerate(sorted(used))}
    for t in terms:t['proof']=[mapping[i] for i in t['proof']]
    return dict(equations=[[[v+1 for v in bits(eqs[i][0])],eqs[i][1]] for i in sorted(used)],terms=terms,row_xors=visits)


def circuit_decoder(source,q,f):
    # Generalizes CIG-004's local functional truth-table qualification to
    # arbitrary orientations and mixed CNF; no temporal dynamics assumed.
    by_scope=defaultdict(list)
    for c in source:
        if 1<=len(c)<=3:by_scope[tuple(map(abs,c))].append(c)
    known={abs(c[0]) for c in q if len(c)==1}; target=set(map(abs,f))
    candidates=[]; wait=defaultdict(list)
    for scope in sorted(by_scope):
        if len(scope)<2:continue
        clauses=tuple(c for s in range(1,len(scope)+1) for sub in combinations(scope,s) for c in by_scope.get(sub,()))
        for out in scope:
            ins=tuple(v for v in scope if v!=out); table=[]
            for x in range(1<<len(ins)):
                state=sum(((x>>i)&1)<<(v-1) for i,v in enumerate(ins))
                vals=[b for b in (0,1) if all(truth(c,state|(b<<(out-1))) for c in clauses)]
                if len(vals)!=1:break
                table.append(vals[0])
            else:
                idx=len(candidates); candidates.append(dict(output=out,inputs=list(ins),table=table,clauses=[list(c) for c in clauses]))
                for v in ins:wait[v].append(idx)
    pending=deque(i for i,g in enumerate(candidates) if set(g['inputs'])<=known);steps=[]
    while pending and not target<=known:
        g=candidates[pending.popleft()];v=g['output']
        if v in known or not set(g['inputs'])<=known:continue
        known.add(v);steps.append(g)
        pending.extend(i for i in wait[v] if set(candidates[i]['inputs'])<=known)
    if not target<=known:return None
    # Trim unused gates, preserving topological order.
    need=set(target); kept=[]
    for g in reversed(steps):
        if g['output'] in need:kept.append(g);need.update(g['inputs'])
    return dict(gates=list(reversed(kept)),candidate_count=len(candidates))


def evaluate(q,f,receipt,code):
    route=receipt['route'];d=receipt['decoder']
    if route=='union':return int(any(code>>j&1 for j in d['inputs']))
    if route=='affine':return int(any(t['constant'] ^ (sum((code>>i)&1 for i in t['inputs'])%2) for t in d['terms']))
    if route=='circuit':
        values={abs(c[0]):((code>>j)&1)^int(c[0]<0) for j,c in enumerate(q) if len(c)==1}
        for g in d['gates']:values[g['output']]=g['table'][sum(values[v]<<i for i,v in enumerate(g['inputs']))]
        return int(any(values[abs(l)]==int(l>0) for l in f))
    if route=='paired' and d is not None:
        from chain_observer_ground import _eval
        return _eval(d['anf'],code)
    raise ValueError('no executable decoder admitted')


def synthesize(n,source,q,f,*,mode='auto',width=12,cells=2_000_000,decoder_bits=6):
    source,q,f=contract(n,source,q,f)
    if mode not in ('auto','paired') or type(decoder_bits)is not int or not 0<=decoder_bits<=8:raise ValueError('mode/budget')
    r=dict(schema='ifs.cig017.global-sufficiency.v1',contract=digest([n,source,q,f]),status='SUFFICIENT',route=None,decoder=None)
    if mode=='auto':
        from nonlinear_sufficient import covers
        cover=covers({'predicates':q,'visible':[]},f)
        if cover is not None:
            r.update(route='union',decoder={'inputs':[j for kind,j in cover]});return r
        a=affine_decoder(source,q,f)
        if a is not None:r.update(route='affine',decoder=a);return r
        c=circuit_decoder(source,q,f)
        if c is not None:r.update(route='circuit',decoder=c);return r
    nn,rows=paired(n,source,q,f)
    r['route']='paired'
    if nn>8192 or len(rows)>150000:r.update(status='UNKNOWN',reason='paired source budget');return r
    proof=compile_ground(rows,nn,max_width=width,max_cells=cells)
    if proof['status']=='UNKNOWN':r.update(status='UNKNOWN',reason='paired factor budget');return r
    if proof['status']=='SAT':
        w=int(proof['witness']);mask=(1<<n)-1;r.update(status='INSUFFICIENT',witness=[str(w&mask),str((w>>n)&mask)]);return r
    r['proof']=proof
    # Existence of a decoder is established globally; construction is a
    # separate bounded phase. Each q-code needs only the f=1 branch.
    if len(q)<=decoder_bits:
        packets=[];table=[]
        for code in range(1<<len(q)):
            extra=[f]
            for j,c in enumerate(q):extra.extend([c] if code>>j&1 else [(-l,) for l in c])
            p=compile_ground([*source,*extra],n,max_width=width,max_cells=cells)
            if p['status']=='UNKNOWN':break
            packets.append(p);table.append(int(p['status']=='SAT'))
        else:
            coeff=table.copy()
            for j in range(len(q)):
                for m in range(len(coeff)):
                    if m>>j&1:coeff[m]^=coeff[m^(1<<j)]
            r['decoder']=dict(anf=[i for i,b in enumerate(coeff) if b],proofs=packets)
    return r


from proof_refinement import ProofLanguage
from verify_global_sufficiency import GlobalReceiver
from collections import Counter
from time import perf_counter_ns


class GlobalLanguage(ProofLanguage):
    """Reuse CIG-016 count/decision admission and CIG-014 retained queries."""
    def __init__(self,n,source,*,width=12,cells=2_000_000):
        self.receiver=GlobalReceiver(n,source);self.n=n;self.source=tuple(canonical(source,n));self.stats=Counter()
        if self._count(self.source,width,cells) is None:raise OverflowError('base count not admitted')
        self.receiver.seed()

    def global_extend(self,f,*,mode='auto',width=12,cells=2_000_000,decoder_bits=6):
        q,_=self.snapshot();start=perf_counter_ns()
        r=synthesize(self.n,self.source,q,f,mode=mode,width=width,cells=cells,decoder_bits=decoder_bits)
        self.stats['global_compile_ns']+=perf_counter_ns()-start
        if r['status']=='UNKNOWN':return r,False
        start=perf_counter_ns()
        ok=self.receiver.accept_global(f,r,width=width,cells=cells,decoder_bits=decoder_bits)
        self.stats['global_verify_ns']+=perf_counter_ns()-start
        self.stats['global_attempts']+=1
        self.stats['global_extensions']+=int(ok)
        return r,ok
