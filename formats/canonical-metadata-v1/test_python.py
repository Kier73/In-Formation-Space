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
    PROFILE_ID,
    canonical_bytes,
    decode_canonical_document,
)
from diverse_host_verifier import (  # noqa: E402
    DiverseVerificationError,
    canonical_bytes as ihp_canonical_bytes,
)
from portable_realization import (  # noqa: E402
    PortableRealizationError,
    _canonical as prc_canonical_bytes,
)


CORPUS_PATH = ROOT / "formats" / "canonical-metadata-v1" / "test-vectors.json"


def load_corpus() -> dict:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    if corpus.get("profile") != PROFILE_ID:
        raise AssertionError("unexpected canonical metadata corpus profile")
    return corpus


class CanonicalMetadataV1Tests(unittest.TestCase):
    def test_valid_vectors_match_all_python_call_sites_and_sha256(self):
        corpus = load_corpus()
        for vector in corpus["valid"]:
            with self.subTest(vector=vector["name"]):
                value = json.loads(vector["input_json"])
                expected = vector["canonical_utf8"].encode("utf-8")
                self.assertEqual(canonical_bytes(value), expected)
                self.assertEqual(ihp_canonical_bytes(value), expected)
                self.assertEqual(prc_canonical_bytes(value), expected)
                self.assertEqual(hashlib.sha256(expected).hexdigest(), vector["sha256"])

    def test_invalid_values_are_rejected_by_all_python_call_sites(self):
        corpus = load_corpus()
        for vector in corpus["invalid_values"]:
            with self.subTest(vector=vector["name"]):
                value = json.loads(vector["input_json"])
                with self.assertRaises(CanonicalMetadataError):
                    canonical_bytes(value)
                with self.assertRaises(DiverseVerificationError):
                    ihp_canonical_bytes(value)
                with self.assertRaises(PortableRealizationError):
                    prc_canonical_bytes(value)

    def test_noncanonical_documents_do_not_become_identical_to_source_bytes(self):
        corpus = load_corpus()
        for vector in corpus["noncanonical_documents"]:
            with self.subTest(vector=vector["name"]):
                value = json.loads(vector["input_json"])
                try:
                    actual = canonical_bytes(value)
                except CanonicalMetadataError:
                    # Numeric lexical forms may be rejected before byte comparison.
                    continue
                self.assertEqual(actual, vector["canonical_utf8"].encode("utf-8"))
                self.assertNotEqual(actual, vector["input_json"].encode("utf-8"))

    def test_artifact_reader_requires_one_lf_and_rejects_duplicate_keys(self):
        corpus = load_corpus()
        first = corpus["valid"][0]
        canonical = first["canonical_utf8"].encode("utf-8")
        self.assertEqual(decode_canonical_document(canonical + b"\n"), json.loads(canonical))

        invalid_artifacts = (
            canonical,
            canonical + b"\n\n",
            canonical + b"\r\n",
            b"\xef\xbb\xbf" + canonical + b"\n",
            b'{"value":1,"value":2}\n',
        )
        for raw in invalid_artifacts:
            with self.subTest(raw=raw):
                with self.assertRaises(CanonicalMetadataError):
                    decode_canonical_document(raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
