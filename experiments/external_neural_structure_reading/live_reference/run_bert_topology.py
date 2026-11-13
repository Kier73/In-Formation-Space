"""Live HFR-002 BERT topology reconstruction from pinned header-only observation."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from ..bert_graph_ir import compile_bert_topology
from ..hub import inspect_huggingface_model
from ..neural_graph_ir import verify_typed_graph

REPOSITORY = "google-bert/bert-base-uncased"
REVISION = "bcde001674fa61ee216714dd9cca5a5f9cfa4b12"


def run(output: Path) -> dict:
    """Reconstruct both checkpoint-present heads without tensor payload acquisition."""
    nsd = inspect_huggingface_model(REPOSITORY, REVISION, license_id="apache-2.0")
    graph = compile_bert_topology(nsd)
    schema = json.loads(
        (Path(__file__).parents[1] / "neural-computation-graph.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(graph)
    report = verify_typed_graph(graph, nsd)
    assert report["verification"]["status"] == "passed", report
    assert report["completeness"]["status"] == "complete-for-supported-family-template"
    assert report["completeness"]["observed_tensor_count"] == 206
    assert report["completeness"]["bound_tensor_count"] == 206
    assert report["verification"]["operation_count"] == 184
    assert report["verification"]["edge_count"] == 455
    assert report["verification"]["failed_check_count"] == 0
    assert len(graph["outputs"]) == 2

    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(graph, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    output.write_text(rendered, encoding="utf-8", newline="\n")
    summary = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "configuration_architectures": nsd["observed"]["configuration"]["architectures"],
        "checkpoint_present_output_heads": [item["name"] for item in graph["outputs"]],
        "tensor_count": report["completeness"]["observed_tensor_count"],
        "bound_tensor_count": report["completeness"]["bound_tensor_count"],
        "operation_count": report["verification"]["operation_count"],
        "edge_count": report["verification"]["edge_count"],
        "input_port_count": report["verification"]["input_port_count"],
        "output_port_count": report["verification"]["output_port_count"],
        "passed_checks": report["verification"]["passed_check_count"],
        "failed_checks": report["verification"]["failed_check_count"],
        "graph_bytes": len(rendered.encode("utf-8")),
        "weight_payload_bytes_read": 0,
        "topology_status": report["verification"]["status"],
    }
    print(json.dumps(summary, sort_keys=True))
    return summary


def main() -> int:
    """Write live BERT topology as a versioned CI evidence artifact."""
    run(Path("experiments/external_neural_structure_reading/results/bert-typed-topology.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
