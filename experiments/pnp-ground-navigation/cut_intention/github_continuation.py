"""CIG-029: native E-CPU bootstrap of CIG continuations on GitHub job lifetimes.

Artifact transfer is performed by the workflow, not a simulated SAB carrier.
The runner-local capability allowlist is deliberately narrow and explicit.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from time import perf_counter_ns

from mailcpu.substrate_bootstrap import (
    AdaptiveBootstrap, BootstrapPolicy, BootstrapRefused, BootstrapTask,
    OperationOffer, RealizerBinding, ResourceObservation, SubstrateObservation,
    digest, verify_bootstrap_report,
)
from ncr_image_codec import NCRCodec
from run_capacity_time import fixture
from run_output_time import circuit_source, expr_eval
from run_temporal_ground import encode_law, power_oracle
from temporal_ground import compile_transport, Navigator
from verify_temporal_ground import Receiver
from shared_proof import synthesize_shared
from source_section import compile_section
from temporal_image import Processor, unpack
from temporal_algebra import compile_algebra, Language
from capacity_time import CapacityNavigator
from verify_capacity_time import CapacityAdmission
from availability_time import AvailabilityNavigator
from verify_availability_time import AvailabilityAdmission
from continuation_checkpoint import save, recover

SCHEMA='ifs.cig029.runner-chain.v1'
SIZES=(24,96,1023)
MAX_BYTES=2_000_000
START=10**1000+173
ORDINAL=10**900+173
ROLES=('seed','contract','resume')
HOSTS=('github-seed','github-contract','github-resume')


def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def raw_digest(raw):
    return sha256(raw).hexdigest()


def provenance():
    # No tokens, private IP addresses or full environment dump.
    return dict(run=os.environ.get('GITHUB_RUN_ID','local'),
                attempt=os.environ.get('GITHUB_RUN_ATTEMPT','0'),
                commit=os.environ.get('GITHUB_SHA','local'),
                job=os.environ.get('GITHUB_JOB','local'),
                os=platform.system(),python=platform.python_version())


class Ground:
    def __init__(self,k):
        clock=perf_counter_ns()
        p,f,initial,exprs,P,live,dead=fixture(k)
        n,s,q,fs=circuit_source(k,exprs)
        d=synthesize_shared(n,s,q,fs);sec=compile_section(n,s,q)
        ts=encode_law(k,3,p,f);g=compile_transport(ts,k,3)
        self.nav=Navigator(k,3,g,d)
        self.receiver=Receiver(n,s,q,fs,d,ts,3,g,initial,section=sec)
        self.k=k;self.initial=initial;self.p=p;self.f=f;self.exprs=exprs
        self.period=P;self.live=live;self.dead=dead
        self.windows=((1,2,HOSTS[0],k-dead),(3,4,HOSTS[1],3*live),
                      (P,P+1,HOSTS[2],3*live))
        self.revised=self.windows[:2]+((START,None,HOSTS[2],3*live),)
        diagram,self.algebra=compile_algebra(self.nav,initial)
        self.language=Language(diagram,self.algebra)
        not_i=self.language.extend('not',0)
        self.always=self.language.extend('or',0,not_i)
        self.extension=self.language.export()
        self.source_ns=perf_counter_ns()-clock

    def fresh(self):
        proc=Processor(self.nav,self.initial,codec=NCRCodec())
        planner=CapacityNavigator(proc,self.language)
        capacity=CapacityAdmission(self.receiver,proc.proof,self.algebra)
        capacity.extend(self.extension)
        for root in (0,self.always):
            capacity.prepare_rank(planner.prepare_rank(root))
        return proc,planner,AvailabilityNavigator(planner,self.windows),AvailabilityAdmission(capacity,self.windows)

    def request(self,stage):
        if stage==0:return self.always,1,1
        if stage==1:return self.always,2,1
        if stage==2:return 0,START,ORDINAL
        raise ValueError('stage')

    def expected(self,stage):
        return (1,3,((START+self.period-1)//self.period+ORDINAL-1)*self.period)[stage]

    def check_oracle(self,stage,move):
        t=self.expected(stage)
        code=power_oracle(self.initial,self.k,3,self.p,self.f,t)
        assert move['time']==str(t)
        assert move['outputs']==[expr_eval(e,code) for e in self.exprs]
        assert move['bits']==(self.k-self.dead if stage==0 else 3*self.live)

    def revise(self,producer,admission):
        old=producer.query(0,4)
        assert old['time']==str(self.period)
        producer.revise(self.revised,4,0)
        admission.revise(self.revised,4,0)
        assert not admission.verify(0,4,1,old)
        return old


def bootstrap(ground,stage,proc,producer,admission,observed):
    """Execute one locally authorized CIG migration through actual E-CPU SAB."""
    root,start,ordinal=ground.request(stage)
    request=dict(root=root,start=str(start),ordinal=str(ordinal),
                 prior_time=str(proc.time),prior_rank=str(proc.rank),
                 schedule=producer.schedule,revision=producer.revision)
    host=HOSTS[stage]
    def handler(value):
        if value!=request:raise ValueError('request changed')
        r=producer.query(root,start,ordinal)
        if r['status']!='FOUND' or r['host']!=host:raise ValueError('host unavailable')
        return dict(query=r,move=proc.move(int(r['time'])))
    def oracle(value,result):
        if value!=request:return False
        # Independently verify on a detached receiver; publication follows below.
        # Copy only the image cursor/receiver; keep the immutable rank language.
        r,m=result['query'],result['move']
        return (r['host']==host and admission.verify(root,start,ordinal,r)
                and deepcopy(admission.capacity.image).accept(int(r['time']),m))
    offer=OperationOffer('cig-migrate','intention','qualified-coordinate',1)
    resource=ResourceObservation(host,'github-runner',stage,stage,'runner-local',
                                 digest(observed),(offer,))
    # Fingerprint the installed local binding, not an untrusted advertisement.
    binding=RealizerBinding(host,'cig-migrate',handler,
                            raw_digest(Path(__file__).read_bytes()),oracle)
    inventory=SubstrateObservation((resource,),())
    policy=BootstrapPolicy(frozenset({(host,'cig-migrate')}),frozenset(),'cig029-job')
    task=BootstrapTask('cig029-migration',proc.key,host,'intention',host,
                       'qualified-coordinate',request,max_bytes=65536,require_oracle=True)
    runtime=AdaptiveBootstrap(inventory,policy,(binding,),())
    plan=runtime.plan(task,coordinate=stage)
    # A sensed operation cannot execute without the locally installed binding.
    try:
        AdaptiveBootstrap(inventory,policy,(),()).plan(task,coordinate=stage)
    except BootstrapRefused:pass
    else:raise AssertionError('unbound advertised operation admitted')
    report=runtime.execute(task,plan,coordinate=stage)
    assert verify_bootstrap_report(report,task,plan)
    assert report['receiver_oracle_checked_steps']==1
    r,m=report['output']['query'],report['output']['move']
    assert admission.accept_move(root,start,ordinal,r,m)
    proc.commit(m);ground.check_oracle(stage,m)
    return report


def replay(ground,records):
    """Reconstruct every publication on a fresh native source-qualified receiver."""
    proc,planner,producer,admission=ground.fresh()
    for stage,record in enumerate(records):
        if stage>=len(ROLES) or record['role']!=ROLES[stage]:raise ValueError('history order')
        if record['parent']!= (digest(records[stage-1]) if stage else None):
            raise ValueError('history predecessor')
        root,start,ordinal=ground.request(stage)
        report=record['report']
        if (report['ground_digest']!=proc.key or report['receiver_oracle_checked_steps']!=1
            or report['output_digest']!=digest(report['output'])
            or report['report_digest']!=digest({k:v for k,v in report.items() if k!='report_digest'})):
            raise ValueError('SAB report identity')
        r,m=report['output']['query'],report['output']['move']
        if r['host']!=HOSTS[stage] or not admission.accept_move(root,start,ordinal,r,m):
            raise ValueError('independent migration replay')
        proc.commit(m);ground.check_oracle(stage,m)
        if stage==1:
            old=ground.revise(producer,admission)
            if record['revoked']!=old:raise ValueError('revision history')
        elif record['revoked'] is not None:raise ValueError('unexpected revision')
        if record['checkpoint']!=admission.snapshot():
            raise ValueError('checkpoint history')
    return proc,planner,producer,admission


def read_bundle(path,expected):
    with Path(path).open('rb') as f:raw=f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES or raw_digest(raw)!=expected:raise ValueError('artifact digest')
    x=json.loads(raw)
    if x['schema']!=SCHEMA or [r['k'] for r in x['grounds']]!=list(SIZES):
        raise ValueError('artifact contract')
    return x


def run(stage,previous,expected,out):
    prior=None if stage==0 else read_bundle(previous,expected)
    result=dict(schema=SCHEMA,grounds=[])
    observed=provenance()
    for j,k in enumerate(SIZES):
        g=Ground(k)
        records=[] if prior is None else prior['grounds'][j]['records']
        if len(records)!=stage:raise ValueError('incomplete predecessor')
        if records:
            _,_,_,checked=replay(g,records)
            assert checked.snapshot()==records[-1]['checkpoint']
            # Distinct fresh receiver, then restore durable coordinate only.
            proc,planner,producer,admission=g.fresh()
            if stage==2:
                producer.revise(g.revised,4,0)
                admission.revise(g.revised,4,0)
            packet=records[-1]['checkpoint']
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'coordinate.json';path.write_bytes(canonical(packet))
                proc=recover(admission,g.nav,g.initial,path,packet['sha256'],codec=NCRCodec())
            planner.processor=proc
            assert proc.time==int(packet['state']['time'])
        else:
            proc,planner,producer,admission=g.fresh()
        clock=perf_counter_ns()
        report=bootstrap(g,stage,proc,producer,admission,observed)
        revoked=g.revise(producer,admission) if stage==1 else None
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'coordinate.json'
            seal=save(admission,path);checkpoint=json.loads(path.read_bytes())
            assert checkpoint['sha256']==seal
        record=dict(role=ROLES[stage],parent=digest(records[-1]) if records else None,
                    provenance=observed,report=report,revoked=revoked,checkpoint=checkpoint,
                    source_ns=g.source_ns,bootstrap_ns=perf_counter_ns()-clock)
        result['grounds'].append(dict(k=k,records=records+[record]))
    raw=canonical(result)
    if len(raw)>MAX_BYTES:raise ValueError('artifact budget')
    path=Path(out);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    print(raw_digest(raw))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
            f.write('sha256='+raw_digest(raw)+'\n')


def audit(path,expected):
    bundle=read_bundle(path,expected);results=[]
    for row in bundle['grounds']:
        g=Ground(row['k']);records=row['records']
        if len(records)!=3:raise ValueError('incomplete runner chain')
        proc,_,_,admission=replay(g,records)
        final=unpack(proc.alphabets(proc.time),3,proc.rank)
        assert final==power_oracle(g.initial,g.k,3,g.p,g.f,proc.time)
        assert g.nav.jump(final,1)!=final
        prov=[r['provenance'] for r in records]
        if os.environ.get('GITHUB_ACTIONS')=='true':
            assert [r['job'] for r in prov]==list(ROLES)
            assert [r['os'] for r in prov]==['Linux','Windows','Linux']
            assert all(r['run']==os.environ['GITHUB_RUN_ID'] and
                       r['attempt']==os.environ['GITHUB_RUN_ATTEMPT'] and
                       r['commit']==os.environ['GITHUB_SHA'] for r in prov)
        results.append(dict(k=g.k,key=proc.key,period=str(g.period),
                            time=str(proc.time),bits=3*g.live,rank=str(proc.rank),
                            checkpoints=[r['checkpoint']['sha256'] for r in records],
                            runner_jobs=prov,verified=True))
    print(json.dumps(dict(schema='ifs.cig029.audit.v1',artifact=expected,results=results),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('role',choices=(*ROLES,'audit'))
    p.add_argument('--input');p.add_argument('--expected');p.add_argument('--output')
    args=p.parse_args()
    if args.role=='audit':audit(args.input,args.expected)
    else:run(ROLES.index(args.role),args.input,args.expected,args.output)
