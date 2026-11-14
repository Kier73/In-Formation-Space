"""PON-001 public-passive route experiment.

An opt-in, expiring local HTTP *byte holder* serves only a partial orbit.
The remaining immutable objects come via unauthenticated public HTTPS
from this repository's Git-commit-pinned raw.githubusercontent.com path.
When the local lease expires, public bytes alone must reconstruct 44.
Neither passive HTTP route interprets arithmetic or executes model code.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from passive_orbit import HERE, ROOT_PIN, Route, canonical, navigate

SERVER = HERE / "passive_orbit.py"
PUBLIC = HERE / "public"


def stage_partial(root: Path) -> None:
    root.mkdir()
    (root / "objects").mkdir()
    (root / "manifest.json").write_bytes((PUBLIC / "manifest.json").read_bytes())
    docs = json.loads((PUBLIC / "manifest.json").read_bytes())
    for ref in docs["objects"]:
        if ref["semantic_id"] not in ("seed", "left"):
            continue
        name = ref["object_sha256"] + ".json"
        shutil.copyfile(PUBLIC / "objects" / name, root / "objects" / name)


def run(revision: str) -> dict:
    if re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", revision) is None:
        raise ValueError("public experiment must use immutable commit SHA")
    base = ("https://raw.githubusercontent.com/Kier73/In-Formation-Space/"
            + revision + "/experiments/passive-orbit-cache/public/")
    public = Route("public", base, "public")
    with tempfile.TemporaryDirectory(prefix="pon001-passive-") as folder:
        local = Path(folder) / "partial"
        stage_partial(local)
        cmd = [sys.executable, str(SERVER), "serve",
               "--directory", str(local), "--ttl", "1.0"]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, bufsize=1)
        try:
            port_line = process.stdout.readline().strip()
            found = re.fullmatch(r"LISTEN_PORT=([0-9]{1,5})", port_line)
            if not found:
                raise RuntimeError("temporary passive HTTP holder failed to start: "
                                   + port_line)
            temp = Route("temporary", "http://127.0.0.1:"
                         + found.group(1) + "/", "temporary")
            time_started = time.perf_counter_ns()
            mixed = navigate([temp, public])
            mixed_duration = time.perf_counter_ns() - time_started
            if mixed["status"] != "locally_reconstructed_pure_result" or \
                    mixed["value"] != 44:
                raise RuntimeError("complementary passive holders did not reconstruct 44")
            if not ("temporary" in mixed["source_by_semantic_id"].values()
                    and "public" in mixed["source_by_semantic_id"].values()):
                raise RuntimeError("mixed route did not use both holders")

            # The temporary route's lease expires, without any remote code
            # execution or renewal. Immutable public objects remain.
            time.sleep(1.25)
            time_started = time.perf_counter_ns()
            fallback = navigate([temp, public])
            fallback_duration = time.perf_counter_ns() - time_started
            if fallback["status"] != "locally_reconstructed_pure_result" or \
                    fallback["value"] != 44:
                raise RuntimeError("expired temporary host prevented verified fallback")
            if any(source != "public"
                   for source in fallback["source_by_semantic_id"].values()):
                raise RuntimeError("expired holder silently served supposedly public result")
            if not any(x["route"] == "temporary" and x["status"] == "http_410"
                       for x in fallback["attempts"]):
                raise RuntimeError("expiry 410 was not actually observed")
            if mixed["reconstruction_digest"] != fallback["reconstruction_digest"]:
                raise RuntimeError("delivery route changed pure computation identity")

            return {
                "schema": "in-formation.pon001.real-public-passive-evidence/0.1",
                "status": "public-https-and-expiring-holder-navigation-verified",
                "root_sha256": ROOT_PIN,
                "public_git_commit": revision,
                "mixed_route": mixed,
                "after_expiration": fallback,
                "mixed_duration_ns_observer_local": mixed_duration,
                "fallback_duration_ns_observer_local": fallback_duration,
                "ephemeral_process_separate": True,
                "public_host": "raw.githubusercontent.com serving user-controlled git objects",
                "actual_public_https_get": True,
                "public_host_executed_operations": False,
                "temporary_host_executed_operations": False,
                "observer_locally_reconstructed_arithmetic": True,
                "network_router_computation_claimed": False,
                "external_effects_authorized": False,
            }
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.public_ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({
        "status": result["status"], "output": result["mixed_route"]["value"],
        "verified_objects": result["mixed_route"]["verified_object_count"],
        "mixed_routes": result["mixed_route"]["source_by_semantic_id"],
        "expired_routes": result["after_expiration"]["source_by_semantic_id"],
        "mixed_duration_ns_observer_local": result["mixed_duration_ns_observer_local"],
        "fallback_duration_ns_observer_local": result["fallback_duration_ns_observer_local"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
