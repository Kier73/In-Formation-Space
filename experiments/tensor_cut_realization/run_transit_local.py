"""TCR-002 subprocess loopback mTLS exercise; no network/host attestation claim."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import numpy as np

from . import tensor_cut as tcr
from .transit_tensor import (ResidentShard, accept_response, request_for, send,
                             worker_name, require, canonical)


def openssl(*args: str, cwd: Path) -> None:
    subprocess.run(["openssl", *args], cwd=cwd, stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE, check=True, timeout=15)


def certificates(directory: Path, partitions: int) -> dict[str, tuple[Path, Path]]:
    directory.mkdir(parents=True, exist_ok=True)
    openssl("req", "-new", "-x509", "-nodes", "-newkey", "rsa:2048",
            "-keyout", "ca.key", "-out", "ca.crt", "-days", "1",
            "-subj", "/CN=TCR002-ephemeral-test-CA", cwd=directory)
    names = ["tcr002-origin"] + [worker_name(i) for i in range(partitions)]
    certs = {}
    for name in names:
        openssl("req", "-nodes", "-newkey", "rsa:2048", "-keyout", name + ".key",
                "-out", name + ".csr", "-subj", f"/CN={name}", cwd=directory)
        ext = directory / (name + ".ext")
        ext.write_text(f"subjectAltName=DNS:{name}\nextendedKeyUsage=serverAuth,clientAuth\n")
        openssl("x509", "-req", "-in", name + ".csr", "-CA", "ca.crt",
                "-CAkey", "ca.key", "-CAcreateserial", "-out", name + ".crt",
                "-days", "1", "-extfile", name + ".ext", cwd=directory)
        certs[name] = (directory / (name + ".crt"), directory / (name + ".key"))
    return certs


def run(prepared: Path, report: Path) -> dict:
    manifest = tcr._validated_manifest(tcr._read_json(prepared / "manifest.json"))
    n = len(manifest["partitions"])
    require(1 <= n <= 4, "bounded local demonstration only")
    with np.load(prepared / "reference.npz", allow_pickle=False) as src:
        x = src["inputs"]
    require(tcr._typed_digest(x) == manifest["input_digest"], "invalid prepared activation")
    with tempfile.TemporaryDirectory(prefix="tcr002-local-") as tmp:
        root = Path(tmp)
        certs = certificates(root / "tls", n)
        processes = []
        records = []
        results = root / "results"
        try:
            for i in range(n):
                name = worker_name(i)
                cert, key = certs[name]
                command = [sys.executable, "-m", "experiments.tensor_cut_realization.transit_tensor",
                           "serve", "--packet", str(prepared / f"shard-{i}"),
                           "--sessions", "3" if i == 0 else "2", "--ca", str(root / "tls/ca.crt"),
                           "--cert", str(cert), "--key", str(key)]
                child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True, bufsize=1)
                processes.append(child)
                ready = child.stdout.readline()
                require(bool(ready), f"worker {i} failed before readiness")
                datum = json.loads(ready)
                require(datum.get("worker") == name and type(datum.get("port")) is int,
                        "invalid peer readiness")
                records.append({"worker": name, "port": datum["port"], "pid": datum["pid"]})
            requests = [request_for(manifest, i, x, request_id=f"tcr002-cut-{i}")
                        for i in range(n)]
            observations = []
            for cycle in range(2):
                for i in range(n):
                    address = records[i]
                    response, net = send("127.0.0.1", address["port"], i, requests[i],
                                         root / "tls/ca.crt", *certs["tcr002-origin"])
                    evidence = accept_response(requests[i], response, manifest, results)
                    require(evidence["replayed"] is (cycle == 1), "resident replay mismatch")
                    observations.append({"partition": i, "cycle": cycle, **net, **evidence})
            bad = dict(requests[0], manifest_digest="0" * 64, request_id="invalid-policy")
            denied, net = send("127.0.0.1", records[0]["port"], 0, bad,
                               root / "tls/ca.crt", *certs["tcr002-origin"])
            require(denied.get("accepted") is False and
                    "receiver source/cut identity denied" in denied.get("reason", ""),
                    "receiver accepted wrong source")
            baseline = tcr.aggregate(prepared, results, root / "dag-report.json")
            require(baseline["verification"]["status"] == "passed", "numeric aggregate failed")
            for child in processes:
                require(child.wait(timeout=15) == 0, "worker process failed")
            result = {"schema": "ifs.tcr002.local-mtls-evidence.v1",
                      "status": "local-authenticated-tensor-cut-reconstructed",
                      "source_provenance": manifest["source_provenance"],
                      "source_digest": manifest["source_digest"],
                      "manifest_digest": manifest["digest"],
                      "partition_count": n, "worker_count": len(processes),
                      "fresh_executions": n, "replayed_responses": n,
                      "receiver_denied_wrong_manifest": True,
                      "verified_output": baseline["verification"],
                      "dag_restored": baseline["dag_restoration_equal"],
                      "result_digest": baseline["result_digest"],
                      "application_bytes": {
                          "requests_both_cycles": sum(p["application_request_bytes"] for p in observations),
                          "responses_both_cycles": sum(p["application_response_bytes"] for p in observations)},
                      "local_cost_observations": observations,
                      "scope": {"transport": "E-CPU SocketTransport, ReliableChannel and reciprocal mTLS",
                                "execution": "four separate subprocesses, one runner, local loopback",
                                "model_residency": "weight shards preprovisioned on each receiver before requests",
                                "authority": "receiver-owned immutable cut and input policy; not VirtualLayer/Hypervisor dispatch",
                                "receipts": "application digest-bound, not independent signed durable host attestations",
                                "network": "no inter-host route or Tailscale overlay tested",
                                "cost": "client/worker local monotonic timings, no global clock or overhead-inclusive byte claim"}}
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_bytes(canonical(result) + b"\n")
            return result
        finally:
            for child in processes:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.prepared, args.report)
    print(json.dumps({"status": result["status"], "workers": result["worker_count"],
                      "verification": result["verified_output"]}, sort_keys=True))


if __name__ == "__main__":
    main()
