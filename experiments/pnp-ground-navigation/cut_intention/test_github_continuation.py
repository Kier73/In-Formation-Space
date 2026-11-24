"""CIG-029: native SAB and artifact chain adversarial controls."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import github_continuation as gh
from mailcpu.substrate_bootstrap import digest, BootstrapRefused


class GitHubContinuationTests(unittest.TestCase):
    def test_native_chain_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(gh,'SIZES',(24,)):
            root=Path(tmp)
            # No job outputs may be published by this local unit test.
            with patch.dict(os.environ,{'GITHUB_OUTPUT':''}):
                expected=None;prior=None
                for stage in range(3):
                    target=root/f'{stage}.json'
                    gh.run(stage,prior,expected,target)
                    expected=gh.raw_digest(target.read_bytes());prior=target
            bundle=gh.read_bundle(prior,expected)
            records=bundle['grounds'][0]['records']
            g=gh.Ground(24)
            p,_,_,a=gh.replay(g,records)
            self.assertEqual(p.time,g.expected(2))
            self.assertEqual(a.host,gh.HOSTS[2])
            self.assertEqual([r['report']['output']['move']['bits'] for r in records],
                             [21,15,15])
            with self.assertRaises(ValueError):gh.read_bundle(prior,'0'*64)
            # A correct artifact hash is insufficient if its semantic claim is false.
            bad=copy.deepcopy(records)
            bad[2]['report']['output']['move']['rank']='0'
            bad[2]['report']['output_digest']=digest(bad[2]['report']['output'])
            bad[2]['report']['receipts'][-1]['output_digest']=bad[2]['report']['output_digest']
            bad[2]['report']['report_digest']=digest({k:v for k,v in bad[2]['report'].items() if k!='report_digest'})
            with self.assertRaises((ValueError,BootstrapRefused)):gh.replay(g,bad)
            bad=copy.deepcopy(records);bad[2]['parent']='0'*64
            with self.assertRaises(ValueError):gh.replay(g,bad)
            bad=copy.deepcopy(records);bad[1]['checkpoint']['state']['rank']='0'
            with self.assertRaises(ValueError):gh.replay(g,bad)

    def test_native_binding_and_future_schedule(self):
        g=gh.Ground(24);p,_,producer,admission=g.fresh()
        report=gh.bootstrap(g,0,p,producer,admission,gh.provenance())
        self.assertEqual(report['receiver_oracle_checked_steps'],1)
        self.assertEqual(report['execution_authority'],'receiver-local-allowlist-and-handler-binding')
        report=gh.bootstrap(g,1,p,producer,admission,gh.provenance())
        old=g.revise(producer,admission)
        self.assertFalse(admission.verify(0,4,1,old))
        self.assertEqual(p.time,3)
        report=gh.bootstrap(g,2,p,producer,admission,gh.provenance())
        self.assertEqual(int(report['output']['query']['time']),g.expected(2))
        self.assertEqual(p.key,admission.capacity.image.key)


if __name__=='__main__':unittest.main()
