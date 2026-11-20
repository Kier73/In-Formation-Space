"""Negative admission controls for the frozen real-source qualification driver."""
import base64
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import unittest

PATH = Path(__file__).with_name("qualify_archived_tpp.py")
spec = importlib.util.spec_from_file_location("tpp_sgn_qualifier", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class QualificationTests(unittest.TestCase):
    def test_refuses_mismatched_schema_without_model_fitting(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            module.archived_series({"schema": "forged", "documents": []})

    def test_refuses_absent_provider_data(self):
        with self.assertRaisesRegex(ValueError, "missing source"):
            module.archived_series({"schema": module.SOURCE_SCHEMA,
                                    "assessment": {"status": "complete"},
                                    "documents": []})

    def test_refuses_rehashed_but_nonoriginal_body(self):
        body = b'{"predictions":[]}'
        manifest = {
            "schema": module.SOURCE_SCHEMA,
            "assessment": {"status": "complete"},
            "documents": [{
                "product": "predictions",
                "raw_body_base64": base64.b64encode(body).decode(),
                "raw_sha256": sha256(body).hexdigest(),
                "raw_bytes": len(body),
            }],
        }
        with self.assertRaisesRegex(ValueError, "pinned evidence"):
            module.archived_series(manifest)

    def test_chronology_fixed_before_observations(self):
        self.assertEqual((module.TRAIN, module.VALID, module.TEST), (720, 480, 480))
        self.assertEqual(sum((module.TRAIN, module.VALID, module.TEST)), 1680)


if __name__ == "__main__":
    unittest.main()
