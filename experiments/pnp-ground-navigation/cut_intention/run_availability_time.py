"""CIG-028 native continuing process under changing host availability."""
import argparse,json,tempfile
from pathlib import Path
from time import perf_counter_ns
from run_capacity_time import fixture
from run_output_time import circuit_source,expr_eval
from run_temporal_ground import encode_law,power_oracle
from temporal_ground import compile_transport,Navigator
from verify_temporal_ground import Receiver
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_image import Processor,unpack
from temporal_algebra import compile_algebra,Language
from capacity_time import CapacityNavigator
from verify_capacity_time import CapacityAdmission
from availability_time import AvailabilityNavigator
from verify_availability_time import AvailabilityAdmission
from continuation_checkpoint import save,recover


def timed(fn,*a,**kw):
    t=perf_counter_ns();value=fn(*a,**kw);return value,perf_counter_ns()-t


def trial(k,codec=None):
    p,f,initial,exprs,P,live,dead=fixture(k)
    start=10**1000+173;tail=((start+P-1)//P)*P
    n,s,q,fs=circuit_source(k,exprs)
    clock=perf_counter_ns()
    dec=synthesize_shared(n,s,q,fs);sec=compile_section(n,s,q)
    ts=encode_law(k,3,p,f);g=compile_transport(ts,k,3)
    nav=Navigator(k,3,g,dec)
    receiver=Receiver(n,s,q,fs,dec,ts,3,g,initial,section=sec)
    proc=Processor(nav,initial,codec=codec)
    d,receipt=compile_algebra(nav,initial);lang=Language(d,receipt)
    source_ns=perf_counter_ns()-clock
    planner=CapacityNavigator(proc,lang)
    cap,admission_ns=timed(CapacityAdmission,receiver,proc.proof,receipt)
    packet,rank_ns=timed(planner.prepare_rank,0)
    _,check_rank_ns=timed(cap.prepare_rank,packet)
    windows=((0,1,'host-A',k),(1,3,'host-A',k-dead),
             (P-1,P+1,'host-B',3*live),(3*P,3*P+1,'host-C',3*live),
             (tail,None,'host-D',3*live))
    producer,plan_ns=timed(AvailabilityNavigator,planner,windows)
    admitted,check_ns=timed(AvailabilityAdmission,cap,windows)
    rows=[]
    def query(lower,ordinal,expected):
        r,seek_ns=timed(producer.query,0,lower,ordinal)
        ok,verify_ns=timed(admitted.verify,0,lower,ordinal,r);assert ok
        assert int(r['time'])==expected
        rows.append(dict(start=str(lower),ordinal=str(ordinal),time=r['time'],
                         host=r['host'],seek_ns=seek_ns,verify_ns=verify_ns))
        return r
    for j,t in enumerate((0,P,3*P,tail,tail+P),1):query(0,j,t)
    query(0,10**900+173,tail+(10**900+169)*P)
    query(2,1,P)
    r=query(1,1,P);move=proc.move(P)
    assert admitted.accept_move(0,1,1,r,move);proc.commit(move)
    old=producer.query(0,P+1)
    assert old['host']=='host-C'
    revised=windows[:3]+((4*P,4*P+1,'replacement',3*live),windows[-1])
    _,revise_ns=timed(producer.revise,revised,P+1,0)
    _,check_revision_ns=timed(admitted.revise,revised,P+1,0)
    assert not admitted.verify(0,P+1,1,old)
    # Persist the accepted coordinate, then create fresh producer and checker.
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'checkpoint.json'
        key,checkpoint_ns=timed(save,admitted,path);checkpoint_bytes=path.stat().st_size
        clock=perf_counter_ns()
        fresh=CapacityAdmission(receiver,proc.proof,receipt);fresh.prepare_rank(packet)
        admitted=AvailabilityAdmission(fresh,revised,revision=1)
        restore_admission_ns=perf_counter_ns()-clock
        original_key=proc.key
        proc,recover_ns=timed(recover,admitted,nav,initial,path,key,codec=codec)
        assert proc.key==original_key
    planner=CapacityNavigator(proc,lang);planner.prepare_rank(0)
    producer=AvailabilityNavigator(planner,revised,revision=1)
    moves=[]
    for lower,expected in ((P+1,4*P),(4*P+1,tail),(tail+1,tail+P)):
        r=query(lower,1,expected)
        move,migrate_ns=timed(proc.move,expected)
        ok,verify_ns=timed(admitted.accept_move,0,lower,1,r,move);assert ok
        proc.commit(move)
        actual=unpack(proc.alphabets(expected),3,proc.rank)
        assert actual==power_oracle(initial,k,3,p,f,expected)
        assert move['outputs']==[expr_eval(e,actual) for e in exprs]
        assert nav.jump(actual,1)!=actual
        moves.append(dict(time=str(expected),host=r['host'],bits=move['bits'],
                          migrate_ns=migrate_ns,verify_ns=verify_ns))
    return dict(k=k,source_variables=n,period=str(P),logical_retained_bits=3*live,
                source_ns=source_ns,capacity_admission_ns=admission_ns,
                rank_ns=rank_ns,rank_check_ns=check_rank_ns,
                schedule_ns=plan_ns,schedule_check_ns=check_ns,
                revise_ns=revise_ns,check_revision_ns=check_revision_ns,
                checkpoint_ns=checkpoint_ns,checkpoint_bytes=checkpoint_bytes,
                restore_admission_ns=restore_admission_ns,recover_ns=recover_ns,
                queries=rows,migrations=moves)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--sizes',nargs='+',type=int,default=[24,96,1023])
    p.add_argument('--native-ncr',action='store_true')
    a=p.parse_args();codec=None
    if a.native_ncr:
        from ncr_image_codec import NCRCodec
        codec=NCRCodec()
    print(json.dumps([trial(k,codec) for k in a.sizes],indent=2))
