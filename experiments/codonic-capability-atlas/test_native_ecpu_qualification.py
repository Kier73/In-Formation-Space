"""COG-009 hosted *native* E-CPU SAB-003 gate, not mocked in CI."""
from __future__ import annotations
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

NATIVE=importlib.util.find_spec('mailcpu') is not None

@unittest.skipUnless(NATIVE,'native E-CPU package must be installed for this gate')
class NativeQualification(unittest.TestCase):
    def test_real_ecpu_qualifies_the_exact_cog009_worker(self):
        from mailcpu.runtime_qualification import (QualificationPolicy,SubprocessQualificationEndpoint,
                                                    ROLES,qualify,verify_report)
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            private=Ed25519PrivateKey.generate()
            key=tmp/'host-private.pem'
            key.write_bytes(private.private_bytes(serialization.Encoding.PEM,
                                                 serialization.PrivateFormat.PKCS8,
                                                 serialization.NoEncryption()))
            cmd=(sys.executable,'-u',str(Path(__file__).with_name('observer_worker.py')),
                 '--id','alpha','--key',str(key),'--subjects','4','--durations','2',
                 '--sab-once','--sab-store',str(tmp/'host_state.json'))
            host=SubprocessQualificationEndpoint('alpha',cmd,timeout=10)
            policy=QualificationPolicy(allowed_hosts=frozenset({'alpha'}),observer_id='cog009-receiver',
                                       expires_at=1000,permitted_roles=ROLES,max_calls=8)
            receipt=qualify(host,policy,coordinate=72,seed='COG009-independent-test-seed')
            self.assertTrue(verify_report(receipt,policy,coordinate=72))
            self.assertEqual(set(receipt.payload['verified_roles']),ROLES)
            self.assertFalse(receipt.payload['hardware_attested'])
            self.assertFalse(receipt.payload['local_hypervisor_permission_granted'])
            self.assertTrue((tmp/'host_state.json').exists())

if __name__=='__main__':unittest.main()
