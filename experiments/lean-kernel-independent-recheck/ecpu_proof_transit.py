#!/usr/bin/env python3
"""Bounded six-artifact VGI receipt transfer over actual E-CPU mTLS + ReliableChannel.

MailCPU SocketTransport carries frames; ReliableChannel acknowledges delivered
frames. These are delivery observations, *never* proof authority. The receiving
process independently uses proof_receipt_receiver.receive() to authenticate the
GitHub/Sigstore issuer chain, its own pinned intention and durable replay ledger.

The reference CLI is a loopback-capable TCP service. It also accepts explicitly
configured host/port for controlled two-host deployments; it does not itself
provision PKI, a distributed trust service or a global replay ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path
import ssl
import sys
import tempfile
import time
from typing import Any, Mapping

from mailcpu.mtls_transport import accept_mutual_tls, connect_mutual_tls
from mailcpu.reliability import ReliableChannel, ReliabilityPolicy
from mailcpu.socket_transport import SocketTransport

import proof_receipt_receiver as receiver
import term_receipt as term

FORMAT = "in-formation.ecpu-vgi-proof-transport/0.1"
MANIFEST_FORMAT = "in-formation.ecpu-vgi-proof-manifest/0.1"
CHANNEL = "vgi-proof-transport-001"
ORIGIN = "proof-origin"
DESTINATION = "proof-recipient"
CHUNK = 8192
MAX_SUBJECT = 2_000_000
MAX_TOTAL = 12_000_000
MAX_FRAMES = 1600
MAX_SECONDS = 75.0
SUBJECTS = receiver.SUBJECTS


class ProofTransitError(ValueError):
    """A MailCPU proof transport frame, manifest or transport stage is invalid."""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fields(doc: Any, expected: set[str], label: str) -> None:
    if not isinstance(doc, dict) or set(doc) != expected:
        raise ProofTransitError(f"{label}: missing, unexpected or malformed fields")


def make_frames(paths: Mapping[str, Path]) -> tuple[dict, ...]:
    """One deterministic manifest, ordered chunks, and a terminal transcript."""
    if set(paths) != set(SUBJECTS):
        raise ProofTransitError("all six proof artifact types are mandatory")
    artifacts: dict[str, dict] = {}
    raw: dict[str, bytes] = {}
    total = 0
    for kind in SUBJECTS:
        path = paths[kind]
        if path.is_symlink() or not path.is_file():
            raise ProofTransitError(f"{kind}: missing or symlinked source")
        data = path.read_bytes()
        if not 0 < len(data) <= MAX_SUBJECT:
            raise ProofTransitError(f"{kind}: invalid source size")
        total += len(data)
        if total > MAX_TOTAL:
            raise ProofTransitError("transfer exceeds total size bound")
        raw[kind] = data
        artifacts[kind] = {
            "size": len(data),
            "sha256": sha(data),
            "chunks": math.ceil(len(data) / CHUNK),
        }
    manifest = {
        "format": MANIFEST_FORMAT,
        "channel": CHANNEL,
        "chunk_size": CHUNK,
        "total_bytes": total,
        "artifacts": artifacts,
    }
    frames: list[dict] = [{"phase": "manifest", "manifest": manifest}]
    for kind in SUBJECTS:
        for i in range(artifacts[kind]["chunks"]):
            segment = raw[kind][i * CHUNK:(i + 1) * CHUNK]
            frames.append({
                "phase": "chunk", "kind": kind, "index": i,
                "hex": segment.hex(),
            })
    frames.append({"phase": "finish", "manifest_sha256": term.digest(manifest)})
    if len(frames) > MAX_FRAMES:
        raise ProofTransitError("transfer exceeds bounded reliable-frame count")
    return tuple(frames)


class ProofStreamDecoder:
    """Finite ordered exact-byte assembler; no trust or VGI admission happens here."""
    def __init__(self) -> None:
        self.manifest: dict | None = None
        self.parts: dict[str, list[bytes]] = {}
        self.next_kind = 0
        self.next_index = 0
        self.frames_seen = 0
        self.finished = False
        self.raw: dict[str, bytes] = {}

    def ingest(self, frame: Any) -> None:
        if self.finished:
            raise ProofTransitError("post-finish frame rejected")
        if self.frames_seen >= MAX_FRAMES:
            raise ProofTransitError("too many transport frames")
        self.frames_seen += 1
        if self.manifest is None:
            _fields(frame, {"phase", "manifest"}, "manifest frame")
            if frame["phase"] != "manifest":
                raise ProofTransitError("proof transfer must start with manifest")
            manifest = frame["manifest"]
            _fields(manifest, {"format", "channel", "chunk_size", "total_bytes", "artifacts"}, "manifest")
            if (manifest["format"] != MANIFEST_FORMAT or
                manifest["channel"] != CHANNEL or manifest["chunk_size"] != CHUNK):
                raise ProofTransitError("unsupported manifest binding")
            if type(manifest["total_bytes"]) is not int or not 0 < manifest["total_bytes"] <= MAX_TOTAL:
                raise ProofTransitError("invalid total size in manifest")
            artifacts = manifest["artifacts"]
            if not isinstance(artifacts, dict) or set(artifacts) != set(SUBJECTS):
                raise ProofTransitError("manifest does not contain exact six subjects")
            expected_total = 0
            for kind in SUBJECTS:
                entry = artifacts[kind]
                _fields(entry, {"size", "sha256", "chunks"}, f"{kind} manifest entry")
                size = entry["size"]
                chunks = entry["chunks"]
                if type(size) is not int or not 0 < size <= MAX_SUBJECT:
                    raise ProofTransitError(f"{kind}: invalid manifest size")
                if type(chunks) is not int or chunks != math.ceil(size / CHUNK):
                    raise ProofTransitError(f"{kind}: invalid manifest chunk count")
                if not isinstance(entry["sha256"], str) or len(entry["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in entry["sha256"]):
                    raise ProofTransitError(f"{kind}: invalid digest")
                expected_total += size
            if expected_total != manifest["total_bytes"]:
                raise ProofTransitError("manifest total does not agree with subject sizes")
            self.manifest = manifest
            self.parts = {kind: [] for kind in SUBJECTS}
            return

        if self.next_kind < len(SUBJECTS):
            _fields(frame, {"phase", "kind", "index", "hex"}, "chunk frame")
            if frame["phase"] != "chunk":
                raise ProofTransitError("missing or out-of-order artifact chunk")
            kind = SUBJECTS[self.next_kind]
            if frame["kind"] != kind or type(frame["index"]) is not int or frame["index"] != self.next_index:
                raise ProofTransitError("substituted, reordered or duplicate chunk")
            hexval = frame["hex"]
            if not isinstance(hexval, str) or len(hexval) % 2 or len(hexval) > 2 * CHUNK:
                raise ProofTransitError("malformed or oversized hex chunk")
            try:
                data = bytes.fromhex(hexval)
            except ValueError as exc:
                raise ProofTransitError("malformed hex transfer") from exc
            if data.hex() != hexval or not data:
                raise ProofTransitError("noncanonical or empty chunk encoding")
            entry = self.manifest["artifacts"][kind]
            expected_chunk_size = min(CHUNK, entry["size"] - self.next_index * CHUNK)
            if len(data) != expected_chunk_size:
                raise ProofTransitError(f"{kind}: chunk length disagrees with manifest")
            self.parts[kind].append(data)
            self.next_index += 1
            if self.next_index == entry["chunks"]:
                reconstructed = b"".join(self.parts[kind])
                if len(reconstructed) != entry["size"] or sha(reconstructed) != entry["sha256"]:
                    raise ProofTransitError(f"{kind}: digest mismatch")
                self.raw[kind] = reconstructed
                self.next_kind += 1
                self.next_index = 0
            return

        _fields(frame, {"phase", "manifest_sha256"}, "finish frame")
        if frame["phase"] != "finish" or frame["manifest_sha256"] != term.digest(self.manifest):
            raise ProofTransitError("unbound or incorrect terminal manifest digest")
        self.finished = True

    def materialize(self, dest: Path) -> dict[str, Path]:
        if not self.finished or set(self.raw) != set(SUBJECTS):
            raise ProofTransitError("incomplete stream cannot be promoted")
        if not dest.is_dir():
            raise ProofTransitError("destination scratch directory is missing")
        output = {}
        for kind in SUBJECTS:
            path = dest / f"{kind}.bin"
            path.write_bytes(self.raw[kind])
            output[kind] = path
        return output


def _ctx(ca: Path, cert: Path, key: Path, *, server: bool) -> ssl.SSLContext:
    if server:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if server:
        ctx.load_verify_locations(cafile=str(ca))
    ctx.load_cert_chain(str(cert), str(key))
    return ctx


def _proof_channels(transport: SocketTransport, *, serving: bool) -> ReliableChannel:
    return ReliableChannel(
        transport,
        source=DESTINATION if serving else ORIGIN,
        destination=DESTINATION,
        channel=CHANNEL,
        peer=ORIGIN if serving else DESTINATION,
        policy=ReliabilityPolicy(lease_ticks=4, max_attempts=7, window_size=4),
    )


def send_frames(
    host: str, port: int, paths: Mapping[str, Path],
    *, ca: Path, cert: Path, key: Path, budget: float = MAX_SECONDS,
) -> dict:
    frames = make_frames(paths)
    tls = connect_mutual_tls(
        host, port, ORIGIN, DESTINATION, _ctx(ca, cert, key, server=False),
        server_hostname=DESTINATION,
        timeout=8.0,
        max_frame_size=1 << 20,
    )
    try:
        channel = _proof_channels(tls, serving=False)
        sent = 0
        for payload in frames:
            sequence = channel.send(payload)
            deadline = time.monotonic() + budget
            last_tick = time.monotonic()
            while sequence in channel.pending_sequences():
                channel.process_ack()
                if sequence not in channel.pending_sequences():
                    break
                now = time.monotonic()
                if now >= deadline:
                    raise ProofTransitError(f"delivery ACK missing for reliable sequence {sequence}")
                if now - last_tick >= 0.1:
                    failed = channel.tick()
                    last_tick = now
                    if sequence in failed:
                        raise ProofTransitError(f"E-CPU reliable delivery retries exhausted: {sequence}")
                time.sleep(0.005)
            if sequence in channel.failed_sequences:
                raise ProofTransitError(f"E-CPU reliable delivery failed: {sequence}")
            sent += 1
        return {
            "frames_sent": sent,
            "manifest_sha256": frames[-1]["manifest_sha256"],
            "transport": "E-CPU ReliableChannel over mutually authenticated TLS",
        }
    finally:
        tls.close()


def serve(
    listener: Any, *, ca: Path, cert: Path, key: Path,
    intent: Path, ledger: Path, output: Path, transport_report: Path,
    budget: float = MAX_SECONDS,
) -> dict:
    tls = accept_mutual_tls(
        listener, DESTINATION, ORIGIN, _ctx(ca, cert, key, server=True),
        expected_peer_dns=ORIGIN,
        max_frame_size=1 << 20,
    )
    decoder = ProofStreamDecoder()
    try:
        channel = _proof_channels(tls, serving=True)
        deadline = time.monotonic() + budget
        while not decoder.finished:
            if time.monotonic() >= deadline:
                raise ProofTransitError("recipient did not receive all bounded proof artifacts")
            result = channel.receive(commit=lambda _seq, payload: decoder.ingest(payload))
            if result is None:
                time.sleep(0.005)
        with tempfile.TemporaryDirectory(prefix="vgi-ecpu-transfer-") as scratch:
            paths = decoder.materialize(Path(scratch))
            # Only this independent verification can issue a receiving receipt.
            decision = receiver.receive(paths=paths, intent_path=intent, ledger_path=ledger)
        term._write(output, decision)
        report = {
            "format": FORMAT,
            "status": "mutual_tls_reliable_frames_delivered_and_independently_verified",
            "transport_authenticated_peer": ORIGIN,
            "recipient_endpoint": DESTINATION,
            "negotiated_tls_version": tls.socket.version(),
            "peer_certificate_sha256": sha(tls.socket.getpeercert(binary_form=True)),
            "frame_count": decoder.frames_seen,
            "transferred_subject_sha256": {k: sha(decoder.raw[k]) for k in SUBJECTS},
            "recipient_proof_receipt_ref": decision["receipt_ref"],
            "recipient_decision_digest": decision["document_digest"],
            "observation_scope": "delivery and local receiving verification only; no physical host separation claim",
        }
        term._write(transport_report, {**report, "document_digest": term.digest(report)})
        time.sleep(0.1)  # leave time for the final wire ACK to be consumed
        return decision
    finally:
        # Transport RACK for the terminal frame is a delivery acknowledgement,
        # even if application-level proof admission fails (e.g. replay). Give
        # the sender time to observe the ACK before closing TLS.
        if decoder.finished:
            time.sleep(0.15)
        tls.close()


def _subjects(args: argparse.Namespace) -> dict[str, Path]:
    return {name: getattr(args, name) for name in SUBJECTS}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sendp = sub.add_parser("send")
    sendp.add_argument("--host", required=True)
    sendp.add_argument("--port", type=int, required=True)
    servep = sub.add_parser("serve")
    servep.add_argument("--bind", default="127.0.0.1")
    servep.add_argument("--port", type=int, default=0)
    for p in (sendp, servep):
        for key in ("ca", "cert", "key"):
            p.add_argument("--" + key, type=Path, required=True)
    for kind in SUBJECTS:
        sendp.add_argument("--" + kind.replace("_", "-"), type=Path, required=True)
    for name in ("intent", "ledger", "output", "transport-report"):
        servep.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "send":
            result = send_frames(
                args.host, args.port, _subjects(args),
                ca=args.ca, cert=args.cert, key=args.key,
            )
            print(f"MAILCPU_PROOF_FRAMES_ACKED:{result['frames_sent']}", flush=True)
        else:
            listener = SocketTransport.listen(args.bind, args.port)
            try:
                print(f"LISTEN_PORT={listener.getsockname()[1]}", flush=True)
                result = serve(
                    listener, ca=args.ca, cert=args.cert, key=args.key,
                    intent=args.intent, ledger=args.ledger,
                    output=args.output, transport_report=args.transport_report,
                )
                print(f"MAILCPU_PROOF_RECIPIENT_ACCEPTED:{result['receipt_ref']}", flush=True)
            finally:
                listener.close()
    except (ProofTransitError, receiver.ReceiverReject, term.TermReceiptError,
            OSError, ssl.SSLError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"MAILCPU_PROOF_TRANSPORT_REJECTED:{exc}\n")


if __name__ == "__main__":
    main()
