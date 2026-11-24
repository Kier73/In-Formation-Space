"""Solve a 1,001-digit lower-bounded temporal intention on the actual decoder."""
import json
from run_temporal_ground import source,law,timed,size,oracle
from shared_proof import synthesize_shared
from temporal_ground import Navigator,compile_transport
from verify_temporal_ground import Receiver
from source_section import compile_section
from inverse_time import seek
from verify_inverse_time import verify_seek

if __name__=='__main__':
    k=1023;w=3;n,s,q,fs,ids=source(k,True);r=synthesize_shared(n,s,q,fs);ts,p,f,c,P=law(k,w,long_period=True);g=compile_transport(ts,k,w);nav=Navigator(k,w,g,r);sec=compile_section(n,s,q);receiver=Receiver(n,s,q,fs,r,ts,w,g,c,section=sec)
    start=10**1000+173;desired=start+P//2;mask=(1<<k)-1;value=nav.jump(c,desired)
    found,ms=timed(seek,nav,c,mask,value,start);ok,vs=timed(verify_seek,ts,k,w,g,c,mask,value,start,found);assert ok and int(found['time'])==desired
    z,pt=timed(nav.result,c,int(found['time']));ok,vt=timed(receiver.accept,int(found['time']),z);assert ok and z['outputs']==oracle(value,k,True,ids)
    # In a pure marker cycle, two markers on one spatial cycle are impossible.
    group=found['groups'][0]['blocks'];bad=0
    for i in group[:2]:bad|=1<<(i*w)
    badmask=sum(7<<(i*w) for i in group)
    impossible,imt=timed(seek,nav,c,badmask,bad,start);good,ivt=timed(verify_seek,ts,k,w,g,c,badmask,bad,start,impossible);assert good and impossible['status']=='UNREACHABLE'
    data=dict(n=n,observed=k,period=str(P),start=str(start),offset=str(desired-start),exact_time=found['time'],local_steps=found['local_steps'],crt_pairs=found['pairs'],groups=len(found['groups']),compile_ms=ms,verify_ms=vs,receipt_bytes=size(found),terminal_producer_ms=pt,terminal_verify_ms=vt,outputs=z['outputs'],unreachable=dict(local_steps=impossible['local_steps'],compile_ms=imt,verify_ms=ivt),receipt=found)
    open('CIG-021-inverse-results.json','w').write(json.dumps(data,indent=2)+'\n');print({k:v for k,v in data.items() if k not in ('receipt','start','exact_time')})
