"""Independent, test-only finite partition oracle. NOT a substitute for IOS-001.

Runs only in local mathematical experiments where `mailcpu` cannot be installed.
Hosted CI tests the real IOS-001 backend and compares outcomes against this.
"""
from __future__ import annotations
import itertools
from cognitive_grounds import GroundRefused,digest
from intention_transit import CognitiveProjection

class ReferenceIOS:
    def plan(self,p:CognitiveProjection, public:str, features:tuple[str,...]):
        candidates=[r for r in p.model_rows() if r['public']==public]
        if not candidates: raise GroundRefused('public observation unknown')
        if len(features)>12 or len(set(features))!=len(features):raise GroundRefused('invalid offered features')
        best=None
        for n in range(len(features)+1):
            for selected in itertools.combinations(sorted(features),n):
                partitions={}
                for row in candidates:
                    key=tuple(tuple(row['features'][f]) for f in selected)
                    partitions.setdefault(key,set()).add(str(row['target']))
                if all(len(v)==1 for v in partitions.values()):
                    rank=(sum(1 if f=='minutes' else 3 for f in selected),len(selected),selected)
                    if best is None or rank<best:best=rank
        if best is None:
            status='REFUSE';selected=();result=None
        else:
            selected=best[2];status='MEASURE' if selected else 'READY'
            result=candidates[0]['target'] if not selected else None
        body={'schema':'ifs.cog010.reference-plan','projection':p.contract_digest,
              'public':public,'features':list(features),'status':status,
              'selected_features':list(selected),'ready_result':result,
              'candidate_count':len(candidates)}
        return {**body,'plan_digest':digest(body)}

    def resolve(self,p:CognitiveProjection, public:str, features:tuple[str,...], plan,
                measured,receipt_digest):
        if plan!=self.plan(p,public,features):raise GroundRefused('changed or stale plan')
        if plan['status']=='REFUSE':raise GroundRefused('refused intention')
        if set(measured)!=set(plan['selected_features']):raise GroundRefused('extra or missing measurement')
        if measured and not receipt_digest:raise GroundRefused('measurement missing evidence')
        if not measured and receipt_digest:raise GroundRefused('READY must not possess measurement')
        candidates=[r for r in p.model_rows() if r['public']==public]
        remain=[r for r in candidates if all(r['features'][f]==v for f,v in measured.items())]
        if not remain or len({str(r['target']) for r in remain})!=1:
            raise GroundRefused('measurement contradiction or residual ambiguity')
        body={'status':'RESOLVED_AFTER_MEASUREMENT' if measured else 'RESOLVED_WITHOUT_MEASUREMENT',
              'result':remain[0]['target'],'plan':plan['plan_digest'],
              'receipt_digest':receipt_digest}
        return {**body,'resolution_digest':digest(body)}
