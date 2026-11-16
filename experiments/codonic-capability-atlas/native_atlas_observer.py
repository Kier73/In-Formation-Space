"""COG-005: COG source Ground -> E-CPU-native Hypervisor -> separate observer.

Uses VP-003's existing NativeInferenceHost; no second Hypervisor. In GitHub
Actions the planner, native receiver, and verifier are separate ephemeral jobs.
Artifact and SHA chains are NOT external signatures or quorum evidence.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from adaptive_arbiter import fixture_atlas
from structural_discovery import EvidenceAtlas, restore as restore_source, canonical, digest
from high_order_capability import (NavigableExpertAtlas, infer_capability, verify_claim,
                                   SCHEMA, PolynomialGround)

PLAN_SCHEMA=SCHEMA+'.native-plan'
REPORT_SCHEMA=SCHEMA+'.native-report'
TICK=(1<<56)+73
POINT=(13,17)


def pinned_atlas()->NavigableExpertAtlas:
    return NavigableExpertAtlas(257,32,1<<48,'cog005-host-source-v1')


def form_plan()->dict[str,Any]:
    atlas=pinned_atlas()
    route=atlas.route(TICK,8)
    model=atlas.capability(route['center'])
    state=EvidenceAtlas(fixture_atlas(),('alpha',))
    # 33 independent x evaluations + one y challenge and withheld probes.
    # The algorithm under observation is deliberately a known synthetic law,
    # but the polynomial coefficients are not given to the learner.
    points=[(x,0) for x in range(33)]+[(0,1), (199,27),(181,213),(241,199)]
    for point in points:
        state=state.admit('alpha',point,model.apply(point))
    claim=infer_capability(state,'alpha',max_degree=32,min_challenges=2)
    if claim.ground!=model:
        raise ValueError('discovered model does not reproduce synthetic source law')
    body={'schema':PLAN_SCHEMA,'atlas':atlas.fingerprint,
          'route':route,'source':state.trace(),'claim':claim.to_dict(),
          'source_head':state.head,'source_fingerprint':state.fingerprint,
          'point':list(POINT),'request_id':'cog005-first-observation',
          'source_class':'synthetic-polynomial-law;not-trained-not-authenticated'}
    return {**body,'digest':digest(body)}


def verify_plan(plan:Mapping[str,Any],*,expected_head:str,expected_fingerprint:str)->tuple[NavigableExpertAtlas,PolynomialGround]:
    if not isinstance(plan,Mapping) or canonical(dict(plan))!=canonical(form_plan()):
        raise ValueError('source plan does not match receiver-owned fixed atlas contract')
    atlas=pinned_atlas()
    restored=restore_source(fixture_atlas(),plan['source'],expected_head=expected_head,
                            expected_fingerprint=expected_fingerprint)
    if not verify_claim(restored,plan['claim'],expected_head=expected_head,
                        expected_fingerprint=expected_fingerprint):
        raise ValueError('source claim was not independently reconstructed')
    model=infer_capability(restored,'alpha',max_degree=32).ground
    if model!=atlas.capability(plan['route']['center']):
        raise ValueError('source law does not match demanded function index')
    return atlas,model


def execute(plan:Mapping[str,Any],*,expected_head:str,expected_fingerprint:str,
            allow_compute:bool=True)->dict[str,Any]:
    atlas,model=verify_plan(plan,expected_head=expected_head,
                            expected_fingerprint=expected_fingerprint)
    # Existing VP receiver uses real MailCPU HeadlessOS, OperatorSpec,
    # Hypervisor and native deterministic pure-operation result ledger.
    from vp.native_inference import NativeInferenceHost
    def handler(request:dict[str,Any])->dict[str,Any]:
        if canonical(request.get('plan'))!=canonical(plan):
            raise ValueError('the receiver is not allowed to accept a different plan')
        observed=atlas.observe(request['plan']['point'],request['plan']['route'])
        atlas.verify_observation(request['plan']['route'],observed)
        return {'schema':SCHEMA+'.native-execution','source_ground':model.fingerprint,
                'learned_result':list(model.apply(request['plan']['point'])),
                'expert_observation':observed}
    receiver=NativeInferenceHost(handler,node_id='cog005-receiver',
                                  model_ground=atlas.fingerprint,
                                  operator_id='ifs.cog005.high-order-expert-observe',
                                  allow_compute=allow_compute)
    request={'request_id':plan['request_id'],'model_ground':atlas.fingerprint,'plan':dict(plan)}
    native=receiver.execute(request,sequence=1)
    if not allow_compute:
        if native.get('accepted') is not False or native.get('handler_calls')!=0:
            raise ValueError('E-CPU capability denial did not prevent handler execution')
        return native
    if (native.get('accepted') is not True or native.get('hypervisor_action')!='allow'
        or native.get('handler_calls')!=1 or native.get('native_replayed') is not False):
        raise ValueError('E-CPU receiver did not admit exactly one execution')
    replay=receiver.execute(request,sequence=1)
    if replay.get('native_replayed') is not True or replay.get('handler_calls')!=1:
        raise ValueError('E-CPU did not preserve pure semantic replay')
    body={'schema':REPORT_SCHEMA,'plan':dict(plan),'native':native,
          'replay_checked':True,'receiver_source_head':expected_head,
          'receiver_source_fingerprint':expected_fingerprint,
          'transport_scope':'github-job-artifacts-not-quorum-or-independent-signature'}
    report={**body,'digest':digest(body)}
    verify_report(report,expected_head=expected_head,expected_fingerprint=expected_fingerprint)
    return report


def verify_report(report:Mapping[str,Any],*,expected_head:str,expected_fingerprint:str)->bool:
    if not isinstance(report,Mapping) or set(report)!={
        'schema','plan','native','replay_checked','receiver_source_head',
        'receiver_source_fingerprint','transport_scope','digest'}:
        raise ValueError('unknown native observer envelope')
    core={k:v for k,v in report.items() if k!='digest'}
    if report['schema']!=REPORT_SCHEMA or report['digest']!=digest(core):
        raise ValueError('native observer receipt content digest invalid')
    atlas,model=verify_plan(report['plan'],expected_head=expected_head,
                            expected_fingerprint=expected_fingerprint)
    native=report['native']
    if (report['receiver_source_head']!=expected_head or
        report['receiver_source_fingerprint']!=expected_fingerprint or
        report['replay_checked'] is not True or
        report['transport_scope']!='github-job-artifacts-not-quorum-or-independent-signature' or
        not isinstance(native,Mapping) or native.get('accepted') is not True or
        native.get('hypervisor_action')!='allow' or
        native.get('native_replayed') is not False or native.get('handler_calls')!=1 or
        native.get('model_ground')!=atlas.fingerprint or
        type(native.get('operator_contract_digest')) is not str or
        len(native['operator_contract_digest'])!=64):
        raise ValueError('native authority receipt is malformed, stale or refused')
    result=native.get('result')
    if (not isinstance(result,Mapping) or set(result)!={
        'schema','source_ground','learned_result','expert_observation'} or
        result['schema']!=SCHEMA+'.native-execution' or
        result['source_ground']!=model.fingerprint or
        result['learned_result']!=list(model.apply(report['plan']['point']))):
        raise ValueError('learned nonlinear capability did not realize the pinned Ground')
    atlas.verify_observation(report['plan']['route'],result['expert_observation'])
    return True


def load(path:str)->dict[str,Any]:
    raw=Path(path).read_bytes()
    if len(raw)>500_000:raise ValueError('observation artifact exceeds max bytes')
    content=json.loads(raw)
    if type(content) is not dict:raise ValueError('expected canonical object')
    return content


def save(path:str, doc:Mapping[str,Any])->None:
    Path(path).write_bytes(canonical(dict(doc))+b'\n')


def main()->None:
    parser=argparse.ArgumentParser(description='COG-005 multi-observer E-CPU native atlas')
    parser.add_argument('mode',choices=('plan','execute','verify'))
    parser.add_argument('--file',required=True)
    parser.add_argument('--out')
    parser.add_argument('--github-output')
    parser.add_argument('--expected-head')
    parser.add_argument('--expected-fingerprint')
    args=parser.parse_args()
    if args.mode=='plan':
        plan=form_plan()
        save(args.file,plan)
        if args.github_output:
            with Path(args.github_output).open('a') as f:
                f.write('head='+plan['source_head']+'\n')
                f.write('fingerprint='+plan['source_fingerprint']+'\n')
        print(json.dumps({'plan':plan['digest'],'source_head':plan['source_head'],
                          'atlas':plan['atlas'],'logical_experts':1<<48},sort_keys=True))
    elif args.mode=='execute':
        report=execute(load(args.file),expected_head=args.expected_head,
                       expected_fingerprint=args.expected_fingerprint)
        if not args.out:raise ValueError('execution requires report output path')
        save(args.out,report)
        print(json.dumps({'native_hypervisor':report['native']['hypervisor_action'],
                          'digest':report['digest'],'source_head':report['receiver_source_head']}))
    else:
        report=load(args.file)
        verify_report(report,expected_head=args.expected_head,
                      expected_fingerprint=args.expected_fingerprint)
        print(json.dumps({'independent_oracle':True,'report_digest':report['digest']}))

if __name__=='__main__':main()
