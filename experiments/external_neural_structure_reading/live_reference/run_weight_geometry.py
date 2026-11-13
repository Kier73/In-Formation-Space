"""Read a bounded pair of GPT-2 matrices and retain geometry summaries only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from ..hub import fetch_selected_tensor_payloads, inspect_huggingface_model
from ..weight_geometry import analyze_selected_weight_geometry

REPOSITORY = "openai-community/gpt2"
REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"
LICENSE_ID = "mit"
SELECTED_TENSORS = [
    "h.0.attn.c_attn.weight",
    "h.11.attn.c_attn.weight",
]
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_TENSOR_BYTES = 8 * 1024 * 1024
EXPECTED_TOTAL_BYTES = 14_155_776


def run(output: Path) -> dict:
    nsd = inspect_huggingface_model(
        REPOSITORY,
        REVISION,
        license_id=LICENSE_ID,
    )
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
        raise AssertionError("reader did not return the exact selected tensor allowlist")
    for item in evidence:
        if item["dtype"] != "F32" or item["shape"] != [768, 2304]:
            raise AssertionError(
                f"unexpected selected tensor layout for {item['name']}: "
                f"{item['dtype']} {item['shape']}"
            )

    result = analyze_selected_weight_geometry(nsd, payloads, evidence)
    schema_path = Path(__file__).parents[1] / "weight-geometry.schema.json"
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

    comparisons = result["cross_layer_comparisons"]
    summary = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "selected_tensors": SELECTED_TENSORS,
        "selected_payload_bytes": total_bytes,
        "max_total_budget_bytes": MAX_TOTAL_BYTES,
        "max_per_tensor_budget_bytes": MAX_TENSOR_BYTES,
        "fused_qkv_cosine_similarity": comparisons["fused_qkv"]["cosine_similarity"],
        "q_cosine_similarity": comparisons["q"]["cosine_similarity"],
        "k_cosine_similarity": comparisons["k"]["cosine_similarity"],
        "v_cosine_similarity": comparisons["v"]["cosine_similarity"],
        "result_path": str(output),
        "result_bytes": len(rendered.encode("utf-8")),
        "raw_payloads_retained": False,
    }
    print(json.dumps(summary, sort_keys=True))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze an explicitly allowlisted pair of GPT-2 QKV weight matrices under a 16 MiB total byte budget."
    )
    parser.add_argument(
        "--output",
        default="experiments/external_neural_structure_reading/results/gpt2-weight-geometry.json",
    )
    args = parser.parse_args(argv)
    run(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
