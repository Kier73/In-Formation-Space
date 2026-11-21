"""CGR-003: independent original E-CPU IPS-008 mTLS effect receiver.

The publisher is reconstructed from a locally pinned observed NCR-004 Ground.
This process owns the native SQLite effect resource and accepts only original
IPS-008 TLS / Message / PREPARE / ACTIVATE / APPLY / ACK protocol calls.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import ssl
import sys

from mailcpu.effect_receiver_service import AuthenticatedGroundEffectService
from mailcpu.fenced_effect_receiver import FencedGroundEffectReceiver
from mailcpu.socket_transport import SocketTransport
from cgr003_observed_ecpu import RESOURCE, open_lineage


def main(args: list[str]) -> int:
    if len(args) != 6:
        raise ValueError("requires native root, cert, key, CA, ready marker, owner DNS")
    root, cert, key, ca, ready, owner_dns = args
    root = Path(root)
    publisher = open_lineage(root)
    receiver = FencedGroundEffectReceiver(
        root / "cgr003-ips008-receiver.sqlite3",
        resource=RESOURCE,
        plan_digest=publisher.plan.digest,
    )
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(cert, key)
    tls.load_verify_locations(cafile=ca)
    tls.verify_mode = ssl.CERT_REQUIRED
    listener = SocketTransport.listen("127.0.0.1", 0)
    listener.settimeout(.25)
    service = AuthenticatedGroundEffectService(
        receiver, publisher, listener, tls, expected_owner_dns=owner_dns,
        publisher_factory=lambda: open_lineage(root),
    )
    marker = Path(ready)
    with marker.open("wb") as stream:
        stream.write(json.dumps({"host": service.address[0],
                                 "port": service.address[1]},
                                sort_keys=True).encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    while True:
        service.serve_once(handshake_timeout=.6)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
