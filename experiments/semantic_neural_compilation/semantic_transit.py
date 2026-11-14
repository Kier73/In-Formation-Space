"""SNC-002: exact semantics vs parameter certificates over E-CPU mTLS ReliableChannel.

The wire carries exactly one bounded, digest-checked document per session.
Reliable delivery is never a semantic proof or execution authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import ssl
import sys
import time
from typing import Any

from mailcpu.mtls_transport import accept_mutual_tls, connect_mutual_tls
from mailcpu.reliability import ReliableChannel, ReliabilityPolicy
from mailcpu.socket_transport import SocketTransport

from compiler import compile_semantics
from verifier import verify_capsule, strict_json
from independent_certificate_checker import json_bytes

SCHEMA = "in-formation-space.snc002.semantic-transfer/0.1"
WIRE = "in-formation-space.snc002.reliable-wire/0.1"
CHANNEL = "snc002-exact-semantic-transfer"
SENDER = "snc002-origin"
RECEIVER = "snc002-recipient"
CHUNK = 8192
MAX_DOCUMENT = 512_000
MAX_FRAMES = 70
DEADLINE = 30.0
MODES = frozenset(("semantic", "parameters"))


class TransitRejected(ValueError):
    """Invalid or incomplete transfer or receiver verification."""


def require(ok: bool, why: str) -> None:
    if not ok:
        raise TransitRejected(why)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json_bytes(value) + b"\n"


def fields(value: object, expected: set[str], name: str) -> dict:
    require(type(value) is dict and set(value) == expected,
            f"{name} must contain exactly {sorted(expected)}")
    return value


def make_frames(payload: bytes, *, mode: str) -> tuple[dict, ...]:
    require(mode in MODES, "unsupported transfer mode")
    require(type(payload) is bytes and 0 < len(payload) <= MAX_DOCUMENT,
            "unbounded transfer body")
    doc = strict_json(payload)
    require(type(doc) is dict and doc.get("schema") == SCHEMA and
            doc.get("kind") == mode, "payload and declared mode disagree")
    count = math.ceil(len(payload) / CHUNK)
    require(count + 2 <= MAX_FRAMES, "reliable frame budget exceeded")
    manifest = {
        "schema": WIRE, "channel": CHANNEL, "kind": mode,
        "byte_length": len(payload), "sha256": digest(payload),
        "chunk_size": CHUNK, "chunks": count,
    }
    out = [{"phase": "manifest", "manifest": manifest}]
    for i in range(count):
        out.append({"phase": "chunk", "index": i,
                    "hex": payload[i * CHUNK:(i + 1) * CHUNK].hex()})
    out.append({"phase": "finish", "manifest_sha256": digest(json_bytes(manifest))})
    return tuple(out)


class Decoder:
    def __init__(self) -> None:
        self.manifest: dict | None = None
        self.parts: list[bytes] = []
        self.completed = False
        self.frames_seen = 0
        self.document: bytes | None = None

    def ingest(self, frame: object) -> None:
        require(not self.completed, "post-finish frame")
        require(self.frames_seen < MAX_FRAMES, "frame count exceeded")
        self.frames_seen += 1
        if self.manifest is None:
            first = fields(frame, {"phase", "manifest"}, "opening frame")
            require(first["phase"] == "manifest", "missing manifest")
            doc = fields(first["manifest"], {
                "schema", "channel", "kind", "byte_length",
                "sha256", "chunk_size", "chunks",
            }, "manifest")
            require(doc["schema"] == WIRE and doc["channel"] == CHANNEL and
                    doc["kind"] in MODES and doc["chunk_size"] == CHUNK,
                    "wrong transport identity")
            size = doc["byte_length"]
            require(type(size) is int and 0 < size <= MAX_DOCUMENT,
                    "invalid promised body length")
            require(type(doc["chunks"]) is int and
                    doc["chunks"] == math.ceil(size / CHUNK) and
                    doc["chunks"] + 2 <= MAX_FRAMES, "invalid chunk count")
            require(type(doc["sha256"]) is str and len(doc["sha256"]) == 64 and
                    all(c in "0123456789abcdef" for c in doc["sha256"]),
                    "invalid content digest")
            self.manifest = doc
            return

        if len(self.parts) < self.manifest["chunks"]:
            part = fields(frame, {"phase", "index", "hex"}, "chunk frame")
            require(part["phase"] == "chunk" and type(part["index"]) is int and
                    part["index"] == len(self.parts),
                    "duplicated or out-of-order chunk")
            raw_hex = part["hex"]
            require(type(raw_hex) is str and 0 < len(raw_hex) <= 2 * CHUNK and
                    len(raw_hex) % 2 == 0, "oversized or malformed hex")
            try:
                piece = bytes.fromhex(raw_hex)
            except ValueError as exc:
                raise TransitRejected("invalid hex chunk") from exc
            require(piece.hex() == raw_hex, "noncanonical chunk encoding")
            expected_length = min(
                CHUNK, self.manifest["byte_length"] - len(self.parts) * CHUNK)
            require(len(piece) == expected_length, "wrong chunk byte count")
            self.parts.append(piece)
            if len(self.parts) == self.manifest["chunks"]:
                result = b"".join(self.parts)
                require(len(result) == self.manifest["byte_length"] and
                        digest(result) == self.manifest["sha256"],
                        "assembled document digest mismatch")
                self.document = result
            return

        end = fields(frame, {"phase", "manifest_sha256"}, "finish frame")
        require(end["phase"] == "finish" and
                end["manifest_sha256"] == digest(json_bytes(self.manifest)),
                "wrong finish commitment")
        self.completed = True


def verify_received(raw: bytes, *, kind: str, expected_semantic_sha256: str
                   ) -> dict[str, object]:
    """Receiver accepts only receiver-owned semantic identity.

    The semantic path constructs fresh weights here; the parameter baseline
    transfers a producer certificate including explicit neural parameters.
    Both paths use the same independent COE-002 semantic verifier.
    """
    require(type(expected_semantic_sha256) is str and
            len(expected_semantic_sha256) == 64 and
            all(c in "0123456789abcdef" for c in expected_semantic_sha256),
            "receiver semantic pin is required")
    data = strict_json(raw)
    if kind == "semantic":
        fields(data, {"schema", "kind", "semantic_atlas"}, "semantic request")
    elif kind == "parameters":
        fields(data, {"schema", "kind", "generated_certificate"},
               "parameter baseline")
    else:
        raise TransitRejected("unrecognized operation mode")
    require(data["schema"] == SCHEMA and data["kind"] == kind,
            "payload kind/schema substitution")
    started = time.perf_counter_ns()
    if kind == "semantic":
        generated = compile_semantics(data["semantic_atlas"])
        constructed_ns = time.perf_counter_ns() - started
    else:
        cert = data["generated_certificate"]
        require(type(cert) is dict and
                type(cert.get("semantic_atlas")) is list,
                "missing parameter-baseline certificate")
        generated = {
            "schema": "in-formation-space.snc001.semantic-to-neural/0.1",
            "source_semantic_atlas": cert["semantic_atlas"],
            "source_semantic_sha256": expected_semantic_sha256,
            "generated_certificate": cert,
        }
        constructed_ns = 0
    verified_start = time.perf_counter_ns()
    result = verify_capsule(
        canonical(generated),
        expected_source_sha256=expected_semantic_sha256,
    )
    verified_ns = time.perf_counter_ns() - verified_start
    return {
        "status": result["status"],
        "mode": kind,
        "source_semantic_sha256": result["source_semantic_sha256"],
        "generated_network_sha256": result["generated_network_sha256"],
        "hidden_neurons": result["hidden_neurons"],
        "construction_ns_receiver_local": constructed_ns,
        "independent_verification_ns_receiver_local": verified_ns,
        "authorization": "no-execution-authority-granted",
    }


def tls_context(ca: Path, cert: Path, key: Path, *, server: bool) -> ssl.SSLContext:
    if server:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_verify_locations(cafile=str(ca))
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH, cafile=str(ca))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    return ctx


def channel(transport: SocketTransport, *, serving: bool) -> ReliableChannel:
    return ReliableChannel(
        transport,
        source=RECEIVER if serving else SENDER,
        destination=RECEIVER,
        peer=SENDER if serving else RECEIVER,
        channel=CHANNEL,
        policy=ReliabilityPolicy(lease_ticks=4, max_attempts=7, window_size=4),
    )


def send(
    host: str, port: int, raw: bytes, *, kind: str,
    ca: Path, cert: Path, key: Path, timeout: float = DEADLINE,
) -> dict[str, object]:
    frames = make_frames(raw, mode=kind)
    tls = connect_mutual_tls(
        host, port, SENDER, RECEIVER,
        tls_context(ca, cert, key, server=False),
        server_hostname=RECEIVER, timeout=8.0, max_frame_size=1 << 20,
    )
    try:
        reliable = channel(tls, serving=False)
        start = time.perf_counter_ns()
        for frame in frames:
            seq = reliable.send(frame)
            deadline = time.monotonic() + timeout
            last_tick = time.monotonic()
            while seq in reliable.pending_sequences():
                reliable.process_ack()
                if seq not in reliable.pending_sequences():
                    break
                now = time.monotonic()
                require(now < deadline, "reliable frame acknowledgement timeout")
                if now - last_tick >= .1:
                    failed = reliable.tick()
                    last_tick = now
                    require(seq not in failed, "reliable frame retries exhausted")
                time.sleep(.005)
            require(seq not in reliable.failed_sequences,
                    "reliable frame failure")
        elapsed = time.perf_counter_ns() - start
        return {
            "kind": kind,
            "application_bytes": len(raw),
            "frames_acked": len(frames),
            "sender_ack_duration_ns": elapsed,
            "tls": "mutually authenticated E-CPU ReliableChannel",
            "note": "delivery ACK does not imply semantic validation",
        }
    finally:
        tls.close()


def serve(
    listener: Any, *, ca: Path, cert: Path, key: Path,
    expected_semantic_sha256: str, report_path: Path,
    timeout: float = DEADLINE,
) -> dict[str, object]:
    tls = accept_mutual_tls(
        listener, RECEIVER, SENDER,
        tls_context(ca, cert, key, server=True),
        expected_peer_dns=SENDER,
        max_frame_size=1 << 20,
    )
    decoder = Decoder()
    try:
        reliable = channel(tls, serving=True)
        deadline = time.monotonic() + timeout
        start = time.perf_counter_ns()
        while not decoder.completed:
            require(time.monotonic() < deadline, "incomplete reliable transfer")
            arrived = reliable.receive(commit=lambda _seq, msg: decoder.ingest(msg))
            if arrived is None:
                time.sleep(.005)
        receive_ns = time.perf_counter_ns() - start
        require(decoder.document is not None and decoder.manifest is not None,
                "incomplete received bytes")
        verdict = verify_received(
            decoder.document,
            kind=decoder.manifest["kind"],
            expected_semantic_sha256=expected_semantic_sha256,
        )
        evidence = {
            "schema": "in-formation-space.snc002.receiver-evidence/0.1",
            "transport_status": "mTLS-reliably-delivered",
            "peer": SENDER,
            "tls_version": tls.socket.version(),
            "peer_certificate_sha256": digest(
                tls.socket.getpeercert(binary_form=True)),
            "frame_count": decoder.frames_seen,
            "received_document_sha256": digest(decoder.document),
            "application_bytes": len(decoder.document),
            "receive_duration_ns_receiver_local": receive_ns,
            "semantic_verification": verdict,
            "scope": "distinct local processes on one host; not independent physical machines",
        }
        report_path.write_bytes(canonical(evidence))
        return evidence
    finally:
        # Let the sender observe the last transport ACK, irrespective of
        # whether a later semantic verification rejects this request.
        if decoder.completed:
            time.sleep(.15)
        tls.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    client = sub.add_parser("send")
    client.add_argument("--host", default="127.0.0.1")
    client.add_argument("--port", type=int, required=True)
    client.add_argument("--payload", type=Path, required=True)
    client.add_argument("--kind", choices=sorted(MODES), required=True)
    server = sub.add_parser("serve")
    server.add_argument("--bind", default="127.0.0.1")
    server.add_argument("--port", type=int, default=0)
    server.add_argument("--expected-semantic-sha256", required=True)
    server.add_argument("--report", type=Path, required=True)
    for command in (client, server):
        for field in ("ca", "cert", "key"):
            command.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.cmd == "send":
            report = send(
                args.host, args.port, args.payload.read_bytes(),
                kind=args.kind, ca=args.ca, cert=args.cert, key=args.key,
            )
            print(json.dumps(report, sort_keys=True), flush=True)
        else:
            listener = SocketTransport.listen(args.bind, args.port)
            try:
                print("LISTEN_PORT=" + str(listener.getsockname()[1]), flush=True)
                result = serve(
                    listener, ca=args.ca, cert=args.cert, key=args.key,
                    expected_semantic_sha256=args.expected_semantic_sha256,
                    report_path=args.report,
                )
                print("SNC002_RECEIVER_VERIFIED:" +
                      result["semantic_verification"]["generated_network_sha256"],
                      flush=True)
            finally:
                listener.close()
    except (TransitRejected, ValueError, OSError, ssl.SSLError, RuntimeError) as exc:
        parser.exit(1, f"SNC002_REJECTED:{exc}\n")


if __name__ == "__main__":
    main()
