from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bridges" / "observation-path"))
sys.path.insert(0, str(ROOT / "experiments" / "portable-realization-capsule"))

from formats.canonical_metadata_v1 import (  # noqa: E402
    CanonicalMetadataError,
    canonical_bytes,
    decode_canonical_document,
)
from diverse_host_verifier import canonical_bytes as ihp_canonical_bytes  # noqa: E402
from portable_realization import _canonical as prc_canonical_bytes  # noqa: E402


def _artifact(vector: dict) -> bytes:
    raw = vector["input_json"].encode("utf-8")
    if vector.get("prefix_bom"):
        raw = b"\xef\xbb\xbf" + raw
    ending = vector["line_ending"]
    if ending == "lf":
        return raw + b"\n"
    if ending == "double_lf":
        return raw + b"\n\n"
    if ending == "crlf":
        return raw + b"\r\n"
    if ending == "none":
        return raw
    raise AssertionError(f"unknown line ending: {ending}")


class CanonicalMetadataV1Vectors(unittest.TestCase):
    def test_shared_acceptance_and_exact_digest_vectors(self):
        corpus_path = ROOT / "formats" / "canonical-metadata-v1" / "vectors.json"
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        self.assertEqual(corpus["schema"], "in-formation.canonical-metadata-conformance-vectors/1")
        self.assertEqual(corpus["profile"], "canonical-metadata-v1")

        for vector in corpus["vectors"]:
            with self.subTest(vector=vector["id"]):
                raw = _artifact(vector)
                if vector["accept"]:
                    document = decode_canonical_document(raw)
                    expected = vector["input_json"].encode("utf-8")
                    self.assertEqual(canonical_bytes(document), expected)
                    self.assertEqual(ihp_canonical_bytes(document), expected)
                    self.assertEqual(prc_canonical_bytes(document), expected)
                    expected_digest = vector["canonical_sha256"]
                    self.assertEqual(hashlib.sha256(expected).hexdigest(), expected_digest)
                    self.assertEqual(hashlib.sha256(canonical_bytes(document)).hexdigest(), expected_digest)
                else:
                    with self.assertRaises(CanonicalMetadataError):
                        decode_canonical_document(raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
