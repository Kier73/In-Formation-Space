"""Native PNF neural-block synthesis must preserve exact trained route costs."""
from pathlib import Path
import importlib.util
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
if str(ROOT/'continuity') not in sys.path:sys.path.insert(0,str(ROOT/'continuity'))
from test_connectome_ground import small_ground
from adaptive_fabric.fabric_policy import (
    candidates, fit, synthesize_workloads, training_data,
)

PNF=importlib.util.find_spec('experiments') is not None

@unittest.skipUnless(PNF,'existing IFS PNF package not mounted in local test; hosted CI requires it')
class NativePNFTests(unittest.TestCase):
    def test_synthesize_learned_cost_as_pnf_relu_and_verified_widening(self):
        from adaptive_fabric.neural_policy_ground import (
            compiled_policy_block, verify_compiled, widen_and_verify,
        )
        g=small_ground()
        tasks=synthesize_workloads(g,15,seed=102)
        model=fit(g,training_data(g,tasks[:12],seed=103))
        block,manifest=compiled_policy_block(g,model)
        self.assertEqual(block.validate(),(4,4,6))
        self.assertEqual(len(manifest['output_routes']),6)
        for work in tasks[12:]:
            verify_compiled(g,model,block,manifest,work,queue=17)
        grown=widen_and_verify(block,tasks[-1],sample_route=candidates()[0])
        self.assertTrue(grown['agreement'])
        self.assertNotEqual(grown['parent'],grown['widened'])
        broken=type(block)(block.up_weight,block.up_bias,
                           block.down_weight.copy(),block.down_bias,'relu')
        broken.down_weight[0,0]+=1
        with self.assertRaisesRegex(Exception,'PNF policy tensor'):
            verify_compiled(g,model,broken,manifest,tasks[-1])

if __name__=='__main__':unittest.main()
