"""RCG-002 evidence-directed training opportunity readiness, not a trainer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from continuity.continuity import Chronicle, ContinuityRefused, source_manifest
from connectome_ground import ConnectomeGround


def assess(ground: ConnectomeGround, chronicle: Chronicle, *, expected_head: str,
           curricula: dict[str, Any]) -> dict[str, Any]:
    audit = chronicle.audit(ground, expected_head=expected_head)
    if curricula.get('schema') != 'ifs.embodied-virtual-intelligence-training-opportunities.v1':
        raise ContinuityRefused('unadmitted curriculum schema')
    courses = curricula.get('opportunities')
    if not isinstance(courses, list) or len(courses) != 6:
        raise ContinuityRefused('curriculum must contain six explicit opportunities')
    evidence = {
        'pinned_source': True,
        'independently_verified_queries': audit['counts']['query'] > 0,
        'varied_query_corpus': audit['counts']['query'] >= 3,
        # Do not infer these from local source or self-reported labels.
        'external_behavioral_or_neural_measurements': False,
        'identity_alignment': False,
        'authenticated_transit': False,
        'durable_recovery_lineage': False,
        'task_safety_and_action_authority': False,
        'real_model_or_task_evidence': False,
    }
    output = []
    found = set()
    for obj in courses:
        if not isinstance(obj, dict) or type(obj.get('id')) is not str or obj['id'] in found or \
                obj.get('status') != 'proposed' or not isinstance(obj.get('requires'), list):
            raise ContinuityRefused('malformed or duplicate proposed training opportunity')
        found.add(obj['id'])
        missing = [condition for condition in obj['requires'] if not evidence.get(condition, False)]
        output.append({'id': obj['id'], 'domain': obj['domain'], 'status': 'design-ready' if not missing else 'blocked',
                       'missing_evidence': missing,
                       'trained_model_exists': False})
    return {'schema': 'ifs.embodied-virtual-intelligence-training-readiness.v1',
            'ground': ground.fingerprint, 'retained_high_water': audit['head'],
            'evidence_counts': audit['counts'], 'opportunities': output,
            'interpretation': 'readiness for bounded research only; no learning or biological validation has occurred'}


def main() -> None:
    p = argparse.ArgumentParser(description='Assess body-and-mind training dependencies from retained Ground evidence')
    p.add_argument('--store', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--expected-head', required=True)
    args = p.parse_args()
    ground = ConnectomeGround.from_csv(args.source.read_bytes())
    path = Path(__file__).with_name('training_tracks.json')
    results = assess(ground, Chronicle(args.store), expected_head=args.expected_head,
                     curricula=json.loads(path.read_text()))
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
