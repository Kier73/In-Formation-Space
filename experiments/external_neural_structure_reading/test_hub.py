"""Offline range-protocol tests for the HFR-001 Hub observer."""

from __future__ import annotations

import json
import re
import unittest
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

try:
    from .hub import NSDError, inspect_huggingface_model
except ImportError:
    from hub import NSDError, inspect_huggingface_model


REVISION = "0123456789abcdef0123456789abcdef01234567"


def safetensors_bytes(name: str, *, dtype: str = "F32", values: int = 2) -> bytes:
    body_size = values * (4 if dtype == "F32" else 2)
    header = {
        name: {
            "dtype": dtype,
            "shape": [values],
            "data_offsets": [0, body_size],
        }
    }
    raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
    raw += b" " * ((-len(raw)) % 8)
    return len(raw).to_bytes(8, "little") + raw + (b"\0" * body_size)


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, headers=None, url: str):
        self.body = body
        self.status = status
        self.headers = headers or {}
        self.url = url
        self.read_sizes: list[int | None] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def read(self, amount: int | None = None) -> bytes:
        self.read_sizes.append(amount)
        return self.body if amount is None else self.body[:amount]


class FakeHub:
    def __init__(
        self,
        files: dict[str, bytes],
        *,
        revision: str = REVISION,
        weight_map: dict[str, str] | None = None,
        ignore_range: bool = False,
        wrong_content_range: bool = False,
    ):
        self.files = files
        self.revision = revision
        self.weight_map = weight_map
        self.ignore_range = ignore_range
        self.wrong_content_range = wrong_content_range
        self.requests: list[dict] = []
        self.responses: list[FakeResponse] = []

    def __call__(self, request, timeout=20):
        url = request.full_url
        parsed = urlparse(url)
        range_header = request.get_header("Range")
        self.requests.append(
            {"url": url, "path": parsed.path, "range": range_header, "timeout": timeout}
        )

        if parsed.path.endswith(f"/api/models/example-org/tiny-model/revision/{REVISION}"):
            if self.weight_map is not None:
                self.files["model.safetensors.index.json"] = json.dumps(
                    {"weight_map": self.weight_map}
                ).encode("utf-8")
            siblings = [{"rfilename": "config.json"}]
            siblings.extend({"rfilename": name} for name in self.files)
            payload = {"sha": self.revision, "siblings": siblings}
            body = json.dumps(payload).encode("utf-8")
            response = FakeResponse(
                body,
                headers={"Content-Length": str(len(body))},
                url=url,
            )
        elif parsed.path.endswith("/resolve/" + REVISION + "/config.json"):
            body = json.dumps(
                {"model_type": "tiny-test", "hidden_size": 4, "num_hidden_layers": 1}
            ).encode("utf-8")
            response = FakeResponse(
                body, headers={"Content-Length": str(len(body))}, url=url
            )
        elif parsed.path.endswith("/resolve/" + REVISION + "/model.safetensors.index.json"):
            body = self.files["model.safetensors.index.json"]
            response = FakeResponse(
                body, headers={"Content-Length": str(len(body))}, url=url
            )
        else:
            shard_name = parsed.path.rsplit("/", 1)[-1]
            if shard_name not in self.files:
                raise AssertionError(f"unexpected Hub request: {url}")
            data = self.files[shard_name]
            if range_header is None:
                raise AssertionError("Safetensors shard was requested without Range")
            match = re.fullmatch(r"bytes=(\d+)-(\d+)", range_header)
            if match is None:
                raise AssertionError(f"malformed Range header: {range_header}")
            start, end = map(int, match.groups())
            if self.ignore_range:
                response = FakeResponse(
                    data,
                    status=200,
                    headers={"Content-Length": str(len(data))},
                    url=url,
                )
            else:
                body = data[start : end + 1]
                content_range = f"bytes {start}-{end}/{len(data)}"
                if self.wrong_content_range:
                    content_range = f"bytes {start + 1}-{end + 1}/{len(data)}"
                response = FakeResponse(
                    body,
                    status=206,
                    headers={
                        "Content-Range": content_range,
                        "Content-Length": str(len(body)),
                    },
                    url=url,
                )
        self.responses.append(response)
        return response


class HubRangeObserverTests(unittest.TestCase):
    def make_observer(self, opener: FakeHub):
        return inspect_huggingface_model(
            "example-org/tiny-model",
            REVISION,
            license_id="apache-2.0",
            opener=opener,
        )

    def test_public_single_file_model_reads_only_prefix_and_header(self):
        shard = safetensors_bytes("transformer.wte.weight", values=2)
        fake = FakeHub({"model.safetensors": shard})
        result = self.make_observer(fake)

        self.assertEqual(result["source"]["repository"], "example-org/tiny-model")
        self.assertEqual(result["source"]["revision"], REVISION)
        self.assertEqual(result["observed"]["configuration"]["model_type"], "tiny-test")
        self.assertEqual(result["inferred"]["tensor_count"], 1)
        self.assertEqual(result["observed"]["tensor_manifest"][0]["name"], "transformer.wte.weight")
        self.assertEqual(
            [item["range"] for item in fake.requests if item["range"]],
            ["bytes=0-7", f"bytes=8-{7 + int.from_bytes(shard[:8], 'little')}"],
        )

        schema_path = __import__("pathlib").Path(__file__).parent / "nsd.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(result)

    def test_sharded_model_index_is_checked_against_each_header(self):
        shard_a = "model-00001-of-00002.safetensors"
        shard_b = "model-00002-of-00002.safetensors"
        fake = FakeHub(
            {
                shard_a: safetensors_bytes("model.embed_tokens.weight", values=2),
                shard_b: safetensors_bytes("model.layers.0.q_proj.weight", dtype="BF16", values=2),
            },
            weight_map={
                "model.embed_tokens.weight": shard_a,
                "model.layers.0.q_proj.weight": shard_b,
            },
        )
        result = self.make_observer(fake)
        self.assertEqual(result["inferred"]["tensor_count"], 2)
        self.assertEqual(result["inferred"]["shard_count"], 2)
        self.assertEqual(len(result["observed"]["weight_map"]), 2)
        range_requests = [item for item in fake.requests if item["range"]]
        self.assertEqual(len(range_requests), 4)
        self.assertTrue(all("model-0000" in item["path"] for item in range_requests))

    def test_hub_must_resolve_the_exact_requested_revision(self):
        fake = FakeHub({"model.safetensors": safetensors_bytes("x")}, revision="f" * 40)
        with self.assertRaisesRegex(NSDError, "did not resolve"):
            self.make_observer(fake)
        self.assertFalse(any(item["range"] for item in fake.requests))

    def test_server_that_ignores_range_is_rejected_before_body_read(self):
        fake = FakeHub(
            {"model.safetensors": safetensors_bytes("x")},
            ignore_range=True,
        )
        with self.assertRaisesRegex(NSDError, "was not honored"):
            self.make_observer(fake)
        shard_responses = [
            response for response in fake.responses
            if response.status == 200 and response.url.endswith("model.safetensors")
        ]
        self.assertEqual(len(shard_responses), 1)
        self.assertEqual(shard_responses[0].read_sizes, [])

    def test_inaccurate_content_range_is_rejected(self):
        fake = FakeHub(
            {"model.safetensors": safetensors_bytes("x")},
            wrong_content_range=True,
        )
        with self.assertRaisesRegex(NSDError, "does not match"):
            self.make_observer(fake)

    def test_invalid_repository_and_mutable_revision_are_rejected_before_network(self):
        fake = FakeHub({"model.safetensors": safetensors_bytes("x")})
        with self.assertRaisesRegex(NSDError, "owner/name"):
            inspect_huggingface_model("../tiny-model", REVISION, opener=fake)
        with self.assertRaisesRegex(NSDError, "immutable"):
            inspect_huggingface_model("example-org/tiny-model", "main", opener=fake)
        self.assertEqual(fake.requests, [])


if __name__ == "__main__":
    unittest.main()
