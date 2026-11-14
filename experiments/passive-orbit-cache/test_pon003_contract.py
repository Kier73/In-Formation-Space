"""PON-003: raw CID, independent publications, tamper and authority contracts."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from passive_orbit import ROOT_PIN, canonical, digest, PassiveRejected
from pon003_origin import (
    raw_cid, check_raw_cid, publisher_source, inventory, sign_publication,
    verify_publication, pubkey, produce, MAX_AGE_S
)
from pon003_navigate import Origin, Fetcher, reconstruct
from pon003_serve import launch

TIME = 2_000_000_000


def signed_origins():
    data = publisher_source()
    keys = {k: Ed25519PrivateKey.generate() for k in ("r2", "ipfs")}
    docs = {
        k: sign_publication(signer=keys[k], kind=k, objects=data,
                            epoch=4, now=TIME) for k in keys
    }
    pins = {k: pubkey(v) for k, v in keys.items()}
    return docs, pins


class PON003(unittest.TestCase):
    def test_raw_sha256_cid_is_spec_cidv1_raw_hello(self):
        sha = digest(b"hello")
        self.assertEqual(raw_cid(sha),
            "bafkreibm6jg3ux5qumhcn2b3flc3tyu6dmlb4xa7u5bf44yegnrjhc4yeq")
        check_raw_cid(raw_cid(sha), sha)
        with self.assertRaises(PassiveRejected):
            check_raw_cid(raw_cid(sha), "1" * 64)

    def test_independent_keys_sign_same_exact_object_set(self):
        docs, pins = signed_origins()
        self.assertNotEqual(pins["r2"], pins["ipfs"])
        entries = [
            verify_publication(receipt=docs[k], trusted_public_key=pins[k],
                               expected_kind=k, root_pin=ROOT_PIN, floor=4,
                               now=TIME) for k in ("r2", "ipfs")
        ]
        self.assertEqual(entries[0], entries[1])
        self.assertEqual(len(entries[0]), 6)
        self.assertEqual(entries[0]["root"]["sha256"], ROOT_PIN)

    def test_signature_tampering_wrong_key_and_wrong_source_rejected(self):
        docs, pins = signed_origins()
        bad_key = pubkey(Ed25519PrivateKey.generate())
        for kind, key, root in (
            ("r2", bad_key, ROOT_PIN),
            ("ipfs", pins["r2"], ROOT_PIN),
            ("r2", pins["r2"], "0"*64),
        ):
            with self.subTest(kind=kind,root=root), self.assertRaises(PassiveRejected):
                verify_publication(receipt=docs[kind], trusted_public_key=key,
                                   expected_kind=kind, root_pin=root,
                                   floor=4, now=TIME)
        bad = deepcopy(docs["r2"])
        bad["object_inventory"][0]["sha256"] = "f"*64
        with self.assertRaises(PassiveRejected):
            verify_publication(receipt=bad, trusted_public_key=pins["r2"],
                               expected_kind="r2", root_pin=ROOT_PIN,
                               floor=4, now=TIME)

    def test_stale_future_and_revoked_epoch_fail_closed(self):
        docs, pins = signed_origins()
        for floor, now in ((5, TIME), (4, TIME - 1), (4, TIME + MAX_AGE_S + 1)):
            with self.subTest(floor=floor,now=now), self.assertRaises(PassiveRejected):
                verify_publication(receipt=docs["r2"],
                    trusted_public_key=pins["r2"], expected_kind="r2",
                    root_pin=ROOT_PIN, floor=floor, now=now)

    def test_cannot_turn_read_only_receipt_into_effect_authority(self):
        docs, pins = signed_origins()
        forged = deepcopy(docs["ipfs"])
        forged["scope"] = "execute-programs"
        with self.assertRaises(PassiveRejected):
            verify_publication(receipt=forged,
                trusted_public_key=pins["ipfs"],
                expected_kind="ipfs", root_pin=ROOT_PIN, floor=4, now=TIME)

    def test_distinct_key_pins_required_before_any_retrieval(self):
        docs, pins = signed_origins()
        from pon003_navigate import Origin
        origins = [Origin("r2", "http://127.0.0.1:12001/"),
                   Origin("ipfs", "http://127.0.0.1:12002/")]
        for failed in (
            {"r2": pins["r2"], "ipfs": pins["r2"]},
            {"r2": pins["r2"]},
        ):
            with self.assertRaises(PassiveRejected):
                reconstruct(origins=origins, receipts=docs, pinned_keys=failed,
                            epoch_floor={"r2": 4, "ipfs": 4}, now=TIME)

    def test_public_endpoints_are_explicitly_restricted(self):
        self.assertTrue(Origin("r2", "https://example-bucket.r2.dev/", True).public)
        self.assertTrue(Origin("ipfs", "https://ipfs.io/", True).public)
        for kind, base in (
            ("r2","http://example-bucket.r2.dev/"),
            ("r2","https://evil.invalid/"),
            ("r2","https://example-bucket.r2.dev/objects/"),
            ("ipfs","https://bad-gateway.invalid/"),
            ("ipfs","https://ipfs.io@evil.invalid/"),
            ("ipfs","http://127.0.0.1:8989/"),
        ):
            with self.subTest(base=base), self.assertRaises(PassiveRejected):
                Origin(kind, base, True)

    def test_canonical_ipfs_and_https_object_urls_do_not_mix_paths(self):
        address = inventory(publisher_source())[0]
        r2 = Origin("r2","https://my-bucket.r2.dev/",True)
        ipfs = Origin("ipfs","https://ipfs.io/",True)
        self.assertEqual(r2.object_url(address),
                         "https://my-bucket.r2.dev/manifest.json")
        self.assertEqual(ipfs.object_url(address),
                         "https://ipfs.io/ipfs/" + address["raw_cid"] + "?format=raw")

    def test_two_read_only_http_origins_recover_same_verified_result(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            produce(kind="r2", output=root / "r2", epoch=4, now=TIME)
            produce(kind="ipfs", output=root / "ipfs", epoch=4, now=TIME)
            servers = [launch(root / kind, kind) for kind in ("r2","ipfs")]
            workers = [threading.Thread(target=s.serve_forever,daemon=True)
                       for s in servers]
            for t in workers:
                t.start()
            try:
                receipts = {
                    k: json.loads((root / k / "receipt.json").read_bytes())
                    for k in ("r2","ipfs")
                }
                pins = {
                    k: bytes.fromhex((root / k / "public-key.hex").read_text().strip())
                    for k in ("r2","ipfs")
                }
                routes = [Origin(kind, "http://127.0.0.1:"+
                                 str(server.server_port)+"/")
                          for kind,server in zip(("r2","ipfs"),servers)]
                first = reconstruct(origins=routes, receipts=receipts,
                                    pinned_keys=pins,
                                    epoch_floor={"r2":4,"ipfs":4},now=TIME)
                second = reconstruct(origins=routes[::-1], receipts=receipts,
                                     pinned_keys=pins,
                                     epoch_floor={"r2":4,"ipfs":4},now=TIME)
                self.assertEqual((first["value"],second["value"]),(44,44))
                self.assertEqual(first["result_digest"],second["result_digest"])
                self.assertEqual(set(first["selected_origins"].values()),{"r2"})
                self.assertEqual(set(second["selected_origins"].values()),{"ipfs"})
                self.assertFalse(first["origins_are_public"])
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(routes[0].base_url+"manifest.json",
                                    method="POST",data=b"x"),timeout=3)
                self.assertEqual(error.exception.code,405)
            finally:
                for server in servers: server.shutdown()
                for server in servers: server.server_close()
                for t in workers: t.join(timeout=3)

    def test_both_origins_unavailable_is_unresolved_not_a_cached_result(self):
        docs,pins=signed_origins()
        result=reconstruct(origins=[
             Origin("r2","http://127.0.0.1:9/"),
             Origin("ipfs","http://127.0.0.1:10/")],
             receipts=docs,pinned_keys=pins,
             epoch_floor={"r2":4,"ipfs":4},now=TIME)
        self.assertEqual(result["status"],"unresolved")
        self.assertEqual(result["missing"],["root"])
        self.assertIsNone(result["value"])

    def test_source_manifest_must_be_canonical_receiver_pinned(self):
        source=publisher_source()
        self.assertEqual(digest(source["manifest.json"]),ROOT_PIN)
        fake=deepcopy(source)
        fake["manifest.json"]=b'{"target":"seed"}'
        with self.assertRaises(PassiveRejected):
            inventory(fake)

    def test_raw_cid_host_only_accepts_exact_block_paths(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            produce(kind="ipfs",output=root,epoch=2,now=TIME)
            server=launch(root,"ipfs")
            th=threading.Thread(target=server.serve_forever,daemon=True)
            th.start()
            try:
                for path in ("/objects/hello", "/ipfs/QmUnknown?format=raw",
                             "/ipfs/bad?format=raw", "/ipfs/../../etc/passwd"):
                    with self.subTest(path=path),self.assertRaises(HTTPError):
                        urlopen("http://127.0.0.1:"+str(server.server_port)+path,
                                timeout=3)
            finally:
                server.shutdown()
                server.server_close()
                th.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
