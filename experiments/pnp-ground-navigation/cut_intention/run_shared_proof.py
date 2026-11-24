"""Matched cold CIG-018 vs shared CIG-019 and verified CIG-020 event execution."""
import argparse,json,random,sys
from time import perf_counter_ns
from test_interpolant_ground import chain
from interpolant_ground import synthesize,evaluate as cold_eval
from verify_interpolant_ground import verify as cold_verify
from shared_proof import synthesize_shared,evaluate
from verify_shared_proof import verify
from incremental_decoder import DecoderState
from verify_incremental_decoder import EventReceiver

def timed(fn,*args,**kw):
    t=perf_counter_ns();v=fn(*args,**kw);return v,(perf_counter_ns()-t)/1e6

def source(k,mixed,spread=False):
    n,s,q,f=chain(k,mixed);labels=list(range(1,n+1));random.Random(73).shuffle(labels)
    ids=sorted({max(1,(k-1)*j//8) for j in range(1,9)}) if spread else list(range(max(1,k-8),k))
    return n,s,q,[(labels[3*k+i-1],) for i in ids],ids

def oracle(code,k,mixed,ids):
    v=code&1;out=[];wanted=set(ids)
    for i in range(1,k):
        b=(code>>i)&1;v=v&b if mixed and i%2 else v^b
        if i in wanted:out.append(v)
    return out

def size(o):return len(json.dumps(o,separators=(',',':')).encode())
def trial(k,mixed,spread=False):
    n,s,q,fs,ids=source(k,mixed,spread);r,ct=timed(synthesize_shared,n,s,q,fs);ok,vt=timed(verify,n,s,q,fs,r);assert ok and all(g['status']=='SUFFICIENT' for g in r['goals']),r.get('reason')
    cold=[];cold_ct=cold_vt=0
    for f in fs:
        x,t=timed(synthesize,n,s,q,f);v,u=timed(cold_verify,n,s,q,f,x);assert v and x['status']=='SUFFICIENT';cold_ct+=t;cold_vt+=u;cold.append(x)
    rng=random.Random(1900+k);codes=[0,(1<<k)-1]+[rng.getrandbits(k) for _ in range(32)]
    for code in codes:assert evaluate(r['circuit'],code,k)==[cold_eval(x['decoder'],code,k) for x in cold]==oracle(code,k,mixed,ids)
    row=dict(n=n,clauses=len(s),observed=k,targets=len(fs),family='mixed' if mixed else 'parity',spread=spread,shared_compile_ms=ct,shared_verify_ms=vt,cold_compile_ms=cold_ct,cold_verify_ms=cold_vt,prefix_pairs=r['prefix_pairs'],suffix_pairs=sum(g['pairs'] for g in r['goals']),cold_pairs=sum(x['pairs'] for x in cold),prefix_steps=len(r['prefix']),suffix_steps=sum(len(g['steps']) for g in r['goals']),cold_steps=sum(len(x['steps']) for x in cold),shared_gates=len(r['circuit']['gates']),cold_gates=sum(len(x['decoder']['gates']) for x in cold),shared_receipt_bytes=size(r),cold_receipt_bytes=sum(map(size,cold)),shared_circuit_bytes=size(r['circuit']),cold_circuit_bytes=sum(size(x['decoder']) for x in cold))
    return row,(n,s,q,fs,ids,r,cold)

def events(k,mixed,data,kind):
    n,s,q,fs,ids,r,cold=data;code=0;g=len(r['circuit']['gates']);p,pt=timed(DecoderState,r['circuit'],k,code);v,vt=timed(EventReceiver,n,s,q,fs,r,code);rng=random.Random(2020+k)
    ev=256;prod=verify_ms=cold_ms=0.;checks=bytes_sent=0;max_checks=0;zero=0
    for _ in range(ev):
        if kind=='local':code^=1<<rng.randrange(max(0,k-8),k)
        elif kind=='random':code^=1<<rng.randrange(k)
        else:code=rng.getrandbits(k)
        z,t=timed(p.update,code);ok,u=timed(v.accept,z);expected,w=timed(evaluate,r['circuit'],code,k)
        assert ok and z['outputs']==expected==oracle(code,k,mixed,ids)
        prod+=t;verify_ms+=u;cold_ms+=w;c=len(z['checks']);checks+=c;max_checks=max(max_checks,c);zero+=c==0;bytes_sent+=size(z)
    return dict(n=n,observed=k,family='mixed' if mixed else 'parity',event_kind=kind,events=ev,gate_count=g,init_producer_ms=pt,init_receiver_ms=vt,producer_ms=prod,receiver_ms=verify_ms,cold_eval_ms=cold_ms,checked_gates=checks,cold_gate_evaluations=g*ev,max_event_checks=max_checks,zero_events=zero,event_bytes=bytes_sent)

def controls():
    out=[]
    for n in (50,100,200,500):
        rng=random.Random(n+1900);s=[tuple(v*rng.choice((-1,1)) for v in sorted(rng.sample(range(1,n+1),3))) for _ in range(round(4.26*n))];q=[(1,2),(3,4)];fs=[(5,),(6,)]
        r,t=timed(synthesize_shared,n,s,q,fs,max_pairs=20000,max_steps=10000,max_width=16)
        if r['status']=='COMPLETE':assert verify(n,s,q,fs,r,max_pairs=20000,max_steps=10000,max_width=16)
        out.append(dict(n=n,status=r['status'],goals=[g['status'] for g in r.get('goals',[])],ms=t,reason=r.get('reason')))
    return out

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',default='CIG-019-020-results.json');a.add_argument('--sizes',nargs='+',type=int,default=[32,128,512,1024]);args=a.parse_args();d=dict(python=sys.version,shared=[],events=[],controls=[])
    def save():open(args.output,'w').write(json.dumps(d,indent=2)+'\n')
    for mixed in (True,False):
        for k in args.sizes:
            row,data=trial(k,mixed);d['shared'].append(row);save();print(row,flush=True)
            for kind in ('local','random','bulk'):
                z=events(k,mixed,data,kind);d['events'].append(z);save();print(z,flush=True)
    for mixed in (True,False):
        row,_=trial(128,mixed,spread=True);d['shared'].append(row);save();print(row,flush=True)
    d['controls']=controls();save();print(d['controls'],flush=True)
