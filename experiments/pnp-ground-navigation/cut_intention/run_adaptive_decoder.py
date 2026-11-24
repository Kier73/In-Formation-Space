"""Compare forced delta, forced full, and adaptive verified realization."""
import json,random
from run_shared_proof import source,oracle,timed,size
from shared_proof import synthesize_shared
from incremental_decoder import DecoderState
from verify_incremental_decoder import EventReceiver

def trial(k,mixed,kind):
    n,s,q,fs,ids=source(k,mixed);r=synthesize_shared(n,s,q,fs);assert all(x['status']=='SUFFICIENT' for x in r['goals']);rng=random.Random(2020+k);codes=[];code=0
    for _ in range(256):
        if kind=='local':code^=1<<rng.randrange(k-8,k)
        elif kind=='random':code^=1<<rng.randrange(k)
        else:code=rng.getrandbits(k)
        codes.append(code)
    g=len(r['circuit']['gates']);results=[]
    for mode in ('delta','full','auto'):
        p,pt=timed(DecoderState,r['circuit'],k,0);v,vt=timed(EventReceiver,n,s,q,fs,r,0);ct=rt=0.;ops=checks=bytes_sent=fulls=attempt=0
        for code in codes:
            z,t=timed(p.update,code,mode);ok,u=timed(v.accept,z);assert ok and z['outputs']==oracle(code,k,mixed,ids);ct+=t;rt+=u;full=z.get('mode')=='full';c=len(z['checks']);a=z.get('attempted',0);ops+=g+a if full else c;checks+=g if full else c;fulls+=full;attempt+=a;bytes_sent+=size(z)
        results.append(dict(mode=mode,producer_ms=ct,receiver_ms=rt,init_producer_ms=pt,init_receiver_ms=vt,producer_gate_evaluations=ops,receiver_gate_evaluations=checks,full_events=fulls,abandoned_delta_checks=attempt,event_bytes=bytes_sent))
    return dict(n=n,family='mixed' if mixed else 'parity',kind=kind,gates=g,events=len(codes),results=results)

if __name__=='__main__':
    d=[]
    for mixed in (True,False):
        for kind in ('local','random','bulk'):
            x=trial(1024,mixed,kind);d.append(x);print(x,flush=True);open('CIG-020-adaptive-results.json','w').write(json.dumps(d,indent=2)+'\n')
