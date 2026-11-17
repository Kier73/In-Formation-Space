"""COG-009 real child-process observer acquisition, crash/rehome and offline replay.

No E-CPU native authority claimed for this local script. The hosted optional
SAB-003 job checks the same worker against pinned actual E-CPU separately.
"""
from __future__ import annotations
import argparse
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cognitive_grounds import canonical, digest, GroundRefused
from predictive_state import Teacher, source_fixture, conformance, minimality
from partial_observation import ObservedOracle, experimental_revision, checkpoint, recover
from multi_observer_fabric import Host,HostProcess,SignedFabric,FrozenFabric


def prepare(out:Path,trust_path:Path,pins_path:Path,*,private_dir:Path,
            subjects:int=4,durations:int=2)->dict:
    private_dir.mkdir(parents=True,exist_ok=True)
    teacher=Teacher(*source_fixture(subjects,durations),named=False)
    hosts=[];peers=[]
    for name,cost,fault in (('alpha',1,'none'),('beta',2,'target'),('gamma',3,'none')):
        key=Ed25519PrivateKey.generate()
        pem_path=private_dir/(name+'.pem')
        pem_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                     serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        pub=key.public_key().public_bytes(serialization.Encoding.PEM,
                                          serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')
        host=Host(name,pub,cost);hosts.append(host)
        command=(sys.executable,'-u',str(Path(__file__).with_name('observer_worker.py')),
                 '--id',name,'--key',str(pem_path),'--subjects',str(subjects),'--durations',str(durations),'--fault',fault)
        client=HostProcess(host,command)
        client.start();peers.append(client)
    try:
        fabric=SignedFabric(teacher.source_root,teacher.alphabet,peers)
        for host in hosts:fabric.qualify(host.name)
        obs=ObservedOracle(fabric,max_queries=20000)
        learner,machine,report=experimental_revision(obs,max_challenges=200)
        # Explicitly independent finite oracle used for audit ONLY, not learning.
        independent=SimpleNamespace(ground=teacher.ground,alphabet=teacher.alphabet,
                                    source_root=fabric.source_root)
        check=conformance(independent,machine)
        if not check.equivalent or not minimality(independent,machine):
            raise GroundRefused('external synthetic conformance audit failed')
        original=('mention:topic_0001','minutes')
        self_check=fabric.query(original)==teacher.query(original)
        calls_before=fabric.external_calls
        peers[0].stop(kill=True)
        # A novel target path ensures the surviving beta/gamma split; no quorum.
        disputed=('noise','noise','mention:topic_0003','minutes')
        while disputed in fabric.votes:
            disputed=('noise',)+disputed
        if len(disputed)>64:raise GroundRefused('no distinct bounded dispute witness')
        unknown=False
        try:fabric.query(disputed)
        except GroundRefused as exc:unknown='unknown:' in str(exc)
        if not unknown:raise GroundRefused('required insufficient-agreement control failed')
        if fabric.query(original)!=teacher.query(original):raise GroundRefused('already committed evidence replay mismatch')
        original_reused_without_host_calls=fabric.external_calls==calls_before+2
        before_restart=fabric.head
        peers[0].start() # new subprocess boot; original key remains operator-provisioned
        resolved=fabric.query(disputed)
        if resolved!=teacher.query(disputed):raise GroundRefused('recovery did not resolve signed disagreement')
        head_after_restart=fabric.head
        if head_after_restart==before_restart:raise GroundRefused('replacement provided no signed observation')
        receipts_alpha=[e['signed_receipt']['body']['boot'] for e in fabric.events
                        if e['request']['host']=='alpha']
        if len(set(receipts_alpha))<2:raise GroundRefused('worker did not restart into distinct boot')
        target=('mention:topic_0003','minutes')
        target_reply=fabric.query(target)
        if machine.run(target)!=target_reply:
            raise GroundRefused('learned hypothesis contradicted by signed observer result')
        cognitive=checkpoint(obs,learner,machine,report)
        signed=fabric.document()
        bundle={'schema':'ifs.cog009.bundle.v1','signed_fabric':signed,'cognitive_checkpoint':cognitive,
                'sample':{'disputed_path':list(disputed),'resolved_response':[list(x) for x in resolved],
                          'source_unknown_during_host_failure':unknown,
                          'original_reused_without_host_calls':original_reused_without_host_calls,
                          'before_replacement_head':before_restart,'after_replacement_head':head_after_restart,
                          'replacement_boot_changed':len(set(receipts_alpha))>1,'membership_calls':obs.external_calls,
                          'signed_host_exchanges':fabric.external_calls,
                          'signed_receipts':len(fabric.events),
                          'source_subjects':subjects,'distinct_durations':durations,
                          'target_path':list(target),
                          'target_reply':[list(v) for v in target_reply],
                          'learned_states':len(machine.representatives),
                          'independent_finite_conformance_edges':check.checked_edges,
                          'independent_finite_equivalent':check.equivalent,
                          'epistemic_status':report['status']}}
        trust={'schema':'ifs.cog009.operator-pinned-keys.v1',
               'hosts':[{'name':h.name,'public_key_pem':h.public_key_pem,'cost':h.cost} for h in hosts]}
        pins={'bundle_digest':digest(bundle),'fabric_head':fabric.head,
              'fabric_digest':signed['digest'],'roster_root':fabric.source_root,
              'cognitive_digest':cognitive['digest'],'observation_head':obs.head,
              'source_root':fabric.source_root,'trust_digest':digest(trust)}
        for p,obj in [(out,bundle),(trust_path,trust),(pins_path,pins)]:
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(canonical(obj))
        return {'phase':'prepared','pins':pins,'sample':bundle['sample']}
    finally:
        for peer in peers:peer.stop(kill=True)


def resume(bundle_path:Path,trust_path:Path,pins:dict)->dict:
    bundle=json.loads(bundle_path.read_bytes());trust=json.loads(trust_path.read_bytes())
    if (digest(bundle)!=pins['bundle_digest'] or digest(trust)!=pins['trust_digest'] or
            bundle.get('schema')!='ifs.cog009.bundle.v1' or
            trust.get('schema')!='ifs.cog009.operator-pinned-keys.v1'):
        raise GroundRefused('wrong external artifact pins or incompatible source')
    hosts=[Host(h['name'],h['public_key_pem'],h['cost']) for h in trust['hosts']]
    signed=FrozenFabric(bundle['signed_fabric'],expected_digest=pins['fabric_digest'],
                        expected_head=pins['fabric_head'],expected_roster_root=pins['roster_root'],
                        trusted_hosts=hosts)
    machine,frozen_obs=recover(bundle['cognitive_checkpoint'],
                                expected_checkpoint_digest=pins['cognitive_digest'],
                                expected_ledger_head=pins['observation_head'],
                                expected_source_root=pins['source_root'])
    # COG-008 membership answers are independently reconstructed from actual signed
    # host evidence. A forged COG-008 ledger cannot substitute its own claimed source.
    for witness in frozen_obs.witnesses:
        if signed.query(witness.path)!=witness.outputs:
            raise GroundRefused('cognitive observation not justified by independently signed host agreement')
    probe=tuple(bundle['sample']['disputed_path'])
    if signed.query(probe)!=tuple(tuple(x) for x in bundle['sample']['resolved_response']):
        raise GroundRefused('signed disagreement resolution did not survive recovery')
    target=tuple(bundle['sample']['target_path'])
    answer=machine.run(target)
    if answer!=signed.query(target) or answer!=tuple(tuple(v) for v in bundle['sample']['target_reply']):
        raise GroundRefused('reconstructed cognition disagrees with signed Ground evidence')
    return {'phase':'fresh_process_recovered','predictive_answer':[list(v) for v in answer],
            'signed_dispute_resolved':True,'offline_signatures_reverified':len(bundle['signed_fabric']['events']),
            'cognitive_memberships_reverified_against_signed_hosts':len(frozen_obs.witnesses),
            'learned_states':len(machine.representatives),'external_host_calls':signed.external_calls+frozen_obs.external_calls,
            'private_keys_required':False,'global_truth_established':False,
            'native_ecpu_mtls_or_quorum':'not_claimed_in_local_demo'}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('command',choices=('prepare','resume'))
    ap.add_argument('--bundle',type=Path,required=True)
    ap.add_argument('--trust',type=Path,required=True)
    ap.add_argument('--pins',type=Path,required=True)
    ap.add_argument('--private-dir',type=Path)
    ap.add_argument('--subjects',type=int,default=4)
    ap.add_argument('--durations',type=int,default=2)
    args=ap.parse_args()
    if args.command=='prepare':
        if args.private_dir is None:ap.error('prepare needs --private-dir')
        result=prepare(args.bundle,args.trust,args.pins,private_dir=args.private_dir,
                       subjects=args.subjects,durations=args.durations)
    else:
        result=resume(args.bundle,args.trust,json.loads(args.pins.read_bytes()))
    print(json.dumps(result,sort_keys=True,indent=2))

if __name__=='__main__':main()
