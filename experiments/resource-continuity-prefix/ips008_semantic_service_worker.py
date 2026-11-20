"""RCP-004 real independent mTLS receiver OS process.

This invokes the original IPS-008 AuthenticatedGroundEffectService. A narrow
subclass adds source-qualified VL-I effect verbs while preserving the exact
E-CPU TLS transport, socket framing, owner SAN checks, ACK semantics and
PREPARE/ACTIVATE native handlers. One SQLite database is the sole protected
resource local authority for both native and semantic effects.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import ssl
import sys

from mailcpu.fenced_effect_receiver import FencedGroundEffectReceiver
from mailcpu.socket_transport import SocketTransport
from ips008_semantic_bridge import (
    AuthenticatedTemporalIPS008Service,
    NATIVE_RESOURCE,open_bound_semantic_receiver,
)
from test_fenced_generated_ground import _lineage


def main(args:list[str])->int:
    if len(args)!=7:
        raise ValueError(
            "requires root, server-cert, key, CA, ready, expected owner DNS, fault mode"
        )
    root,cert,key,ca,ready,owner_dns,fault=args
    root=Path(root)
    original=(root/"ips008-original-root.txt").read_text(encoding="ascii").strip()
    native_root=root/"native"
    publisher=_lineage(native_root)
    database=root/"protected-receiver.sqlite3"
    native=FencedGroundEffectReceiver(
        database,resource=NATIVE_RESOURCE,plan_digest=publisher.plan.digest,
    )
    semantic=open_bound_semantic_receiver(
        root,publisher,source_root=original,database=database,
    )
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(cert),str(key))
    ctx.load_verify_locations(cafile=str(ca))
    ctx.verify_mode=ssl.CERT_REQUIRED
    listener=SocketTransport.listen("127.0.0.1",0)
    listener.settimeout(.25)
    service=AuthenticatedTemporalIPS008Service(
        native,publisher,listener,ctx,
        expected_owner_dns=owner_dns,
        publisher_factory=lambda:_lineage(native_root),
        semantic_receiver=semantic,source_root=original,
        temporal_root=root/"temporal",
        fault_injection=fault=="test",
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
