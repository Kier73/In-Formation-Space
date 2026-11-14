"""SNC-003: one-request-per-session semantic host over E-CPU ReliableChannel/mTLS.

Uses *two* E-CPU reliable channels: source request and independently decided
application response. A transport ACK is never a proof or observer receipt.
The local SQLite/receiver policy belongs exclusively to the recipient.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import ssl
import time
from typing import Any

from mailcpu.mtls_transport import accept_mutual_tls, connect_mutual_tls
from mailcpu.reliability import ReliableChannel, ReliabilityPolicy
from mailcpu.socket_transport import SocketTransport

from persistent_host import (
    HostRejected, PersistentSemanticHost, canonical, exact_object, require,
)
from semantic_transit import tls_context, SENDER, RECEIVER

REQUEST_SCHEMA = "in-formation-space.snc003.host-request/0.1"
RESPONSE_SCHEMA = "in-formation-space.snc003.host-response/0.1"
REQUEST_CHANNEL = "snc003-host-request"
RESPONSE_CHANNEL = "snc003-host-response"
MAX_SECONDS = 25.0
MAX_REQUEST_BYTES = 25_000


def channel(transport: SocketTransport, *, outgoing: bool,
            serving: bool) -> ReliableChannel:
    local = RECEIVER if serving else SENDER
    peer = SENDER if serving else RECEIVER
    destination = peer if outgoing else local
    return ReliableChannel(
        transport, source=local, destination=destination,
        peer=peer, channel=RESPONSE_CHANNEL if outgoing == serving else REQUEST_CHANNEL,
        policy=ReliabilityPolicy(lease_ticks=4, max_attempts=7, window_size=2),
    )


def validate_request(raw: object) -> dict[str, Any]:
    require(type(raw) is dict and len(canonical(raw)) <= MAX_REQUEST_BYTES,
            "bad or oversized request")
    kind = raw.get("kind")
    if kind == "seed":
        exact_object(raw, {"schema", "kind", "model", "coordinate",
                           "request_id", "semantic_atlas"}, "seed request")
    elif kind == "observe":
        exact_object(raw, {"schema", "kind", "model", "coordinate",
                           "request_id"}, "reference request")
    else:
        raise HostRejected("unsupported request kind")
    require(raw["schema"] == REQUEST_SCHEMA, "unsupported request schema")
    return raw


def handle(host: PersistentSemanticHost, request: object) -> dict[str, object]:
    rid = request.get("request_id") if type(request) is dict else None
    # The application response is separate from the transport delivery ACK.
    try:
        r = validate_request(request)
        decision = host.observe(
            model=r["model"], coordinate=r["coordinate"],
            request_id=r["request_id"],
            source=r.get("semantic_atlas") if r["kind"] == "seed" else None,
        )
        return {"schema": RESPONSE_SCHEMA, "request_id": r["request_id"],
                "accepted": True, "decision": decision}
    except (HostRejected, ValueError, TypeError) as exc:
        return {"schema": RESPONSE_SCHEMA,
                "request_id": rid if type(rid) is str and len(rid) <= 64 else "",
                "accepted": False, "reason": str(exc)[:200]}


def send_request(
    *, host: str, port: int, request: dict[str, Any],
    ca: Path, cert: Path, key: Path,
) -> dict[str, object]:
    validate_request(request)
    tls = connect_mutual_tls(
        host, port, SENDER, RECEIVER, tls_context(ca, cert, key, server=False),
        server_hostname=RECEIVER, timeout=8.0, max_frame_size=1 << 20,
    )
    try:
        writer = channel(tls, outgoing=True, serving=False)
        reader = channel(tls, outgoing=False, serving=False)
        start = time.perf_counter_ns()
        seq = writer.send(request)
        deadline = time.monotonic() + MAX_SECONDS
        last_tick = time.monotonic()
        response = None
        while time.monotonic() < deadline:
            writer.process_ack()
            if seq not in writer.pending_sequences():
                observed = reader.receive()
                if observed is not None:
                    response = observed[1]
                    break
            now = time.monotonic()
            if now - last_tick >= .1:
                require(seq not in writer.tick(), "request delivery retries exhausted")
                last_tick = now
            time.sleep(.005)
        require(response is not None, "missing application response")
        elapsed = time.perf_counter_ns() - start
        require(type(response) is dict and
                response.get("schema") == RESPONSE_SCHEMA and
                response.get("request_id") == request["request_id"] and
                type(response.get("accepted")) is bool,
                "invalid or mismatched application response")
        # The response receiver has just sent its ReliableChannel ACK.
        # Preserve the live TLS stream long enough for the server to consume
        # that ACK before TLS closure; transport ACK is not proof authority.
        time.sleep(.3)
        return {
            "response": response, "client_request_elapsed_ns_local": elapsed,
            "application_request_bytes": len(canonical(request)),
            "tls_version": tls.socket.version(),
            "transport": "E-CPU mTLS + request and response ReliableChannel",
        }
    finally:
        tls.close()


def serve_one(
    listener: Any, *, ca: Path, cert: Path, key: Path,
    database: Path, policy: Path, report: Path,
) -> dict[str, object]:
    tls = accept_mutual_tls(
        listener, RECEIVER, SENDER,
        tls_context(ca, cert, key, server=True),
        expected_peer_dns=SENDER, max_frame_size=1 << 20,
    )
    try:
        reader = channel(tls, outgoing=False, serving=True)
        writer = channel(tls, outgoing=True, serving=True)
        semantic_host = PersistentSemanticHost(database, policy)
        deadline = time.monotonic() + MAX_SECONDS
        request = None
        while time.monotonic() < deadline:
            received = reader.receive()
            if received is not None:
                request = received[1]
                break
            time.sleep(.005)
        require(request is not None, "no semantic request received")
        response = handle(semantic_host, request)
        seq = writer.send(response)
        last_tick = time.monotonic()
        while time.monotonic() < deadline:
            writer.process_ack()
            if seq not in writer.pending_sequences():
                break
            now = time.monotonic()
            if now - last_tick > .1:
                require(seq not in writer.tick(), "response retries exhausted")
                last_tick = now
            time.sleep(.005)
        require(seq not in writer.pending_sequences(), "application response unacknowledged")
        record = {
            "schema": "in-formation-space.snc003.session-evidence/0.1",
            "tls_version": tls.socket.version(),
            "client_identity": SENDER,
            "accepted": response["accepted"],
            "request_id": response.get("request_id", ""),
            "source_was_transferred": request.get("kind") == "seed",
            "ground_admitted": False,
        }
        report.write_bytes(canonical(record))
        return record
    finally:
        tls.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    sender = commands.add_parser("send")
    sender.add_argument("--host", default="127.0.0.1")
    sender.add_argument("--port", type=int, required=True)
    sender.add_argument("--request", type=Path, required=True)
    receiver = commands.add_parser("serve")
    receiver.add_argument("--bind", default="127.0.0.1")
    receiver.add_argument("--port", type=int, default=0)
    receiver.add_argument("--database", type=Path, required=True)
    receiver.add_argument("--policy", type=Path, required=True)
    receiver.add_argument("--report", type=Path, required=True)
    for command in (sender, receiver):
        command.add_argument("--ca", type=Path, required=True)
        command.add_argument("--cert", type=Path, required=True)
        command.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "send":
            request = json.loads(args.request.read_text())
            print(json.dumps(send_request(
                host=args.host, port=args.port, request=request,
                ca=args.ca, cert=args.cert, key=args.key), sort_keys=True), flush=True)
        else:
            listener = SocketTransport.listen(args.bind, args.port)
            try:
                print(f"LISTEN_PORT={listener.getsockname()[1]}", flush=True)
                result = serve_one(
                    listener, ca=args.ca, cert=args.cert, key=args.key,
                    database=args.database, policy=args.policy,
                    report=args.report,
                )
                print(json.dumps(result, sort_keys=True), flush=True)
            finally:
                listener.close()
    except (HostRejected, OSError, RuntimeError, ValueError, ssl.SSLError) as exc:
        parser.exit(1, f"SNC003_REJECTED:{exc}\n")


if __name__ == "__main__":
    main()
