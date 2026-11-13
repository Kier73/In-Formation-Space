"""Live, zero-payload HFR-002 typed topology reconstruction for pinned GPT-2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from ..hub import inspect_huggingface_model
from ..neural_graph_ir import compile_gpt2_topology, verify_typed_graph

REPOSITORY = "openai-community/gpt2"
REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"
LICENSE_ID = "mit"


def run(output: Path) -> dict:
    nsd = inspect_huggingface_model(
        REPOSITORY,
        REVISION,
        license_id=LICENSE_ID,
    )
    graph = compile_gpt2_topology(nsd)

    schema_path = Path(__file__).parents[1] / "neural-computation-graph.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(graph)

    verification = verify_typed_graph(graph, nsd)["verification"]
    if verification["status"] != "passed":
        raise AssertionError(
            "typed graph verification failed: "
            + json.dumps(verification["checks"], sort_keys=True)
        )
    if graph["completeness"]["status"] != "complete-for-supported-family-template":
        raise AssertionError("GPT-2 topology classification is incomplete")
    if graph["completeness"]["observed_tensor_count"] != 160:
        raise AssertionError(
            "pinned GPT-2 tensor inventory changed: "
            f"{graph['completeness']['observed_tensor_count']}"
        )
    if verification["operation_count"] != 149:
        raise AssertionError(
            f"expected 149 operations for 12 GPT-2 blocks, got {verification['operation_count']}"
        )
    if verification["edge_count"] != 337:
        raise AssertionError(
            f"expected 337 typed edges for the 12-block graph, got {verification['edge_count']}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        graph,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"
    output.write_text(rendered, encoding="utf-8", newline="\n")

    summary = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "observed_tensor_count": graph["completeness"]["observed_tensor_count"],
        "classified_tensor_count": graph["completeness"]["classified_tensor_count"],
        "bound_tensor_count": graph["completeness"]["bound_tensor_count"],
        "operation_count": verification["operation_count"],
        "edge_count": verification["edge_count"],
        "input_port_count": verification["input_port_count"],
        "output_port_count": verification["output_port_count"],
        "passed_checks": verification["passed_check_count"],
        "failed_checks": verification["failed_check_count"],
        "graph_bytes": len(rendered.encode("utf-8")),
        "graph_path": str(output),
        "weight_payload_bytes_read": 0,
        "completeness": graph["completeness"]["status"],
        "verification": verification["status"],
    }
    print(json.dumps(summary, sort_keys=True))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconstruct a typed GPT-2 computation graph from Hub config and Safetensors headers only."
    )
    parser.add_argument(
        "--output",
        default="experiments/external_neural_structure_reading/results/gpt2-typed-topology.json",
    )
    args = parser.parse_args(argv)
    run(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
