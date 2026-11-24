"""CIG-026 measured image preparation and compact migration campaign."""
import argparse,json,random
from time import perf_counter_ns
from temporal_ground import compile_transport,Navigator
from verify_temporal_ground import Receiver
from temporal_image import Processor,capacity,unpack
from verify_temporal_image import Admission
from run_temporal_ground import encode_law,law,source,oracle,power_oracle
from shared_proof import synthesize_shared
from source_section import compile_section


def timed(fn,*args,**kwargs):
    start=perf_counter_ns()
    result=fn(*args,**kwargs)
    return result,perf_counter_ns()-start


def trial(k,mode,codec=None):
    w=3;m=k//w
    n,s,q,fs,ids=source(k,True)
    d,decoder_ns=timed(synthesize_shared,n,s,q,fs)
    section,section_ns=timed(compile_section,n,s,q)
    if mode=='contract':
        # Irreversible nonlinear symbol map: 8 -> 4 -> 2 -> 1.
        p=[(j-1)%m for j in range(m)]
        f=[[0,0,0,1,1,2,3,3] for j in p]
        ts=encode_law(k,w,p,f)
    else:
        ts,p,f,_,_=law(k,w,long_period=mode=='bijective')
    g,transport_ns=timed(compile_transport,ts,k,w)
    initial=random.Random(2525+k).getrandbits(k)
    nav=Navigator(k,w,g,d)
    receiver,receiver_ns=timed(Receiver,n,s,q,fs,d,ts,w,g,initial,section=section)
    processor,build_ns=timed(Processor,nav,initial,codec=codec)
    admission,check_ns=timed(Admission,receiver,processor.proof)
    count,bits=capacity(processor.alphabets(0))
    rows=[dict(t='0',bits=bits,classes=str(count))]
    for t in (1,2,3,17,10**1000+173):
        receipt,producer_ns=timed(processor.move,t)
        ok,verify_ns=timed(admission.accept,t,receipt)
        assert ok
        _,commit_ns=timed(processor.commit,receipt)
        alph=processor.alphabets(t)
        count,bits=capacity(alph)
        actual=unpack(alph,w,processor.rank)
        assert actual==nav.jump(initial,t)==power_oracle(initial,k,w,p,f,t)
        assert receipt['outputs']==oracle(actual,k,True,ids)
        if mode=='contract':assert bits==max(0,3-t)*m
        if mode=='bijective':assert bits==k
        rows.append(dict(t=str(t),bits=bits,classes=str(count),
            producer_ns=producer_ns,verify_ns=verify_ns,commit_ns=commit_ns,
            rank_payload_bytes=(bits+7)//8,
            receipt_bytes=len(json.dumps(receipt,separators=(',',':')).encode())))
    return dict(k=k,mode=mode,source_variables=n,decoder_ns=decoder_ns,
                section_ns=section_ns,transport_ns=transport_ns,
                native_receiver_ns=receiver_ns,image_build_ns=build_ns,image_check_ns=check_ns,
                height_entries=len(processor.h),image_proof_bytes=len(json.dumps(processor.proof).encode()),
                rows=rows)


def run(sizes,codec=None):
    return [trial(k,mode,codec) for k in sizes for mode in ('contract','mixed','bijective')]


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--sizes',nargs='+',type=int,default=[24,96,384,1023])
    p.add_argument('--native-ncr',action='store_true')
    p.add_argument('--output')
    a=p.parse_args()
    codec=None
    if a.native_ncr:
        from ncr_image_codec import NCRCodec
        codec=NCRCodec()
    result=run(a.sizes,codec)
    out=json.dumps(dict(schema='ifs.cig026.campaign.v1',native_ncr=a.native_ncr,rows=result),indent=2)
    if a.output:
        with open(a.output,'w',encoding='utf-8') as stream:stream.write(out+'\n')
    else:print(out)
