"""PGT-001: bounded read-only local HTTP model-artifact path.

HTTP selects where to read an immutable blob; its location does not become the
Ground or model identity. Two local child processes model route replacement,
NOT actual public/CDN/TLS host independence. This narrower adapter follows
the PON-003 failover experiment's trust split without modifying its protocol.
"""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request

MAX_BYTES=1_000_000
PATH=re.compile(r"^/objects/([0-9a-f]{64})\.npz$")

class Refused(ValueError):pass

class _RedirectRefusal(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise Refused('no HTTP redirects to unpinned resources')

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            u=urlsplit(self.path)
            m=PATH.fullmatch(u.path)
            if m is None or u.query or u.fragment:raise Refused('unrecognized path')
            f=self.server.root/'objects'/(m.group(1)+'.npz')
            if not f.is_file() or f.is_symlink():raise Refused('no object')
            raw=f.read_bytes()
            if not 0<len(raw)<=MAX_BYTES or hashlib.sha256(raw).hexdigest()!=m.group(1):
                raise Refused('corrupt or unadmitted artifact')
        except (Refused,OSError):
            self.send_error(404);return
        self.send_response(200)
        self.send_header('Content-Type','application/octet-stream')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers();self.wfile.write(raw)
    def do_POST(self):self.send_error(405)
    def log_message(self,*args):pass

def server(root:Path):
    r=Path(root).resolve(strict=True)
    s=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    s.root=r;s.daemon_threads=True
    return s

def get_verified(roots:list[str],digest:str):
    if not re.fullmatch('[0-9a-f]{64}',digest):raise Refused('invalid external model pin')
    failures=[]
    for root in roots:
        u=urlsplit(root)
        if u.scheme!='http' or u.hostname!='127.0.0.1' or not u.port or u.path!='/' or u.query or u.fragment or u.username or u.password:
            raise Refused('only explicitly selected loopback HTTP origins accepted')
        path=f'{root}objects/{digest}.npz'
        try:
            with build_opener(_RedirectRefusal()).open(Request(path,method='GET',headers={'Accept':'application/octet-stream'}),timeout=2) as response:
                if response.status!=200 or response.headers.get_content_type()!='application/octet-stream':
                    raise Refused('unexpected HTTP representation metadata')
                raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES or hashlib.sha256(raw).hexdigest()!=digest:
                raise Refused('unexpected model bytes; digest mismatch')
            return raw,root,failures
        except Exception as exc:
            failures.append(type(exc).__name__+':'+str(exc)[:100])
    raise Refused('no verified reachable HTTP model origin')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    args=p.parse_args()
    h=server(args.root)
    print('LISTEN_PORT='+str(h.server_port),flush=True)
    try:h.serve_forever(poll_interval=0.02)
    finally:h.server_close()
