"""CIG-027: continuing nonlinear processes under declining capacity."""
import argparse,json
from math import prod
from time import perf_counter_ns
from run_output_time import expr_eval,circuit_source
from run_disjunctive_time import fold
from run_temporal_ground import encode_law,power_oracle
from temporal_ground import compile_transport,Navigator
from verify_temporal_ground import Receiver
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_image import Processor,capacity,unpack
from temporal_algebra import compile_algebra,Language
from capacity_time import CapacityNavigator,threshold
from verify_capacity_time import CapacityAdmission


def timed(fn,*args,**kwargs):
    t=perf_counter_ns();x=fn(*args,**kwargs);return x,perf_counter_ns()-t


def fixture(k):
    """Rotating Toffoli marker cycles alongside irreversible symbol lanes."""
    if k%3 or k<24 or k>1023:raise ValueError('fixture width')
    m=k//3;p=list(range(m));f=[];off=0;periods=[];markers=[];initial=0
    for L in (2,3,5,7,11,13,17,19,23,29,31,37,41,43,47):
        if off+L>m//2:break
        periods.append(L);markers.append(3*off);initial|=1<<(3*off)
        for j in range(off,off+L):
            p[j]=off+(j-off-1)%L
            f.append([x^(4 if x&3==3 else 0) for x in range(8)])
        off+=L
    for j in range(off,m):
        f.append([0,0,0,1,1,2,3,3]);initial|=7<<(3*j)
    exprs=[fold('and',markers),3*off+2,markers[0]]
    return p,f,initial,exprs,prod(periods),off,m-off


def trial(k,codec=None):
    p,f,initial,exprs,P,live,dead=fixture(k)
    n,s,q,fs=circuit_source(k,exprs)
    dec,decoder_ns=timed(synthesize_shared,n,s,q,fs)
    sec,section_ns=timed(compile_section,n,s,q)
    ts=encode_law(k,3,p,f)
    g,transport_ns=timed(compile_transport,ts,k,3)
    nav=Navigator(k,3,g,dec)
    receiver,receiver_ns=timed(Receiver,n,s,q,fs,dec,ts,3,g,initial,section=sec)
    processor,image_ns=timed(Processor,nav,initial,codec=codec)
    (diagram,receipt),algebra_ns=timed(compile_algebra,nav,initial)
    language=Language(diagram,receipt);planner=CapacityNavigator(processor,language)
    admission,admit_ns=timed(CapacityAdmission,receiver,processor.proof,receipt)
    packet,rank_ns=timed(planner.prepare_rank,0)
    _,rank_check_ns=timed(admission.prepare_rank,packet)
    assert prod(diagram.base)==P
    assert [capacity(processor.alphabets(t))[1] for t in range(4)]==[k-dead*t for t in range(4)]
    rows=[]
    for B in (k,k-dead,k-2*dead,3*live,3*live-1):
        tau=threshold(processor,B)
        for start,ordinal,route in ((0,1,'next'),(10**1000+173,1,'next'),
                                    (0,1,'rank'),(10**1000+173,10**900+173,'rank')):
            r,seek_ns=timed(planner.query,0,start,B,ordinal=ordinal,route=route)
            ok,verify_ns=timed(admission.verify,0,start,B,r,ordinal=ordinal,route=route)
            assert ok
            expected=None if tau is None else ((max(start,tau)+P-1)//P+ordinal-1)*P
            assert (None if r['time'] is None else int(r['time']))==expected
            rows.append(dict(B=B,start=str(start),ordinal=str(ordinal),route=route,
                             threshold=tau,status=r['status'],time=r['time'],
                             seek_ns=seek_ns,verify_ns=verify_ns,
                             receipt_bytes=len(json.dumps(r,separators=(',',':')).encode())))
    # Transient-only original output is lost under the first capacity reduction.
    r=planner.query(1,0,k-dead);assert r['status']=='UNREACHABLE'
    assert admission.verify(1,0,k-dead,r)
    # Use an admitted tautology to request the next logical instant during contraction.
    neg=language.extend('not',0);always=language.extend('or',0,neg)
    admission.extend(language.export());moves=[]
    for t in (1,2,3):
        B=k-dead*t;r=planner.query(always,t,B)
        assert r['time']==str(t)
        move,migrate_ns=timed(processor.move,t)
        ok,verify_ns=timed(admission.accept_move,always,t,B,r,move);assert ok
        _,commit_ns=timed(processor.commit,move)
        actual=unpack(processor.alphabets(t),3,processor.rank)
        assert actual==power_oracle(initial,k,3,p,f,t)
        assert move['outputs']==[expr_eval(e,actual) for e in exprs]
        moves.append(dict(time=str(t),bits=move['bits'],migrate_ns=migrate_ns,
                          verify_ns=verify_ns,commit_ns=commit_ns))
    # Then repeatedly realize rare events while the live periodic part remains active.
    for start in (4,P+1,10**1000+173):
        # Start values are strictly beyond prior accepted time, including small P.
        start=max(start,processor.time+1)
        r=planner.query(0,start,3*live)
        t=int(r['time']);move,migrate_ns=timed(processor.move,t)
        ok,verify_ns=timed(admission.accept_move,0,start,3*live,r,move);assert ok
        _,commit_ns=timed(processor.commit,move)
        actual=unpack(processor.alphabets(t),3,processor.rank)
        assert actual==power_oracle(initial,k,3,p,f,t)
        assert move['outputs']==[expr_eval(e,actual) for e in exprs]
        # The remaining process is not stationary: the marker moves at t+1.
        assert nav.jump(actual,1)!=actual
        moves.append(dict(time=str(t),bits=move['bits'],migrate_ns=migrate_ns,
                          verify_ns=verify_ns,commit_ns=commit_ns))
    return dict(k=k,source_variables=n,live_blocks=live,contracting_blocks=dead,
                period=str(P),decoder_ns=decoder_ns,section_ns=section_ns,
                transport_ns=transport_ns,native_receiver_ns=receiver_ns,
                image_ns=image_ns,algebra_ns=algebra_ns,joint_admit_ns=admit_ns,
                rank_ns=rank_ns,rank_check_ns=rank_check_ns,
                rank_terms=len(packet['terms']),queries=rows,migrations=moves)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--sizes',type=int,nargs='+',default=[24,96,384,1023])
    p.add_argument('--native-ncr',action='store_true')
    p.add_argument('--output')
    args=p.parse_args();codec=None
    if args.native_ncr:
        from ncr_image_codec import NCRCodec
        codec=NCRCodec()
    data=dict(schema='ifs.cig027.campaign.v1',native_ncr=args.native_ncr,
              rows=[trial(k,codec) for k in args.sizes])
    out=json.dumps(data,indent=2)
    if args.output:
        with open(args.output,'w',encoding='utf-8') as s:s.write(out+'\n')
    else:print(out)
