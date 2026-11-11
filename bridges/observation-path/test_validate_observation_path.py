import json
import unittest
from pathlib import Path

from validate_observation_path import validate_path_record


HERE = Path(__file__).parent
SCHEMA = json.loads((HERE / "observation-path.schema.json").read_text(encoding="utf-8"))


class ObservationPathSchemaTests(unittest.TestCase):
    def test_example_record_passes_schema_and_lifecycle_validation(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        validate_path_record(record, SCHEMA)

    def test_status_must_match_final_event(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["status"] = "admitted"
        with self.assertRaises(ValueError):
            validate_path_record(record, SCHEMA)

    def test_terminal_flag_must_match_lifecycle_stage(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["terminal"] = False
        with self.assertRaises(ValueError):
            validate_path_record(record, SCHEMA)

    def test_invalid_transition_is_rejected(self):
        record = json.loads((HERE / "examples" / "happy-path.json").read_text(encoding="utf-8"))
        record["events"][3]["stage"] = "query_determined"
        with self.assertRaises(Exception):
            validate_path_record(record, SCHEMA)


if __name__ == "__main__":
    unittest.main()
