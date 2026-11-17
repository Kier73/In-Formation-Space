"""No-native tests: learned recommendation, signed path, and TLS fixture isolation."""
from __future__ import annotations
import hashlib, json, tempfile, unittest
from pathlib import Path
import numpy as np
from decision_experiment import H,ALL,context,Context,indices,split,terminal
from train_policy import restore,propose
from run_path_navigation import create_peers,save_bundle
from path_navigator import MixedPathGround,recover_paths
from run_native_transit import make_certs
from cryptography import x509

WEIGHTS=Path(__import__('train_policy').__file__).resolve().parent/'results'

class ProtocolStructure(unittest.TestCase):
    def test_learned_query_requires_no_hidden_source_value_to_choose(self):
        model,manifest=restore(WEIGHTS)
        rng=np.random.default_rng(9)
        rng.integers(len(H))
        ctx=context(rng)
        proposed=propose(model,ctx,ALL,0)
        self.assertEqual(proposed,2)
        self.assertEqual(ctx.target,6)
        # The query cannot itself be represented as mathematical admission.
        self.assertNotEqual(proposed,ctx.target)

    def test_source_outside_hypothesis_family_has_false_conditional_candidate(self):
        model,_=restore(WEIGHTS)
        rng=np.random.default_rng(9);rng.integers(len(H));ctx=context(rng)
        actual=tuple(int(ch) for ch in '00101000')
        self.assertNotIn(actual,{tuple(int(x) for x in row) for row in H})
        mask=ALL;used=0;queried=[]
        for _ in range(6):
            if not mask or terminal(ctx,mask):break
            q=propose(model,ctx,mask,used)
            if q is None:break
            queried.append(q);mask=split(mask,q)[actual[q]];used|=1<<q
        self.assertTrue(terminal(ctx,mask))
        self.assertNotIn(ctx.target,queried)
        candidate=int(H[indices(mask)[0],ctx.target])
        self.assertNotEqual(candidate,actual[ctx.target])

    def test_actual_http_and_stdio_queries_retained_and_independently_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source,peers=create_peers(root,H[12].tolist())
            for p in peers:p.start()
            try:
                ground=MixedPathGround(source['root'],peers)
                for q in (2,6):self.assertEqual(ground.read(q),int(H[12,q]))
                doc,trust=save_bundle(ground,root/'witnesses')
                checked=recover_paths(doc,trust)
                self.assertEqual(checked['qualified_observations'],ground.observed)
                self.assertGreater(checked['http_reads'],0)
                self.assertGreater(checked['stdio_reads'],0)
                self.assertFalse(checked['admitted'])
            finally:
                for p in peers:p.stop(kill=True)

    def test_generated_tls_certs_distinguish_real_ca_and_two_dns_peer_identities(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td);make_certs(path)
            ca=x509.load_pem_x509_certificate((path/'ca.pem').read_bytes())
            provider=x509.load_pem_x509_certificate((path/'provider.pem').read_bytes())
            receiver=x509.load_pem_x509_certificate((path/'receiver.pem').read_bytes())
            self.assertNotEqual(provider.serial_number,receiver.serial_number)
            self.assertEqual(provider.issuer,ca.subject)
            self.assertEqual(receiver.issuer,ca.subject)
            pnames=provider.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
            rnames=receiver.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
            self.assertEqual(pnames,['provider-b.fabric.test'])
            self.assertEqual(rnames,['receiver-a.fabric.test'])
            self.assertFalse((path/'ca.key').exists())

if __name__=='__main__':unittest.main()
