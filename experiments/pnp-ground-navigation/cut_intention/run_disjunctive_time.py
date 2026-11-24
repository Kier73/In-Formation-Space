"""Broad output intentions: sparse parity and rare global alternatives."""
import argparse,json
from run_output_time import fixture,circuit_source,expr_eval
from run_temporal_ground import timed,power_oracle,step,size
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_ground import Navigator
from verify_temporal_ground import Receiver
from output_time import seek_outputs
from disjunctive_time import seek
from verify_disjunctive_time import verify


def fold(op,items):
    if len(items)==1:return items[0]
    mid=len(items)//2;return op,fold(op,items[:mid]),fold(op,items[mid:])


def trial(k):
    _,_,_,_,ts,g,p,f,initial,P,start,_,markers,desired=fixture(k)
    parity=fold('xor',[a for a,b in markers]);A=fold('and',[a for a,b in markers]);B=fold('and',[b for a,b in markers]);alt=('or',A,B)
    # Two structurally separate but temporally impossible alternatives.
    impossible=('or',('and',*markers[0]),('and',*markers[-1]))
    exprs=[parity,alt,impossible]
    n,s,q,fs=circuit_source(k,exprs);d,compile_ms=timed(synthesize_shared,n,s,q,fs)
    assert d['status']=='COMPLETE' and all(x['status']=='SUFFICIENT' for x in d['goals'])
    sec,section_ms=timed(compile_section,n,s,q);rec,admit_ms=timed(Receiver,n,s,q,fs,d,ts,3,g,initial,section=sec);nav=Navigator(k,3,g,d)
    initial_at_start=power_oracle(initial,k,3,p,f,start);target=1-expr_eval(parity,initial_at_start)
    # Independent local stepping only for parity, known to be close in this fixture.
    u=initial_at_start;offset=0
    while expr_eval(parity,u)!=target and offset<100000:
        u=step(u,k,3,p,f);offset+=1
    assert offset<100000
    a=start+(desired-start)%P;b=start+(desired+1-start)%P
    expected_alt=min(a,b)
    # Select parity at one alternative; independent evaluation of both candidates.
    choice=expr_eval(parity,power_oracle(initial,k,3,p,f,b));valid=[t for t in (a,b) if expr_eval(parity,power_oracle(initial,k,3,p,f,t))==choice]
    cases=[('wide_parity',[target,None,None],start+offset),('rare_or',[None,1,None],expected_alt),('rare_or_and_parity',[choice,1,None],min(valid)),('impossible_or',[None,None,1],None)]
    rows=[]
    for name,targets,expected in cases:
        old,old_ms=timed(seek_outputs,nav,initial,targets,start)
        for mode in (16,0):
            telemetry={};r,ms=timed(seek,nav,initial,targets,start,interval_steps=mode,telemetry=telemetry)
            ok,vs=timed(verify,rec,targets,start,r,interval_steps=mode)
            assert ok,(k,name,mode,r['status'],r['nodes'],r['pairs'])
            assert (int(r['time']) if r['status']=='FOUND' else None)==expected,(k,name,mode,r['status'])
            if expected is not None:
                code=power_oracle(initial,k,3,p,f,expected);assert r['terminal']['code']==str(code);assert r['terminal']['outputs']==[expr_eval(e,code) for e in exprs]
            rows.append(dict(case=name,interval_steps=mode,status=r['status'],offset=None if expected is None else str(expected-start),local_cells=r['local_cells'],pairs=r['pairs'],nodes=r['nodes'],leaps=len(r['leaps']),expansions=len(r['trace']),seek_ms=ms,verify_ms=vs,receipt_bytes=size(r),previous_status=old['status'],previous_estimated_cells=old['local_cells'],previous_ms=old_ms,receipt=r,**telemetry))
    return dict(n=n,observed=k,period=str(P),cycles=len(markers),gates=len(d['circuit']['gates']),decoder_ms=compile_ms,section_ms=section_ms,admit_ms=admit_ms,cases=rows)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='+',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='CIG-023-results.json');a=p.parse_args();rows=[]
    for k in a.sizes:
        r=trial(k);rows.append(r);open(a.output,'w').write(json.dumps(rows,indent=2)+'\n')
        print({x:y for x,y in r.items() if x!='cases'},flush=True)
        for c in r['cases']:print({x:y for x,y in c.items() if x!='receipt'},flush=True)
