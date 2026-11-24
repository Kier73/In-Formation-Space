"""Reproduce CIG-007 policy and matching benchmark, standard library."""
import json,platform,random
from time import perf_counter_ns
from joint_intention_ground import make_branching_source
from language_selector import compile_language
from evidence_ground import compile_policy
from verify_evidence_ground import verify
from hall_ground import compile_hall,verify_hall
from heavy_campaign import pigeonhole
from heavy_ground import dpll,normalize

def ms(t):return round((perf_counter_ns()-t)/1e6,3)
def run():
    s=make_branching_source();t=perf_counter_ns();g,_=compile_language(s,[0,1,2,3,4],steps=3,initial=4);language_ms=ms(t);q=g['intent']
    offers=[[x,b,1] for x in range(32) for b in range(7)]
    policies=[]
    for name,pool,identify in [('intention',offers,False),('identification',offers,True),('no-distinguishing-probe',[[0,0,1]],False),('priced-intention',[[x,b,5 if b==4 else 1] for x,b,_ in offers],False)]:
        t=perf_counter_ns();p=compile_policy(s,g,q,pool,identify=identify);compile_ms=ms(t)
        t=perf_counter_ns();assert verify(s,g,q,pool,identify,p);verify_ms=ms(t)
        policies.append({'case':name,'offered_probes':len(pool),'compile_ms_including_language_replay':compile_ms,'verify_ms_including_language_replay':verify_ms,**p})
    cases=[]
    for a,b in [(7,7),(8,7),(16,15),(32,31),(64,63)]:
        n,r,_=pigeonhole(a,b)
        # scramble variable labels and order to avoid dependence on layout
        rng=random.Random(73);labels=list(range(1,n+1));rng.shuffle(labels)
        r=[tuple((1 if l>0 else -1)*labels[abs(l)-1] for l in row) for row in r];rng.shuffle(r)
        t=perf_counter_ns();p=compile_hall(r,n);construct=ms(t)
        t=perf_counter_ns();assert verify_hall(r,n,p);checked=ms(t)
        item={'pigeons':a,'holes':b,'variables':n,'clauses':len(r),'status':p['status'],'construct_ms':construct,'verify_ms':checked,'edge_scans':p['edge_scans'],'certificate_bytes':len(json.dumps(p,separators=(',',':')).encode()),'proof_demands':len(p.get('demands',[])),'proof_exclusions':len(p.get('exclusions',[]))}
        if (a,b)==(8,7):
            direct=dpll(normalize(r,n),n,'SAT',max_nodes=1200,seconds=1.5,with_proof=False)
            item['direct_dpll']={k:direct[k] for k in ('status','nodes','literal_checks','wall_ms')}
        cases.append(item)
    return {'schema':'ifs.cig007.campaign.v1','python':platform.python_version(),'platform':platform.platform(),'source_language_construction_ms':language_ms,'conditional_predictions':[c['conditional_observation'] for c in g['candidates']],'policies':policies,'hall_cases':cases}
if __name__=='__main__':print(json.dumps(run(),indent=2))
