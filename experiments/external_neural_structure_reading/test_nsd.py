"""Offline conformance tests for the HFR-001 NSD observer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

try:
    from .nsd import MAX_HEADER_BYTES, NSDError, inspect_snapshot
except ImportError:  # unittest discovery with this directory as its top level
    from nsd import MAX_HEADER_BYTES, NSDError, inspect_snapshot


REVISION = "0123456789abcdef0123456789abcdef01234567"


def write_safetensors(path: Path, header: dict, body_size: int) -> None:
    raw = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    padding = (-len(raw)) % 8
    encoded_header = raw + (b" " * padding)
    path.write_bytes(
        len(encoded_header).to_bytes(8, "little")
        + encoded_header
        + (b"\0" * body_size)
    )


def make_snapshot(root: Path, *, weight_map: dict | None = None) -> None:
    (root / "config.json").write_text(
        json.dumps(
            {
                "architectures": ["TinyForCausalLM"],
                "model_type": "tiny-test",
                "hidden_size": 4,
                "num_hidden_layers": 1,
                "rope_theta": 10000.0,
            }
        ),
        encoding="utf-8",
    )
    first = "model-00001-of-00002.safetensors"
    second = "model-00002-of-00002.safetensors"
    write_safetensors(
        root / first,
        {
            "__metadata__": {"format": "pt"},
            "model.embed_tokens.weight": {
                "dtype": "F32",
                "shape": [2, 2],
                "data_offsets": [0, 16],
            },
        },
        16,
    )
    write_safetensors(
        root / second,
        {
            "model.layers.0.self_attn.q_proj.weight": {
                "dtype": "BF16",
                "shape": [2, 2],
                "data_offsets": [0, 8],
            }
        },
        8,
    )
    mapping = weight_map or {
        "model.embed_tokens.weight": first,
        "model.layers.0.self_attn.q_proj.weight": second,
    }
    (root / "model.safetensors.index.json").write_text(
        json.dumps({"metadata": {"total_size": 24}, "weight_map": mapping}),
        encoding="utf-8",
    )


class NSDObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        make_snapshot(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def inspect(self) -> dict:
        return inspect_snapshot(
            self.root,
            repository="example-org/tiny-model",
            revision=REVISION,
            license_id="apache-2.0",
        )

    def test_builds_valid_nsd_and_separates_observed_inferred_generated(self) -> None:
        description = self.inspect()
        self.assertEqual(description["schema"], "in-formation-space.neural-structure-description.v0.1")
        self.assertEqual(description["source"]["revision"], REVISION)
        self.assertEqual(description["source"]["license_id"], "apache-2.0")
        self.assertEqual(description["observed"]["configuration"]["model_type"], "tiny-test")
        self.assertEqual(description["inferred"]["tensor_count"], 2)
        self.assertEqual(description["inferred"]["shard_count"], 2)
        self.assertEqual(description["inferred"]["dtypes"], ["BF16", "F32"])
        self.assertIsNone(description["generated"]["architecture_graph"])
        self.assertEqual(description["generated"]["parameter_rules"], [])

        shard_records = [
            item for item in description["observed"]["files"]
            if item["role"] == "safetensors-shard"
        ]
        self.assertEqual(len(shard_records), 2)
        self.assertTrue(
            all(item["sha256_scope"] == "8-byte-prefix-and-header-only" for item in shard_records)
        )

        schema = json.loads(
            (Path(__file__).parent / "nsd.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(description)

    def test_unsharded_snapshot_without_index_is_supported(self) -> None:
        (self.root / "model.safetensors.index.json").unlink()
        (self.root / "model-00002-of-00002.safetensors").unlink()
        description = self.inspect()
        self.assertIsNone(description["observed"]["weight_map"])
        self.assertEqual(description["inferred"]["tensor_count"], 1)
        self.assertEqual(description["inferred"]["shard_count"], 1)

    def test_revision_must_be_an_immutable_commit_sha(self) -> None:
        with self.assertRaisesRegex(NSDError, "40-character"):
            inspect_snapshot(
                self.root,
                repository="example-org/tiny-model",
                revision="main",
            )

    def test_shard_paths_cannot_escape_snapshot(self) -> None:
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps(
                {
                    "weight_map": {
                        "tensor": "../../outside.safetensors"
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(NSDError, "unsafe snapshot-relative path"):
            self.inspect()

    def test_index_must_exactly_match_the_observed_tensor_inventory(self) -> None:
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps(
                {
                    "weight_map": {
                        "not.in.any.shard": "model-00001-of-00002.safetensors"
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(NSDError, "does not match shard headers"):
            self.inspect()

    def test_overlapping_tensor_data_ranges_are_rejected(self) -> None:
        shard = self.root / "model-00001-of-00002.safetensors"
        write_safetensors(
            shard,
            {
                "tensor.a": {"dtype": "F32", "shape": [4], "data_offsets": [0, 16]},
                "tensor.b": {"dtype": "F32", "shape": [2], "data_offsets": [8, 16]},
            },
            16,
        )
        with self.assertRaisesRegex(NSDError, "overlap"):
            self.inspect()

    def test_duplicate_json_keys_in_safetensors_header_are_rejected(self) -> None:
        raw = (
            b'{"duplicate":{"dtype":"F32","shape":[1],"data_offsets":[0,4]},'
            b'"duplicate":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}'
        )
        encoded_header = raw + (b" " * ((-len(raw)) % 8))
        shard = self.root / "model-00001-of-00002.safetensors"
        shard.write_bytes(
            len(encoded_header).to_bytes(8, "little") + encoded_header + (b"\0" * 4)
        )
        with self.assertRaisesRegex(NSDError, "duplicate JSON object key"):
            self.inspect()

    def test_header_size_is_bounded_before_reading_it(self) -> None:
        shard = self.root / "model-00001-of-00002.safetensors"
        declared = MAX_HEADER_BYTES + 1
        shard.write_bytes(declared.to_bytes(8, "little") + b"{}")
        with self.assertRaisesRegex(NSDError, "safety limit"):
            self.inspect()

    def test_weight_payload_is_not_misrepresented_as_hashed(self) -> None:
        before = self.inspect()
        shard = self.root / "model-00001-of-00002.safetensors"
        raw = bytearray(shard.read_bytes())
        raw[-1] ^= 0x01
        shard.write_bytes(raw)
        after = self.inspect()
        before_record = next(
            item for item in before["observed"]["files"]
            if item["path"] == shard.name
        )
        after_record = next(
            item for item in after["observed"]["files"]
            if item["path"] == shard.name
        )
        self.assertEqual(before_record["sha256"], after_record["sha256"])
        self.assertEqual(before_record["sha256_scope"], "8-byte-prefix-and-header-only")

    def test_symlinked_shard_is_rejected(self) -> None:
        target = self.root / "model-00001-of-00002.safetensors"
        linked = self.root / "linked.safetensors"
        linked.symlink_to(target)
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"model.embed_tokens.weight": linked.name}}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(NSDError, "symbolic link"):
            self.inspect()


if __name__ == "__main__":
    unittest.main()
