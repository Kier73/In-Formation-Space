"""RCG-003: readiness from evidence, never inferred from a synthetic label."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from connectome_ground import ConnectomeGround
from continuity.continuity import Chronicle, ContinuityRefused

SCHEMA='ifs.adaptive-fabric-virtual-intelligence-training-opportunities.v2'


def assess(ground: ConnectomeGround, store: Chronicle, *, expected_head: str,
           curricula: dict[str, Any], verified_synthetic_study: dict[str, Any] | None = None) -> dict:
    audit=store.audit(ground, expected_head=expected_head)
    if curricula.get('schema') != SCHEMA or len(curricula.get('opportunities',[])) != 6:
        raise ContinuityRefused('v2 adaptive-fabric curriculum schema or count differs')
    old=store.verify(expected_head=expected_head)
    pairs=set()
    for entry in old:
        if entry['kind']=='query':
            capsule=store._verified_object(entry)
            query=capsule.get('query',{})
            pairs.add((query.get('source'),query.get('target')))
    # A standalone local study file is not a trusted Chronicle event, so it
    # cannot automatically promote hard remote/evidence prerequisites.
    summary={'pinned_source':True,
             'independently_verified_queries':audit['counts']['query']>0,
             'varied_query_corpus':len(pairs)>=3,
             'synthetic_fabric_telemetry':False,
             'held_out_synthetic_tasks':False,
             'distinct_verified_parameter_content':False,
             'authenticated_transit':False,
             'host_authority_evidence':False,
             'durable_recovery_lineage':False}
    if verified_synthetic_study is not None:
        from adaptive_fabric.fabric_policy import SCHEMA as FABRIC, canonical_hash
        doc=verified_synthetic_study
        if type(doc) is not dict or doc.get('schema')!=FABRIC+'.study.v1' or \
                doc.get('ground')!=ground.fingerprint or \
                doc.get('digest')!=canonical_hash({k:v for k,v in doc.items() if k!='digest'}):
            raise ContinuityRefused('synthetic study is not even self-consistent')
        # A supplied study is self-reported until its dataset/receiver receipts
        # have been independently reconstructed and externally pinned.
        summary['synthetic_fabric_telemetry']='self-reported-not-authoritative'
        summary['held_out_synthetic_tasks']='self-reported-not-authoritative'
    decisions=[];seen=set()
    for x in curricula['opportunities']:
        if type(x) is not dict or type(x.get('id')) is not str or x['id'] in seen or \
                x.get('domain') not in ('body','mind') or x.get('status')!='proposed' or \
                type(x.get('requires')) is not list:
            raise ContinuityRefused('invalid v2 opportunity')
        seen.add(x['id'])
        missing=[key for key in x['requires'] if summary.get(key) is not True]
        decisions.append({'id':x['id'],'status':'design-ready' if not missing else 'blocked',
                          'missing_evidence':missing,'trained_ai_model_exists':False})
    return {'schema':SCHEMA+'.readiness.v1','ground':ground.fingerprint,
            'head':audit['head'],'evidence':summary,'opportunities':decisions,
            'note':'readiness and potential are not evidence of trained AI or remote computation'}


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--store',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--expected-head',required=True)
    a=p.parse_args()
    g=ConnectomeGround.from_csv(a.source.read_bytes())
    tracks=json.loads(Path(__file__).resolve().parents[1].joinpath('training_tracks_v2.json').read_text())
    print(json.dumps(assess(g,Chronicle(a.store),expected_head=a.expected_head,curricula=tracks),indent=2))


if __name__=='__main__':main()
