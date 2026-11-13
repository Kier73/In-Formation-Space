"""Child process hosting one real E-CPU recovery-lineage mTLS authority service."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import ssl
import sys

from mailcpu import RecoveryLineageAuthorityService, SeedCommitMembership, SocketTransport


def main(args: list[str]) -> int:
    if len(args) != 7:
        raise SystemExit(
            "worker requires member id, membership, journal, server certificate, "
            "server key, client CA and expected owner DNS"
        )
    member_id, membership_path, journal_path, certificate, private_key, client_ca, owner_dns = args
    membership = SeedCommitMembership.from_snapshot(
        json.loads(Path(membership_path).read_text(encoding="utf-8"))
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, private_key)
    context.load_verify_locations(cafile=client_ca)
    context.verify_mode = ssl.CERT_REQUIRED

    listener = SocketTransport.listen("127.0.0.1", 0)
    service = RecoveryLineageAuthorityService(
        membership,
        member_id,
        journal_path,
        listener,
        context,
        expected_owner_dns=owner_dns,
    )
    host, port = service.address
    print(
        json.dumps(
            {
                "member_id": member_id,
                "host": host,
                "port": port,
                "process_id": os.getpid(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )
    service.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
