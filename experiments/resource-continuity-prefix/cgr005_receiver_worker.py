"""CGR-005: original IPS-008 mTLS service over a general-language native quorum.

This process uses original E-CPU TLS framing, original SQLite effect receiver,
original current-quorum checks and original PREPARE/ACTIVATE/APPLY handlers.
The only changed part is the publisher's mathematical stage verifier.
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
from cgr005_general_quorum import RESOURCE, open_general


def main(args: list[str]) -> int:
    if len(args)!=6:
        raise ValueError("requires root, certificate, key, CA, ready marker, authorized owner DNS")
    root,cert,key,ca,ready,owner_dns=args
    root=Path(root)
    publisher=open_general(root)
    receiver=FencedGroundEffectReceiver(
        root/"cgr005-receiver.sqlite3",resource=RESOURCE,
        plan_digest=publisher.plan.digest,
    )
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version=ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(cert,key)
    tls.load_verify_locations(cafile=ca)
    tls.verify_mode=ssl.CERT_REQUIRED
    listener=SocketTransport.listen("127.0.0.1",0)
    listener.settimeout(.25)
    service=AuthenticatedGroundEffectService(
        receiver,publisher,listener,tls,expected_owner_dns=owner_dns,
        publisher_factory=lambda:open_general(root),
    )
    marker=Path(ready)
    with marker.open("wb") as output:
        output.write(json.dumps({
            "host":service.address[0],"port":service.address[1],
        },sort_keys=True).encode("ascii"))
        output.flush()
        os.fsync(output.fileno())
    while True:
        service.serve_once(handshake_timeout=.6)


if __name__=="__main__":
    raise SystemExit(main(sys.argv[1:]))
