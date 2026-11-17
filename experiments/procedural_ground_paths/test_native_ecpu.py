"""Native authority and representation gate; must run in E-CPU-pinned CI."""
from __future__ import annotations
import hashlib,os,unittest
from decision_experiment import H
try:
    from mailcpu.intent_embedding import IntentEmbedding
    from mailcpu.intention_sufficiency import FiniteGround,FiniteState,MeasurementCapability,plan_sufficiency,verify_sufficiency_plan,resolve_sufficiency,verify_sufficiency_resolution
    AVAILABLE=True
except ImportError:AVAILABLE=False

def sha(value):return hashlib.sha256(value.encode()).hexdigest()

class NativeECPU(unittest.TestCase):
    @unittest.skipUnless(AVAILABLE or os.getenv('PGT004_REQUIRE_NATIVE'), 'native E-CPU unavailable locally')
    def test_http_and_stdio_paths_have_distinct_embeddings_under_same_intention(self):
        if not AVAILABLE:raise AssertionError('native E-CPU package not installed in required gate')
        embed=IntentEmbedding(dimension=128)
        common={'intention':{'target_coordinate':6,'ground':sha('hypothesis-set-30')},'request':{'coordinate':1}}
        http=embed.encode({**common,'path':{'transport':'http','method':'GET','content_type':'application/vnd.ifs.signed-observation+json','host':'alpha'}})
        stdio=embed.encode({**common,'path':{'transport':'stdio','framing':'jsonl','host':'beta'}})
        self.assertNotEqual(http.digest,stdio.digest)
        self.assertEqual(http,embed.encode({**common,'path':{'transport':'http','method':'GET','content_type':'application/vnd.ifs.signed-observation+json','host':'alpha'}}))

    @unittest.skipUnless(AVAILABLE or os.getenv('PGT004_REQUIRE_NATIVE'),'native E-CPU unavailable locally')
    def test_exact_ground_planner_receives_only_restricted_observations(self):
        if not AVAILABLE:raise AssertionError('native E-CPU package not installed in required gate')
        # This is only a conditional finite-30-law Ground. No actual remote
        # source is established as a member of that language by this test.
        for target in (0,2,6,7):
            g=FiniteGround(sha('model'),sha('public'),sha('target'+str(target)),sha('context'),
                tuple(FiniteState.create(str(k).zfill(2),0,int(H[k,target]),{f'q{q}':int(H[k,q]) for q in range(8)}) for k in range(len(H))))
            offers=[MeasurementCapability(f'q{q}',sha('contract'+str(q)),'observer'+str(q),q+1) for q in range(8)]
            plan=plan_sufficiency(g,0,offers,sha('authority'))
            verify_sufficiency_plan(plan,g,0,offers,sha('authority'))
            self.assertEqual(plan['status'],'MEASURE')
            readings={key:int(H[17,int(key[1:])]) for key in plan['selected_features']}
            receipt=sha('separate-receiver-admitted-test-evidence')
            result=resolve_sufficiency(g,0,offers,sha('authority'),plan,readings,receipt)
            verify_sufficiency_resolution(result,g,0,offers,sha('authority'),plan,readings,receipt)
            self.assertEqual(result['result'],int(H[17,target]))
            # A capability catalogue that cannot distinguish target states refuses.
            none=plan_sufficiency(g,0,[],sha('authority'))
            self.assertEqual(none['status'],'REFUSE')

if __name__=='__main__':unittest.main()
