"""Source-pinned E-CPU DAG and IFS operation-span adapter for MMG-005.

Run with an E-CPU checkout at the pinned revision. Verification is local;
remote transport, quorum and rehome are separate integration experiments.
"""
import argparse, hashlib, importlib.util, json, sys, tempfile
from pathlib import Path
import numpy as np
from mmg005_compile import maps,pack,unpack,WALK3
from mmg003_order import plan,realize

ECPU_REV='6f05be0b4ecbb53c5f64580c7b82ee531fdd1f73'
DAG_BLOB='ea66eda9b7ba3c35854812d4b14102ed5b80d84b'
SPAN_BLOB='79390c116f846efa04e512089f22bcabee6b2f07'

def load(name,path,blob):
    raw=path.read_bytes()
    if hashlib.sha1(('blob %d\0'%len(raw)).encode()+raw).hexdigest()!=blob:raise ValueError('source pin mismatch: '+str(path))
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def key(x):
    return hashlib.sha256(json.dumps(list(x.shape)).encode()+b'\0'+x.astype('<i8').tobytes()).hexdigest()

def run(ecpu_root):
    dagmod=load('pinned_dag',ecpu_root/'mailcpu/computation_dag.py',DAG_BLOB)
    spans=load('pinned_spans',Path(__file__).resolve().parents[2]/'bridges/observation-path/operation_spans.py',SPAN_BLOB)
    Node,DAG=dagmod.ComputationNode,dagmod.NavigableComputationDAG
    recorder=spans.OperationSpanRecorder(clock_actor_id='mmg-local',clock_segment_id='run-1')
    b,k=3,3;n=b**k;u,v,w,_=maps(b,WALK3)
    rng=np.random.default_rng(20261125);a=rng.integers(0,2,(n,n),dtype=np.int64);bb=rng.integers(0,2,(n,n),dtype=np.int64)
    trans=lambda x,m:realize(x,[m]*k,plan([m]*k),2)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        def put(x):
            h=key(x);np.save(root/(h+'.npy'),x,allow_pickle=False);return {'digest':h,'shape':list(x.shape)}
        def get(r):
            x=np.load(root/(r['digest']+'.npy'),allow_pickle=False)
            if key(x)!=r['digest'] or list(x.shape)!=r['shape']:raise ValueError('array receipt mismatch')
            return x
        source_a,source_b=put(a),put(bb)
        ctx=hashlib.sha256(json.dumps(dict(base=b,power=k,field=2,rank=WALK3,A=source_a,B=source_b),sort_keys=True).encode()).hexdigest()
        def node(i,op,deps,payload):return Node(i,1,op,'mmg.gf2',ctx,deps,payload)
        dag=DAG([node('left','encode',[],{'source':source_a}),node('right','encode',[],{'source':source_b}),node('multiply','pointwise',['left','right'],{}),node('decode','decode',['multiply'],{})])
        def measured(i,fn):return recorder.measure(attempt_id='run-1',span_id=i,operation_id=i,operation=fn,context={'ground':ctx})
        assert sorted(x.node_id for x in dag.ready_nodes())==['left','right']
        frontier={'left':measured('left',lambda:put(trans(pack(get(source_a),b,k),u))),'right':measured('right',lambda:put(trans(pack(get(source_b),b,k),v)))}
        dag.commit_frontier(frontier,expected_node_ids=['left','right'])
        # Serialize across a local recovery boundary, then resume without repeating encoders.
        snap=json.loads(json.dumps(dag.snapshot()));dag=DAG.from_snapshot(snap)
        assert dag.commit_frontier(frontier,expected_node_ids=['left','right'])
        assert [x.node_id for x in dag.ready_nodes()]==['multiply']
        dag.commit('multiply',measured('multiply',lambda:put(get(dag.result('left'))*get(dag.result('right')))))
        dag.commit('decode',measured('decode',lambda:put(unpack(trans(get(dag.result('multiply')),w),b,k))))
        actual=get(dag.result('decode'));assert np.array_equal(actual,a@bb%2)
        assert dag.is_complete
        # Correct digest alone is insufficient if stored bytes change.
        receipt=dag.result('decode');path=root/(receipt['digest']+'.npy');bad=actual.copy();bad[0,0]^=1;np.save(path,bad,allow_pickle=False)
        try:get(receipt);raise AssertionError('corruption accepted')
        except ValueError:pass
        return {'ecpu_revision':ECPU_REV,'matrix_side':n,'rank_products':26**k,'checkpoint_restored':True,'full_result_verified':True,'tamper_rejected':True,'spans':list(recorder.spans),'graph_digest':dag.digest}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ecpu-root',required=True,type=Path);print(json.dumps(run(p.parse_args().ecpu_root),indent=2))
