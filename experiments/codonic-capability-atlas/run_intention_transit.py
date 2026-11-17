"""COG-010 direct operation: signed observer process -> intention gate -> pinned replay.

The native E-CPU IOS-001 and fgraph backends are REQUIRED in the hosted CI job;
when absent locally, an explicitly test-only oracle exercises the same bounded
mathematical contract. COG-009 stdio peers are NOT E-CPU native mTLS providers.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import tempfile
from pathlib import Path
from hashlib import sha256
from cognitive_grounds import GroundRefused,canonical,digest
from predictive_state import Teacher,source_fixture
from partial_observation import recover
from multi_observer_fabric import Host,HostProcess,SignedFabric,FrozenFabric
from run_multi_observer_fabric import prepare as acquire
from run_multi_observer_fabric import resume as prior_replay
from intention_transit import (CognitiveProjection,NativeIOSPlanner,
                               SignedFeatureReader,execute_intention,FiniteCognitiveOrbit)
from reference_ios_for_tests import ReferenceIOS

SCHEMA='ifs.cog010.intention-conditioned-transit.v1'
HERE=Path(__file__).resolve().parent
AUTH=sha256(b'COG010-experimental-receiver-admission-v1').hexdigest()
PROGRAM=('mention:topic_0000','minutes','seconds','repeat','clear','noise',
         'mention:topic_0001','minutes','repeat','clear')
HORIZON=10**30+11


def backend(require_native:bool=False):
    try:
        from mailcpu.intention_sufficiency import FiniteGround
        return NativeIOSPlanner(AUTH),'native-mailcpu-IOS001'
    except ImportError:
        if require_native:raise RuntimeError('native E-CPU IOS-001 is required in CI')
        return ReferenceIOS(),'test-only-reference-IOS'


def load_machine(path:Path,pins:dict):
    cp=json.loads(path.read_bytes())['cognitive_checkpoint']
    machine,_=recover(cp,expected_checkpoint_digest=pins['cognitive_digest'],
                     expected_ledger_head=pins['observation_head'],
                     expected_source_root=pins['source_root'])
    return machine


def start_existing_hosts(trust:dict,private:Path,subjects:int,durations:int):
    peers=[]
    for item in trust['hosts']:
        name=item['name'];host=Host(name,item['public_key_pem'],item['cost'])
        cmd=(sys.executable,'-u',str(HERE/'observer_worker.py'),
             '--id',name,'--key',str(private/(name+'.pem')),
             '--subjects',str(subjects),'--durations',str(durations),
             '--fault',('target' if name=='beta' else 'none'))
        peer=HostProcess(host,cmd)
        peer.start();peers.append(peer)
    return peers


def prepare(out:Path,trust_path:Path,pins_path:Path,private:Path,
            *,subjects:int=4,durations:int=2,require_native:bool=False)->dict:
    if not 2<=durations<=subjects<=64:raise GroundRefused('run subjects range must be 2..64')
    out.parent.mkdir(parents=True,exist_ok=True)
    stage=out.parent/'prior-cog009-bundle.json'
    old_pins=out.parent/'prior-cog009-pins.json'
    start=time.perf_counter_ns()
    acquire(stage,trust_path,old_pins,private_dir=private,subjects=subjects,durations=durations)
    retained=json.loads(old_pins.read_bytes())
    machine=load_machine(stage,retained)
    trust=json.loads(trust_path.read_bytes())
    planner,mode=backend(require_native)
    peers=start_existing_hosts(trust,private,subjects,durations)
    try:
        teacher=Teacher(*source_fixture(subjects,durations),named=False)
        fabric=SignedFabric(teacher.source_root,teacher.alphabet,peers)
        if fabric.source_root!=machine.source_root:raise GroundRefused('retained Ground is from different observed host epoch')
        for peer in peers:fabric.qualify(peer.host.name)

        start_query=time.perf_counter_ns()
        ready=execute_intention(CognitiveProjection(machine,'has_anchor'),'anchored',planner)
        refused=execute_intention(CognitiveProjection(machine,'repeat'),'anchored',planner,
                                 features=('minutes',))
        before=fabric.external_calls
        hidden=('noise','mention:topic_0003')
        # Deliberately remove the first honest observer to expose signed dissent.
        alpha=next(p for p in peers if p.host.name=='alpha')
        alpha.stop(kill=True)
        reader=SignedFeatureReader(machine,fabric,hidden)
        unknown=False
        try:
            execute_intention(CognitiveProjection(machine,'seconds'),'anchored',planner,
                              features=('minutes','repeat'),reader=reader)
        except GroundRefused as exc:
            unknown='unknown:' in str(exc)
        if not unknown:raise GroundRefused('missing source quorum failed to preserve unknown')
        before_rehome=fabric.external_calls
        alpha.start()
        measured=execute_intention(CognitiveProjection(machine,'seconds'),'anchored',planner,
                                   features=('minutes','repeat'),reader=reader)
        if measured['status']!='RESOLVED_AFTER_MEASUREMENT':
            raise GroundRefused('signed observation did not resolve the admitted intention')
        before_repeat=fabric.external_calls
        repeated=execute_intention(CognitiveProjection(machine,'seconds'),'anchored',planner,
                                   features=('minutes',),reader=reader)
        if fabric.external_calls!=before_repeat or repeated['result']!=measured['result']:
            raise GroundRefused('committed measurement replay changed or repeated effect')
        duration_ns=time.perf_counter_ns()-start_query
        orbit=FiniteCognitiveOrbit.compile(machine,PROGRAM)
        orbit.independent_validate()
        distant=orbit.native_at(HORIZON) if mode.startswith('native') else orbit.at(HORIZON)
        # Short-step independent source semantics vs the compiled structural orbit.
        for t in range(min(80,len(orbit.states)*3)):
            self_step_state=machine.state_after(PROGRAM[:0])
            phase=0
            for i in range(t):
                self_step_state=machine.run_from(self_step_state,(PROGRAM[phase],))[1]
                phase=(phase+1)%len(PROGRAM)
            if orbit.at(t)!=(self_step_state,phase):
                raise GroundRefused('independent stepper contradicts structural orbit')
        fabric_doc=fabric.document()
        sample={'READY':ready,'REFUSE':refused,'MEASURE':measured,
                'cached_measurement':repeated,'status_while_observer_missing':'unknown' if unknown else 'invalid',
                'signed_reads_before_observer_kill':before,
                'signed_reads_during_dispute':before_rehome-before,
                'signed_reads_after_rehome':fabric.external_calls-before_rehome,
                'fresh_process_observation_duration_ms':round(duration_ns/1e6,4),
                'orbit':{'coordinate':str(HORIZON),'result':[distant[0],distant[1]],
                         'mu':orbit.mu,'period':orbit.period,'materialized_states':len(orbit.states),
                         'program_length':len(PROGRAM),'digest':orbit.digest},
                'backend':mode,'source_subjects':subjects,'source_distinct_durations':durations}
        evidence={'schema':SCHEMA,'prior_cog009_bundle':json.loads(stage.read_bytes()),
                  'current_signed_fabric':fabric_doc,'sample':sample,'source_root':machine.source_root,
                  'machine_fingerprint':machine.fingerprint}
        pins={'schema':SCHEMA+'.independently-carried-pin','bundle_digest':digest(evidence),
              'prior_cog009_pins':retained,'current_fabric_head':fabric.head,
              'current_fabric_digest':fabric_doc['digest'],
              'roster_root':fabric.source_root,'trust_digest':digest(trust),
              'machine_fingerprint':machine.fingerprint}
        out.write_bytes(canonical(evidence));pins_path.write_bytes(canonical(pins))
        report={'phase':'prepared','source_subjects':subjects,'mode':mode,
                'source_root':machine.source_root,'machine_states':len(machine.representatives),
                'status_ready':ready['status'],'status_measure':measured['status'],
                'status_refuse':refused['status'],'measurement_value':measured['result'],
                'ready_additional_host_exchanges':ready['additional_host_exchanges'],
                'refuse_additional_host_exchanges':refused['additional_host_exchanges'],
                'measure_additional_host_exchanges_after_rehome':measured['additional_host_exchanges'],
                'cached_additional_host_exchanges':repeated['additional_host_exchanges'],
                'missing_quorum_held_unknown':unknown,'orbit':sample['orbit'],
                'new_signed_observer_receipts':len(fabric.events),
                'prior_cognitive_membership_evidence':len(evidence['prior_cog009_bundle']['cognitive_checkpoint']['ledger']['witnesses']),
                'elapsed_ms':round((time.perf_counter_ns()-start)/1e6,3)}
        return report
    finally:
        for p in peers:p.stop(kill=True)


def resume(bundle_path:Path,trust_path:Path,pins:dict,*,require_native:bool=False)->dict:
    evidence=json.loads(bundle_path.read_bytes());trust=json.loads(trust_path.read_bytes())
    if (pins.get('schema')!=SCHEMA+'.independently-carried-pin' or
            evidence.get('schema')!=SCHEMA or digest(evidence)!=pins['bundle_digest'] or
            digest(trust)!=pins['trust_digest']):
        raise GroundRefused('external pins refuse changed semantic bundle or enrolled keys')
    prior=evidence['prior_cog009_bundle']
    # Recheck original learning against the historical signed host evidence.
    oldpins=pins['prior_cog009_pins']
    if (digest(prior)!=oldpins['bundle_digest'] or
            prior['signed_fabric']['head']!=oldpins['fabric_head']):
        raise GroundRefused('prior cognitive Ground evidence changed')
    from run_multi_observer_fabric import resume as verify_cog009
    with tempfile.TemporaryDirectory(prefix='cog010-fresh-') as d:
        tmp=Path(d);pr=tmp/'prior.json';tr=tmp/'trust.json'
        pr.write_bytes(canonical(prior));tr.write_bytes(canonical(trust))
        verify_cog009(pr,tr,oldpins)
    cp=prior['cognitive_checkpoint']
    machine,_=recover(cp,expected_checkpoint_digest=oldpins['cognitive_digest'],
                      expected_ledger_head=oldpins['observation_head'],
                      expected_source_root=oldpins['source_root'])
    if (machine.fingerprint!=pins['machine_fingerprint'] or
            machine.source_root!=evidence['source_root'] or
            machine.fingerprint!=evidence['machine_fingerprint']):
        raise GroundRefused('reconstructed machine differs from admitted source model')
    roster=[Host(h['name'],h['public_key_pem'],h['cost']) for h in trust['hosts']]
    frozen=FrozenFabric(evidence['current_signed_fabric'],
                        expected_digest=pins['current_fabric_digest'],
                        expected_head=pins['current_fabric_head'],
                        expected_roster_root=pins['roster_root'],trusted_hosts=roster)
    planner,mode=backend(require_native)
    sample=evidence['sample'];hidden=('noise','mention:topic_0003')
    actual_ready=execute_intention(CognitiveProjection(machine,'has_anchor'),'anchored',planner)
    actual_refuse=execute_intention(CognitiveProjection(machine,'repeat'),'anchored',planner,features=('minutes',))
    reader=SignedFeatureReader(machine,frozen,hidden)
    actual_measure=execute_intention(CognitiveProjection(machine,'seconds'),'anchored',planner,
                                    features=('minutes','repeat'),reader=reader)
    if (actual_ready['result']!=sample['READY']['result'] or
            actual_refuse['status']!=sample['REFUSE']['status'] or
            actual_measure['result']!=sample['MEASURE']['result'] or
            actual_measure['status']!=sample['MEASURE']['status']):
        raise GroundRefused('fresh receiver continuation contradicts pinned intentions')
    orbit=FiniteCognitiveOrbit.compile(machine,PROGRAM)
    if not orbit.independent_validate() or orbit.digest!=sample['orbit']['digest']:
        raise GroundRefused('fresh receiver structural orbit differs')
    actual_orbit=orbit.native_at(HORIZON) if mode.startswith('native') else orbit.at(HORIZON)
    if list(actual_orbit)!=sample['orbit']['result']:
        raise GroundRefused('fresh receiver distant coordinate differs')
    return {'phase':'independent_fresh_process_verified','mode':mode,
            'machine_states':len(machine.representatives),'source_root':machine.source_root,
            'ready':actual_ready['result'],'measured':actual_measure['result'],
            'refused':actual_refuse['status'],'future_state':list(actual_orbit),
            'signed_host_receipts_rechecked':len(evidence['current_signed_fabric']['events']),
            'external_host_calls':frozen.external_calls,'private_keys_required':False,
            'native_cryptographically_authenticated_transport':False,
            'native_ECPU_fabric_measurement':'not part of COG009 stdio path'}


def main():
    a=argparse.ArgumentParser()
    a.add_argument('phase',choices=['prepare','resume'])
    a.add_argument('--bundle',type=Path,required=True)
    a.add_argument('--trust',type=Path,required=True)
    a.add_argument('--pins',type=Path,required=True)
    a.add_argument('--private-dir',type=Path)
    a.add_argument('--subjects',type=int,default=4)
    a.add_argument('--durations',type=int,default=2)
    a.add_argument('--require-native',action='store_true')
    args=a.parse_args()
    if args.phase=='prepare':
        if args.private_dir is None:a.error('prepare requires private-dir')
        report=prepare(args.bundle,args.trust,args.pins,args.private_dir,subjects=args.subjects,
                       durations=args.durations,require_native=args.require_native)
    else:
        report=resume(args.bundle,args.trust,json.loads(args.pins.read_bytes()),
                      require_native=args.require_native)
    print(json.dumps(report,sort_keys=True,indent=2))

if __name__=='__main__':main()
