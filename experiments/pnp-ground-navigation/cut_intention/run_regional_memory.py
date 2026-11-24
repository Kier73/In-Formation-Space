"""CIG-009: source-local revisions and a separate receiver over a JSON pipe."""
import json
import random
import subprocess
import sys
from pathlib import Path
from time import perf_counter_ns
from regional_memory import discover, realize, VerifiedMemory, wire
from run_composed_ground import chain, xor_clauses
from composed_ground import compile_ground
from verify_composed_ground import verify


def worker():
    """Separate process retains independently admitted receiver RAM, not sender RAM."""
    memory=VerifiedMemory()
    for line in sys.stdin:
        try:
            req=json.loads(line)
            result=realize(req['clauses'],req['n'],req['plan'],memory,incoming=req['messages'])
            print(json.dumps({k:result[k] for k in ('source','root','count','metrics','bind_ns','navigation_ns','witness_ns')}),flush=True)
        except (ValueError,KeyError,OverflowError,TypeError) as exc:
            print(json.dumps({'rejected':str(exc)}),flush=True)


def request(proc,source,n,plan,messages):
    packet=wire(dict(clauses=source,n=n,plan=plan,messages=messages)); t=perf_counter_ns()
    proc.stdin.write(packet+b'\n');proc.stdin.flush(); raw=proc.stdout.readline();elapsed=perf_counter_ns()-t
    if not raw: raise RuntimeError('receiver exited')
    return json.loads(raw),len(packet)+1,elapsed


def timed(source,n,plan,memory):
    t=perf_counter_ns();r=realize(source,n,plan,memory);return r,perf_counter_ns()-t


def summary(r,ns):
    return dict(count=r['count'],messages=len(r['messages']),message_bytes=len(wire(r['messages'])),total_ms=ns/1e6,
        bind_ms=r['bind_ns']/1e6,navigation_ms=r['navigation_ns']/1e6,witness_ms=r['witness_ns']/1e6,
        **r['metrics'])


def campaign():
    out=[]
    for stages in (32,128,256,512):
        n,c=chain(stages); t=perf_counter_ns();p=discover(c,n);plan_ns=perf_counter_ns()-t
        m=VerifiedMemory();a,an=timed(c,n,p,m);assert int(a['count'])==stages+2
        perm=list(range(1,n+1));random.Random(73).shuffle(perm);v=perm[stages//2]
        revised=c+[(v,)]; b,bn=timed(revised,n,p,m); assert int(b['count'])==stages//2+1
        fresh,fn=timed(revised,n,p,VerifiedMemory());assert fresh['root']==b['root']
        contradictory,cn=timed(revised+[(-v,)],n,p,m);assert contradictory['count']=='0'
        restored,rn=timed(c,n,p,m);assert restored['root']==a['root']
        delta={k:r for k,r in b['messages'].items() if k not in a['messages']}
        assert len(delta)==1+(stages.bit_length()-1)
        rec=dict(stages=stages,n=n,clauses=len(c),leaves=len(p['leaves']),plan_ms=plan_ns/1e6,plan_bytes=len(wire(p)),cold=summary(a,an),revision=summary(b,bn),fresh_revision=summary(fresh,fn),contradictory=summary(contradictory,cn),restored=summary(restored,rn),delta_messages=len(delta),delta_bytes=len(wire(delta)))
        if stages==256:
            old=compile_ground(c,n);assert verify(c,n,old) and old['count']==a['count'];rec['cig008_certificate_bytes']=len(wire(old))
            with subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as proc:
                remote,bytes_,time_=request(proc,c,n,p,a['messages']);assert remote['root']==a['root']
                remote2,bytes2,time2=request(proc,revised,n,p,delta);assert remote2['root']==b['root']
                # No trusted memory in this producer-supplied packet; forge one
                # fresh leaf on the contradictory revision, including its key.
                d={k:r for k,r in contradictory['messages'].items() if k not in b['messages']}
                bad=json.loads(wire(d));k=next(iter(bad));bad[k]['counts'][0]=str(int(bad[k]['counts'][0])+1)
                refused,_,_=request(proc,revised+[(-v,)],n,p,bad);assert 'rejected' in refused
                good,_,_=request(proc,revised+[(-v,)],n,p,d);assert good['count']=='0'
                rec['receiver_process']={'cold_wire_bytes':bytes_,'cold_roundtrip_ms':time_/1e6,'cold_metrics':remote['metrics'],
                    'delta_wire_bytes':bytes2,'delta_roundtrip_ms':time2/1e6,'delta_metrics':remote2['metrics'],'forgery_rejected':True,'corrected_packet_count':good['count']}
                proc.stdin.close();proc.wait(timeout=10)
        out.append(rec)
    # A genuinely heterogeneous, connected source. Gate and parity scopes
    # share articulation variables; with width=3 discovery preserves regions.
    n=3;c=[(-1,-2,3),(1,-3),(2,-3)];end=3
    for _ in range(128):
        n+=2;c+=xor_clauses((end,n-1,n));end=n
    p=discover(c,n,width=3);r,ns=timed(c,n,p,VerifiedMemory());assert r['count']==str(4*2**128)
    return {'connected_revisions':out,'mixed_affine_boolean':dict(n=n,clauses=len(c),leaves=len(p['leaves']),**summary(r,ns))}

if __name__=='__main__':
    if '--worker' in sys.argv:worker()
    else:print(json.dumps(campaign(),indent=2))
