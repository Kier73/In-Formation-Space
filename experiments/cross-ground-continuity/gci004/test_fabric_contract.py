"""Runtime-free GCI-004 policy and receipt tamper controls."""
from __future__ import annotations

import base64
import datetime
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

import fabric_contract as c


def signed_fixture():
    now=datetime.datetime.now(datetime.timezone.utc)
    root_key=ec.generate_private_key(ec.SECP256R1())
    root_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'GCI004 test root')])
    root=(x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name)
       .public_key(root_key.public_key()).serial_number(x509.random_serial_number())
       .not_valid_before(now-datetime.timedelta(minutes=1))
       .not_valid_after(now+datetime.timedelta(days=1))
       .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
       .sign(root_key,hashes.SHA256()))
    key=ec.generate_private_key(ec.SECP256R1())
    dns=c.PEERS['observer-a'][1]
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,dns)])
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(root_name)
       .public_key(key.public_key()).serial_number(x509.random_serial_number())
       .not_valid_before(now-datetime.timedelta(minutes=1))
       .not_valid_after(now+datetime.timedelta(days=1))
       .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
       .add_extension(x509.SubjectAlternativeName([x509.DNSName(dns)]),critical=False)
       .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
       .sign(root_key,hashes.SHA256()))
    root_pem=root.public_bytes(serialization.Encoding.PEM).decode()
    leaf_pem=cert.public_bytes(serialization.Encoding.PEM).decode()
    return key,leaf_pem,root_pem


class FabricContractTests(unittest.TestCase):
    def test_leaf_certificate_signs_exact_observation_receipt(self):
        key,leaf,root=signed_fixture()
        cert=c.check_cert(leaf,root,c.PEERS['observer-a'][1])
        binding={'source_digest':'a'*64,'ground_fingerprint':'b'*64,
                 'orbit_certificate_fingerprint':'c'*64,'gci002_report_digest':'d'*64}
        public={'report_digest':'e'*64,'phase_commitment':'f'*64}
        plan={'report_digest':'1'*64}
        request=c.expected_request('far-y-parity','parity',public,plan,binding,'0'*32)
        payload=c.signed_payload(request,'observer-a','2'*64,1)
        sig=c.sign_receipt(key,payload)
        c.verify_receipt(cert,payload,sig)
        altered=dict(payload)
        altered['value']=0
        with self.assertRaises(Exception):
            c.verify_receipt(cert,altered,sig)
        altered=dict(payload)
        altered['request_digest']='3'*64
        with self.assertRaises(Exception):
            c.verify_receipt(cert,altered,sig)
        altered=dict(payload)
        altered['phase_commitment']='4'*64
        with self.assertRaises(Exception):
            c.verify_receipt(cert,altered,sig)

    def test_mismatched_dns_identity_refused(self):
        _key,leaf,root=signed_fixture()
        with self.assertRaises(c.gci3.SufficiencyRefused):
            c.check_cert(leaf,root,c.PEERS['observer-b'][1])

    def test_self_claimed_other_root_refused(self):
        _key,leaf,_root=signed_fixture()
        _other_key,_other_leaf,root=signed_fixture()
        with self.assertRaises(Exception):
            c.check_cert(leaf,root,c.PEERS['observer-a'][1])

    def test_receipt_wrong_signer_refused(self):
        key,leaf,root=signed_fixture()
        wrong=ec.generate_private_key(ec.SECP256R1())
        cert=c.check_cert(leaf,root,c.PEERS['observer-a'][1])
        receipt={'peer_id':'observer-a','value':1,'task_id':'far-y-parity'}
        with self.assertRaises(Exception):
            c.verify_receipt(cert,receipt,c.sign_receipt(wrong,receipt))

    def test_invalid_real_time_counters(self):
        for value in (True, -1, 1.25, 10**15):
            with self.subTest(value=value):
                with self.assertRaises(c.gci3.SufficiencyRefused):
                    c.require_positive_ns(value,'elapsed')
        c.require_positive_ns(0,'elapsed')
        c.require_positive_ns(138000,'elapsed')

    def test_exact_binding_changes_request_identity(self):
        binding={'source_digest':'a'*64,'ground_fingerprint':'b'*64,
                 'orbit_certificate_fingerprint':'c'*64,'gci002_report_digest':'d'*64}
        public={'report_digest':'e'*64,'phase_commitment':'f'*64}
        plan={'report_digest':'1'*64}
        first=c.expected_request('far-y-parity','parity',public,plan,binding,'0'*32)
        second=c.expected_request('far-y-parity','parity',public,plan,binding,'2'*32)
        self.assertNotEqual(c.jdigest(first),c.jdigest(second))
        self.assertNotEqual(c.jdigest(c.signed_payload(first,'observer-a','3'*64,1)),
                            c.jdigest(c.signed_payload(second,'observer-a','3'*64,1)))

    def test_payload_byte_size_is_canonical_deterministic(self):
        self.assertEqual(c.payload_bytes({'b':2,'a':1}),
                         c.payload_bytes({'a':1,'b':2}))


if __name__=='__main__':
    unittest.main()
