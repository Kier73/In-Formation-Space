"""RCG-001 tests: real release provenance, causal queries, independent oracle."""
from __future__ import annotations
import hashlib
import importlib.util
import unittest
from pathlib import Path
from connectome_ground import (
    ConnectomeGround, Query, ConnectomeRefused, SOURCE_BLOB, sha,
    native_ecpu_stage_dag,
)

# Faithful source rows from OpenWorm c302. Includes outgoing edges excluded
# by the exact query cone, ensuring the normalizer retains full Ground mass.
ACTUAL_SOURCE_ROWS = '''Source,Target,Weight,Type
AWCL,ASER,1,chemical
AWCL,ASGR,1,chemical
AWCL,ASIL,1,chemical
AWCL,AWCR,11,chemical
AWCL,AFDL,2,chemical
AWCL,AIAL,2,chemical
AWCL,AIAR,4,chemical
AWCL,AIBL,12,chemical
AWCL,AIBR,2,chemical
AWCL,AIYL,22,chemical
AWCL,AIZL,1,chemical
AWCL,RIAL,6,chemical
AWCL,AVAL,1,chemical
AWCL,SMDVL,1,chemical
ASER,AIYL,9,chemical
ASER,AIBR,32,chemical
ASIL,AIYL,3,chemical
ASIL,AWCL,3,chemical
AWCR,AIYL,12,chemical
AFDL,AIYL,25,chemical
'''


def small_ground():
    return ConnectomeGround.from_csv(ACTUAL_SOURCE_ROWS.encode(),require_original=False)


class ConnectomeGroundTests(unittest.TestCase):
    def test_real_sample_query_agrees_with_whole_graph(self):
        g=small_ground();q=Query('AWCL','AIYL',2)
        plan=g.plan(q);r=g.run(plan)
        self.assertEqual(plan['layered_nodes'],[['AWCL'],['AFDL','ASER','ASIL','AWCR'],['AIYL']])
        self.assertEqual(r['selected_edge_evaluations'],8)
        self.assertEqual(g.verify(plan,r),g.independent_whole_graph(q))
        self.assertGreater(g.verify(plan,r),0)
        self.assertEqual(r['all_graph_edge_evaluations_reference'],40)
        self.assertLess(r['active_node_labels'],len(g.nodes))
        self.assertFalse(r['is_biological_firing_prediction'])

    def test_pruned_outgoing_edges_must_not_change_denominator(self):
        g=small_ground();p=g.plan(Query('AWCL','AIYL',2))
        aser=[row for row in p['layered_edges'] if row[1]=='ASER']
        self.assertEqual(len(aser),1)
        self.assertEqual(aser[0][-1],41)
        self.assertEqual(aser[0][-2],9)
        self.assertEqual(g.verify(p,g.run(p)),g.independent_whole_graph(Query('AWCL','AIYL',2)))

    def test_query_without_valid_path_returns_exact_zero(self):
        g=small_ground();q=Query('ASGR','AFDL',2)
        p=g.plan(q)
        self.assertEqual(p['layered_edges'],[])
        self.assertEqual(g.verify(p,g.run(p)),0)
        self.assertEqual(g.run(p)['selected_edge_evaluations'],0)

    def test_rejects_forged_plan_receipt_and_budget(self):
        g=small_ground();p=g.plan(Query('AWCL','AIYL',2));r=g.run(p)
        bad={**p,'layered_edges':[list(v) for v in p['layered_edges']]}
        bad['layered_edges'][0][3]+=1
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(ConnectomeRefused,'receiver-owned'):
            g.run(bad)
        altered={**r,'transfer':'77/1'}
        altered['digest']=sha({k:v for k,v in altered.items() if k!='digest'})
        with self.assertRaisesRegex(ConnectomeRefused,'reconstructable'):
            g.verify(p,altered)
        with self.assertRaisesRegex(ConnectomeRefused,'probe budget'):
            g.plan(Query('AWCL','AIYL',2),max_probes=1)
        with self.assertRaises(ConnectomeRefused):
            g.plan(Query('UNKNOWN','AIYL',2))
        with self.assertRaises(ConnectomeRefused):
            g.plan(Query('AWCL','AIYL',True))

    def test_source_github_blob_and_invalid_release_rejected(self):
        with self.assertRaisesRegex(ConnectomeRefused,'altered'):
            ConnectomeGround.from_csv(ACTUAL_SOURCE_ROWS.encode())
        with self.assertRaisesRegex(ConnectomeRefused,'source columns'):
            ConnectomeGround.from_csv(b'wrong,columns\n',require_original=False)
        with self.assertRaises(ConnectomeRefused):
            ConnectomeGround.from_csv((ACTUAL_SOURCE_ROWS+'AWCL,AIYL,22,chemical\n').encode(),require_original=False)

    @unittest.skipUnless(importlib.util.find_spec('mailcpu') is not None,'native E-CPU not installed')
    def test_real_ecpu_dag_readiness_and_recovery(self):
        g=small_ground();p=g.plan(Query('AWCL','AIYL',2));r=g.run(p)
        native=native_ecpu_stage_dag(g,p,r)
        self.assertEqual(native['nodes'],2)
        self.assertTrue(native['recovered_complete'])

    def test_real_complete_openworm_graph_exact_oracle(self):
        data=Path(__file__).parent/'data'/'herm_full_edgelist.csv'
        if not data.exists():
            self.skipTest('full pinned CSV exists in GitHub branch and CI, not local fixture')
        raw=data.read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),SOURCE_BLOB)
        g=ConnectomeGround.from_csv(raw)
        self.assertEqual(len(g.nodes),448)
        self.assertEqual(len(g.edges),7379)
        self.assertEqual(sum(e.kind=='chemical' for e in g.edges),4681)
        self.assertEqual(sum(e.kind=='electrical' for e in g.edges),2698)
        for q,stages,nedges,nnodes in (
            (Query('ASHL','AVAL',3),[1,20,49,1],245,58),
            (Query('ASER','AVBL',3),[1,16,27,1],110,42),
            (Query('AWCL','AIYL',2),[1,4,1],8,6),
            (Query('ASHL','AVAR',3),[1,18,44,1],215,55),
        ):
            p=g.plan(q);r=g.run(p)
            self.assertEqual([len(row) for row in p['layered_nodes']],stages)
            self.assertEqual(r['selected_edge_evaluations'],nedges)
            self.assertEqual(r['active_node_labels'],nnodes)
            self.assertEqual(g.verify(p,r),g.independent_whole_graph(q))


if __name__=='__main__':
    unittest.main()
