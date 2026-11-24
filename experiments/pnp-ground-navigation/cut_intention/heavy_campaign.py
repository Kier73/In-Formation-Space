"""CIG-006 reproducible difficult SAT/#SAT task campaign.

Native dispatcher and a bounded DPLL control always run. Optional local SciPy
HiGHS MILP supplies an independent non-CDCL feasibility comparator; it has no
UNSAT proof certificate. Explicit timestamps/version, source-verified models,
UNKNOWN on resource exhaustion. Not an industrial CDCL speed claim.
"""
from __future__ import annotations
import argparse,json,platform,random,time
from hashlib import sha256
from pathlib import Path
from heavy_ground import compile_ground,dpll,normalize,accepts,xor_encoding
from verify_heavy_ground import verify


def xor_chain(n,unsat=False):
    rows=[]
    for j in range(1,n-1):rows.extend(xor_encoding((j,j+1,j+2),j%2))
    if unsat:
        # First triple has parity one; these two further source equations
        # imply first triple has parity zero, a checked GF(2) 0=1 witness.
        rows.extend(xor_encoding((1,2,4),0))
        rows.extend(xor_encoding((3,4),0))
    return n,rows,'#SAT' if not unsat else 'SAT'

def gates_80(count=80):
    n=3*count;rows=[]
    for i in range(count):
        a,b,o=3*i+1,3*i+2,3*i+3
        if i%2:
            rows.extend(xor_encoding((a,b,o),0))
        else:
            for va in (0,1):
                for vb in (0,1):
                    for vo in (0,1):
                        if vo!=(va&vb):
                            rows.append(tuple((-v if bit else v)
                                 for v,bit in ((a,va),(b,vb),(o,vo))))
    return n,rows,'#SAT'

def pigeonhole(pigeons,holes):
    n=pigeons*holes;rows=[]
    for p in range(pigeons):rows.append(tuple(p*holes+h+1 for h in range(holes)))
    for h in range(holes):
        for a in range(pigeons):
            for b in range(a+1,pigeons):
                rows.append((-(a*holes+h+1),-(b*holes+h+1)))
    return n,rows,'SAT'

def color_graph(vertices,edges,colors=3):
    n=vertices*colors;rows=[]
    for v in range(vertices):
        rows.append(tuple(colors*v+c+1 for c in range(colors)))
        for c,d in __import__('itertools').combinations(range(colors),2):
            rows.append((-colors*v-c-1,-colors*v-d-1))
    for u,v in edges:
        for c in range(colors):rows.append((-colors*u-c-1,-colors*v-c-1))
    return n,rows,'SAT'

def odd_wheel(cycle=31):
    edges=[(i,(i+1)%cycle) for i in range(cycle)]
    edges.extend((i,cycle) for i in range(cycle))
    return color_graph(cycle+1,edges)

def unsat_disjoint_k4(count=40):
    rows=[]
    for j in range(count):
        _,local,_=color_graph(4,list(__import__('itertools').combinations(range(4),2)))
        offset=12*j
        rows.extend(tuple((1 if l>0 else -1)*(abs(l)+offset) for l in c) for c in local)
    return count*12,rows,'SAT'

def random_3sat(n,ratio=4.26,seed=73):
    rng=random.Random(seed);rows=[]
    for _ in range(round(n*ratio)):
        vs=rng.sample(range(1,n+1),3)
        rows.append(tuple(v if rng.getrandbits(1) else -v for v in vs))
    return n,rows,'SAT'

def _milp_check(n,clauses,seconds):
    import numpy as np,scipy
    from scipy.optimize import milp,Bounds,LinearConstraint
    from scipy.sparse import lil_matrix
    normal=normalize(clauses,n)
    A=lil_matrix((len(normal),n),dtype=np.float64)
    lb=np.ones(len(normal))
    for i,row in enumerate(normal):
        for l in row:
            A[i,abs(l)-1]+=1 if l>0 else -1
            if l<0:lb[i]-=1
    t=time.perf_counter()
    res=milp(np.zeros(n),integrality=np.ones(n),bounds=Bounds(np.zeros(n),np.ones(n)),
        constraints=LinearConstraint(A.tocsr(),lb,np.full(len(normal),np.inf)),
        options={'time_limit':seconds,'disp':False})
    elapsed=round((time.perf_counter()-t)*1000,3)
    if res.status==0:
        assignment=sum((int(round(x))<<i) for i,x in enumerate(res.x))
        if not accepts(normal,assignment):raise AssertionError('HiGHS model violates original CNF')
        status='SAT'
    elif res.status==2:status='UNSAT_CLAIM_NO_PROOF'
    else:status='UNKNOWN'
    return {'backend':'SciPy HiGHS MILP, not CDCL','scipy':scipy.__version__,
            'status':status,'wall_ms':elapsed,'status_code':int(res.status),
            'model_source_checked':res.status==0}

def run(*,dpll_nodes=1200,dpll_seconds=1.5,with_milp=False,milp_seconds=3.0):
    fixtures=[('xor192_sat',*xor_chain(192)),('xor192_unsat',*xor_chain(192,True)),
              ('nonlinear80_count',*gates_80()),('pigeonhole8_7',*pigeonhole(8,7)),
              ('odd_wheel_32',*odd_wheel()),('independent_K4_40',*unsat_disjoint_k4()),
              ('random3sat_50',*random_3sat(50,seed=73)),
              ('random3sat_75',*random_3sat(75,seed=71)),
              ('random3sat_100',*random_3sat(100,seed=79))]
    items=[]
    for name,n,rows,intention in fixtures:
        t=time.perf_counter_ns()
        ground,elapsed=compile_ground(rows,n,intent=intention,
                                      max_nodes=dpll_nodes,wall_seconds=dpll_seconds)
        verification_start=time.perf_counter_ns()
        assert verify(rows,n,ground,expected_intention=intention)
        verification_ms=round((time.perf_counter_ns()-verification_start)/1e6,3)
        source_normal=normalize(rows,n)
        direct=dpll(source_normal,n,'SAT',max_nodes=dpll_nodes,seconds=dpll_seconds,
                    with_proof=False) if intention=='SAT' else None
        comparator=None
        if with_milp:
            comparator=_milp_check(n,rows,milp_seconds)
            if comparator['status']=='SAT' and ground['result']['status']=='UNSAT':
                raise AssertionError('independent feasible model contradicts proven UNSAT')
            if comparator['status']=='UNSAT_CLAIM_NO_PROOF' and ground['result']['status']=='SAT':
                raise AssertionError('independent infeasibility contradicts checked SAT witness')
        items.append({'case':name,'variables':n,'clauses':len(rows),
           'source_digest':ground['source_digest'],'intention':intention,
           'chosen_family':ground['chosen_family'], 'status':ground['result']['status'],
           'count':ground['result']['count'],
           'source_proof_verified':True,'construction_ms':round(elapsed['full_construction_ns']/1e6,3),
           'independent_verification_ms':verification_ms,
           'independent_direct_DPLL_control':None if direct is None else
             {k:direct[k] for k in ('status','nodes','literal_checks','wall_ms')},
           'external_milp_control':comparator})
    return {'schema':'ifs.cig006.heavy-problem-campaign.v1',
      'environment':{'python':platform.python_version(),'platform':platform.platform()},
      'budgets':{'direct_and_fallback_dpll_nodes':dpll_nodes,
                 'direct_and_fallback_dpll_wall_seconds':dpll_seconds,
                 'milp_seconds_per_case':milp_seconds if with_milp else None},
      'cases':items,
      'interpretation':'SAT source-ground accuracy and construction/verification cost; UNKNOWN is not UNSAT; no universal polynomial time claim'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--with-milp',action='store_true');p.add_argument('--nodes',type=int,default=1200);p.add_argument('--seconds',type=float,default=1.5)
    o=p.parse_args();print(json.dumps(run(dpll_nodes=o.nodes,dpll_seconds=o.seconds,with_milp=o.with_milp),indent=2))


def heldout(*,seeds=(201,202,203,204),widths=(50,75,100),dpll_nodes=1200,
            dpll_seconds=1.5,with_milp=True,milp_seconds=2.5):
    """Fixed unseen random source cases; measured and verified, no training set.

    Source-only portfolio chooses architecture before any solver outcome.
    No policy learning or benchmark-driven adaptation takes place.
    """
    rows=[]
    for n in widths:
        for seed in seeds:
            nv,cnf,intention=random_3sat(n,seed=seed)
            report,spent=compile_ground(cnf,nv,intent=intention,
                    max_nodes=dpll_nodes,wall_seconds=dpll_seconds)
            t=time.perf_counter_ns()
            assert verify(cnf,nv,report,expected_intention=intention)
            verified_ms=round((time.perf_counter_ns()-t)/1e6,3)
            benchmark=_milp_check(nv,cnf,milp_seconds) if with_milp else None
            if benchmark:
                assert not (benchmark['status']=='SAT' and report['result']['status']=='UNSAT')
                assert not (benchmark['status']=='UNSAT_CLAIM_NO_PROOF' and report['result']['status']=='SAT')
            rows.append({'size':n,'seed':seed,'clauses':len(cnf),
                   'source_digest':report['source_digest'],
                   'source_formed_status':report['result']['status'],
                   'source_formed_family':report['chosen_family'],
                   'verified':True,
                   'construct_ms':round(spent['full_construction_ns']/1e6,3),
                   'verify_ms':verified_ms,'independent_milp':benchmark})
    return {'schema':'ifs.cig006.blind-random3sat-holdout.v1',
      'environment':{'python':platform.python_version(),'platform':platform.platform()},
      'source_only_selection':True,
      'dpll_budget':{'nodes':dpll_nodes,'seconds':dpll_seconds},
      'milp_limit_seconds':milp_seconds if with_milp else None,
      'cases':rows,
      'scope':'deterministic held-out random 3-CNF near 4.26 ratio; HiGHS infeasibility has no independently checked proof'}
