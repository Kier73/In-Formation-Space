"""Hard-required hosted native E-CPU cross-process mTLS integration tests."""
from __future__ import annotations
import copy,json,os,tempfile,unittest
from pathlib import Path

try:
    from mailcpu.intention_measurement_fabric import MeasurementPeerClient
    from native_contract import model_at,probe_contract,exact_target_status,authority_for
    import run_native_transit as native
    NATIVE_AVAILABLE=True
except ImportError:
    NATIVE_AVAILABLE=False


def require_native(fn):
    def run(self):
        if not NATIVE_AVAILABLE:
            if os.environ.get('PGT005_REQUIRE_NATIVE'):
                self.fail('native E-CPU missing from strict integration environment')
            self.skipTest('E-CPU not installed locally; strict CI must run')
        return fn(self)
    return run


class NativeAuthorityIntegration(unittest.TestCase):
    @require_native
    def test_ios001_probe_contract_replans_and_unavailable_features_refuse(self):
        from mailcpu.intention_sufficiency import plan_sufficiency
        root='a'*64
        for q in range(8):
            model,offers,plan,contracts=probe_contract(q,root)
            self.assertEqual(plan['selected_features'],['q'+str(q)])
            self.assertEqual(plan['status'],'MEASURE')
            blocked=plan_sufficiency(model,0,(),authority_for(root))
            self.assertEqual(blocked['status'],'REFUSE')
        self.assertEqual(exact_target_status(6,{},root)['status'],'REFUSE')

    @require_native
    def test_live_native_mtls_remote_provider_and_signed_http_stdio_offline(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            outcome=native.run(root,index=12,target=6)
            self.assertEqual(outcome['receiver_result']['terminal_status'],'WITNESSED_NOT_GROUND_ADMITTED')
            self.assertEqual(outcome['receiver_result']['result'],0)
            self.assertGreater(outcome['native_receipt_count'],0)
            self.assertGreater(outcome['signature_count'],outcome['native_receipt_count'])
            self.assertGreater(outcome['http_signed_reads'],0)
            self.assertGreater(outcome['stdio_signed_reads'],0)
            self.assertFalse(outcome['ground_admitted'])
            again=native.verify(root,outcome['high_water_head'],outcome['source_root'])
            self.assertEqual(again['source_calls'],0)
            with self.assertRaises(ValueError):native.verify(root,'0'*64,outcome['source_root'])
            # Outer sidecar rehash cannot forge native/signed source claims.
            path=root/'evidence/bundle.json'
            doc=json.loads(path.read_bytes())
            doc['events'][0]['frame_sha256']='0'*64
            import cognitive_grounds
            doc['digest']=cognitive_grounds.digest({k:v for k,v in doc.items() if k!='digest'})
            path.write_bytes(cognitive_grounds.canonical(doc))
            with self.assertRaises(ValueError):native.verify(root,outcome['high_water_head'],outcome['source_root'])

    @require_native
    def test_native_refusal_under_dissent_and_recovery_without_replaying_accepted_source(self):
        with tempfile.TemporaryDirectory() as td:
            outcome=native.run(Path(td),index=12,target=6,fault=2)
            self.assertEqual(outcome['native_provider']['injected_dissent'],1)
            self.assertEqual(outcome['native_provider']['restarted_observers'],1)
            refusals=outcome['receiver_result']['refusals']
            self.assertTrue(refusals,refusals)
            self.assertTrue(any(x['outcome']=='REFUSED' for x in refusals))
            self.assertEqual(outcome['receiver_result']['result'],0)
            self.assertEqual(outcome['receiver_result']['terminal_status'],'WITNESSED_NOT_GROUND_ADMITTED')
            self.assertGreater(outcome['native_provider']['signed_receipts'],0)

    @require_native
    def test_out_of_family_false_candidate_cannot_be_admitted(self):
        # This 8-bit source is absent from the 30-law candidate language.
        # In the local model-alone rollout its target candidate is 1,
        # while a direct source measurement is 0.
        with tempfile.TemporaryDirectory() as td:
            outcome=native.run(Path(td),target=6,source_bits='00101000')
            r=outcome['receiver_result']
            self.assertEqual(r['result'],0)
            self.assertFalse(r['language_source_proven'])
            self.assertEqual(r['terminal_status'],'WITNESSED_NOT_GROUND_ADMITTED')
            if r['candidate_before_direct'] is not None:
                self.assertNotEqual(r['candidate_before_direct'],r['result'])

if __name__=='__main__':unittest.main()
