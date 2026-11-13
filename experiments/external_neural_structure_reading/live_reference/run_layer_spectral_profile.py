"""Live five-point depth spectral profile for pinned GPT-2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from ..hub import fetch_selected_tensor_payloads, inspect_huggingface_model
from ..layer_spectral_profile import (
    EXPECTED_LAYERS,
    analyze_gpt2_layer_spectral_profile,
)

REPOSITORY = "openai-community/gpt2"
REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"
LICENSE_ID = "mit"
SELECTED_TENSORS = [
    f"h.{index}.attn.c_attn.weight"
    for index in EXPECTED_LAYERS
]
MAX_TOTAL_BYTES = 48 * 1024 * 1024
MAX_TENSOR_BYTES = 8 * 1024 * 1024
EXPECTED_TOTAL_BYTES = 35_389_440


def run(output: Path) -> dict:
    nsd = inspect_huggingface_model(
        REPOSITORY,
        REVISION,
        license_id=LICENSE_ID,
    )
    config = nsd["observed"]["configuration"]
    if config.get("model_type") != "gpt2" or config.get("n_layer") != 12:
        raise AssertionError("pinned observation no longer matches the expected 12-layer GPT-2 family")

    payloads, evidence = fetch_selected_tensor_payloads(
        nsd,
        SELECTED_TENSORS,
        max_total_bytes=MAX_TOTAL_BYTES,
        max_tensor_bytes=MAX_TENSOR_BYTES,
    )
    total_bytes = sum(item["size_bytes"] for item in evidence)
    if total_bytes != EXPECTED_TOTAL_BYTES:
        raise AssertionError(
            f"selected tensor bytes changed: expected {EXPECTED_TOTAL_BYTES}, got {total_bytes}"
        )
    if set(payloads) != set(SELECTED_TENSORS):
        raise AssertionError("reader did not return the exact five-tensor allowlist")

    result = analyze_gpt2_layer_spectral_profile(nsd, payloads, evidence)
    schema_path = Path(__file__).parents[1] / "gpt2-layer-spectral-profile.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(result)

    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"
    output.write_text(rendered, encoding="utf-8", newline="\n")

    comparison_ranges = {
        role: {
            "minimum_mean_abs_distance": min(
                item["mean_absolute_normalized_spectrum_distance"]
                for item in result["pairwise_spectral_comparisons"][role]
            ),
            "maximum_mean_abs_distance": max(
                item["mean_absolute_normalized_spectrum_distance"]
                for item in result["pairwise_spectral_comparisons"][role]
            ),
            "mean_mean_abs_distance": sum(
                item["mean_absolute_normalized_spectrum_distance"]
                for item in result["pairwise_spectral_comparisons"][role]
            ) / 10,
        }
        for role in ("query", "key", "value")
    }
    summary = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "sampled_layers": list(EXPECTED_LAYERS),
        "selected_tensor_names": SELECTED_TENSORS,
        "selected_payload_bytes": total_bytes,
        "max_total_budget_bytes": MAX_TOTAL_BYTES,
        "pairwise_spectral_distance_ranges": comparison_ranges,
        "result_path": str(output),
        "result_bytes": len(rendered.encode("utf-8")),
        "raw_payloads_retained": False,
    }
    print(json.dumps(summary, sort_keys=True))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a five-point GPT-2 Q/K/V singular-spectrum profile under a 48 MiB total payload budget."
    )
    parser.add_argument(
        "--output",
        default="experiments/external_neural_structure_reading/results/gpt2-layer-spectral-profile.json",
    )
    args = parser.parse_args(argv)
    run(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
