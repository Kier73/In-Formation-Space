"""Run HFR-001 against a pinned public GPT-2 Hub revision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..hub import inspect_huggingface_model

REPOSITORY = "openai-community/gpt2"
REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"
LICENSE_ID = "mit"


def run(output: Path) -> dict:
    description = inspect_huggingface_model(
        REPOSITORY,
        REVISION,
        license_id=LICENSE_ID,
    )
    configuration = description["observed"]["configuration"]
    if configuration.get("model_type") != "gpt2":
        raise AssertionError(
            f"pinned reference expected model_type='gpt2', got {configuration.get('model_type')!r}"
        )
    architectures = configuration.get("architectures")
    if not isinstance(architectures, list) or "GPT2LMHeadModel" not in architectures:
        raise AssertionError(f"unexpected GPT-2 architecture declaration: {architectures!r}")

    shards = [
        item for item in description["observed"]["files"]
        if item["role"] == "safetensors-shard"
    ]
    if not shards or description["inferred"]["tensor_count"] < 1:
        raise AssertionError("Hub observation returned no Safetensors tensor inventory")
    if any(item["sha256_scope"] != "8-byte-prefix-and-header-only" for item in shards):
        raise AssertionError("a shard record claims a hash scope beyond its header")

    full_shard_bytes = sum(item["size_bytes"] for item in shards)
    transferred_header_bytes = sum(8 + item["header_bytes"] for item in shards)
    if transferred_header_bytes >= full_shard_bytes:
        raise AssertionError(
            "header transfer was not smaller than the complete Safetensors shard inventory"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        description,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"
    output.write_text(rendered, encoding="utf-8", newline="\n")

    summary = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "model_type": configuration["model_type"],
        "architectures": architectures,
        "tensor_count": description["inferred"]["tensor_count"],
        "shard_count": description["inferred"]["shard_count"],
        "dtypes": description["inferred"]["dtypes"],
        "full_shard_bytes_from_content_range": full_shard_bytes,
        "transferred_safetensors_header_bytes": transferred_header_bytes,
        "header_fraction_of_full_shard_bytes": transferred_header_bytes / full_shard_bytes,
        "nsd_path": str(output),
        "nsd_bytes": len(rendered.encode("utf-8")),
        "weight_payload_read": False,
    }
    print(json.dumps(summary, sort_keys=True))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Observe a pinned GPT-2 Safetensors header inventory from the public Hub."
    )
    parser.add_argument(
        "--output",
        default="experiments/external_neural_structure_reading/results/gpt2-nsd.json",
    )
    args = parser.parse_args(argv)
    run(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
