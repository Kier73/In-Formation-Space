from pathlib import Path
import json
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
if str(ROOT/'continuity') not in sys.path:sys.path.insert(0,str(ROOT/'continuity'))
from test_connectome_ground import small_ground
from connectome_ground import Query
from continuity.continuity import Chronicle, ContinuityRefused, GENESIS
from adaptive_fabric.assess_fabric_curriculum import assess
from adaptive_fabric.fabric_policy import experiment
COURSES=json.loads(Path(__file__).resolve().parents[1].joinpath('training_tracks_v2.json').read_text())

class CurriculumTests(unittest.TestCase):
    def test_body_not_biology_and_no_unsupported_promotions(self):
        ids=[(e['id'],e['domain']) for e in COURSES['opportunities']]
        self.assertEqual(len(ids),6)
        self.assertTrue(all('biological' not in e['target'] for e in COURSES['opportunities']))
        self.assertTrue(any(x[0].startswith('body.fabric') for x in ids))
        g=small_ground()
        with tempfile.TemporaryDirectory() as d:
            st=Chronicle(Path(d));h=st.source(g,expected_head=GENESIS)['head']
            h=st.query(g,Query('AWCL','AIYL',2),expected_head=h)['head']
            audit=assess(g,st,expected_head=h,curricula=COURSES,
                         verified_synthetic_study=experiment(g,train_count=10,test_count=4))
            self.assertTrue(all(row['trained_ai_model_exists'] is False for row in audit['opportunities']))
            self.assertFalse(audit['evidence']['authenticated_transit'])
            self.assertNotEqual(audit['evidence']['synthetic_fabric_telemetry'],True)
            with self.assertRaises(ContinuityRefused):
                assess(g,st,expected_head=h,curricula={**COURSES,'schema':'forge'})

if __name__=='__main__':unittest.main()
