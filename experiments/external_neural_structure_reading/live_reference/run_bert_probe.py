"""HFR-002 comparative BERT snapshot probe with zero weight payload reads.

Observation-only precursor to the BERT graph adapter: retain explicit source
revision and tensor shape evidence while making no model graph claims.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..hub import inspect_huggingface_model

REPOSITORY = "google-bert/bert-base-uncased"
REVISION = "bcde001674fa61ee216714dd9cca5a5f9cfa4b12"


def run(output: Path) -> dict:
    """Observe and summarize the pinned Safetensors manifest, never tensor values."""
    nsd = inspect_huggingface_model(REPOSITORY, REVISION, license_id="apache-2.0")
    config = nsd["observed"]["configuration"]
    if config.get("model_type") != "bert" or "BertForMaskedLM" not in config.get("architectures", []):
        raise AssertionError("source does not declare the supported BertForMaskedLM family")
    manifest = nsd["observed"]["tensor_manifest"]
    if not manifest:
        raise AssertionError("empty BERT tensor inventory")
    shard_files = [item for item in nsd["observed"]["files"] if item.get("role") == "safetensors-shard"]
    report = {
        "source": nsd["source"],
        "configuration": config,
        "tensor_count": len(manifest),
        "root_counts": dict(sorted(Counter(item["name"].split(".")[0] for item in manifest).items())),
        "shard_header_records": shard_files,
        "tensors": [{"name": item["name"], "dtype": item["dtype"], "shape": item["shape"], "shard": item["shard"]} for item in manifest],
        "weight_payload_bytes_read": 0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return report


def main() -> int:
    """Write deterministic header-only observations to a CI artifact."""
    run(Path("experiments/external_neural_structure_reading/results/bert-family-inventory.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
