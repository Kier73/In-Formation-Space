from __future__ import annotations
import unittest
from fractions import Fraction
from pathlib import Path
from connectome_ground import ConnectomeGround, ConnectomeRefused, Query
from query_attribution import attribute
from test_connectome_ground import small_ground


class AttributionTests(unittest.TestCase):
    def test_exact_real_excerpt_conserves_mediator_mass(self):
        ground = small_ground()
        plan = ground.plan(Query('AWCL', 'AIYL', 2))
        receipt = ground.run(plan)
        result = attribute(ground, plan, receipt, top_n=2)
        self.assertEqual(len(result['stages']), 1)
        stage = result['stages'][0]
        self.assertEqual(stage['ranked_node_count'], 4)
        partial = sum((Fraction(z['mass']) for z in stage['most_contributing']), Fraction(0))
        self.assertEqual(partial + Fraction(stage['omitted_mass']), Fraction(result['total']))
        with self.assertRaises(ConnectomeRefused):
            attribute(ground, plan, receipt, top_n=0)

    def test_pinned_complete_source_exact_mediator_rankings(self):
        path=Path(__file__).parent/'data'/'herm_full_edgelist.csv'
        if not path.is_file():
            self.skipTest('full original data is pinned in the GitHub branch and CI')
        ground=ConnectomeGround.from_csv(path.read_bytes())
        plan=ground.plan(Query('ASHL','AVAL',3))
        evidence=attribute(ground,plan,ground.run(plan))
        self.assertEqual(len(evidence['stages']),2)
        self.assertEqual(evidence['stages'][0]['most_contributing'][0]['node'],'AIBL')
        self.assertEqual(evidence['stages'][1]['most_contributing'][0]['node'],'AVDR')
        for stage in evidence['stages']:
            observed = sum((Fraction(x['mass']) for x in stage['most_contributing']), Fraction(0))
            self.assertEqual(observed + Fraction(stage['omitted_mass']), Fraction(evidence['total']))


if __name__=='__main__':
    unittest.main()
