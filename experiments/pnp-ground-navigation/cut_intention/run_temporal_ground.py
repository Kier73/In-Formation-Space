"""Heavy transport / temporal proof-derived decoder campaign, exact integer oracle."""
import argparse,json,random,math
from time import perf_counter_ns
from run_shared_proof import source,oracle,timed,size
from shared_proof import synthesize_shared,evaluate
from temporal_ground import compile_transport,Navigator
from verify_temporal_ground import Receiver,verify_transport
from source_section import compile_section,section_witness
from verify_source_section import verify_section


def encode_law(k,w,pred,tables,seed=21):
    """Each input word implies each bit of its next word; no opcode tags."""
    rows=[];a=1<<w
    for j,i in enumerate(pred):
        for x in range(a):
            premise=tuple(-(i*w+b+1) if x>>b&1 else i*w+b+1 for b in range(w))
            for b in range(w):
                v=k+j*w+b+1;rows.append(premise+(v if tables[j][x]>>b&1 else -v,))
    random.Random(seed).shuffle(rows);return rows


def law(k,w,seed=21,long_period=False):
    rng=random.Random(seed);m=k//w;a=1<<w;order=list(range(m));rng.shuffle(order)
    if long_period:
        lengths=[2,3,5,7,11,13,17,19,23,29,31,37,41,43,47];lengths=[l for i,l in enumerate(lengths) if sum(lengths[:i+1])<=m];lengths += [m-sum(lengths)] if sum(lengths)<m else []
    else:
        # A few long cycles; maps include irreversible operations and Toffoli.
        lengths=[m//3,m//3,m-2*(m//3)] if m>=3 else [m]
    pred=list(range(m));tables=[None]*m;initial=0;off=0
    for idx,L in enumerate(lengths):
        cycle=order[off:off+L];off+=L
        for z,j in enumerate(cycle):
            pred[j]=cycle[z-1]
            if long_period:
                # Nonlinear bijective local map; symbols 0 and 1 are fixed.
                tables[j]=[x^(((x&1) and (x&2)) and 4 or 0) for x in range(a)]
            elif z==0 and idx%2==0:
                tables[j]=[(x&3)|((x&1 and x&2) and 4 or 0) for x in range(a)]
            elif z%3==0:tables[j]=[x^(((x&1) and (x&2)) and 4 or 0) for x in range(a)]
            else:tables[j]=[x^1 for x in range(a)]
        initial|=1<<(cycle[0]*w)
    return encode_law(k,w,pred,tables),pred,tables,initial,math.lcm(*lengths)


def step(code,k,w,pred,tables):
    a=1<<w
    return sum(tables[j][(code>>(i*w))&(a-1)]<<(j*w) for j,i in enumerate(pred))


def power_oracle(code,k,w,pred,tables,t):
    """Independent binary composition of destination-to-source maps."""
    p=list(pred);f=[list(x) for x in tables];a=1<<w
    while t:
        if t&1:code=step(code,k,w,p,f)
        t//=2
        if t:
            p,f=[p[i] for i in p],[[f[j][f[i][x]] for x in range(a)] for j,i in enumerate(p)]
    return code


def witness(code,k,mixed):
    """Fixture section: explicit source-valid realization of every observation code.
    This is not supplied to the decoder compiler or transport compiler.
    """
    n=4*k-1;labels=list(range(1,n+1));random.Random(73).shuffle(labels);out=0;v=0
    def put(i,b):return b<<(labels[i-1]-1)
    for i in range(k):
        b=(code>>i)&1;out|=put(3*i+1,b)|put(3*i+3,b)
        if i==0:v=b
        else:
            v=v&b if mixed and i%2 else v^b;out|=put(3*k+i,v)
    return out


def trial(k,mixed,steps=4096):
    w=3;n,s,q,fs,ids=source(k,mixed);r,ct=timed(synthesize_shared,n,s,q,fs);assert r['status']=='COMPLETE' and all(g['status']=='SUFFICIENT' for g in r['goals'])
    src,p,f,_,_=law(k,w);g,gt=timed(compile_transport,src,k,w);v,vt=timed(verify_transport,src,k,w,g);assert v
    a=(1<<w);initial=random.Random(2100+k).getrandbits(k);nav,nt=timed(Navigator,k,w,g,r);receiver,rt=timed(Receiver,n,s,q,fs,r,src,w,g,initial,witness(initial,k,mixed))
    sec,st=timed(compile_section,n,s,q);assert sec is not None
    qualified,sv=timed(verify_section,n,s,q,sec);assert qualified
    section_receiver,srt=timed(Receiver,n,s,q,fs,r,src,w,g,initial,section=sec)
    def query(t):
        code,jt=timed(nav.jump,initial,t);witness_code,wt=timed(witness,code,k,mixed);z,pt=timed(nav.result,initial,t,witness_code);ok,qt=timed(receiver.accept,t,z);expected,ot=timed(power_oracle,initial,k,w,p,f,t)
        zr,spt=timed(nav.result,initial,t);good,sqt=timed(section_receiver.accept,t,zr);assert good and zr['outputs']==z['outputs'] and zr['code']==z['code']
        assert section_receiver.total_image and receiver.accept(t,nav.result(initial,t,section_witness(n,q,sec,code)))
        assert ok and code==expected and z['outputs']==oracle(code,k,mixed,ids)
        return dict(t=str(t),jump_ms=jt,witness_ms=wt,receipt_ms=pt,receiver_ms=qt,oracle_ms=ot,receipt_bytes=size(z),section_receipt_ms=spt,section_receiver_ms=sqt,section_receipt_bytes=size(zr),outputs=z['outputs'])
    qs=[query(t) for t in (0,1,17,steps,10**100+173,10**1000+173)]
    def iterate():
        code=initial
        for _ in range(steps):code=step(code,k,w,p,f)
        return code,evaluate(r['circuit'],code,k)
    (end,y),it=timed(iterate);assert end==nav.jump(initial,steps) and y==qs[3]['outputs']
    # Repeated jumps from arbitrary anchors; compare against direct iteration at small times.
    rng=random.Random(2117+k);random_trials=24
    for _ in range(random_trials):
        code=rng.getrandbits(k);t=rng.randrange(128);x=code
        for _ in range(t):x=step(x,k,w,p,f)
        assert nav.jump(code,t)==x
    return dict(n=n,observed=k,blocks=k//w,transition_clauses=len(src),family='mixed' if mixed else 'parity',decoder_gates=len(r['circuit']['gates']),decoder_compile_ms=ct,transport_compile_ms=gt,transport_verify_ms=vt,navigator_init_ms=nt,receiver_admit_ms=rt,section_compile_ms=st,section_verify_ms=sv,section_receiver_admit_ms=srt,section_gates=len(sec['gates']),section_bytes=size(sec),lift_vertices=k//w*a,cycles=len(g['cycles']),max_depth=max(g['depth']),ground_bytes=size(g),query=qs,iteration_steps=steps,iteration_ms=it,random_trials=random_trials)


def period_control(k=1023):
    w=3;s,p,f,code,period=law(k,w,long_period=True);g=compile_transport(s,k,w);assert verify_transport(s,k,w,g)
    # No decoder needed for transport-only theorem. Initial marker on each cycle;
    # maps preserve 0/1, so the exact period is lcm of spatial cycle lengths.
    dummy={'contract':'transport-only','circuit':{'gates':[],'outputs':[]}};nav=Navigator(k,w,g,dummy)
    assert nav.jump(code,period)==code
    for prime in (2,3,5,7,11,13,17,19,23,29,31,37,41,43,47):
        if period%prime==0:assert nav.jump(code,period//prime)!=code
    t=10**1000+173;out=nav.jump(code,t);assert out==power_oracle(code,k,w,p,f,t)
    return dict(observed=k,exact_orbit_period=str(period),lift_vertices=k//w*8,query_time=str(t),exact=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',type=int,nargs='+',default=[24,96,384,1023]);p.add_argument('--steps',type=int,default=4096);p.add_argument('--output',default='CIG-021-results.json');a=p.parse_args();ledger={'trials':[]}
    def save():open(a.output,'w').write(json.dumps(ledger,indent=2)+'\n')
    for mixed in (True,False):
        for k in a.sizes:
            row=trial(k,mixed,a.steps);ledger['trials'].append(row);save();print({x:y for x,y in row.items() if x!='query'},flush=True)
    ledger['period_control']=period_control();save();print('period',ledger['period_control']['exact_orbit_period'],flush=True)
