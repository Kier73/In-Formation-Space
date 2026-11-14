"""PON-003: read-only protocol-faithful local origin adapters for failure injection.

These are bounded emulators of public R2-style object GET and an IPFS
trustless raw-block gateway. They do not run R2 or Kubo themselves. Each
process has a separate directory; tests actually terminate a process.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from passive_orbit import require, PassiveRejected
from pon003_origin import CID_PATTERN

RE_OBJECT = re.compile(r"/objects/[0-9a-f]{64}\.json\Z")
RE_CID = re.compile(r"/ipfs/(b[a-z2-7]+)\Z")
MAX_BYTES = 12_000


class OriginServer(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        kind = self.server.kind
        parsed = urlsplit(self.path)
        if kind == "r2":
            if parsed.query or parsed.fragment or (
                parsed.path != "/manifest.json" and
                RE_OBJECT.fullmatch(parsed.path) is None
            ):
                self.send_error(404)
                return
            target = self.server.root / parsed.path.lstrip("/")
            media = "application/octet-stream"
        else:
            match = RE_CID.fullmatch(parsed.path)
            if match is None or CID_PATTERN.fullmatch(match.group(1)) is None or \
                    parsed.query != "format=raw":
                self.send_error(404)
                return
            target = self.server.root / "blocks" / match.group(1)
            media = "application/vnd.ipld.raw"
        if not target.is_file() or target.is_symlink():
            self.send_error(404)
            return
        raw = target.read_bytes()
        if not 0 < len(raw) <= MAX_BYTES:
            self.send_error(413)
            return
        self.send_response(200)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        self.send_error(405)

    def log_message(self, *args) -> None:
        pass


def launch(root: Path, kind: str, port: int = 0) -> ThreadingHTTPServer:
    require(kind in ("r2", "ipfs") and root.is_dir() and
            not root.is_symlink() and type(port) is int and
            0 <= port <= 65535, "no arbitrary origin storage, port or path")
    server = ThreadingHTTPServer(("127.0.0.1", port), OriginServer)
    server.kind = kind
    server.root = root
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("r2", "ipfs"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    srv = launch(args.root, args.kind)
    print("LISTEN_PORT=" + str(srv.server_port), flush=True)
    try:
        srv.serve_forever()
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
