"""PON-003 optional *real public* R2 and raw-IPFS read-only probe.

Requires independently provisioned exact bytes in a Cloudflare R2 bucket and
IPFS persistent pinning provider. It never publishes or uploads unconsented
data. Only checks bytes from each allowlisted public service independently.
The report is NOT evidence of issuer ownership, origin physically independent,
or that an origin was taken offline. Those are separate proof obligations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from passive_orbit import ROOT_PIN, canonical, digest
from pon003_navigate import Origin, reconstruct


def probe(*, r2_base: str, ipfs_base: str,
          r2_dir: Path, ipfs_dir: Path) -> dict:
    routes = {
        "r2": Origin("r2", r2_base, public=True),
        "ipfs": Origin("ipfs", ipfs_base, public=True),
    }
    receipts = {
        k: json.loads((p / "receipt.json").read_bytes())
        for k,p in (("r2", r2_dir),("ipfs", ipfs_dir))
    }
    keys = {
        k: bytes.fromhex((p / "public-key.hex").read_text().strip())
        for k,p in (("r2", r2_dir),("ipfs", ipfs_dir))
    }
    t = int(time.time())
    policies = {"r2":1, "ipfs":1}
    outcomes = {}
    for first,second in (("r2","ipfs"),("ipfs","r2")):
        result = reconstruct(
            origins=[routes[first],routes[second]],
            receipts=receipts, pinned_keys=keys,
            epoch_floor=policies, now=t,
        )
        if result["status"] != "verified_reconstruction" or \
                result["value"] != 44 or \
                set(result["selected_origins"].values()) != {first}:
            raise RuntimeError(
                "public " + first + " did not return all six verified raw objects"
            )
        outcomes[first] = result
    if outcomes["r2"]["result_digest"] != outcomes["ipfs"]["result_digest"]:
        raise RuntimeError("two public stores reconstruct different mathematics")
    return {
        "schema": "in-formation.pon003.real-public-origin-probe/0.1",
        "status": "both-opt-in-public-storage-protocols-returned-verifiable-source",
        "root_sha256": ROOT_PIN,
        "result_digest": outcomes["r2"]["result_digest"],
        "result": 44,
        "r2": outcomes["r2"], "ipfs": outcomes["ipfs"],
        "real_public_gets_verified": True,
        "storage_publication_credentials_used_by_probe": False,
        "publisher_keys_externally_authenticated": False,
        "independent_storage_admins_attested": False,
        "forced_external_origin_outage_observed": False,
        "passive_hosts_executed_computation": False,
        "external_effects_authorized": False,
        "public_origin_source_selection":
            "single allowlisted HTTPS operator per proof pass, no fallback used",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r2-base", required=True)
    parser.add_argument("--ipfs-base", required=True)
    parser.add_argument("--r2-dir", type=Path, required=True)
    parser.add_argument("--ipfs-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    result=probe(r2_base=args.r2_base, ipfs_base=args.ipfs_base,
                 r2_dir=args.r2_dir, ipfs_dir=args.ipfs_dir)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(canonical(result)+b"\n")
    print(json.dumps({
        "status":result["status"],"value":result["result"],
        "r2_result":result["r2"]["result_digest"],
        "ipfs_result":result["ipfs"]["result_digest"],
    },sort_keys=True))


if __name__ == "__main__":
    main()
