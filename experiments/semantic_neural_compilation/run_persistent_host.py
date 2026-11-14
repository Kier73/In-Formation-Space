"""SNC-003: measured cold source transfer, restart reuse and observation replay.

Three independent server *processes* use one durable SQLite database.
Only the first request transports a semantic atlas; later requests name the
previously verified semantic model without retransmitting its coefficients.
"""
from __future__ import annotations

from pathlib import Path
import json
import re
import statistics
import subprocess
import sys
import tempfile
import time

from independent_certificate_checker import hash_bytes
from persistent_host import POLICY_SCHEMA, PersistentSemanticHost, canonical
from persistent_wire import REQUEST_SCHEMA
from run_semantic_transit import test_certificates

HERE = Path(__file__).resolve().parent
SERVER = HERE / "persistent_wire.py"
MAX_T = 65


def roundtrip(
    folder: Path, certs: dict[str, Path], database: Path, policy: Path,
    request: dict, n: int,
) -> dict:
    req_path = folder / f"request-{n}.json"
    report_path = folder / f"server-{n}.json"
    req_path.write_bytes(canonical(request))
    serve = [
        sys.executable, str(SERVER), "serve", "--bind", "127.0.0.1",
        "--port", "0", "--ca", str(certs["ca"]),
        "--cert", str(certs["server_cert"]), "--key", str(certs["server_key"]),
        "--database", str(database), "--policy", str(policy),
        "--report", str(report_path),
    ]
    parent_start = time.perf_counter_ns()
    server = subprocess.Popen(serve, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        first = server.stdout.readline().strip()
        parsed = re.fullmatch(r"LISTEN_PORT=([1-9][0-9]*)", first)
        if not parsed:
            raise RuntimeError("receiver did not start: " + first)
        send = [
            sys.executable, str(SERVER), "send", "--host", "127.0.0.1",
            "--port", parsed.group(1), "--request", str(req_path),
            "--ca", str(certs["ca"]), "--cert", str(certs["client_cert"]),
            "--key", str(certs["client_key"]),
        ]
        sender = subprocess.run(send, capture_output=True, text=True,
                                timeout=MAX_T, check=False)
        s_out, s_err = server.communicate(timeout=MAX_T)
        elapsed = time.perf_counter_ns() - parent_start
        if sender.returncode or server.returncode:
            raise RuntimeError(
                "mTLS client: " + sender.stderr[-600:]
                + "\nmTLS server: " + s_err[-600:])
        response = json.loads(sender.stdout)
        decision = response["response"]
        if not decision["accepted"]:
            raise RuntimeError("semantic application rejected: "
                               + decision.get("reason", "unknown"))
        if not report_path.exists():
            raise RuntimeError("receiver session evidence absent")
        if not json.loads(report_path.read_text())["accepted"]:
            raise RuntimeError("server did not commit verified response")
        return {
            "application_request_bytes": response["application_request_bytes"],
            "parent_wall_ns": elapsed,
            "client_application_response_ns": response["client_request_elapsed_ns_local"],
            "cache_state": decision["decision"]["cache_state"],
            "disposition": decision["decision"]["disposition"],
            "construction_ns": decision["decision"]["construction_ns"],
            "verification_ns": decision["decision"]["independent_verification_ns"],
            "outputs": decision["decision"]["receipt"]["outputs"],
            "network_sha256": decision["decision"]["receipt"]["generated_network_sha256"],
            "receipt_sha256": decision["decision"]["receipt_sha256"],
            "tls_version": response["tls_version"],
        }
    finally:
        if server.poll() is None:
            server.kill()
            server.communicate(timeout=5)


def experiment(out: Path) -> dict:
    examples = json.loads((HERE / "examples.json").read_text())
    source = examples["clamp_0_1"]
    semantic_id = hash_bytes(source)
    with tempfile.TemporaryDirectory(prefix="snc003-host-fixture-") as raw:
        folder = Path(raw)
        certs = test_certificates(folder)
        policy_path = folder / "receiver-policy.json"
        database = folder / "models.sqlite3"
        policy_path.write_bytes(canonical({
            "schema": POLICY_SCHEMA, "models": {"clamp": semantic_id}
        }))
        seed = {
            "schema": REQUEST_SCHEMA, "kind": "seed", "model": "clamp",
            "coordinate": "1/2", "request_id": "seed1", "semantic_atlas": source,
        }
        observe = {
            "schema": REQUEST_SCHEMA, "kind": "observe", "model": "clamp",
            "coordinate": "3/4", "request_id": "observe2",
        }
        replay = dict(observe)
        first = roundtrip(folder, certs, database, policy_path, seed, 1)
        second = roundtrip(folder, certs, database, policy_path, observe, 2)
        third = roundtrip(folder, certs, database, policy_path, replay, 3)
        if (first["cache_state"], second["cache_state"], third["cache_state"]) != (
            "constructed-verified", "restored-verified", "restored-verified"):
            raise RuntimeError("incorrect construction/restoration lifecycle")
        if third["disposition"] != "idempotent-replay" or \
                third["receipt_sha256"] != second["receipt_sha256"]:
            raise RuntimeError("retry changed the durable exact observation")
        if (first["outputs"], second["outputs"]) != (["1/2"], ["3/4"]):
            raise RuntimeError("wrong mathematical observations")
        if len({x["network_sha256"] for x in (first, second, third)}) != 1:
            raise RuntimeError("network identity changed after receiver restart")
        host = PersistentSemanticHost(database, policy_path)
        restored = host.observe(model="clamp", coordinate="1/4",
                                request_id="warm0")
        warm = []
        for i in range(32):
            result = host.observe(
                model="clamp", coordinate=str(i % 9) + "/8"
                if i % 9 else "0", request_id=f"warm{i+1}",
            )
            if result["cache_state"] != "memory-reused" or \
                    result["construction_ns"] or result["independent_verification_ns"]:
                raise RuntimeError("warm host unexpectedly recompiled or reverified")
            warm.append(result["request_elapsed_ns_local"])
        models, n_observations = host.count("clamp")
        if models != 1 or n_observations != 35:
            raise RuntimeError(f"incorrect committed state: {models}, {n_observations}")
        result = {
            "schema": "in-formation-space.snc003.persistent-host-experiment/0.1",
            "status": "all-lifecycle-gates-verified",
            "transfer": "two distinct Python processes per round over E-CPU mTLS ReliableChannel",
            "host_scope": "one physical GitHub Actions runner; no cross-machine claim",
            "source_sha256": semantic_id,
            "cold_seed": first,
            "restart_reference": second,
            "idempotent_retry_after_restart": third,
            "same_process_verified_restoration": {
                "state": restored["cache_state"],
                "verification_ns": restored["independent_verification_ns"],
            },
            "warm_observations": {
                "count": len(warm),
                "median_ns": int(statistics.median(warm)),
                "min_ns": min(warm), "max_ns": max(warm),
                "all_construction_ns": 0, "all_verification_ns": 0,
            },
            "persisted_model_count": models,
            "committed_observation_count": n_observations,
            "physical_node_count": 1,
            "external_execution_authority": False,
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(canonical(result))
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(experiment(args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
