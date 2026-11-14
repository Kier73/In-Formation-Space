"""PON-003: two publisher bundles, two actual local HTTP processes, physical kill.

Artifacts carry complete independently produced *test* copies, but GitHub
Actions is still one shared artifact substrate. Processes serve distinct
storage directories on one verifier runner; no proof of independently
operated public storage or physically distinct live origin machines is made.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from passive_orbit import ROOT_PIN, canonical, digest
from pon003_navigate import Origin, reconstruct
from pon003_origin import publisher_source

HERE = Path(__file__).resolve().parent


def start(kind: str, directory: Path) -> tuple[subprocess.Popen, Origin]:
    cmd = [sys.executable, str(HERE / "pon003_serve.py"),
           "--kind", kind, "--root", str(directory)]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    line = proc.stdout.readline().strip()
    found = re.fullmatch(r"LISTEN_PORT=(\d{1,5})", line)
    if found is None:
        try:
            proc.kill()
        finally:
            out, err = proc.communicate(timeout=3)
        raise RuntimeError(f"{kind} read-only origin failed to bind: {line} {err[:300]}")
    origin = Origin(kind=kind, base_url="http://127.0.0.1:" +
                    found.group(1) + "/", public=False)
    return proc, origin


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=5)


def run(r2: Path, ipfs: Path) -> dict:
    source = publisher_source()
    receipts = {
        kind: json.loads((folder / "receipt.json").read_bytes())
        for kind, folder in (("r2", r2), ("ipfs", ipfs))
    }
    pins = {
        kind: bytes.fromhex((folder / "public-key.hex").read_text().strip())
        for kind, folder in (("r2", r2), ("ipfs", ipfs))
    }
    epochs = {"r2": 1, "ipfs": 1}
    alive: list[subprocess.Popen] = []
    try:
        a, a_origin = start("r2", r2)
        alive.append(a)
        b, b_origin = start("ipfs", ipfs)
        alive.append(b)
        routes = [a_origin, b_origin]

        def observe() -> dict:
            return reconstruct(
                origins=routes, receipts=receipts,
                pinned_keys=pins, epoch_floor=epochs,
                now=int(time.time()),
            )

        baseline = observe()
        if baseline["status"] != "verified_reconstruction" or \
                baseline["value"] != 44 or \
                set(baseline["selected_origins"].values()) != {"r2"}:
            raise RuntimeError("baseline bucket-origin reconstruction failed")

        # An origin is not a trusted source of mathematical meaning.
        # Change real served bytes after the publisher has signed its exact
        # inventory: receiver must reject the substituted object and recover
        # the correct object through the independently signed IPFS route.
        r2_manifest = r2 / "manifest.json"
        original = r2_manifest.read_bytes()
        r2_manifest.write_bytes(b'{"incorrect":"alternate root"}')
        try:
            corrupted = observe()
        finally:
            r2_manifest.write_bytes(original)
        if corrupted["status"] != "verified_reconstruction" or \
                corrupted["value"] != 44 or \
                corrupted["selected_origins"].get("root") != "ipfs" or \
                not any(e["status"] == "rejected_integrity_or_semantics"
                        for e in corrupted["events"]):
            raise RuntimeError("altered origin content was falsely admitted")

        # Actually terminate the origin listener: this is not an HTTP
        # 404 simulation or a relabelled URL.
        stop(a)
        if a.poll() is None:
            raise RuntimeError("bucket origin shutdown not observed")
        recovered = observe()
        if recovered["status"] != "verified_reconstruction" or \
                recovered["value"] != 44 or \
                set(recovered["selected_origins"].values()) != {"ipfs"} or \
                not any(e["origin"] == "r2" and e["status"] == "unavailable"
                        for e in recovered["events"]):
            raise RuntimeError("real listener loss did not recover via block-origin")

        # Removing the *only* surviving origin is a negative control:
        # no arithmetic result may appear from absence or cached reports.
        stop(b)
        if b.poll() is None:
            raise RuntimeError("IPFS origin listener shutdown not observed")
        neither = observe()
        if neither["status"] != "unresolved" or \
                neither["value"] is not None or \
                neither["reason"] != "all_origins_missing_or_invalid_root" or \
                set(neither["selected_origins"]) != set():
            raise RuntimeError("inaccessible origins were mislabeled as available")

        return {
            "schema": "in-formation.pon003.local-killed-origin-evidence/0.1",
            "status": "two-separately-published-origin-contracts-with-kill-recovery",
            "source_root_sha256": ROOT_PIN,
            "r2_receipt_sha256": digest(canonical(receipts["r2"])),
            "ipfs_receipt_sha256": digest(canonical(receipts["ipfs"])),
            "distinct_signing_keys": pins["r2"] != pins["ipfs"],
            "baseline": baseline,
            "tampered_origin": corrupted,
            "bucket_origin_killed": recovered,
            "both_origins_killed": neither,
            "simulated_adapters": ["r2-style read-only HTTP", "IPFS raw block HTTP"],
            "real_process_kill": True,
            "physical_origin_machine_count": 1,
            "public_origin_success_verified": False,
            "independent_storage_admins_attested": False,
            "shared_artifact_backend": "GitHub Actions",
            "source_content_mathematically_reconstructed_by_observer": True,
            "passive_hosts_executed_computation": False,
            "external_execution_authorized": False,
        }
    finally:
        for proc in alive:
            stop(proc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r2-dir", type=Path, required=True)
    parser.add_argument("--ipfs-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.r2_dir, args.ipfs_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({
        "status": result["status"],
        "before": result["baseline"]["value"],
        "after_kill": result["bucket_origin_killed"]["value"],
        "after_both_kills": result["both_origins_killed"]["status"],
        "tampered_root_fallback": result["tampered_origin"]["selected_origins"]["root"],
        "public_origin_success_verified": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
